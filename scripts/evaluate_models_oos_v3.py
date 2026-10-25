"""NAVIER V3 — modelos y compatibilidad del evaluador.

The original evaluation implementation is retained below as
`evaluate_dataset_v3_legacy` for historical reproducibility. The exported
`evaluate_dataset_v3` is rebound at the end of this module to the timestamp-
purged post-hoc diagnostic implementation. Because the validation dataset was
already inspected, that implementation labels its results non-confirmatory.

Implementa la arquitectura formal V3:
1. Modelos:
   - Model_B: BASIC_MODEL + TRADITIONAL_ONLY
   - Model_B_plus: Model_B + LAGS
   - Model_B_plusplus: Model_B_plus + [_ofi_x_imb, _ofi_div_depth10] (convencional)
   - Model_B_tripleplus: Model_B_plusplus + [v03_pnpc_k3] (control razón presión/profundidad)
   - Model_E: Model_B_tripleplus + [v03_liq_conc_ask, v03_liq_conc_bid, v03_impact_conc_k3] (hipótesis geométrica)
   - Model_E_H1a: Model_E + [v03_depth_replenish_ask, v03_depth_replenish_bid] (exploratorio dinámica)

2. Muestra Común Rigurosa:
   - Todos los modelos confirmatorios (B, B+, B++, B+++, E) se ajustan y evalúan
     sobre exactamente las mismas filas válidas (intersección común).
   - E_H1a se evalúa en C5 sobre su submuestra limpia recalculando E en la misma.

3. Walk-Forward Estricto:
   - 5 folds expansivos (4 splits de test).
   - Purga = 10s al final de train.
   - Embargo = 10s antes de test.
   - Normalización z-score estrictamente causal (ajustada SOLO en train).
   - Holdout final (20% cronológico) preservado intacto.

4. Pruebas Estadísticas Preespecificadas:
   - C1 (E vs B+++): Contraste confirmatorio principal.
   - C2 (E vs B++), C3 (E vs B+), C4 (E vs B): Confirmatorios secundarios.
   - C5 (E_H1a vs E): Exploratorio.
   - Diebold-Mariano HAC Newey-West con lags primarios L=20, sensibilidad en L=10 y L=40.
   - Control FDR Benjamini-Hochberg al 5% sobre C1..C4.
   - Stationary Block Bootstrap (Politis & Romano 1994, p_geo=1/15, B=1000).
   - Matriz de decisión MECE sin contradicciones y con umbral de futilidad delta_min = 0.0010.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from navier_lab.analysis import nw_lrv, bh_adjust
from navier_lab.features import (
    BASIC_MODEL,
    TRADITIONAL_ONLY,
    LAGS,
    NAVIER_V3_CORE,
    NAVIER_V3_REPLENISH,
    TARGET,
)

# Definiciones canónicas de features
INTERACTIONS_BPLUSPLUS = ["_ofi_x_imb", "_ofi_div_depth10"]
CONTROL_RATIO = ["v03_pnpc_k3"]
GEOMETRY_V3 = ["v03_liq_conc_ask", "v03_liq_conc_bid", "v03_impact_conc_k3"]

MODEL_SPECS_V3 = {
    "Model_B": BASIC_MODEL + TRADITIONAL_ONLY,
    "Model_B_plus": BASIC_MODEL + TRADITIONAL_ONLY + LAGS,
    "Model_B_plusplus": BASIC_MODEL + TRADITIONAL_ONLY + LAGS + INTERACTIONS_BPLUSPLUS,
    "Model_B_tripleplus": BASIC_MODEL + TRADITIONAL_ONLY + LAGS + INTERACTIONS_BPLUSPLUS + CONTROL_RATIO,
    "Model_E": BASIC_MODEL + TRADITIONAL_ONLY + LAGS + INTERACTIONS_BPLUSPLUS + CONTROL_RATIO + GEOMETRY_V3,
}

CONFIRMATORY_PAIRS = [
    ("Model_E", "Model_B_tripleplus"),  # C1 — Contraste primario decisivo
    ("Model_E", "Model_B_plusplus"),    # C2 — vs interacción convencional
    ("Model_E", "Model_B_plus"),        # C3 — vs temporal
    ("Model_E", "Model_B"),             # C4 — vs baseline mínimo
]

FUTILITY_DELTA_MIN = 0.0010  # 0.10% de ganancia de R2 OOS

VERDICT_EXITO = "ÉXITO (EVIDENCIA ROBUSTA DE SEÑAL GEOMÉTRICA INCREMENTAL)"
VERDICT_FRACASO = "FRACASO (HIPÓTESIS RECHAZADA — ABSORBIDA POR B+++)"
VERDICT_FUTILIDAD = "FUTILIDAD (MEJORA INFERIOR AL UMBRAL MÍNIMO DE RELEVANCIA — LÍNEA CERRADA)"
VERDICT_DISCREPANCIA = "DISCREPANCIA HOLDOUT (ÉXITO EN WF PERO DETERIORO EN HOLDOUT — NO SE ACEPTA H1)"
VERDICT_INCONCLUSO = "INCONCLUSO (EVIDENCIA DÉBIL O POTENCIA INSUFICIENTE TRAS FDR)"


def classify_v3_verdict(
    delta_r2_wf: float,
    p_fdr_wf: float,
    folds_positive_count: int,
    delta_r2_ho: float,
    p_ho: float,
    delta_min: float = FUTILITY_DELTA_MIN,
) -> str:
    """Clasificación determinista y MECE de la matriz de decisión V3 sobre C1 (E vs B+++).

    Jerarquía determinista y condiciones mutuamente excluyentes:
    1. ÉXITO:
       - WF: delta_r2_wf >= delta_min, p_fdr_wf < 0.05, folds_positive_count >= 3 (>= 75%).
       - HO: delta_r2_ho > 0, p_ho < 0.05.
    2. DISCREPANCIA HOLDOUT:
       - WF: delta_r2_wf >= delta_min, p_fdr_wf < 0.05, folds_positive_count >= 3.
       - HO: delta_r2_ho <= 0 O p_ho >= 0.05.
    3. FRACASO (Falsación):
       - delta_r2_wf <= 0 O folds_positive_count < 2 (< 50%).
       - Prelación determinista: la falta de consistencia o la ausencia de ganancia positiva
         falsifica la hipótesis con prioridad absoluta sobre futilidad o inconclusión.
    4. FUTILIDAD:
       - 0 < delta_r2_wf < delta_min Y folds_positive_count >= 2.
    5. INCONCLUSO:
       - delta_r2_wf >= delta_min Y folds_positive_count >= 2, pero sin significancia
         suficiente (p_fdr_wf >= 0.05) O con consistencia frontera (folds_positive_count == 2).
    """
    wf_success = (delta_r2_wf >= delta_min) and (p_fdr_wf < 0.05) and (folds_positive_count >= 3)
    ho_success = (delta_r2_ho > 0.0) and (p_ho < 0.05)

    if wf_success and ho_success:
        return VERDICT_EXITO
    if wf_success and not ho_success:
        return VERDICT_DISCREPANCIA
    if (delta_r2_wf <= 0.0) or (folds_positive_count < 2):
        return VERDICT_FRACASO
    if (0.0 < delta_r2_wf < delta_min) and (folds_positive_count >= 2):
        return VERDICT_FUTILIDAD
    return VERDICT_INCONCLUSO


def prepare_feature_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula interacciones de B++ de forma causal y determinista."""
    work = df.copy()
    eps = 1e-6
    # 1. ofi_5 * imb_full
    work["_ofi_x_imb"] = work["ofi_5"] * work["imb_full"]
    # 2. Razón convencional de penetración sobre los 10 niveles (dimensionalmente coherente):
    # ofi_raw_5 en BTC dividido por profundidad total en BTC (exp(depth_log) = vb + va).
    # Unidades: BTC / BTC = 1 (estrictamente adimensional).
    total_depth_btc = np.exp(work["depth_log"].to_numpy(float))
    if "ofi_raw_5" in work.columns:
        ofi_raw = work["ofi_raw_5"].to_numpy(float)
    elif "v03_ofi_raw_5" in work.columns:
        ofi_raw = work["v03_ofi_raw_5"].to_numpy(float)
    else:
        ofi_raw = work["ofi_5"].to_numpy(float)
    work["_ofi_div_depth10"] = ofi_raw / (total_depth_btc + eps)
    return work


def make_walk_forward_splits(n: int, k_folds: int = 5, purge: int = 10, embargo: int = 10) -> list[tuple[np.ndarray, np.ndarray]]:
    """Walk-forward expansivo con purga y embargo estricto."""
    edges = np.linspace(0, n, k_folds + 1).astype(int)
    splits = []
    for i in range(1, k_folds):
        train_end_raw = edges[i]
        train_end_purged = max(0, train_end_raw - purge)
        train_idx = np.arange(0, train_end_purged)

        test_start = min(n, train_end_raw + embargo)
        test_end = edges[i + 1]
        if test_start < test_end:
            test_idx = np.arange(test_start, test_end)
            splits.append((train_idx, test_idx))
    return splits


def fit_and_predict_wf(X: np.ndarray, y: np.ndarray, splits: list[tuple[np.ndarray, np.ndarray]], clip_sd: float = 5.0) -> np.ndarray:
    """Ajuste OLS con normalización estrictamente causal estimada exclusivamente sobre train."""
    pred = np.full(len(y), np.nan)
    for tr, te in splits:
        mu = X[tr].mean(axis=0)
        sd = X[tr].std(axis=0) + 1e-12

        Xtr = np.clip((X[tr] - mu) / sd, -clip_sd, clip_sd)
        Xte = np.clip((X[te] - mu) / sd, -clip_sd, clip_sd)

        A = np.c_[np.ones(len(Xtr)), Xtr]
        ridge_eye = 1e-6 * len(Xtr) * np.eye(A.shape[1])
        ridge_eye[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + ridge_eye, A.T @ y[tr])

        pred[te] = beta[0] + Xte @ beta[1:]
    return pred


def paired_oos_r2(y_true: np.ndarray, pred_base: np.ndarray, pred_alt: np.ndarray, test_mask: np.ndarray) -> tuple[float, float, float]:
    """Delta R2 OOS = 1 - MSE(alt) / MSE(base) calculado sobre el conjunto de test especificado."""
    y = y_true[test_mask]
    pb = pred_base[test_mask]
    pa = pred_alt[test_mask]

    mse_base = float(np.mean((y - pb) ** 2))
    mse_alt = float(np.mean((y - pa) ** 2))
    delta_r2_global = 1.0 - (mse_alt / max(1e-15, mse_base))

    return float(delta_r2_global), mse_base, mse_alt


def diebold_mariano_test(y_true: np.ndarray, pred_base: np.ndarray, pred_alt: np.ndarray, test_mask: np.ndarray, lags: int = 20) -> dict:
    """Test de Diebold-Mariano HAC Newey-West con ancho de banda preespecificado."""
    y = y_true[test_mask]
    e_base = y - pred_base[test_mask]
    e_alt = y - pred_alt[test_mask]
    d = e_base ** 2 - e_alt ** 2
    dm_mean = float(d.mean())

    lrv = nw_lrv(d - dm_mean, lags)
    se = np.sqrt(max(1e-15, lrv)) / len(d)
    t_stat = dm_mean / se
    p_val = float(2.0 * stats.norm.sf(abs(t_stat)))

    return {
        "mean_diff": dm_mean,
        "t_stat": float(t_stat),
        "p_value": p_val,
        "n_obs": len(d),
        "lags": lags,
    }


def stationary_block_bootstrap_ci(y_true: np.ndarray, pred_base: np.ndarray, pred_alt: np.ndarray,
                                   test_mask: np.ndarray, avg_block_len: int = 15, n_boot: int = 1000,
                                   ci_level: float = 0.95, seed: int = 42) -> tuple[float, float]:
    """Bootstrap de bloques geométricos (Politis & Romano 1994) para delta R2 OOS."""
    rng = np.random.default_rng(seed)
    y = y_true[test_mask]
    pb = pred_base[test_mask]
    pa = pred_alt[test_mask]
    n = len(y)
    p_geo = 1.0 / avg_block_len

    boot_deltas = []
    for _ in range(n_boot):
        indices = []
        cur_idx = rng.integers(0, n)
        while len(indices) < n:
            indices.append(cur_idx)
            if rng.random() < p_geo:
                cur_idx = rng.integers(0, n)
            else:
                cur_idx = (cur_idx + 1) % n
        idx = np.array(indices[:n])
        mse_b = np.mean((y[idx] - pb[idx]) ** 2)
        mse_a = np.mean((y[idx] - pa[idx]) ** 2)
        boot_deltas.append(1.0 - (mse_a / max(1e-12, mse_b)))

    alpha_boot = (1.0 - ci_level) / 2.0
    ci_lower = float(np.percentile(boot_deltas, 100 * alpha_boot))
    ci_upper = float(np.percentile(boot_deltas, 100 * (1 - alpha_boot)))
    return ci_lower, ci_upper


def evaluate_dataset_v3(df_raw_features: pd.DataFrame, holdout_ratio: float = 0.20,
                        k_folds: int = 5, purge: int = 10, embargo: int = 10,
                        seed: int = 42) -> dict:
    """Evaluación OOS completa con muestra común garantizada para B, B+, B++, B+++, E."""
    # Preparar interacciones causales
    df_full = prepare_feature_dataframe(df_raw_features)
    df_full = df_full.sort_values("timestamp").reset_index(drop=True)

    # 1. Regla de Muestra Común Confirmatoria:
    # Garantizar que todos los modelos confirmatorios tengan datos válidos
    confirmatory_features = MODEL_SPECS_V3["Model_E"]
    clean_mask = (
        df_full[TARGET].notna() &
        df_full[confirmatory_features].notna().all(axis=1)
    )
    df = df_full[clean_mask].copy().reset_index(drop=True)
    n_total = len(df)

    if n_total < 500:
        raise ValueError(f"Muestra insuficiente tras filtro común: n={n_total}")

    # 2. Separación de Hold-out final (último 20% cronológico)
    split_point = int(n_total * (1.0 - holdout_ratio))
    df_eval = df.iloc[:split_point].copy().reset_index(drop=True)
    df_holdout = df.iloc[split_point:].copy().reset_index(drop=True)

    y_eval = df_eval[TARGET].to_numpy(float)
    y_holdout = df_holdout[TARGET].to_numpy(float)

    n_eval = len(df_eval)
    splits = make_walk_forward_splits(n_eval, k_folds=k_folds, purge=purge, embargo=embargo)
    n_splits = len(splits)

    # 3. Predicciones Walk-Forward sobre df_eval (misma muestra para todos)
    eval_preds = {}
    for m_name, cols in MODEL_SPECS_V3.items():
        X = df_eval[cols].to_numpy(float)
        eval_preds[m_name] = fit_and_predict_wf(X, y_eval, splits)

    test_indices = np.concatenate([te for _, te in splits])
    test_mask = np.zeros(n_eval, dtype=bool)
    test_mask[test_indices] = True

    # 4. Métricas y comparaciones en Walk-Forward
    comparisons = {}
    p_values_to_adjust = []
    confirmatory_keys = []

    for alt, base in CONFIRMATORY_PAIRS:
        comp_key = f"{alt}_vs_{base}"
        delta_r2, mse_b, mse_a = paired_oos_r2(y_eval, eval_preds[base], eval_preds[alt], test_mask)

        # DM con lag principal L=20 (2H) y sensibilidad en L=10 y L=40
        dm_20 = diebold_mariano_test(y_eval, eval_preds[base], eval_preds[alt], test_mask, lags=20)
        dm_10 = diebold_mariano_test(y_eval, eval_preds[base], eval_preds[alt], test_mask, lags=10)
        dm_40 = diebold_mariano_test(y_eval, eval_preds[base], eval_preds[alt], test_mask, lags=40)

        ci_low, ci_high = stationary_block_bootstrap_ci(
            y_eval, eval_preds[base], eval_preds[alt], test_mask,
            avg_block_len=15, n_boot=1000, seed=seed
        )

        # Consistencia por fold
        fold_deltas = []
        for _, te in splits:
            f_mask = np.zeros(n_eval, dtype=bool)
            f_mask[te] = True
            f_delta, _, _ = paired_oos_r2(y_eval, eval_preds[base], eval_preds[alt], f_mask)
            fold_deltas.append(f_delta)

        folds_pos = int(np.sum(np.array(fold_deltas) > 0))
        folds_ratio = round(folds_pos / n_splits, 2)

        res_dict = {
            "alt_model": alt,
            "base_model": base,
            "delta_r2_oos": delta_r2,
            "ci_95": [ci_low, ci_high],
            "dm_t_stat": dm_20["t_stat"],
            "dm_p_value": dm_20["p_value"],
            "dm_sensitivity": {
                "lags_10": {"t_stat": dm_10["t_stat"], "p_value": dm_10["p_value"]},
                "lags_20": {"t_stat": dm_20["t_stat"], "p_value": dm_20["p_value"]},
                "lags_40": {"t_stat": dm_40["t_stat"], "p_value": dm_40["p_value"]},
            },
            "fold_deltas": fold_deltas,
            "folds_positive_count": folds_pos,
            "folds_total": n_splits,
            "folds_positive_ratio": folds_ratio,
            "n_eval_obs": int(test_mask.sum()),
        }
        comparisons[comp_key] = res_dict
        p_values_to_adjust.append(dm_20["p_value"])
        confirmatory_keys.append(comp_key)

    # 5. Ajuste Benjamini-Hochberg (FDR) sobre las 4 comparaciones confirmatorias
    adjusted_p = bh_adjust(np.array(p_values_to_adjust))
    for i, key in enumerate(confirmatory_keys):
        comparisons[key]["dm_p_fdr_adjusted"] = float(adjusted_p[i])

    # 6. Evaluación en Hold-out final (modelo ajustado con el 100% de df_eval)
    holdout_preds = {}
    for m_name, cols in MODEL_SPECS_V3.items():
        X_tr = df_eval[cols].to_numpy(float)
        mu = X_tr.mean(axis=0)
        sd = X_tr.std(axis=0) + 1e-12
        X_tr_std = np.clip((X_tr - mu) / sd, -5.0, 5.0)

        A = np.c_[np.ones(len(X_tr_std)), X_tr_std]
        ridge_eye = 1e-6 * len(X_tr_std) * np.eye(A.shape[1])
        ridge_eye[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + ridge_eye, A.T @ y_eval)

        X_te = df_holdout[cols].to_numpy(float)
        X_te_std = np.clip((X_te - mu) / sd, -5.0, 5.0)
        holdout_preds[m_name] = beta[0] + X_te_std @ beta[1:]

    ho_mask = np.ones(len(y_holdout), dtype=bool)
    holdout_comparisons = {}
    for alt, base in CONFIRMATORY_PAIRS:
        comp_key = f"{alt}_vs_{base}"
        delta_r2_ho, _, _ = paired_oos_r2(y_holdout, holdout_preds[base], holdout_preds[alt], ho_mask)
        dm_ho = diebold_mariano_test(y_holdout, holdout_preds[base], holdout_preds[alt], ho_mask, lags=20)
        holdout_comparisons[comp_key] = {
            "delta_r2_oos_holdout": delta_r2_ho,
            "dm_t_stat": dm_ho["t_stat"],
            "dm_p_value": dm_ho["p_value"],
            "n_holdout_obs": len(y_holdout),
        }

    # 7. Evaluación Exploratoria C5: Model_E_H1a vs Model_E
    # Se evalúa sobre la submuestra donde las features de reposición son no-nulas
    exploratory_cols = MODEL_SPECS_V3["Model_E"] + NAVIER_V3_REPLENISH
    clean_h1a = df_full[TARGET].notna() & df_full[exploratory_cols].notna().all(axis=1)
    df_h1a = df_full[clean_h1a].copy().reset_index(drop=True)
    split_h1a = int(len(df_h1a) * (1.0 - holdout_ratio))
    df_h1a_eval = df_h1a.iloc[:split_h1a].copy().reset_index(drop=True)
    y_h1a_eval = df_h1a_eval[TARGET].to_numpy(float)
    splits_h1a = make_walk_forward_splits(len(df_h1a_eval), k_folds=k_folds, purge=purge, embargo=embargo)

    p_e_h1a = fit_and_predict_wf(df_h1a_eval[exploratory_cols].to_numpy(float), y_h1a_eval, splits_h1a)
    p_e_base = fit_and_predict_wf(df_h1a_eval[MODEL_SPECS_V3["Model_E"]].to_numpy(float), y_h1a_eval, splits_h1a)
    te_h1a_idx = np.concatenate([te for _, te in splits_h1a])
    mask_h1a = np.zeros(len(df_h1a_eval), dtype=bool)
    mask_h1a[te_h1a_idx] = True

    delta_h1a, _, _ = paired_oos_r2(y_h1a_eval, p_e_base, p_e_h1a, mask_h1a)
    dm_h1a = diebold_mariano_test(y_h1a_eval, p_e_base, p_e_h1a, mask_h1a, lags=20)
    c5_exploratory = {
        "alt_model": "Model_E_H1a",
        "base_model": "Model_E",
        "delta_r2_oos": delta_h1a,
        "dm_t_stat": dm_h1a["t_stat"],
        "dm_p_value": dm_h1a["p_value"],
        "n_obs": int(mask_h1a.sum()),
        "status": "EXPLORATORIO_POST_HOC",
    }

    # 8. Matriz de Decisión Formal Preespecificada sobre C1 (E vs B+++)
    c1_wf = comparisons["Model_E_vs_Model_B_tripleplus"]
    c1_ho = holdout_comparisons["Model_E_vs_Model_B_tripleplus"]

    verdict = classify_v3_verdict(
        delta_r2_wf=c1_wf["delta_r2_oos"],
        p_fdr_wf=c1_wf["dm_p_fdr_adjusted"],
        folds_positive_count=c1_wf["folds_positive_count"],
        delta_r2_ho=c1_ho["delta_r2_oos_holdout"],
        p_ho=c1_ho["dm_p_value"],
        delta_min=FUTILITY_DELTA_MIN,
    )

    return {
        "timestamp_eval": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "sample_sizes": {
            "total_clean_sample": n_total,
            "eval_sample": n_eval,
            "holdout_sample": len(df_holdout),
            "walk_forward_test_obs": int(test_mask.sum()),
        },
        "walk_forward_comparisons": comparisons,
        "holdout_comparisons": holdout_comparisons,
        "exploratory_c5": c5_exploratory,
        "verdict": verdict,
        "criteria_breakdown": {
            "delta_r2_wf": c1_wf["delta_r2_oos"],
            "delta_min_threshold": FUTILITY_DELTA_MIN,
            "p_fdr_c1": c1_wf["dm_p_fdr_adjusted"],
            "folds_positive": f"{c1_wf['folds_positive_count']}/{c1_wf['folds_total']}",
            "delta_r2_holdout": c1_ho["delta_r2_oos_holdout"],
            "p_holdout_c1": c1_ho["dm_p_value"],
        },
    }


# Keep the frozen historical implementation available for provenance, while the
# public evaluator points to the corrected, timestamp-aware diagnostic path.
evaluate_dataset_v3_legacy = evaluate_dataset_v3
from scripts.evaluate_models_oos_v3_temporal import evaluate_dataset_v3 as evaluate_dataset_v3
