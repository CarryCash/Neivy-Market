"""Script de auditoría de calidad y control de integridad multisesión (Fase 3).

Inspecciona sesiones de captura L2 en data/kraken/sessions/, evalúa:
1. Integridad criptográfica y contadores de WebSocket (CRC32, reconexiones, fallos).
2. Frecuencia y ráfagas de mensajes por segundo.
3. Resampleo causal a 1.0s y clasificación de estados (OBSERVED, CARRIED_FORWARD, GAP).
4. Métricas de microestructura (spread bps, profundidad nominal quote USD, staleness).
5. Cumplimiento de criterios de invalidación del protocolo congelado (Punto 13).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

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


def audit_session(raw_parquet_path: Path) -> dict:
    manifest_path = raw_parquet_path.with_suffix(raw_parquet_path.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    file_sha = sha256_file(raw_parquet_path)
    manifest_sha = manifest.get("output_sha256")
    sha_match = (file_sha == manifest_sha) if manifest_sha else None

    df_raw = pd.read_parquet(raw_parquet_path)
    cfg = ResamplerConfig(bin_size_seconds=1.0, gap_threshold_seconds=3.0)
    df_1s = resample_l2_to_1s(df_raw, cfg)

    total_sec = len(df_1s)
    state_counts = df_1s["state_source"].value_counts().to_dict()
    obs_sec = int(state_counts.get(STATE_OBSERVED, 0))
    car_sec = int(state_counts.get(STATE_CARRIED_FORWARD, 0))
    gap_sec = int(state_counts.get(STATE_GAP_DISCONTINUITY, 0))

    valid_mask = df_1s["state_source"] != STATE_GAP_DISCONTINUITY

    # Spread
    bpx1 = df_1s["bid_px_1"]
    apx1 = df_1s["ask_px_1"]
    mid = (bpx1 + apx1) / 2.0
    spread_bps = (apx1 - bpx1) / mid * 10000.0
    sp_valid = spread_bps[valid_mask].dropna()

    # Depth nominal quote (USD)
    bid_nom = sum(df_1s[f"bid_px_{i}"] * df_1s[f"bid_qty_{i}"] for i in range(1, 11))
    ask_nom = sum(df_1s[f"ask_px_{i}"] * df_1s[f"ask_qty_{i}"] for i in range(1, 11))
    tot_nom = (bid_nom + ask_nom)[valid_mask].dropna()

    # Staleness
    st_valid = df_1s["staleness_ms"][valid_mask].dropna()

    # Updates per second
    ups = df_1s["updates_count"]

    # Protocol Point 13 Invalidation checks:
    # 1. Pérdida de conexión > 30s o > 2 reconexiones
    adapter_counters = manifest.get("adapter_counters", {})
    reconnects = adapter_counters.get("reconnects", 0)
    crc_failures = adapter_counters.get("checksum_failures", 0)
    
    # Max continuous gap
    gap_series = (df_1s["state_source"] == STATE_GAP_DISCONTINUITY).astype(int)
    gap_blocks = (gap_series != gap_series.shift()).cumsum()
    max_gap_duration = int(gap_series.groupby(gap_blocks).sum().max()) if gap_sec > 0 else 0

    gap_pct = (gap_sec / total_sec * 100.0) if total_sec else 0.0
    usable_sec = int(valid_mask.sum())

    invalidation_reasons = []
    if reconnects > 2:
        invalidation_reasons.append(f"Exceso de reconexiones ({reconnects} > 2)")
    if crc_failures > 0:
        invalidation_reasons.append(f"Fallo de checksum CRC32 ({crc_failures} > 0)")
    if max_gap_duration > 30:
        invalidation_reasons.append(f"Desconexión prolongada sin mensajes ({max_gap_duration}s > 30s)")
    if gap_pct > 3.0:
        invalidation_reasons.append(f"Porcentaje de gaps excesivo ({gap_pct:.2f}% > 3.0%)")

    status = "VALID" if not invalidation_reasons else "INVALID"

    return {
        "session_name": raw_parquet_path.stem,
        "file_path": str(raw_parquet_path),
        "file_sha256": file_sha,
        "manifest_sha256": manifest_sha,
        "sha_matches_manifest": sha_match,
        "status": status,
        "invalidation_reasons": invalidation_reasons,
        "duration_seconds": manifest.get("elapsed_seconds", total_sec),
        "raw_valid_rows": len(df_raw),
        "adapter_counters": adapter_counters,
        "resampled_seconds": {
            "total": total_sec,
            "observed": obs_sec,
            "observed_pct": round(obs_sec / total_sec * 100.0, 2) if total_sec else 0.0,
            "carried_forward": car_sec,
            "carried_forward_pct": round(car_sec / total_sec * 100.0, 2) if total_sec else 0.0,
            "gap_discontinuity": gap_sec,
            "gap_pct": round(gap_pct, 2),
            "max_consecutive_gap_seconds": max_gap_duration,
            "usable_seconds": usable_sec,
        },
        "spread_bps": {
            "mean": round(float(sp_valid.mean()), 4) if len(sp_valid) else None,
            "median": round(float(sp_valid.median()), 4) if len(sp_valid) else None,
            "p05": round(float(sp_valid.quantile(0.05)), 4) if len(sp_valid) else None,
            "p95": round(float(sp_valid.quantile(0.95)), 4) if len(sp_valid) else None,
            "min": round(float(sp_valid.min()), 4) if len(sp_valid) else None,
            "max": round(float(sp_valid.max()), 4) if len(sp_valid) else None,
        },
        "depth_quote_usd": {
            "median": round(float(tot_nom.median()), 2) if len(tot_nom) else None,
            "mean": round(float(tot_nom.mean()), 2) if len(tot_nom) else None,
            "p05": round(float(tot_nom.quantile(0.05)), 2) if len(tot_nom) else None,
            "p95": round(float(tot_nom.quantile(0.95)), 2) if len(tot_nom) else None,
        },
        "staleness_ms": {
            "median": round(float(st_valid.median()), 2) if len(st_valid) else None,
            "p95": round(float(st_valid.quantile(0.95)), 2) if len(st_valid) else None,
            "max": round(float(st_valid.max()), 2) if len(st_valid) else None,
        },
        "updates_per_second": {
            "median": round(float(ups.median()), 2) if len(ups) else None,
            "p95": round(float(ups.quantile(0.95)), 2) if len(ups) else None,
            "max": int(ups.max()) if len(ups) else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", default="data/kraken/sessions", help="Directorio de sesiones")
    parser.add_argument("--output-json", default="results/session_quality_audit.json", help="Salida JSON")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir).expanduser().resolve()
    raw_files = sorted(sessions_dir.glob("*.parquet"))
    # Exclude resampled files if any
    raw_files = [f for f in raw_files if not f.name.endswith("_1s.parquet")]

    if not raw_files:
        print(f"No se encontraron archivos parquet crudos en {sessions_dir}")
        return

    results = []
    for f in raw_files:
        print(f"Auditando sesión: {f.name}...")
        res = audit_session(f)
        results.append(res)
        print(f"  -> Estado: {res['status']} | Obs: {res['resampled_seconds']['observed_pct']}% | Usables: {res['resampled_seconds']['usable_seconds']} s")

    out_p = Path(args.output_json).expanduser().resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Resultados de auditoría guardados en {out_p}")


if __name__ == "__main__":
    main()
