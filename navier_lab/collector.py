"""Fuentes batch del pipeline. ParquetSource y SyntheticSource comparten RAW_COLUMNS.

KrakenL2Source sigue siendo un stub de streaming dentro de esta interfaz. La captura
live implementada está separada en scripts/capture_kraken_l2.py y
navier_lab.kraken_ws_v2.KrakenSpotBookV2Adapter; no se debe inferir que este módulo
genérico sea el adaptador efectivo del exchange.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .schema import RAW_COLUMNS, BID_PX, ASK_PX, BID_QTY, ASK_QTY


def validate_chunk(df: pd.DataFrame) -> None:
    """Chequeos de integridad del contrato de datos (falla ruidosamente)."""
    missing = set(RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"faltan columnas: {sorted(missing)[:5]}...")
    if not (df[ASK_PX[0]] > df[BID_PX[0]]).all():
        raise ValueError("libro cruzado: ask_1 <= bid_1")
    if (df[BID_QTY + ASK_QTY] <= 0).any().any():
        raise ValueError("cantidades no positivas")
    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError("timestamps no monótonos")
    dt = df["timestamp"].diff().dropna()
    if len(dt) and (dt != pd.Timedelta("1s")).any():
        raise ValueError("huecos/irregularidades en la malla de 1 s (usar to_1s_grid antes)")


class ParquetSource:
    """Lee un parquet L2 por row-groups. Memoria acotada al tamaño del row-group."""
    def __init__(self, path, validate: bool = True):
        self.path, self.validate = path, validate

    def __iter__(self) -> Iterator[pd.DataFrame]:
        pf = pq.ParquetFile(self.path)
        for i in range(pf.num_row_groups):
            df = pf.read_row_group(i).to_pandas()
            if self.validate:
                validate_chunk(df)
            yield df[RAW_COLUMNS]


def to_1s_grid(events: pd.DataFrame) -> pd.DataFrame:
    """Para datos REALES a nivel evento: último estado del libro dentro de cada segundo,
    rellenando (ffill) los segundos sin eventos. Requiere columna 'timestamp' (UTC).
    NOTA: si se usa por chunks hay que acarrear el segundo incompleto del final (pendiente)."""
    ev = events.copy()
    ev["timestamp"] = ev["timestamp"].dt.floor("1s")
    g = ev.groupby("timestamp", sort=True).last()
    full = pd.date_range(g.index.min(), g.index.max(), freq="1s")
    return g.reindex(full).ffill().rename_axis("timestamp").reset_index()


class KrakenL2Source:
    """STUB deliberado. No hay descarga ni conexión de red en la V0.1."""
    def __init__(self, *a, **k):
        raise NotImplementedError(
            "Fuente real pendiente de decisión conjunta: WebSocket L2 (book depth=10), "
            "duración de captura, almacenamiento y reducción a rejilla de 1 s.")
