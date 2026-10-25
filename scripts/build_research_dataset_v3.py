"""Construcción del Dataset de Investigación NAVIER V3 (Fase 4).

Procesa las 7 sesiones independientes congeladas de captura L2 (BTC/USD):
1. Validación criptográfica y de integridad por sesión (SHA-256, orden temporal, sin duplicados, esquema y manifiesto raw).
2. Cálculo de variables Modelos B, B+, B++, B+++, E y E_H1a de forma estrictamente causal y separada por sesión.
3. Exclusión causal por sesión:
   - Calentamiento inicial de 60 segundos (vol60_bps y ventanas históricas).
   - Fin de sesión de 10 segundos (evita que retornos futuros crucen límites de sesión).
   - Invalidador de discontinuidad (gaps en [t, t+H] y staleness futura > 1000 ms).
   - Invalidador de historia corrompida (gaps en los últimos 60 s o arrastre excesivo).
   - Suelo de volatilidad causal (vol60_bps >= 0.01 bps).
4. Trazabilidad: preservación de session_id, session_idx, timestamp, state_source, staleness_ms y updates_count.
5. Concatenación exclusiva de observaciones limpias que satisfacen la regla de muestra común.
6. Generación de manifiesto formal con hashes y estadísticas de descarte por sesión.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from navier_lab.features import (
    compute_features,
    BASIC_MODEL,
    TRADITIONAL_ONLY,
    LAGS,
    NAVIER_V3_CORE,
    NAVIER_V3_REPLENISH,
    TARGET,
    TARGET_BPS,
)
from navier_lab.schema import (
    Config,
    DEFAULT_CONFIG,
    STATE_OBSERVED,
    STATE_CARRIED_FORWARD,
    STATE_GAP_DISCONTINUITY,
    RESAMPLED_L2_COLUMNS,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


CONFIRMATORY_REQUIRED_COLS = (
    BASIC_MODEL + TRADITIONAL_ONLY + LAGS + NAVIER_V3_CORE + [TARGET]
)


def process_single_session(
    session_raw_path: Path,
    session_1s_path: Path,
    session_idx: int,
    cfg: Config = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict]:
    """Procesa una única sesión con estricta independencia temporal y sin fuga entre sesiones."""
    session_id = session_raw_path.stem
    raw_sha = sha256_file(session_raw_path) if session_raw_path.exists() else None
    resampled_sha = sha256_file(session_1s_path) if session_1s_path.exists() else None

    # 1. Validación de manifiesto de captura original L2
    raw_manifest_path = session_raw_path.with_suffix(".parquet.manifest.json")
    if not raw_manifest_path.exists():
        raise FileNotFoundError(f"Sesión {session_id}: manifiesto raw no encontrado en {raw_manifest_path}")

    raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    if raw_sha != raw_manifest.get("output_sha256"):
        raise ValueError(f"Sesión {session_id}: hash raw no coincide con manifiesto ({raw_sha} vs {raw_manifest.get('output_sha256')})")
    if raw_manifest.get("final_book_status") != "VALID":
        raise ValueError(f"Sesión {session_id}: estado final no válido: {raw_manifest.get('final_book_status')}")
    if raw_manifest.get("adapter_counters", {}).get("checksum_failures", 0) != 0:
        raise ValueError(f"Sesión {session_id}: se detectaron checksum failures en adapter_counters")

    # 2. Lectura y validación de esquema y orden temporal del archivo _1s.parquet
    df_1s = pd.read_parquet(session_1s_path)
    n_1s = len(df_1s)

    # Validar esquema de entrada
    missing_cols = set(RESAMPLED_L2_COLUMNS) - set(df_1s.columns)
    if missing_cols:
        raise ValueError(f"Sesión {session_id}: faltan columnas requeridas del esquema resampleado: {missing_cols}")

    # Monotonicidad estricta y ausencia de duplicados
    if not df_1s["timestamp"].is_monotonic_increasing:
        raise ValueError(f"Sesión {session_id}: timestamps no estrictamente crecientes")
    if df_1s["timestamp"].duplicated().any():
        raise ValueError(f"Sesión {session_id}: existen timestamps duplicados")

    timestamps = pd.to_datetime(df_1s["timestamp"], utc=True).reset_index(drop=True)
    if len(timestamps) > 1 and (timestamps.diff().dropna() != pd.Timedelta(seconds=1)).any():
        raise ValueError(
            f"Sesión {session_id}: el target por shift({cfg.horizon}) requiere una rejilla exacta de 1 s"
        )

    # Validar valores de estado y staleness
    valid_states = {STATE_OBSERVED, STATE_CARRIED_FORWARD, STATE_GAP_DISCONTINUITY}
    actual_states = set(df_1s["state_source"].unique())
    if not actual_states.issubset(valid_states):
        raise ValueError(f"Sesión {session_id}: estados inválidos detectados: {actual_states - valid_states}")

    if (df_1s["staleness_ms"] < 0).any() or df_1s["staleness_ms"].isna().any():
        raise ValueError(f"Sesión {session_id}: staleness_ms contiene valores negativos o NaN")

    # 3. Cálculo causal de variables y target aislado por sesión
    feat = compute_features(df_1s, cfg, with_target=True)

    # Persist the exact market times used by compute_features' positional target:
    # y_t = log(mid[t + H] / mid[t]). The 1-second grid was validated above,
    # so the shifted timestamp is the actual endpoint, not an index-based guess
    # made later after invalid rows have been removed.
    feat["timestamp"] = timestamps
    feat["feature_time"] = timestamps
    feat["label_start_time"] = timestamps
    feat["label_end_time"] = timestamps.shift(-cfg.horizon)
    feat["label_end_session_id"] = np.where(
        feat["label_end_time"].notna().to_numpy(), session_id, None
    )
    feat["label_horizon_seconds"] = int(cfg.horizon)

    # Inyectar trazabilidad
    feat["session_id"] = session_id
    feat["session_idx"] = session_idx
    feat["state_source"] = df_1s["state_source"].to_numpy()
    feat["staleness_ms"] = df_1s["staleness_ms"].to_numpy()
    feat["updates_count"] = df_1s["updates_count"].to_numpy()

    # 4. Auditoría rigurosa de motivos de descarte
    warmup_n = cfg.vol_window
    horizon_n = cfg.horizon

    warmup_mask = np.zeros(n_1s, dtype=bool)
    warmup_mask[:warmup_n] = True

    end_session_mask = np.zeros(n_1s, dtype=bool)
    end_session_mask[-horizon_n:] = True

    gap_direct_mask = (df_1s["state_source"] == STATE_GAP_DISCONTINUITY).to_numpy()

    # Discontinuidades y staleness en ventana futura (t, t+H]
    gap_numeric = (df_1s["state_source"] == STATE_GAP_DISCONTINUITY).astype(int)
    gap_fut_mask = (
        gap_numeric.iloc[::-1].rolling(horizon_n, min_periods=1).max().iloc[::-1].shift(-1).fillna(0).to_numpy() == 1
    )
    stale_series = pd.Series(df_1s["staleness_ms"].to_numpy())
    stale_thresh = getattr(cfg, "staleness_threshold_ms", 1000.0)
    stale_at_h = (stale_series.shift(-horizon_n) > stale_thresh).fillna(False).to_numpy()
    stale_in_fut = (
        (stale_series > stale_thresh).astype(int).iloc[::-1].rolling(horizon_n, min_periods=1).max().iloc[::-1].shift(-1).fillna(0).to_numpy() == 1
    )
    future_staleness_mask = stale_at_h | stale_in_fut

    # Corrupción histórica en [t-60, t]
    gap_hist_mask = gap_numeric.rolling(warmup_n, min_periods=1).max().to_numpy() == 1
    carried_ratio = (df_1s["state_source"] == STATE_CARRIED_FORWARD).astype(float).rolling(warmup_n, min_periods=1).mean().to_numpy()
    hist_corrupted_mask = gap_hist_mask | (carried_ratio > 0.20)

    # Suelo de volatilidad
    vol_floor_mask = feat["vol60_bps"].to_numpy() < 0.01

    feat_na_mask = feat[CONFIRMATORY_REQUIRED_COLS[:-1]].isna().any(axis=1).to_numpy()
    target_na_mask = feat[TARGET].isna().to_numpy()

    # Filtro común confirmatorio estricto
    valid_mask = (~feat_na_mask) & (~target_na_mask)
    df_valid = feat[valid_mask].copy().reset_index(drop=True)

    session_audit = {
        "session_idx": session_idx,
        "session_id": session_id,
        "raw_file": session_raw_path.name,
        "raw_sha256": raw_sha,
        "resampled_file": session_1s_path.name,
        "resampled_sha256": resampled_sha,
        "total_1s_bins": n_1s,
        "clean_rows_retained": len(df_valid),
        "discarded_rows_total": n_1s - len(df_valid),
        "discards_warmup_60s": int(warmup_mask.sum()),
        "discards_end_session_10s": int(end_session_mask.sum()),
        "discards_direct_gap_bins": int(gap_direct_mask.sum()),
        "discards_future_gap_10s": int(gap_fut_mask.sum()),
        "discards_future_staleness_10s": int(future_staleness_mask.sum()),
        "discards_hist_corrupted_60s": int(hist_corrupted_mask.sum()),
        "discards_vol60_floor_low": int(vol_floor_mask.sum()),
        "discards_target_na": int(target_na_mask.sum()),
        "discards_features_na": int(feat_na_mask.sum()),
        "timestamp_start": str(df_1s["timestamp"].iloc[0]),
        "timestamp_end": str(df_1s["timestamp"].iloc[-1]),
        "label_horizon_seconds": int(cfg.horizon),
        "one_second_grid_validated": True,
    }

    return df_valid, session_audit


def build_research_dataset_v3(
    sessions_dir: Path,
    output_path: Path,
    manifest_path: Path,
    cfg: Config = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict]:
    """Construye data/research_dataset_v3.parquet y su manifiesto a partir de las 7 sesiones."""
    sessions_dir = sessions_dir.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Identificar las 7 sesiones en orden
    session_files = []
    for i in range(1, 8):
        raw_p = sessions_dir / f"v3_val_session_{i:02d}_btc_usd_l2.parquet"
        res_p = sessions_dir / f"v3_val_session_{i:02d}_btc_usd_l2_1s.parquet"
        if not raw_p.exists() or not res_p.exists():
            raise FileNotFoundError(f"Sesión {i:02d} incompleta en {sessions_dir}: {raw_p} o {res_p} no existe")
        session_files.append((i, raw_p, res_p))

    valid_frames = []
    session_metas = []

    print(f"Iniciando procesamiento de {len(session_files)} sesiones independientes...")
    for idx, raw_p, res_p in session_files:
        print(f"  Procesando sesión {idx:02d}: {raw_p.name} -> {res_p.name}...")
        df_clean, meta = process_single_session(raw_p, res_p, idx, cfg)
        valid_frames.append(df_clean)
        session_metas.append(meta)
        print(f"    Total bins: {meta['total_1s_bins']} | Limpios válidos: {meta['clean_rows_retained']} ({meta['clean_rows_retained']/meta['total_1s_bins']*100:.1f}%)")

    # Concatenación ordenada
    combined = pd.concat(valid_frames, ignore_index=True)
    combined = combined.sort_values(by=["timestamp", "session_idx"]).reset_index(drop=True)

    # Verificación de unicidad
    dup_mask = combined.duplicated(subset=["session_id", "timestamp"])
    if dup_mask.any():
        raise ValueError(f"Error crítico: se encontraron {dup_mask.sum()} filas con clave duplicada (session_id, timestamp)")

    # Guardar Parquet comprimido con Zstandard
    table = pa.Table.from_pandas(combined, preserve_index=False)
    pq.write_table(table, output_path, compression="zstd")
    output_sha = sha256_file(output_path)

    # Construir manifiesto
    manifest = {
        "project": "NAVIER",
        "phase": "FASE_4_DATASET_CONSTRUCTION",
        "version": "001.9-temporal-endpoints",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": output_path.name,
        "output_sha256": output_sha,
        "total_valid_rows": len(combined),
        "total_columns": len(combined.columns),
        "column_names": list(combined.columns),
        "parameters": {
            "horizon_seconds": cfg.horizon,
            "vol_window_seconds": cfg.vol_window,
            "ofi_window_seconds": cfg.ofi_window,
            "vel_window_seconds": cfg.vel_window,
            "gap_threshold_seconds": 3.0,
            "staleness_threshold_ms": 1000.0,
            "min_vol_floor_bps": 0.01,
        },
        "sessions_summary": session_metas,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDataset construido con éxito:")
    print(f"  Archivo: {output_path} ({len(combined)} filas)")
    print(f"  SHA-256: {output_sha}")
    print(f"  Manifiesto: {manifest_path}")

    return combined, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions-dir",
        default="data/v3_validation/sessions",
        help="Directorio con las 7 sesiones independientes",
    )
    parser.add_argument(
        "--output",
        default="data/research_dataset_v3.parquet",
        help="Ruta destino del dataset consolidado",
    )
    parser.add_argument(
        "--manifest",
        default="data/research_dataset_v3.manifest.json",
        help="Ruta destino del manifiesto JSON",
    )
    args = parser.parse_args()

    build_research_dataset_v3(
        sessions_dir=Path(args.sessions_dir),
        output_path=Path(args.output),
        manifest_path=Path(args.manifest),
    )


if __name__ == "__main__":
    main()
