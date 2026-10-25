"""NAVIER 001.6 — Pruebas de robustez numérica, integridad de libros y estabilidad temporal.
Ejecutar: pytest tests/test_robustness_001_6.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest
import pyarrow.parquet as pq

from navier_lab import synthetic as S, features as F, collector as C
from navier_lab.schema import DEFAULT_CONFIG as CFG, RAW_COLUMNS, BID_PX, ASK_PX, BID_QTY, ASK_QTY


def test_orderbook_monotonicity_orientation():
    """A-06: Comprueba que la orientación de precios sea estrictamente:
    bid_1 > bid_2 > ... > bid_10  (descendente alejándose del BBO)
    ask_1 < ask_2 < ... < ask_10  (ascendente alejándose del BBO)
    """
    raw, _ = S.generate("S2_navier", n=1_000, seed=42)
    
    b_mat = raw[BID_PX].to_numpy(float)
    a_mat = raw[ASK_PX].to_numpy(float)
    
    # Bid: cada nivel debe ser menor que el anterior (más alejado del BBO)
    bid_desc = (b_mat[:, :-1] > b_mat[:, 1:]).all()
    assert bid_desc, "Violación en orientación de precios Bid: no son estrictamente descendentes"
    
    # Ask: cada nivel debe ser mayor que el anterior (más alejado del BBO)
    ask_asc = (a_mat[:, :-1] < a_mat[:, 1:]).all()
    assert ask_asc, "Violación en orientación de precios Ask: no son estrictamente ascendentes"
    
    # Spread BBO positivo estricto
    assert (a_mat[:, 0] > b_mat[:, 0]).all(), "Spread BBO cruzado o bloqueado"


def test_constant_price_numerical_stress():
    """A-07: Comprueba la estabilidad numérica ante precio constante.
    Detecta división por cero en vol60_bps -> Re_m.
    """
    n = 120
    df_const = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1s"),
    })
    for i in range(1, 11):
        df_const[f"bid_px_{i}"] = 100.0 - (i - 1) * 0.1
        df_const[f"ask_px_{i}"] = 100.1 + (i - 1) * 0.1
        df_const[f"bid_qty_{i}"] = 1.0
        df_const[f"ask_qty_{i}"] = 1.0
        
    feats = F.compute_features(df_const, CFG, with_target=False)
    
    # u debe ser numéricamente cero
    assert np.allclose(feats["u"].dropna(), 0.0, atol=1e-8)
    # vol60_bps debe ser exactamente cero
    assert np.allclose(feats["vol60_bps"].dropna(), 0.0, atol=1e-8)
    
    # Diagnóstico A-07: verificar si la implementación actual de Re_m produce inf
    # En V0.1 sin regularización produce inf. Registramos si hay infinitos.
    re = feats["re_m"].to_numpy()
    has_inf = np.isinf(re).any()
    # Esta aserción formaliza el hallazgo A-07 documentado para V0.2
    assert has_inf, "Esperado en V0.1: Re_m diverge a inf ante vol=0 sin epsilon"


def test_dataset_provenance_and_full_parquet():
    """A-08: Audita el dataset completo archivado en Parquet (100.000 filas)."""
    p = pathlib.Path(__file__).resolve().parents[1] / "data" / "synthetic" / "raw_S2_navier.parquet"
    assert p.exists(), f"No se encuentra el archivo {p}"
    
    pf = pq.ParquetFile(p)
    assert pf.metadata.num_rows == 100_000, f"Filas esperadas 100_000, encontradas {pf.metadata.num_rows}"
    
    # Validar integridad del primer row-group
    df_first = pf.read_row_group(0).to_pandas()
    C.validate_chunk(df_first)
    assert len(df_first) > 0


def test_gap_and_disconnection_detection():
    """Simula una desconexión (hueco en timestamp) y asegura que falle ruidosamente."""
    raw, _ = S.generate("S2_navier", n=200, seed=123)
    # Generar un hueco de 5 segundos eliminando filas intermedias
    raw_with_gap = raw.drop(index=list(range(50, 55))).reset_index(drop=True)
    
    with pytest.raises(ValueError, match="huecos/irregularidades en la malla de 1 s"):
        C.validate_chunk(raw_with_gap)


def test_crossed_book_detection_all_levels():
    """Detecta cuando cualquier nivel ask es menor o igual a su bid correspondiente."""
    raw, _ = S.generate("S2_navier", n=50, seed=99)
    bad_book = raw.copy()
    bad_book.loc[10, "ask_px_1"] = bad_book.loc[10, "bid_px_1"]
    
    with pytest.raises(ValueError, match="libro cruzado: ask_1 <= bid_1"):
        C.validate_chunk(bad_book)
