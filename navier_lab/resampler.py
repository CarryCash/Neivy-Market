"""NAVIER 001.9: Resampleador causal de libros L2 a intervalos regulares de 1 segundo.

Garantiza:
1. Causalidad estricta: cada intervalo (T - 1.0s, T] se etiqueta con la cota superior T (instante de cierre).
   Ningún evento posterior a T interviene en la selección del estado de T.
2. Desempate determinista: en timestamps de exchange idénticos (Delta t = 0), se desempata por orden posicional
   de lectura en el stream de entrada (row_id).
3. Clasificación de estados:
   - OBSERVED: Al menos un mensaje recibido en (T - 1.0s, T].
   - CARRIED_FORWARD: Cero mensajes en el intervalo, pero staleness <= gap_threshold_seconds.
   - GAP_DISCONTINUITY: Cero mensajes y staleness > gap_threshold_seconds, o reinicio.
4. Generación de metadatos de trazabilidad: updates_count, state_source, staleness_ms, last_checksum.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Iterator
import numpy as np
import pandas as pd

from .schema import (
    BID_PX,
    BID_QTY,
    ASK_PX,
    ASK_QTY,
    STATE_OBSERVED,
    STATE_CARRIED_FORWARD,
    STATE_GAP_DISCONTINUITY,
    RESAMPLED_L2_COLUMNS,
)

LEVEL_COLS = BID_PX + BID_QTY + ASK_PX + ASK_QTY


@dataclass(frozen=True)
class ResamplerConfig:
    bin_size_seconds: float = 1.0
    gap_threshold_seconds: float = 3.0  # Parámetro operativo provisional


def resample_l2_to_1s(
    df: pd.DataFrame,
    cfg: ResamplerConfig = ResamplerConfig(),
) -> pd.DataFrame:
    """Transforma un DataFrame de eventos L2 en una serie temporal regular de 1 s causal.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame con columnas ['timestamp', 'symbol', 'checksum'] + 10 niveles L2.
        `timestamp` debe ser datetime64 con zona horaria UTC o convertible a ella.
    cfg : ResamplerConfig
        Configuración del resampleador (tamaño del bin y umbral provisional de gap).

    Retorna
    -------
    pd.DataFrame
        DataFrame regular indexado cada segundo exacto, conteniendo RESAMPLED_L2_COLUMNS.
    """
    if df.empty:
        return pd.DataFrame(columns=RESAMPLED_L2_COLUMNS)

    # 1. Asegurar tipos y orden causal estricto
    work = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(work["timestamp"].dtype):
        work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    elif getattr(work["timestamp"].dt, "tz", None) is None:
        work["timestamp"] = work["timestamp"].dt.tz_localize("UTC")
    else:
        work["timestamp"] = work["timestamp"].dt.tz_convert("UTC")

    # Event order is the state-transition order. Sorting a reversal by exchange
    # time can silently place a later book state before an earlier one.
    if not work["timestamp"].is_monotonic_increasing:
        raise ValueError("timestamp de exchange retrocede; resampleo rechazado")

    # Preservar el orden original inequívoco para desempate en ráfagas con idéntico timestamp
    work["_source_row_id"] = np.arange(len(work), dtype=np.int64)

    # Stable row order preserves the websocket ordering for equal timestamps.
    work = work.reset_index(drop=True)

    symbol = work["symbol"].iloc[0] if "symbol" in work.columns else "BTC/USDT"

    # 2. Definir rejilla temporal regular de 1 segundo
    # Inicio: primer segundo entero que cierra el primer intervalo que contiene o sigue a first_ts
    first_ts = work["timestamp"].iloc[0]
    last_ts = work["timestamp"].iloc[-1]

    # Redondeo hacia arriba al segundo cerrado exacto
    start_sec = first_ts.ceil("1s")
    # Redondeo hacia arriba del último evento para capturar el intervalo de cierre
    end_sec = last_ts.ceil("1s")

    if start_sec > end_sec:
        return pd.DataFrame(columns=RESAMPLED_L2_COLUMNS)

    grid_seconds = pd.date_range(start=start_sec, end=end_sec, freq="1s", tz="UTC")

    # 3. Asignación causal de eventos a intervalos semiabiertos (T - 1.0s, T]
    # Trabajamos directamente sobre int64 de nanosegundos para evitar advertencias de zona horaria y ser ultrarrápidos
    ts_ns = work["timestamp"].astype("int64").values
    
    rows_out = []
    
    # Estado del libro arrastrado
    last_known_levels: Optional[dict[str, float]] = None
    last_observed_time: Optional[pd.Timestamp] = None
    last_known_checksum: Optional[int] = None
    availability_fields = ("capture_row_id", "received_at", "received_monotonic_ns",
                           "processed_at", "processed_monotonic_ns",
                           "frame_received_monotonic_ns",
                           "state_processed_monotonic_ns",
                           "state_validated_monotonic_ns")
    last_availability = {field: None for field in availability_fields}

    # Inicializar con el último evento previo a start_sec si existe
    left_boundary_ns = (start_sec - pd.Timedelta(seconds=1)).value
    prev_idx = np.searchsorted(ts_ns, left_boundary_ns, side="right") - 1
    if prev_idx >= 0:
        prev_row = work.iloc[prev_idx]
        last_known_levels = {col: float(prev_row[col]) for col in LEVEL_COLS}
        last_observed_time = prev_row["timestamp"]
        last_known_checksum = int(prev_row["checksum"]) if "checksum" in prev_row and pd.notna(prev_row["checksum"]) else None
        last_availability = {field: prev_row[field] if field in prev_row else None for field in availability_fields}

    current_left_ns = left_boundary_ns
    for T_k in grid_seconds:
        T_k_ns = T_k.value
        # Intervalo: (current_left_ns, T_k_ns]
        idx_start = np.searchsorted(ts_ns, current_left_ns, side="right")
        idx_end = np.searchsorted(ts_ns, T_k_ns, side="right")

        updates_count = idx_end - idx_start

        if updates_count > 0:
            # Seleccionar el último estado observado en el intervalo (respetando orden determinista)
            chosen_row = work.iloc[idx_end - 1]
            last_known_levels = {col: float(chosen_row[col]) for col in LEVEL_COLS}
            last_observed_time = chosen_row["timestamp"]
            last_known_checksum = int(chosen_row["checksum"]) if "checksum" in chosen_row and pd.notna(chosen_row["checksum"]) else None
            last_availability = {field: chosen_row[field] if field in chosen_row else None for field in availability_fields}

            staleness_ms = max(0.0, (T_k - last_observed_time).total_seconds() * 1000.0)
            state_source = STATE_OBSERVED

        else:
            # Cero mensajes en el segundo actual
            if last_observed_time is not None:
                staleness_sec = (T_k - last_observed_time).total_seconds()
                staleness_ms = staleness_sec * 1000.0
                if staleness_sec <= cfg.gap_threshold_seconds:
                    state_source = STATE_CARRIED_FORWARD
                else:
                    state_source = STATE_GAP_DISCONTINUITY
            else:
                staleness_ms = np.nan
                state_source = STATE_GAP_DISCONTINUITY

        row_dict = {
            "timestamp": T_k,
            "symbol": symbol,
            "updates_count": np.int32(updates_count),
            "state_source": state_source,
            "staleness_ms": float(staleness_ms),
            "last_checksum": last_known_checksum,
            **last_availability,
        }

        if last_known_levels is not None and state_source != STATE_GAP_DISCONTINUITY:
            row_dict.update(last_known_levels)
        else:
            for col in LEVEL_COLS:
                row_dict[col] = np.nan

        rows_out.append(row_dict)
        current_left_ns = T_k_ns

    out_df = pd.DataFrame(rows_out)
    return out_df[RESAMPLED_L2_COLUMNS]
