"""Pruebas de integridad, causalidad, fronteras y compatibilidad para el Dataset V3 (Fase 4)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

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
from navier_lab.schema import DEFAULT_CONFIG, STATE_GAP_DISCONTINUITY
from scripts.evaluate_models_oos_v3 import (
    prepare_feature_dataframe,
    MODEL_SPECS_V3,
)

DATASET_PATH = Path("data/research_dataset_v3.parquet")
MANIFEST_PATH = Path("data/research_dataset_v3.manifest.json")
SESSIONS_DIR = Path("data/v3_validation/sessions")


def test_research_dataset_v3_structure_and_hashes():
    """Valida la existencia, hash, dimensiones y ausencia de duplicados del dataset V3."""
    assert DATASET_PATH.exists(), f"No existe {DATASET_PATH}"
    assert MANIFEST_PATH.exists(), f"No existe {MANIFEST_PATH}"

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    
    # Verificar hash SHA-256
    digest = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
    assert digest == manifest["output_sha256"], "El hash SHA-256 no coincide con el manifiesto"

    df = pd.read_parquet(DATASET_PATH)
    assert len(df) == 13558, f"Esperadas 13558 filas, encontradas {len(df)}"
    assert len(df) == manifest["total_valid_rows"]

    # Verificar unicidad
    dups = df.duplicated(subset=["session_id", "timestamp"]).sum()
    assert dups == 0, f"Existen {dups} duplicados de (session_id, timestamp)"

    # Verificar monotonicidad de timestamps
    assert df["timestamp"].is_monotonic_increasing, "Los timestamps no están ordenados cronológicamente"

    # Verificar que no hay NaN o Inf en columnas confirmatorias requeridas ni en target
    conf_cols = BASIC_MODEL + TRADITIONAL_ONLY + LAGS + NAVIER_V3_CORE + [TARGET]
    for col in conf_cols:
        assert col in df.columns, f"Columna requerida {col} ausente en dataset"
        n_nan = df[col].isna().sum()
        assert n_nan == 0, f"Columna {col} contiene {n_nan} valores NaN"
        vals = df[col].to_numpy(float)
        assert np.isfinite(vals).all(), f"Columna {col} contiene valores infinitos"


def test_session_boundary_isolation():
    """Verifica que ninguna ventana de features ni target cruce los límites entre sesiones."""
    df_dataset = pd.read_parquet(DATASET_PATH)

    # Procesar sesión 1 y 2 por separado
    p1 = SESSIONS_DIR / "v3_val_session_01_btc_usd_l2_1s.parquet"
    p2 = SESSIONS_DIR / "v3_val_session_02_btc_usd_l2_1s.parquet"
    
    df1_1s = pd.read_parquet(p1)
    df2_1s = pd.read_parquet(p2)

    feat1 = compute_features(df1_1s, DEFAULT_CONFIG, with_target=True)
    feat2 = compute_features(df2_1s, DEFAULT_CONFIG, with_target=True)

    # Las últimas 10 filas de la sesión 1 DEBEN ser NaN en target
    assert feat1[TARGET].iloc[-10:].isna().all(), "Los targets de las últimas 10 filas de sesión 1 no son NaN"

    # Las primeras 60 filas de la sesión 2 DEBEN ser NaN en vol60_bps
    assert feat2["vol60_bps"].iloc[:60].isna().all(), "Las primeras 60 filas de sesión 2 no son NaN en vol60_bps"

    # Comprobar que en el dataset consolidado las filas de sesión 1 coinciden exactamente
    df_s1 = df_dataset[df_dataset["session_id"] == "v3_val_session_01_btc_usd_l2"]
    conf_cols = BASIC_MODEL + TRADITIONAL_ONLY + LAGS + NAVIER_V3_CORE + [TARGET]
    clean_feat1 = feat1.dropna(subset=conf_cols)
    assert len(df_s1) == len(clean_feat1) == 2259
    np.testing.assert_allclose(
        df_s1[TARGET].to_numpy(float),
        clean_feat1[TARGET].to_numpy(float),
        rtol=1e-10, atol=1e-10,
    )


def test_features_causality_under_future_perturbations_v3():
    """Verifica que perturbar datos en t > t0 no altere ninguna feature de Model_E en t <= t0."""
    p1 = SESSIONS_DIR / "v3_val_session_01_btc_usd_l2_1s.parquet"
    raw_orig = pd.read_parquet(p1).head(300).copy()
    
    t0 = 150
    feat_orig = compute_features(raw_orig, DEFAULT_CONFIG, with_target=False)

    # Perturbar datos posteriores a t0
    raw_pert = raw_orig.copy()
    raw_pert.loc[t0 + 1:, "bid_px_1"] *= 1.15
    raw_pert.loc[t0 + 1:, "ask_px_1"] *= 1.25
    raw_pert.loc[t0 + 1:, "bid_qty_1"] *= 5.0
    raw_pert.loc[t0 + 1:, "ask_qty_1"] *= 0.2

    feat_pert = compute_features(raw_pert, DEFAULT_CONFIG, with_target=False)

    # Comprobar todas las columnas de Model_E en t <= t0
    cols_to_check = BASIC_MODEL + TRADITIONAL_ONLY + LAGS + NAVIER_V3_CORE + ["ofi_raw_5"]
    for col in cols_to_check:
        v_orig = feat_orig[col].iloc[:t0 + 1].to_numpy(float)
        v_pert = feat_pert[col].iloc[:t0 + 1].to_numpy(float)
        # Comparar admitiendo NaNs iguales
        np.testing.assert_equal(
            np.isnan(v_orig), np.isnan(v_pert),
            err_msg=f"Discrepancia en máscara NaN para {col} en t <= t0"
        )
        valid = ~np.isnan(v_orig)
        np.testing.assert_allclose(
            v_orig[valid], v_pert[valid], rtol=1e-12, atol=1e-12,
            err_msg=f"Fuga causal detectada en variable {col} en t <= t0"
        )


def test_target_horizon_and_normalization_protocol_adherence():
    """Verifica que el target respete exactamente la definición formal del protocolo."""
    df = pd.read_parquet(DATASET_PATH).head(100)
    
    # Protocolo Sección 5: y = [ln(mid(t+10)/mid(t)) * 10^4] / [vol60_bps * sqrt(10)]
    y_target = df[TARGET].to_numpy(float)
    y_bps = df[TARGET_BPS].to_numpy(float)
    vol60 = df["vol60_bps"].to_numpy(float)

    denom = vol60 * np.sqrt(DEFAULT_CONFIG.horizon)
    expected_y = y_bps / denom
    np.testing.assert_allclose(y_target, expected_y, rtol=1e-10, atol=1e-10)


def test_gap_and_staleness_mask_propagation():
    """Verifica que las discontinuidades y staleness se propaguen correctamente a las máscaras."""
    p3 = SESSIONS_DIR / "v3_val_session_03_btc_usd_l2_1s.parquet"
    raw3 = pd.read_parquet(p3)
    feat3 = compute_features(raw3, DEFAULT_CONFIG, with_target=True)

    # Sesión 3 tiene gaps directos
    gaps = (raw3["state_source"] == STATE_GAP_DISCONTINUITY).to_numpy()
    assert gaps.sum() > 0, "Se esperaba que la sesión 3 contuviera gaps"

    # En cada bin con gap directo, las features V3 y el target DEBEN ser NaN
    gap_idx = np.where(gaps)[0]
    for idx in gap_idx:
        assert np.isnan(feat3[TARGET].iloc[idx]), f"Target en bin de gap {idx} no es NaN"
        assert np.isnan(feat3["v03_pnpc_k3"].iloc[idx]), f"pnpc_k3 en bin de gap {idx} no es NaN"


def test_compatibility_with_evaluate_models_oos_v3():
    """Verifica que el dataset sea 100% compatible con evaluate_models_oos_v3 sin modificaciones."""
    df = pd.read_parquet(DATASET_PATH)
    
    # Probar prepare_feature_dataframe
    df_prepared = prepare_feature_dataframe(df)
    assert "_ofi_x_imb" in df_prepared.columns
    assert "_ofi_div_depth10" in df_prepared.columns
    assert not df_prepared["_ofi_x_imb"].isna().any()
    assert not df_prepared["_ofi_div_depth10"].isna().any()
    assert np.isfinite(df_prepared["_ofi_div_depth10"].to_numpy(float)).all()

    # Probar que todas las variables de todos los modelos existen en df_prepared
    for m_name, cols in MODEL_SPECS_V3.items():
        for col in cols:
            assert col in df_prepared.columns, f"Modelo {m_name} requiere columna {col} que no está en el DataFrame preparado"
            assert not df_prepared[col].isna().any(), f"Modelo {m_name} tiene valores NaN en {col}"


def test_row_selection_and_masks_no_future_leakage():
    """Verifica que la máscara de validez en t solo dependa de t..t+H y no de t > t+H."""
    p1 = SESSIONS_DIR / "v3_val_session_01_btc_usd_l2_1s.parquet"
    raw = pd.read_parquet(p1).head(200).copy()
    t0 = 80
    H = DEFAULT_CONFIG.horizon  # 10
    
    feat_orig = compute_features(raw, DEFAULT_CONFIG, with_target=True)
    conf_cols = BASIC_MODEL + TRADITIONAL_ONLY + LAGS + NAVIER_V3_CORE
    valid_orig = feat_orig[conf_cols].notna().all(axis=1) & feat_orig[TARGET].notna()
    
    # Perturbar fuertemente en t > t0 + H (t > 90)
    raw_pert = raw.copy()
    raw_pert.loc[t0 + H + 1:, "bid_px_1"] *= 2.0
    raw_pert.loc[t0 + H + 1:, "ask_px_1"] *= 2.0
    raw_pert.loc[t0 + H + 1:, "bid_qty_1"] *= 10.0
    raw_pert.loc[t0 + H + 1:, "state_source"] = STATE_GAP_DISCONTINUITY
    raw_pert.loc[t0 + H + 1:, "staleness_ms"] = 50000.0

    feat_pert = compute_features(raw_pert, DEFAULT_CONFIG, with_target=True)
    valid_pert = feat_pert[conf_cols].notna().all(axis=1) & feat_pert[TARGET].notna()
    
    # La validez de las filas 0..t0 no debe verse alterada en absoluto
    np.testing.assert_array_equal(
        valid_orig.iloc[:t0 + 1].to_numpy(),
        valid_pert.iloc[:t0 + 1].to_numpy(),
        err_msg="La selección de filas en t <= t0 cambió al perturbar datos en t > t0 + H"
    )


def test_all_seven_sessions_raw_manifests_and_schemas():
    """Valida los manifiestos raw y esquemas para las 7 sesiones independientes congeladas."""
    for i in range(1, 8):
        raw_p = SESSIONS_DIR / f"v3_val_session_{i:02d}_btc_usd_l2.parquet"
        res_p = SESSIONS_DIR / f"v3_val_session_{i:02d}_btc_usd_l2_1s.parquet"
        man_p = raw_p.with_suffix(".parquet.manifest.json")
        
        assert raw_p.exists(), f"Archivo raw {raw_p} no existe"
        assert res_p.exists(), f"Archivo 1s {res_p} no existe"
        assert man_p.exists(), f"Manifiesto {man_p} no existe"

        man = json.loads(man_p.read_text(encoding="utf-8"))
        assert man["final_book_status"] == "VALID", f"Sesión {i} no tiene final_book_status VALID"
        assert man["adapter_counters"]["checksum_failures"] == 0, f"Sesión {i} tiene checksum failures"

        raw_sha = hashlib.sha256(raw_p.read_bytes()).hexdigest()
        assert raw_sha.lower() == man["output_sha256"].lower(), f"Hash raw de sesión {i} no coincide con manifiesto"

        df_1s = pd.read_parquet(res_p)
        assert df_1s["timestamp"].is_monotonic_increasing, f"Sesión {i} tiene timestamps no monótonos"
        assert not df_1s["timestamp"].duplicated().any(), f"Sesión {i} tiene timestamps duplicados"
        assert (df_1s["staleness_ms"] >= 0).all(), f"Sesión {i} contiene staleness negativo"

