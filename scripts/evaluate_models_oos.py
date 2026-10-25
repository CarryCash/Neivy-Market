"""NAVIER V2 — Fase 5: Motor de Evaluación Predictiva Fuera de Muestra y Pruebas Estadísticas.

Implementa los requisitos preespecificados en el protocolo congelado:
1. Familias de modelos anidados:
   - Modelo A: spread_bps, depth_log, vol60_bps
   - Modelo B: Modelo A + imb_full, imb_top1, ofi_5, ret_1, ret_5, ret_30
   - Modelo B+: Modelo B + imb_full_lag2, imb_full_lag5, imb_full_lag8
   - Modelo C: Modelo B + Navier V0.1 (u, dI_dt, grad_bid, grad_ask, curv_bid, curv_ask, re_log)
   - Modelo D: Modelo B + Navier V0.2 (v02_l_vwap_bps, v02_grad_bid_norm, v02_grad_ask_norm, v02_re_log_reg)

2. Validación temporal Walk-Forward con Purga y Embargo:
   - Hold-out final intocable: último 20% cronológico preservado intacto.
   - Purgado: supresión de los últimos 10s de cada bloque de entrenamiento.
   - Embargo: 10s de separación entre entrenamiento y prueba.
   - Normalización z-score ajustada exclusivamente sobre train.

3. Pruebas estadísticas rigurosas:
   - Métrica primaria: Delta R2_OOS pareado frente a B y B+.
   - Test de Diebold-Mariano con varianza HAC Newey-West (lags = 20).
   - Ajuste Benjamini-Hochberg (FDR) al 5%.
   - Intervalos de confianza por bootstrap de bloques estacionarios.
   - Veredicto determinista preespecificado (Éxito, Fracaso, Inconcluso).
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
from navier_lab.features import BASIC_MODEL, TRADITIONAL_ONLY, LAGS, NAVIER, NAVIER_V02, TARGET


MODEL_SPECS = {
    "Model_A": BASIC_MODEL,
    "Model_B": BASIC_MODEL + TRADITIONAL_ONLY,
    "Model_B_plus": BASIC_MODEL + TRADITIONAL_ONLY + LAGS,
    "Model_C_Navier_V01": BASIC_MODEL + TRADITIONAL_ONLY + NAVIER,
    "Model_D_Navier_V02": BASIC_MODEL + TRADITIONAL_ONLY + NAVIER_V02,
}


def make_walk_forward_splits(n: int, k_folds: int = 5, purge: int = 10, embargo: int = 10) -> list[tuple[np.ndarray, np.ndarray]]:
    """Walk-forward expansivo con purga y embargo estricto."""
    edges = np.linspace(0, n, k_folds + 1).astype(int)
    splits = []
    for i in range(1, k_folds):
        train_end_raw = edges[i]
        # Purga: descartar las últimas 'purge' observaciones del entrenamiento
        train_end_purged = max(0, train_end_raw - purge)
        train_idx = np.arange(0, train_end_purged)

        # Embargo: iniciar el test set 'embargo' observaciones después del fin crudo del entrenamiento
        test_start = min(n, train_end_raw + embargo)
        test_end = edges[i + 1]
        if test_start < test_end:
            test_idx = np.arange(test_start, test_end)
            splits.append((train_idx, test_idx))
    return splits


def fit_and_predict_wf(X: np.ndarray, y: np.ndarray, splits: list[tuple[np.ndarray, np.ndarray]], clip_sd: float = 5.0) -> np.ndarray:
    """Ajuste OLS con normalización estrictamente causal estimada solo en train."""
    pred = np.full(len(y), np.nan)
    for tr, te in splits:
        mu = X[tr].mean(axis=0)
        sd = X[tr].std(axis=0) + 1e-12

        Xtr = np.clip((X[tr] - mu) / sd, -clip_sd, clip_sd)
        Xte = np.clip((X[te] - mu) / sd, -clip_sd, clip_sd)

        # OLS con regularización ridge infinitesimal para estabilidad numérica
        A = np.c_[np.ones(len(Xtr)), Xtr]
        ridge_eye = 1e-6 * len(Xtr) * np.eye(A.shape[1])
        ridge_eye[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + ridge_eye, A.T @ y[tr])

        pred[te] = beta[0] + Xte @ beta[1:]
    return pred


def paired_oos_r2(y_true: np.ndarray, pred_base: np.ndarray, pred_alt: np.ndarray, test_mask: np.ndarray) -> tuple[float, list[float]]:
    """Delta R2 OOS = 1 - MSE(alt) / MSE(base)."""
    y = y_true[test_mask]
    pb = pred_base[test_mask]
    pa = pred_alt[test_mask]

    mse_base = np.mean((y - pb) ** 2)
    mse_alt = np.mean((y - pa) ** 2)
    delta_r2_global = 1.0 - (mse_alt / mse_base)

    return float(delta_r2_global), float(mse_base), float(mse_alt)


def diebold_mariano_test(y_true: np.ndarray, pred_base: np.ndarray, pred_alt: np.ndarray, test_mask: np.ndarray, lags: int = 20) -> dict:
    """Test de Diebold-Mariano HAC Newey-West sobre pérdidas cuadráticas d_t = e_base^2 - e_alt^2."""
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
                                   test_mask: np.ndarray, avg_block_len: int = 15, n_boot: int = 500,
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


def evaluate_dataset(df: pd.DataFrame, holdout_ratio: float = 0.20, k_folds: int = 5, purge: int = 10, embargo: int = 10) -> dict:
    # Asegurar orden estrictamente cronológico
    df = df.sort_values("timestamp").reset_index(drop=True)
    n_total = len(df)
    
    # 1. Separación de Hold-out final intocable (último 20%)
    split_point = int(n_total * (1.0 - holdout_ratio))
    df_eval = df.iloc[:split_point].copy().reset_index(drop=True)
    df_holdout = df.iloc[split_point:].copy().reset_index(drop=True)

    y_eval = df_eval[TARGET].to_numpy(float)
    y_holdout = df_holdout[TARGET].to_numpy(float)

    n_eval = len(df_eval)
    splits = make_walk_forward_splits(n_eval, k_folds=k_folds, purge=purge, embargo=embargo)

    # 2. Predicciones Walk-Forward sobre df_eval
    eval_preds = {}
    for m_name, cols in MODEL_SPECS.items():
        X = df_eval[cols].to_numpy(float)
        eval_preds[m_name] = fit_and_predict_wf(X, y_eval, splits)

    test_indices = np.concatenate([te for _, te in splits])
    test_mask = np.zeros(n_eval, dtype=bool)
    test_mask[test_indices] = True

    # 3. Métricas y comparaciones en la fase de evaluación (Walk-forward)
    comparisons = {}
    pairs = [
        ("Model_C_Navier_V01", "Model_B"),
        ("Model_C_Navier_V01", "Model_B_plus"),
        ("Model_D_Navier_V02", "Model_B"),
        ("Model_D_Navier_V02", "Model_B_plus"),
        ("Model_B_plus", "Model_B"),
    ]

    p_values_to_adjust = []
    pair_results = []

    for alt, base in pairs:
        delta_r2, mse_b, mse_a = paired_oos_r2(y_eval, eval_preds[base], eval_preds[alt], test_mask)
        dm = diebold_mariano_test(y_eval, eval_preds[base], eval_preds[alt], test_mask, lags=2 * purge)
        ci_low, ci_high = stationary_block_bootstrap_ci(y_eval, eval_preds[base], eval_preds[alt], test_mask)

        # Consistencia entre folds
        fold_deltas = []
        for _, te in splits:
            f_mask = np.zeros(n_eval, dtype=bool)
            f_mask[te] = True
            f_delta, _, _ = paired_oos_r2(y_eval, eval_preds[base], eval_preds[alt], f_mask)
            fold_deltas.append(f_delta)

        folds_positive = int(np.sum(np.array(fold_deltas) > 0))
        folds_ratio = round(folds_positive / len(splits), 2)

        res_dict = {
            "alt_model": alt,
            "base_model": base,
            "delta_r2_oos": delta_r2,
            "ci_95": [ci_low, ci_high],
            "dm_t_stat": dm["t_stat"],
            "dm_p_value": dm["p_value"],
            "fold_deltas": fold_deltas,
            "folds_positive_ratio": folds_ratio,
            "n_eval_obs": int(test_mask.sum()),
        }
        comparisons[f"{alt}_vs_{base}"] = res_dict
        p_values_to_adjust.append(dm["p_value"])
        pair_results.append(res_dict)

    # 4. Ajuste Benjamini-Hochberg FDR al 5%
    adjusted_p = bh_adjust(np.array(p_values_to_adjust))
    for i, (alt, base) in enumerate(pairs):
        comparisons[f"{alt}_vs_{base}"]["dm_p_fdr_adjusted"] = float(adjusted_p[i])

    # 5. Evaluación en Hold-out final (modelo reajustado con el 100% de df_eval)
    holdout_results = {}
    mu_eval = {}
    sd_eval = {}
    fitted_models = {}

    for m_name, cols in MODEL_SPECS.items():
        X_tr = df_eval[cols].to_numpy(float)
        mu = X_tr.mean(axis=0)
        sd = X_tr.std(axis=0) + 1e-12
        mu_eval[m_name], sd_eval[m_name] = mu, sd
        X_tr_std = np.clip((X_tr - mu) / sd, -5.0, 5.0)

        A = np.c_[np.ones(len(X_tr_std)), X_tr_std]
        ridge_eye = 1e-6 * len(X_tr_std) * np.eye(A.shape[1])
        ridge_eye[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + ridge_eye, A.T @ y_eval)
        fitted_models[m_name] = beta

        # Predicción sobre Hold-out
        X_te = df_holdout[cols].to_numpy(float)
        X_te_std = np.clip((X_te - mu) / sd, -5.0, 5.0)
        pred_ho = beta[0] + X_te_std @ beta[1:]
        holdout_results[f"pred_{m_name}"] = pred_ho

    # Comparaciones en Hold-out
    ho_mask = np.ones(len(y_holdout), dtype=bool)
    ho_comparisons = {}
    for alt, base in pairs:
        delta_r2_ho, _, _ = paired_oos_r2(y_holdout, holdout_results[f"pred_{base}"], holdout_results[f"pred_{alt}"], ho_mask)
        dm_ho = diebold_mariano_test(y_holdout, holdout_results[f"pred_{base}"], holdout_results[f"pred_{alt}"], ho_mask, lags=2 * purge)
        ho_comparisons[f"{alt}_vs_{base}"] = {
            "delta_r2_oos_holdout": delta_r2_ho,
            "dm_t_stat": dm_ho["t_stat"],
            "dm_p_value": dm_ho["p_value"],
            "n_holdout_obs": len(y_holdout),
        }

    # 6. Veredicto del Protocolo Congelado (Punto 12)
    # Éxito: Delta R2_OOS > 0 y p_fdr < 0.05 frente a B y B+, persistente en >= 70% de folds y en hold-out final.
    c_vs_b = comparisons["Model_C_Navier_V01_vs_Model_B"]
    c_vs_bplus = comparisons["Model_C_Navier_V01_vs_Model_B_plus"]
    c_vs_b_ho = ho_comparisons["Model_C_Navier_V01_vs_Model_B"]
    c_vs_bplus_ho = ho_comparisons["Model_C_Navier_V01_vs_Model_B_plus"]

    cond_positive_eval = (c_vs_b["delta_r2_oos"] > 0) and (c_vs_bplus["delta_r2_oos"] > 0)
    cond_sig_eval = (c_vs_b["dm_p_fdr_adjusted"] < 0.05) and (c_vs_bplus["dm_p_fdr_adjusted"] < 0.05)
    cond_folds = (c_vs_b["folds_positive_ratio"] >= 0.70) and (c_vs_bplus["folds_positive_ratio"] >= 0.70)
    cond_positive_ho = (c_vs_b_ho["delta_r2_oos_holdout"] > 0) and (c_vs_bplus_ho["delta_r2_oos_holdout"] > 0)
    cond_sig_ho = (c_vs_b_ho["dm_p_value"] < 0.05) and (c_vs_bplus_ho["dm_p_value"] < 0.05)

    if cond_positive_eval and cond_sig_eval and cond_folds and cond_positive_ho and cond_sig_ho:
        verdict_str = "ÉXITO (EVIDENCIA ROBUSTA DE SEÑAL INCREMENTAL)"
    elif (c_vs_b["delta_r2_oos"] <= 0) or (c_vs_b["dm_p_fdr_adjusted"] >= 0.05) or (c_vs_bplus["delta_r2_oos"] <= 0):
        verdict_str = "FRACASO (HIPÓTESIS RECHAZADA O ABSORBIDA POR MODELO BASE B/B+)"
    else:
        verdict_str = "INCONCLUSO (EVIDENCIA DÉBIL O INESTABLE ENTRE PARTICIONES/HOLD-OUT)"

    return {
        "timestamp_eval": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "sample_sizes": {
            "total_sample": n_total,
            "eval_sample": n_eval,
            "holdout_sample": len(df_holdout),
            "walk_forward_test_obs": int(test_mask.sum()),
        },
        "walk_forward_comparisons": comparisons,
        "holdout_comparisons": ho_comparisons,
        "verdict": {
            "result": verdict_str,
            "criteria_status": {
                "positive_delta_r2_eval": bool(cond_positive_eval),
                "dm_sig_fdr_eval": bool(cond_sig_eval),
                "folds_consistency_ge_70pct": bool(cond_folds),
                "positive_delta_r2_holdout": bool(cond_positive_ho),
                "dm_sig_holdout": bool(cond_sig_ho),
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/research_dataset_v2.parquet", help="Dataset Parquet con features")
    parser.add_argument("--output-json", default="results/oos_model_evaluation.json", help="Salida JSON")
    args = parser.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        raise FileNotFoundError(f"Dataset de features no encontrado: {in_path}")

    print(f"Cargando dataset de investigación desde {in_path}...")
    df = pd.read_parquet(in_path)
    
    # Filtrar solo observaciones completas
    core_cols = BASIC_MODEL + TRADITIONAL_ONLY + LAGS + NAVIER + NAVIER_V02 + [TARGET]
    df_clean = df.dropna(subset=core_cols).copy()
    print(f"Observaciones totales: {len(df)} | Limpias completas: {len(df_clean)}")

    res = evaluate_dataset(df_clean)
    out_path = Path(args.output_json).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("VEREDICTO FINAL NAVIER V2 (FASE 5):")
    print(f"  Resultado: {res['verdict']['result']}")
    print("=" * 60)
    print(f"Resultados completos guardados en {out_path}")


if __name__ == "__main__":
    main()
