"""NAVIER V3 — Script de Diagnóstico Post-Fase 5 (Solo Lectura).

Ejecuta las comprobaciones cuantitativas de las Investigaciones 1, 2, 3 y 4:
1. Verificación de fórmulas, signos, purga/embargo, FDR y correspondencia de métricas.
2. Diagnóstico del target: distribución de y_bps vs y vs vol60_bps, suelo de volatilidad,
   concentración de MSE en |y| > 10, y desglose del holdout (|y| <= 10 vs |y| > 10).
3. Diagnóstico algebraico de las variables geométricas: correlaciones, descomposición
   y redundancia frente a OFI, imbalance y profundidad.
4. Auditoría de costes y métricas económicas.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy import stats

# Configurar path
PROJECT_ROOT = Path("C:/Users/USER/Downloads/navier_lab_project/navier_lab_project")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from navier_lab.analysis import nw_lrv, bh_adjust
from navier_lab.features import TARGET, TARGET_BPS
from scripts.evaluate_models_oos_v3 import (
    MODEL_SPECS_V3,
    CONFIRMATORY_PAIRS,
    prepare_feature_dataframe,
    make_walk_forward_splits,
    fit_and_predict_wf,
    paired_oos_r2,
    diebold_mariano_test,
)


def run_diagnostics():
    print("=" * 80)
    print("NAVIER V3 — DIAGNÓSTICO CUANTITATIVO POST-FASE 5")
    print("=" * 80)

    # Cargar dataset Parquet
    parquet_path = PROJECT_ROOT / "data" / "research_dataset_v3.parquet"
    print(f"Cargando dataset desde {parquet_path}...")
    df_raw = pd.read_parquet(parquet_path)
    df_full = prepare_feature_dataframe(df_raw)
    df_full = df_full.sort_values("timestamp").reset_index(drop=True)

    # Filtrar muestra común confirmatoria
    confirmatory_features = MODEL_SPECS_V3["Model_E"]
    clean_mask = df_full[TARGET].notna() & df_full[confirmatory_features].notna().all(axis=1)
    df = df_full[clean_mask].copy().reset_index(drop=True)
    n_total = len(df)
    print(f"Filas totales limpias en muestra común: {n_total}")

    # Separación eval / holdout (80% / 20%)
    split_point = int(n_total * 0.80)
    df_eval = df.iloc[:split_point].copy().reset_index(drop=True)
    df_holdout = df.iloc[split_point:].copy().reset_index(drop=True)
    y_eval = df_eval[TARGET].to_numpy(float)
    y_holdout = df_holdout[TARGET].to_numpy(float)

    # =========================================================================
    # INVESTIGACIÓN 1: Integridad estadística y fórmulas
    # =========================================================================
    print("\n" + "-" * 60)
    print("INVESTIGACIÓN 1: INTEGRIDAD ESTADÍSTICA Y FÓRMULAS")
    print("-" * 60)

    # 1.1 Verificar purga y embargo en los cortes
    splits = make_walk_forward_splits(len(df_eval), k_folds=5, purge=10, embargo=10)
    print(f"Splits Walk-Forward generados: {len(splits)}")
    overlap_detected = False
    for i, (tr, te) in enumerate(splits, 1):
        tr_max = tr.max()
        te_min = te.min()
        gap_sec = te_min - tr_max
        # Dado que el target proyecta 10 segundos hacia adelante, la observación tr_max
        # mira hasta tr_max + 10. Por tanto, te_min debe ser >= tr_max + 10 + embargo.
        # En make_walk_forward_splits:
        # train_end_raw = edges[i]
        # train_end_purged = edges[i] - 10 => tr_max = edges[i] - 11
        # test_start = edges[i] + 10 => te_min = edges[i] + 10
        # te_min - tr_max = 21 observaciones.
        # Dado H = 10, tr_max + 10 = edges[i] - 1 < te_min = edges[i] + 10.
        target_horizon_tr_max = tr_max + 10
        has_overlap = target_horizon_tr_max >= te_min
        print(f"  Split {i}: Train max={tr_max} (Target mira hasta {target_horizon_tr_max}) | Test min={te_min} | Gap={te_min - target_horizon_tr_max}s | Contaminación: {has_overlap}")
        if has_overlap:
            overlap_detected = True
    print(f"Resultado de verificación de purga/embargo: {'ERROR CONTAMINACIÓN' if overlap_detected else 'PASS (CERO CONTAMINACIÓN TEMPORAL)'}")

    # 1.2 Cargar resultados de Fase 5 y comprobar ajuste FDR
    res_path = PROJECT_ROOT / "results" / "phase5_v3" / "oos_evaluation_results.json"
    with open(res_path, "r", encoding="utf-8") as f:
        res_phase5 = json.load(f)

    wf_comps = res_phase5["walk_forward_comparisons"]
    p_vals = [wf_comps[f"{alt}_vs_{base}"]["dm_p_value"] for alt, base in CONFIRMATORY_PAIRS]
    p_fdr_reported = [wf_comps[f"{alt}_vs_{base}"]["dm_p_fdr_adjusted"] for alt, base in CONFIRMATORY_PAIRS]
    p_fdr_calc = bh_adjust(np.array(p_vals)).tolist()
    print("\nVerificación de ajuste Benjamini-Hochberg (FDR):")
    for (alt, base), pv, rep, calc in zip(CONFIRMATORY_PAIRS, p_vals, p_fdr_reported, p_fdr_calc):
        match = abs(rep - calc) < 1e-9
        print(f"  {alt} vs {base}: p_nominal={pv:.4f} | p_FDR_rep={rep:.4f} | p_FDR_calc={calc:.4f} | Match: {match}")

    # =========================================================================
    # INVESTIGACIÓN 2: Diagnóstico del target y episodios extremos
    # =========================================================================
    print("\n" + "-" * 60)
    print("INVESTIGACIÓN 2: DIAGNÓSTICO DEL TARGET Y EPISODIOS EXTREMOS")
    print("-" * 60)

    # 2.1 Distribución de y_bps vs y vs vol60_bps por sesión
    session_stats = []
    for s_name, s_df in df.groupby("session_id", sort=False):
        y_bps_s = s_df[TARGET_BPS].to_numpy()
        y_s = s_df[TARGET].to_numpy()
        vol60_s = s_df["vol60_bps"].to_numpy()
        n_s = len(s_df)
        near_floor_015 = (vol60_s < 0.015).sum()
        near_floor_020 = (vol60_s < 0.020).sum()
        extreme_y = (np.abs(y_s) > 10.0).sum()
        session_stats.append({
            "session": s_name,
            "n_obs": n_s,
            "y_bps_mean": float(np.mean(y_bps_s)),
            "y_bps_std": float(np.std(y_bps_s)),
            "y_bps_min": float(np.min(y_bps_s)),
            "y_bps_max": float(np.max(y_bps_s)),
            "y_mean": float(np.mean(y_s)),
            "y_std": float(np.std(y_s)),
            "y_kurtosis": float(stats.kurtosis(y_s)),
            "y_min": float(np.min(y_s)),
            "y_max": float(np.max(y_s)),
            "vol60_mean": float(np.mean(vol60_s)),
            "vol60_min": float(np.min(vol60_s)),
            "near_floor_015": int(near_floor_015),
            "near_floor_015_pct": float(near_floor_015 / n_s * 100),
            "near_floor_020": int(near_floor_020),
            "extreme_y_gt10": int(extreme_y),
        })
    df_sess_stats = pd.DataFrame(session_stats)
    print("Estadísticas por sesión:")
    print(df_sess_stats[["session", "n_obs", "y_bps_min", "y_bps_max", "y_min", "y_max", "y_kurtosis", "vol60_min", "near_floor_015_pct", "extreme_y_gt10"]].to_string())

    # 2.2 Descomposición de las 45 observaciones con |y| > 10
    mask_ext = np.abs(df[TARGET].to_numpy()) > 10.0
    print(f"\nObservaciones con |y| > 10: {mask_ext.sum()} de {len(df)} ({mask_ext.mean()*100:.2f}%)")
    df_ext = df[mask_ext].copy()
    print("Resumen de las 45 observaciones extremas:")
    print(f"  Rango de retorno bruto (y_bps): [{df_ext[TARGET_BPS].min():.4f}, {df_ext[TARGET_BPS].max():.4f}] bps")
    print(f"  Media abs retorno bruto (y_bps): {df_ext[TARGET_BPS].abs().mean():.4f} bps")
    print(f"  Rango de vol60_bps:              [{df_ext['vol60_bps'].min():.6f}, {df_ext['vol60_bps'].max():.6f}] bps")
    print(f"  Media de vol60_bps:              {df_ext['vol60_bps'].mean():.6f} bps")
    print(f"  Rango de denominador (vol*sqrt10): [{ (df_ext['vol60_bps']*np.sqrt(10)).min():.6f}, { (df_ext['vol60_bps']*np.sqrt(10)).max():.6f}] bps")
    print(f"  Rango de y normalizado:          [{df_ext[TARGET].min():.2f}, {df_ext[TARGET].max():.2f}]")

    # Comparar con observaciones NO extremas:
    df_norm = df[~mask_ext]
    print("Comparación con observaciones normales (|y| <= 10):")
    print(f"  Media abs retorno bruto: {df_norm[TARGET_BPS].abs().mean():.4f} bps (vs {df_ext[TARGET_BPS].abs().mean():.4f} bps en extremos)")
    print(f"  Media de vol60_bps:      {df_norm['vol60_bps'].mean():.4f} bps (vs {df_ext['vol60_bps'].mean():.4f} bps en extremos)")
    print(f"  Ratio de vol60:          {df_norm['vol60_bps'].mean() / df_ext['vol60_bps'].mean():.2f}x menor volatilidad en extremos!")

    # 2.3 Desglose del error en Holdout (20% cronológico)
    # Re-obtener predicciones de holdout para B+++ y E exactamente como en evaluate_dataset_v3
    cols_b3 = MODEL_SPECS_V3["Model_B_tripleplus"]
    cols_e = MODEL_SPECS_V3["Model_E"]

    X_eval_b3 = df_eval[cols_b3].to_numpy(float)
    X_eval_e = df_eval[cols_e].to_numpy(float)
    X_ho_b3 = df_holdout[cols_b3].to_numpy(float)
    X_ho_e = df_holdout[cols_e].to_numpy(float)

    # Ajuste causal estandarizado
    def fit_and_predict_holdout(X_tr, y_tr, X_te):
        mu = X_tr.mean(axis=0)
        sd = X_tr.std(axis=0) + 1e-12
        Xtr_std = np.clip((X_tr - mu) / sd, -5.0, 5.0)
        Xte_std = np.clip((X_te - mu) / sd, -5.0, 5.0)
        A = np.c_[np.ones(len(Xtr_std)), Xtr_std]
        ridge_eye = 1e-6 * len(Xtr_std) * np.eye(A.shape[1])
        ridge_eye[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + ridge_eye, A.T @ y_tr)
        return beta[0] + Xte_std @ beta[1:]

    pred_ho_b3 = fit_and_predict_holdout(X_eval_b3, y_eval, X_ho_b3)
    pred_ho_e = fit_and_predict_holdout(X_eval_e, y_eval, X_ho_e)

    ho_mask_ext = np.abs(y_holdout) > 10.0
    ho_mask_norm = ~ho_mask_ext

    print(f"\nHoldout total: {len(y_holdout)} obs | Extremos (|y|>10): {ho_mask_ext.sum()} obs ({ho_mask_ext.mean()*100:.2f}%)")

    # Error global en Holdout
    e_b3_all = y_holdout - pred_ho_b3
    e_e_all = y_holdout - pred_ho_e
    mse_b3_all = np.mean(e_b3_all ** 2)
    mse_e_all = np.mean(e_e_all ** 2)
    delta_r2_all = 1.0 - (mse_e_all / mse_b3_all)

    # Error en subconjunto NORMAL (|y| <= 10)
    e_b3_norm = e_b3_all[ho_mask_norm]
    e_e_norm = e_e_all[ho_mask_norm]
    mse_b3_norm = np.mean(e_b3_norm ** 2)
    mse_e_norm = np.mean(e_e_norm ** 2)
    delta_r2_norm = 1.0 - (mse_e_norm / mse_b3_norm)

    # Error en subconjunto EXTREMO (|y| > 10)
    e_b3_ext = e_b3_all[ho_mask_ext]
    e_e_ext = e_e_all[ho_mask_ext]
    mse_b3_ext = np.mean(e_b3_ext ** 2)
    mse_e_ext = np.mean(e_e_ext ** 2)
    delta_r2_ext = 1.0 - (mse_e_ext / mse_b3_ext)

    # Concentración de la suma de errores al cuadrado (SSE)
    sse_b3_total = np.sum(e_b3_all ** 2)
    sse_b3_ext = np.sum(e_b3_ext ** 2)
    sse_e_total = np.sum(e_e_all ** 2)
    sse_e_ext = np.sum(e_e_ext ** 2)

    print("Desglose del comportamiento del Holdout:")
    print(f"  Holdout Global (100%):")
    print(f"    MSE(B+++) = {mse_b3_all:.6f} | MSE(E) = {mse_e_all:.6f} | Delta R2 = {delta_r2_all*100:+.4f}%")
    print(f"  Holdout Normal (|y| <= 10, {ho_mask_norm.sum()} obs = {ho_mask_norm.mean()*100:.1f}% de la muestra):")
    print(f"    MSE(B+++) = {mse_b3_norm:.6f} | MSE(E) = {mse_e_norm:.6f} | Delta R2 = {delta_r2_norm*100:+.4f}%")
    print(f"  Holdout Extremo (|y| > 10, {ho_mask_ext.sum()} obs = {ho_mask_ext.mean()*100:.1f}% de la muestra):")
    print(f"    MSE(B+++) = {mse_b3_ext:.6f} | MSE(E) = {mse_e_ext:.6f} | Delta R2 = {delta_r2_ext*100:+.4f}%")
    print(f"  Concentración de pérdida:")
    print(f"    Las {ho_mask_ext.sum()} obs extremas ({ho_mask_ext.mean()*100:.2f}% de las filas) concentran el {sse_b3_ext/sse_b3_total*100:.2f}% del error cuadrático total de B+++ y el {sse_e_ext/sse_e_total*100:.2f}% de E.")

    # =========================================================================
    # INVESTIGACIÓN 3: Diagnóstico de las features geométricas
    # =========================================================================
    print("\n" + "-" * 60)
    print("INVESTIGACIÓN 3: DIAGNÓSTICO CONCEPTUAL Y ALGEBRAICO DE FEATURES")
    print("-" * 60)

    geom_cols = ["v03_liq_conc_ask", "v03_liq_conc_bid", "v03_impact_conc_k3", "v03_pnpc_k3"]
    conv_cols = ["imb_full", "imb_top1", "ofi_5", "_ofi_x_imb", "_ofi_div_depth10", "depth_log"]
    all_diag_cols = geom_cols + conv_cols

    corr_matrix = df[all_diag_cols].corr()
    print("Matriz de correlación lineal (Pearson) entre variables geométricas y convencionales:")
    print(corr_matrix[geom_cols].loc[conv_cols].to_string())

    spearman_matrix = df[all_diag_cols].corr(method="spearman")
    print("\nMatriz de correlación monótona (Spearman):")
    print(spearman_matrix[geom_cols].loc[conv_cols].to_string())

    # Correlación entre v03_impact_conc_k3 y v03_pnpc_k3
    r_impact_pnpc = corr_matrix.loc["v03_impact_conc_k3", "v03_pnpc_k3"]
    rho_impact_pnpc = spearman_matrix.loc["v03_impact_conc_k3", "v03_pnpc_k3"]
    print(f"\nCorrelación v03_impact_conc_k3 vs v03_pnpc_k3: Pearson r = {r_impact_pnpc:.4f} | Spearman rho = {rho_impact_pnpc:.4f}")

    # Correlación entre v03_pnpc_k3 y _ofi_div_depth10
    r_pnpc_depth = corr_matrix.loc["v03_pnpc_k3", "_ofi_div_depth10"]
    rho_pnpc_depth = spearman_matrix.loc["v03_pnpc_k3", "_ofi_div_depth10"]
    print(f"Correlación v03_pnpc_k3 vs _ofi_div_depth10: Pearson r = {r_pnpc_depth:.4f} | Spearman rho = {rho_pnpc_depth:.4f}")

    # VIF auxiliar de las 3 variables de Model_E agregadas sobre B+++
    from numpy.linalg import lstsq
    def compute_vif_series(data, col_names):
        vifs = {}
        for c in col_names:
            y_c = data[c].to_numpy(float)
            x_cols = [o for o in col_names if o != c]
            X_c = data[x_cols].to_numpy(float)
            X_c = np.c_[np.ones(len(X_c)), X_c]
            beta, residuals, rank, s = lstsq(X_c, y_c, rcond=None)
            pred = X_c @ beta
            r2 = 1.0 - np.sum((y_c - pred) ** 2) / np.sum((y_c - y_c.mean()) ** 2)
            vif = 1.0 / max(1e-6, 1.0 - r2)
            vifs[c] = vif
        return vifs

    vif_model_e = compute_vif_series(df[MODEL_SPECS_V3["Model_E"]], MODEL_SPECS_V3["Model_E"])
    print("\nVIF en Model_E para variables V3:")
    for c in ["v03_pnpc_k3", "v03_liq_conc_ask", "v03_liq_conc_bid", "v03_impact_conc_k3", "_ofi_div_depth10"]:
        print(f"  {c}: VIF = {vif_model_e.get(c, np.nan):.2f}")

    # =========================================================================
    # INVESTIGACIÓN 4: Auditoría de costes económicos y métricas
    # =========================================================================
    print("\n" + "-" * 60)
    print("INVESTIGACIÓN 4: AUDITORÍA DE COSTES Y MÉTRICAS")
    print("-" * 60)
    # Comparar magnitud del retorno 10s medio frente al spread y comisiones
    mean_abs_ret_10 = df[TARGET_BPS].abs().mean()
    median_abs_ret_10 = df[TARGET_BPS].abs().median()
    p95_abs_ret_10 = np.percentile(df[TARGET_BPS].abs(), 95)
    mean_spread_bps = df["spread_bps"].mean()
    median_spread_bps = df["spread_bps"].median()

    # Comisiones de Kraken en bps:
    # Taker fee estándar: 0.40% = 40 bps; Taker tier 1: 0.26% = 26 bps; Maker tier 1: 0.16% = 16 bps
    kraken_taker_bps = 26.0  # 0.26% = 26 bps
    kraken_maker_bps = 16.0  # 0.16% = 16 bps

    print(f"Retorno absoluto a 10s: Media = {mean_abs_ret_10:.4f} bps | Mediana = {median_abs_ret_10:.4f} bps | p95 = {p95_abs_ret_10:.4f} bps")
    print(f"Spread del libro:        Media = {mean_spread_bps:.4f} bps | Mediana = {median_spread_bps:.4f} bps")
    print(f"Comisión Kraken Taker:  0.26% = {kraken_taker_bps:.1f} bps (Round-trip = {kraken_taker_bps*2:.1f} bps)")
    print(f"Comisión Kraken Maker:  0.16% = {kraken_maker_bps:.1f} bps (Round-trip = {kraken_maker_bps*2:.1f} bps)")
    print(f"Ratio Retorno Medio / Comisión Taker Round-trip: {mean_abs_ret_10 / (kraken_taker_bps * 2):.4f}x")

    # Guardar resumen diagnóstico
    out_diag = {
        "n_obs_total": n_total,
        "n_eval": len(df_eval),
        "n_holdout": len(df_holdout),
        "overlap_temporal_detected": overlap_detected,
        "holdout_decomposition": {
            "delta_r2_all": float(delta_r2_all),
            "delta_r2_norm": float(delta_r2_norm),
            "delta_r2_ext": float(delta_r2_ext),
            "sse_ext_pct_b3": float(sse_b3_ext / sse_b3_total * 100),
            "sse_ext_pct_e": float(sse_e_ext / sse_e_total * 100),
            "n_ext_holdout": int(ho_mask_ext.sum()),
            "n_norm_holdout": int(ho_mask_norm.sum()),
        },
        "extreme_obs_summary": {
            "n_ext": int(mask_ext.sum()),
            "y_bps_abs_mean_ext": float(df_ext[TARGET_BPS].abs().mean()),
            "y_bps_abs_mean_norm": float(df_norm[TARGET_BPS].abs().mean()),
            "vol60_mean_ext": float(df_ext['vol60_bps'].mean()),
            "vol60_mean_norm": float(df_norm['vol60_bps'].mean()),
        },
        "correlations": {
            "r_impact_pnpc": float(r_impact_pnpc),
            "rho_impact_pnpc": float(rho_impact_pnpc),
            "r_pnpc_depth": float(r_pnpc_depth),
            "rho_pnpc_depth": float(rho_pnpc_depth),
        },
        "vifs": {k: float(v) for k, v in vif_model_e.items()},
    }
    scratch_out = PROJECT_ROOT / "scratch" / "postmortem_diagnostics_summary.json"
    scratch_out.parent.mkdir(parents=True, exist_ok=True)
    scratch_out.write_text(json.dumps(out_diag, indent=2), encoding="utf-8")
    print(f"\nResumen guardado en {scratch_out}")


if __name__ == "__main__":
    run_diagnostics()
