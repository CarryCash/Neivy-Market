"""Construcción del Dataset de Investigación NAVIER V2 (Fase 4).

Procesa sesiones de captura L2 resampleadas a 1.0s:
1. Resampleo causal estricto (T-1s, T].
2. Cálculo de variables Modelos A, B, B+, C (Navier V0.1) y D (Navier V0.2).
3. Aplicación rigurosa de las exclusiones del protocolo congelado:
   - Descarte de calentamiento (warmup 60s).
   - Invalidador de historia contaminada (gaps en 60s o >20% arrastre).
   - Invalidador de etiqueta futura ante gaps en t..t+10s.
   - Suelo de volatilidad causal (vol60 >= 0.01 bps).
4. Generación de manifiesto con hashes de entrada y salida, recuentos y trazabilidad.
"""
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
from navier_lab.features import compute_features, FEATURE_COLUMNS, NAVIER_V02, TARGET, TARGET_BPS
from navier_lab.schema import Config, DEFAULT_CONFIG


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_session(raw_path: Path, cfg: Config = DEFAULT_CONFIG, resampler_cfg: ResamplerConfig = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if resampler_cfg is None:
        resampler_cfg = ResamplerConfig(bin_size_seconds=1.0, gap_threshold_seconds=3.0)

    df_raw = pd.read_parquet(raw_path)
    in_sha = sha256_file(raw_path)

    # 1. Resampleo causal a 1.0 s
    df_1s = resample_l2_to_1s(df_raw, resampler_cfg)

    # 2. Features y Target causal
    df_feat = compute_features(df_1s, cfg, with_target=True)

    # Copiar metadatos de estado del resampler al dataframe de features
    df_feat["session_id"] = raw_path.stem
    df_feat["state_source"] = df_1s["state_source"].to_numpy()
    df_feat["staleness_ms"] = df_1s["staleness_ms"].to_numpy()
    df_feat["updates_count"] = df_1s["updates_count"].to_numpy()

    # 3. Aplicar exclusión por calentamiento (warmup)
    # Primeras 60 filas no tienen vol60_bps válida
    warmup_n = cfg.vol_window
    df_valid = df_feat.iloc[warmup_n:].copy()

    meta = {
        "session_file": raw_path.name,
        "input_sha256": in_sha,
        "raw_rows": len(df_raw),
        "resampled_rows": len(df_1s),
        "post_warmup_rows": len(df_valid),
    }

    return df_1s, df_valid, meta


def build_dataset(sessions_dir: Path, output_path: Path, cfg: Config = DEFAULT_CONFIG) -> None:
    raw_files = sorted(sessions_dir.glob("*.parquet"))
    raw_files = [f for f in raw_files if not f.name.endswith("_1s.parquet") and not f.name.endswith("features.parquet")]
    # Only include sessions with a completed manifest (excludes in-progress captures)
    raw_files = [f for f in raw_files if f.with_suffix(f.suffix + ".manifest.json").exists()]

    if not raw_files:
        raise FileNotFoundError(f"No se encontraron sesiones crudas en {sessions_dir}")

    all_resampled = []
    all_features = []
    session_metas = []

    for f in raw_files:
        print(f"Procesando sesión: {f.name}...")
        df_1s, df_feat, meta = process_session(f, cfg)
        
        # Guardar versión 1s individual
        out_1s = f.with_name(f"{f.stem}_1s.parquet")
        table_1s = pa.Table.from_pandas(df_1s, preserve_index=False)
        pq.write_table(table_1s, out_1s, compression="zstd")
        meta["output_1s_file"] = out_1s.name
        meta["output_1s_sha256"] = sha256_file(out_1s)

        all_resampled.append(df_1s)
        all_features.append(df_feat)
        session_metas.append(meta)

    # Consolidar dataset de features multisesión
    consolidated_df = pd.concat(all_features, ignore_index=True)
    
    # Exclusiones finales de modelado: filas donde target o features principales son NaN
    core_features = FEATURE_COLUMNS + NAVIER_V02
    clean_mask = consolidated_df[[TARGET, TARGET_BPS] + core_features].notna().all(axis=1)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table_out = pa.Table.from_pandas(consolidated_df, preserve_index=False)
    pq.write_table(table_out, output_path, compression="zstd")
    out_sha = sha256_file(output_path)

    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest = {
        "project": "NAVIER",
        "version": "2.0.0-FROZEN",
        "stage": "research_dataset_phase_4",
        "symbol": "BTC/USD",
        "exchange": "Kraken Spot",
        "horizon_seconds": cfg.horizon,
        "input_sessions": session_metas,
        "total_consolidated_rows": len(consolidated_df),
        "clean_complete_rows": int(clean_mask.sum()),
        "clean_ratio": round(float(clean_mask.mean()), 4),
        "output_file": output_path.name,
        "output_sha256": out_sha,
        "features_available": {
            "model_a": ["spread_bps", "depth_log", "vol60_bps"],
            "model_b": ["spread_bps", "depth_log", "vol60_bps", "imb_full", "imb_top1", "ofi_5", "ret_1", "ret_5", "ret_30"],
            "model_bplus": ["spread_bps", "depth_log", "vol60_bps", "imb_full", "imb_top1", "ofi_5", "ret_1", "ret_5", "ret_30", "imb_full_lag2", "imb_full_lag5", "imb_full_lag8"],
            "model_c_navier_v01": ["u", "dI_dt", "grad_bid", "grad_ask", "curv_bid", "curv_ask", "re_log"],
            "model_d_navier_v02": ["v02_l_vwap_bps", "v02_grad_bid_norm", "v02_grad_ask_norm", "v02_re_log_reg"],
            "target": TARGET,
            "target_bps": TARGET_BPS,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Dataset consolidado guardado en {output_path} ({len(consolidated_df)} filas, {int(clean_mask.sum())} limpias)")
    print(f"Manifiesto guardado en {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", default="data/kraken/sessions", help="Directorio con sesiones")
    parser.add_argument("--output", default="data/research_dataset_v2.parquet", help="Archivo Parquet consolidado")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    build_dataset(sessions_dir, output_path)


if __name__ == "__main__":
    main()
