"""Script CLI para resamplear capturas L2 de Kraken a 1 segundo con trazabilidad y manifiesto."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from navier_lab.resampler import resample_l2_to_1s, ResamplerConfig
from navier_lab.schema import STATE_OBSERVED, STATE_CARRIED_FORWARD, STATE_GAP_DISCONTINUITY


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/kraken/btc_usdt_l2.parquet", help="Archivo L2 de entrada")
    parser.add_argument("--output", default="data/kraken/btc_usdt_l2_1s.parquet", help="Archivo L2 1s de salida")
    parser.add_argument("--gap-threshold", type=float, default=3.0, help="Umbral provisional de gap (segundos)")
    parser.add_argument("--overwrite", action="store_true", help="Sobrescribir si ya existe")
    args = parser.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    if not in_path.exists():
        raise FileNotFoundError(f"Archivo de entrada no encontrado: {in_path}")

    manifest_path = out_path.with_suffix(out_path.suffix + ".manifest.json")
    if (out_path.exists() or manifest_path.exists()) and not args.overwrite:
        raise FileExistsError(f"Archivo de salida o manifiesto ya existen: {out_path}. Usa --overwrite.")

    print(f"Cargando dataset original desde {in_path}...")
    t0 = time.monotonic()
    df_raw = pd.read_parquet(in_path)
    in_sha = sha256_file(in_path)
    print(f"Cargadas {len(df_raw)} filas en {time.monotonic() - t0:.2f} s. SHA256: {in_sha}")

    cfg = ResamplerConfig(bin_size_seconds=1.0, gap_threshold_seconds=args.gap_threshold)
    print(f"Ejecutando resampleo causal a 1 s (gap_threshold={cfg.gap_threshold_seconds} s)...")
    t1 = time.monotonic()
    df_1s = resample_l2_to_1s(df_raw, cfg)
    resample_time = time.monotonic() - t1
    print(f"Resampleo completado en {resample_time:.2f} s. Filas resultantes: {len(df_1s)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df_1s, preserve_index=False)
    pq.write_table(table, out_path, compression="zstd")
    out_sha = sha256_file(out_path)

    # Métricas para el manifiesto de trazabilidad
    counts = df_1s["state_source"].value_counts().to_dict()
    observed_sec = int(counts.get(STATE_OBSERVED, 0))
    carried_sec = int(counts.get(STATE_CARRIED_FORWARD, 0))
    gap_sec = int(counts.get(STATE_GAP_DISCONTINUITY, 0))
    total_sec = len(df_1s)

    manifest = {
        "project": "NAVIER",
        "version": "001.9",
        "stage": "1s_causal_resampling",
        "input_file": in_path.name,
        "input_sha256": in_sha,
        "output_file": out_path.name,
        "output_sha256": out_sha,
        "resample_rule": "semi_open_left_closed_right_(T-1s,T]_labeled_at_T",
        "gap_threshold_seconds_provisional": cfg.gap_threshold_seconds,
        "total_seconds": total_sec,
        "observed_seconds": observed_sec,
        "carried_forward_seconds": carried_sec,
        "gap_discontinuity_seconds": gap_sec,
        "observed_ratio": round(observed_sec / total_sec, 4) if total_sec else 0.0,
        "staleness_ms_stats": {
            "mean": round(float(df_1s["staleness_ms"].mean()), 2) if total_sec else None,
            "median": round(float(df_1s["staleness_ms"].median()), 2) if total_sec else None,
            "max": round(float(df_1s["staleness_ms"].max()), 2) if total_sec else None,
        },
        "updates_per_second_stats": {
            "mean": round(float(df_1s["updates_count"].mean()), 2) if total_sec else None,
            "median": round(float(df_1s["updates_count"].median()), 2) if total_sec else None,
            "max": int(df_1s["updates_count"].max()) if total_sec else None,
        },
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Guardado archivo {out_path} (SHA256: {out_sha})")
    print(f"Manifiesto guardado en {manifest_path}:")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
