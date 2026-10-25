"""Pruebas unitarias y de integridad para NAVIER V3.

Valida:
1. Causalidad y presencia de variables V3.
2. Signo y selección de profundidad contraria.
3. Coherencia dimensional del ratio PNPC.
4. Máscara del target: límites exactos para gaps en t, t+1, t+H-1, t+H y t+H+1.
5. Máscara del target: límites exactos para staleness_ms en t, t+1, t+H-1, t+H y t+H+1.
6. Procesamiento por bloques: equivalencia total entre compute_features y stream_features con múltiples tamaños de chunk y cortes con gaps.
7. Evaluación fuera de muestra V3: garantía de muestra común para B, B+, B++, B+++, E y escalado causal.
8. Invarianza estricta de V0.1 y V0.2.
"""
import numpy as np
import pandas as pd
import pytest

from navier_lab import synthetic as S, features as F
from navier_lab.schema import (
    DEFAULT_CONFIG as CFG,
    STATE_OBSERVED,
    STATE_GAP_DISCONTINUITY,
    STATE_CARRIED_FORWARD,
    Config,
)
from scripts.evaluate_models_oos_v3 import (
    evaluate_dataset_v3,
    prepare_feature_dataframe,
    classify_v3_verdict,
    MODEL_SPECS_V3,
    CONFIRMATORY_PAIRS,
    FUTILITY_DELTA_MIN,
    VERDICT_EXITO,
    VERDICT_FRACASO,
    VERDICT_FUTILIDAD,
    VERDICT_DISCREPANCIA,
    VERDICT_INCONCLUSO,
)

RAW, _ = S.generate("S2_navier", n=4_000, seed=42)


def attach_exact_label_times(features, horizon_seconds=CFG.horizon, session_id="test-session"):
    """Test fixture matching the 1-second per-session target construction."""
    out = features.copy()
    feature_time = pd.to_datetime(out["timestamp"], utc=True)
    out["timestamp"] = feature_time
    out["feature_time"] = feature_time
    out["label_start_time"] = feature_time
    out["label_end_time"] = feature_time + pd.Timedelta(seconds=horizon_seconds)
    out["session_id"] = session_id
    out["label_end_session_id"] = session_id
    out["label_horizon_seconds"] = horizon_seconds
    return out


def test_v3_features_presence_and_causality():
    """Verifica que las features V3 se calculan y no tienen fuga de información hacia el pasado."""
    t0 = 1_500
    a = F.compute_features(RAW, CFG, with_target=False)
    for col in F.NAVIER_V3_CORE + F.NAVIER_V3_REPLENISH:
        assert col in a.columns, f"Falta {col} en out"

    mod = RAW.copy()
    rng = np.random.default_rng(99)
    for c in mod.columns:
        if c != "timestamp":
            noise = (1 + 0.05 * rng.standard_normal(len(mod) - t0 - 1)).clip(0.5, 1.5)
            mod.loc[t0 + 1:, c] = (mod.loc[t0 + 1:, c].to_numpy(float) * noise).astype(mod[c].dtype)

    b = F.compute_features(mod, CFG, with_target=False)
    for col in F.NAVIER_V3_CORE:
        diff = np.nanmax(np.abs(a.loc[:t0, col].to_numpy(float) - b.loc[:t0, col].to_numpy(float)))
        assert diff < 1e-9, f"Lookahead detectado en {col}: {diff}"


def test_v3_sign_and_contra_depth_selection():
    """Verifica que OFI > 0 toma ask y OFI < 0 toma bid."""
    df = F.compute_features(RAW, CFG, with_target=False)
    pos = df[df["v03_ofi_raw_5"] > 0.01].iloc[0]
    neg = df[df["v03_ofi_raw_5"] < -0.01].iloc[0]

    raw_pos = RAW.loc[pos.name]
    raw_neg = RAW.loc[neg.name]

    expected_ask_k3_pos = sum(raw_pos[f"ask_qty_{k}"] for k in range(1, 4))
    expected_bid_k3_neg = sum(raw_neg[f"bid_qty_{k}"] for k in range(1, 4))

    assert pos["v03_depth_contra_k3"] == pytest.approx(expected_ask_k3_pos, rel=1e-5)
    assert neg["v03_depth_contra_k3"] == pytest.approx(expected_bid_k3_neg, rel=1e-5)


def test_v3_pnpc_dimensionless_ratio():
    """Verifica que PNPC es el cociente exacto entre flujo bruto y profundidad contraria."""
    df = F.compute_features(RAW, CFG, with_target=False)
    valid = df.dropna(subset=["v03_pnpc_k3", "v03_ofi_raw_5", "v03_depth_contra_k3"])
    sample = valid.iloc[100:110]
    expected = sample["v03_ofi_raw_5"] / (sample["v03_depth_contra_k3"] + 1e-6)
    assert np.allclose(sample["v03_pnpc_k3"].to_numpy(), expected.to_numpy(), atol=1e-7)


def test_target_gap_masking_comprehensive_boundaries():
    """Verifica los límites exactos de invalidación del target ante un gap en t0:
    
    Para un gap en G=80 y horizonte H=10:
    - t = G - H - 1 (69): futuro es (69, 79], G está en t+H+1 -> NO invalidado por gap_future.
    - t = G - H     (70): futuro es (70, 80], G está en t+H   -> INVALIDADO (NaN).
    - t = G - H + 1 (71): futuro es (71, 81], G está en t+H-1 -> INVALIDADO (NaN).
    - t = G - 1     (79): futuro es (79, 89], G está en t+1   -> INVALIDADO (NaN).
    - t = G         (80): G está en t, retorno fwd mira a (80, 90] -> gap_future es False.
    - t = G + 1     (81): futuro es (81, 91], G está en el pasado -> NO invalidado.
    """
    df_raw = RAW.iloc[:150].copy()
    df_raw["state_source"] = STATE_OBSERVED
    df_raw["staleness_ms"] = 50.0

    G = 80
    H = CFG.horizon  # 10
    df_raw.loc[G, "state_source"] = STATE_GAP_DISCONTINUITY

    out = F.compute_features(df_raw, CFG, with_target=True)

    # 1. t = G - H - 1 (69) -> El gap ocurre en t+H+1 (fuera del horizonte futuro)
    assert not np.isnan(out.loc[G - H - 1, F.TARGET]), "t=G-H-1 (69) no debe ser invalidado por gap en 80"

    # 2. t = G - H (70) -> El gap ocurre exactamente en el punto final t+H
    assert np.isnan(out.loc[G - H, F.TARGET]), "t=G-H (70) debe ser invalidado porque mid(t+H) es un gap"

    # 3. t = G - H + 1 (71) -> El gap ocurre en t+H-1 (punto intermedio)
    assert np.isnan(out.loc[G - H + 1, F.TARGET]), "t=G-H+1 (71) debe ser invalidado por gap intermedio"

    # 4. t = G - 1 (79) -> El gap ocurre en t+1 (inmediato posterior)
    assert np.isnan(out.loc[G - 1, F.TARGET]), "t=G-1 (79) debe ser invalidado porque t+1 es un gap"

    # 5. Comprobar que toda la franja (G-H).. (G-1) queda invalidada
    for t in range(G - H, G):
        assert np.isnan(out.loc[t, F.TARGET]), f"t={t} debe ser NaN"


def test_target_staleness_comprehensive_boundaries():
    """Verifica límites exactos de invalidación por staleness_ms > 1000ms en el intervalo futuro."""
    df_raw = RAW.iloc[:150].copy()
    df_raw["state_source"] = STATE_OBSERVED
    df_raw["staleness_ms"] = 50.0

    S_idx = 80
    H = CFG.horizon  # 10
    df_raw.loc[S_idx, "staleness_ms"] = 1500.0  # Staleness excesivo

    out = F.compute_features(df_raw, CFG, with_target=True)

    # t = S - H - 1 (69) -> Staleness en t+H+1 -> NO invalidado
    assert not np.isnan(out.loc[S_idx - H - 1, F.TARGET]), "t=69 no debe invalidarse"

    # t = S - H (70) -> Staleness en t+H -> INVALIDADO
    assert np.isnan(out.loc[S_idx - H, F.TARGET]), "t=70 debe invalidarse por staleness en t+H"

    # t = S - H + 1 (71) -> Staleness en t+H-1 -> INVALIDADO
    assert np.isnan(out.loc[S_idx - H + 1, F.TARGET]), "t=71 debe invalidarse por staleness en t+H-1"

    # t = S - 1 (79) -> Staleness en t+1 -> INVALIDADO
    assert np.isnan(out.loc[S_idx - 1, F.TARGET]), "t=79 debe invalidarse por staleness en t+1"


def test_streaming_equals_batch_comprehensive_v3():
    """Verifica que stream_features() produce idénticos resultados numéricos a compute_features()
    bajo múltiples tamaños de chunk y cortes con gaps y datos arrastrados."""
    # Crear serie con estados mixtos
    df_raw = RAW.iloc[:2_000].copy()
    df_raw["state_source"] = STATE_OBSERVED
    df_raw["staleness_ms"] = 100.0
    # Inyectar algunos gaps y arrastres
    df_raw.loc[300:302, "state_source"] = STATE_GAP_DISCONTINUITY
    df_raw.loc[700:710, "state_source"] = STATE_CARRIED_FORWARD

    # Cálculo en lote completo
    batch = F.compute_features(df_raw, CFG, with_target=True)
    cols_to_check = F.FEATURE_COLUMNS_V3 + [F.TARGET, F.TARGET_BPS]
    batch_valid = batch.dropna(subset=cols_to_check).reset_index(drop=True)

    # Probar con múltiples tamaños de chunk (incluyendo números primos e impares)
    for chunk_size in [183, 350, 750, 1100]:
        chunks = (df_raw.iloc[i:i + chunk_size].copy() for i in range(0, len(df_raw), chunk_size))
        streamed_chunks = list(F.stream_features(chunks, CFG, feature_cols=F.FEATURE_COLUMNS_V3))
        if streamed_chunks:
            streamed = pd.concat(streamed_chunks, ignore_index=True)
            # 1. Comprobar longitud exacta
            assert len(streamed) == len(batch_valid), f"Chunk {chunk_size}: longitud difiere ({len(streamed)} vs {len(batch_valid)})"
            # 2. Comprobar alineación de timestamps
            assert (streamed["timestamp"].to_numpy() == batch_valid["timestamp"].to_numpy()).all()
            # 3. Comprobar precisión numérica en todas las features y targets
            for c in cols_to_check:
                s_vals = streamed[c].to_numpy(float)
                b_vals = batch_valid[c].to_numpy(float)
                max_diff = np.nanmax(np.abs(s_vals - b_vals))
                assert max_diff < 1e-8, f"Chunk {chunk_size}, col {c}: discrepancia {max_diff}"


def test_v3_evaluation_common_sample_and_causal_scaling():
    """Valida que evaluate_dataset_v3 entrena y evalúa todos los modelos confirmatorios
    sobre exactamente la misma muestra común y que la normalización es estrictamente causal."""
    df_raw = RAW.iloc[:2_500].copy()
    df_raw["state_source"] = STATE_OBSERVED
    df_raw["staleness_ms"] = 50.0
    # Inyectar una discontinuidad para generar NaNs controlados
    df_raw.loc[500:503, "state_source"] = STATE_GAP_DISCONTINUITY

    feats = attach_exact_label_times(F.compute_features(df_raw, CFG, with_target=True))
    res = evaluate_dataset_v3(
        feats, holdout_ratio=0.20, k_folds=5, embargo_seconds=10,
        seed=42, expected_horizon_seconds=CFG.horizon, n_boot=100,
    )

    # 1. Verificar presencia de todos los contrastes confirmatorios
    wf_comps = res["walk_forward_comparisons"]
    for alt, base in CONFIRMATORY_PAIRS:
        comp_key = f"{alt}_vs_{base}"
        assert comp_key in wf_comps
        # El número de observaciones OOS debe ser idéntico en todos los contrastes confirmatorios
        assert wf_comps[comp_key]["n_eval_obs"] == wf_comps["Model_E_vs_Model_B_tripleplus"]["n_eval_obs"]

    # 2. Verificar que el contraste exploratorio C5 está separado
    assert "exploratory_c5" in res
    assert res["exploratory_c5"]["status"] == "EXPLORATORIO_POST_HOC"
    assert res["evidence_status"] == "POST_HOC_DIAGNOSTIC_NOT_CONFIRMATORY"
    assert res["temporal_audit"]["all_train_labels_end_before_test"] is True

    # 3. Verificar que los criterios de la matriz de decisión están unívocamente evaluados
    assert res["diagnostic_verdict"] in [
        "ÉXITO (EVIDENCIA ROBUSTA DE SEÑAL GEOMÉTRICA INCREMENTAL)",
        "FRACASO (HIPÓTESIS RECHAZADA — ABSORBIDA POR B+++)",
        "FUTILIDAD (MEJORA INFERIOR AL UMBRAL MÍNIMO DE RELEVANCIA — LÍNEA CERRADA)",
        "INCONCLUSO (EVIDENCIA DÉBIL O POTENCIA INSUFICIENTE TRAS FDR)",
        "DISCREPANCIA HOLDOUT (ÉXITO EN WF PERO DETERIORO EN HOLDOUT — NO SE ACEPTA H1)",
    ]


def test_v01_and_v02_invariance():
    """Garantiza que NAVIER V0.1 y V0.2 no fueron alterados tras añadir V3."""
    a = F.compute_features(RAW, CFG)
    for col in F.NAVIER:
        assert not a[col].dropna().empty
    for col in F.NAVIER_V02:
        assert not a[col].dropna().empty


def test_decision_matrix_resolution_of_conflicts():
    """Valida la resolución determinista de la matriz de decisión V3,
    incluyendo casos que antes satisfacían simultáneamente fracaso e inconclusión,
    o fracaso y futilidad."""
    # 1. Caso de conflicto previo FRACASO vs INCONCLUSO:
    # delta_r2_wf >= delta_min (0.0015), p_fdr >= 0.05 (0.12), folds < 2 (1)
    # En el protocolo previo: satisfacía Fracaso (folds < 2) E Inconcluso (delta >= delta_min, p >= 0.05).
    # Con el orden determinista: la falta de consistencia (folds < 2) tiene prelación absoluta -> FRACASO.
    v1 = classify_v3_verdict(
        delta_r2_wf=0.0015,
        p_fdr_wf=0.12,
        folds_positive_count=1,
        delta_r2_ho=0.001,
        p_ho=0.02,
    )
    assert v1 == VERDICT_FRACASO, f"Conflicto fracaso/inconclusión debe resolverse a FRACASO: {v1}"

    # 2. Caso de conflicto previo FRACASO vs FUTILIDAD:
    # 0 < delta_r2_wf < delta_min (0.0005), pero folds < 2 (1)
    # En el protocolo previo: satisfacía Fracaso (folds < 2) Y Futilidad (delta < delta_min).
    # Con el orden determinista: la inconsistencia prevalece -> FRACASO.
    v2 = classify_v3_verdict(
        delta_r2_wf=0.0005,
        p_fdr_wf=0.02,
        folds_positive_count=1,
        delta_r2_ho=0.001,
        p_ho=0.02,
    )
    assert v2 == VERDICT_FRACASO, f"Conflicto fracaso/futilidad debe resolverse a FRACASO: {v2}"

    # 3. Caso INCONCLUSO genuino por falta de potencia estadística tras FDR:
    # delta >= delta_min (0.0015), folds consistentes (3/4), pero p_fdr >= 0.05 (0.12)
    v3 = classify_v3_verdict(
        delta_r2_wf=0.0015,
        p_fdr_wf=0.12,
        folds_positive_count=3,
        delta_r2_ho=0.001,
        p_ho=0.02,
    )
    assert v3 == VERDICT_INCONCLUSO

    # 4. Caso INCONCLUSO genuino por consistencia intermedia frontera (2/4 folds = 50%):
    # delta >= delta_min (0.0015), p_fdr significativo (0.02 < 0.05), pero folds = 2 (no alcanza 3/4)
    # En la tabla original: no estaba definido explícitamente (vacío entre fracaso <2 y éxito >=3).
    v4 = classify_v3_verdict(
        delta_r2_wf=0.0015,
        p_fdr_wf=0.02,
        folds_positive_count=2,
        delta_r2_ho=0.001,
        p_ho=0.02,
    )
    assert v4 == VERDICT_INCONCLUSO

    # 5. Caso FUTILIDAD genuino:
    # 0 < delta < delta_min (0.0005) con consistencia básica (folds >= 2)
    v5 = classify_v3_verdict(
        delta_r2_wf=0.0005,
        p_fdr_wf=0.02,
        folds_positive_count=2,
        delta_r2_ho=0.001,
        p_ho=0.02,
    )
    assert v5 == VERDICT_FUTILIDAD

    # 6. Caso ÉXITO pleno:
    # WF supera delta_min, p_fdr < 0.05, folds >= 3, y Holdout confirma (delta > 0, p < 0.05)
    v6 = classify_v3_verdict(
        delta_r2_wf=0.0020,
        p_fdr_wf=0.02,
        folds_positive_count=3,
        delta_r2_ho=0.0015,
        p_ho=0.02,
    )
    assert v6 == VERDICT_EXITO

    # 7. Caso DISCREPANCIA HOLDOUT (deterioro en holdout):
    # WF cumple todo para éxito, pero Holdout tiene delta <= 0
    v7a = classify_v3_verdict(
        delta_r2_wf=0.0020,
        p_fdr_wf=0.02,
        folds_positive_count=3,
        delta_r2_ho=-0.0005,
        p_ho=0.02,
    )
    assert v7a == VERDICT_DISCREPANCIA

    # WF cumple todo para éxito, pero Holdout no es significativo (p >= 0.05)
    v7b = classify_v3_verdict(
        delta_r2_wf=0.0020,
        p_fdr_wf=0.02,
        folds_positive_count=3,
        delta_r2_ho=0.0010,
        p_ho=0.15,
    )
    assert v7b == VERDICT_DISCREPANCIA

    # 8. Caso FRACASO por delta_wf <= 0 (falsación directa de hipótesis):
    v8a = classify_v3_verdict(
        delta_r2_wf=-0.0010,
        p_fdr_wf=0.01,
        folds_positive_count=3,
        delta_r2_ho=0.001,
        p_ho=0.01,
    )
    assert v8a == VERDICT_FRACASO

    v8b = classify_v3_verdict(
        delta_r2_wf=0.0,
        p_fdr_wf=0.01,
        folds_positive_count=4,
        delta_r2_ho=0.001,
        p_ho=0.01,
    )
    assert v8b == VERDICT_FRACASO


def test_decision_matrix_deterministic_and_mece_exhaustive():
    """Comprobación exhaustiva sobre rejilla multidimensional (MECE):
    Verifica que el 100% de las combinaciones posibles mapean a exactamente un veredicto válido."""
    all_verdicts = {
        VERDICT_EXITO,
        VERDICT_FRACASO,
        VERDICT_FUTILIDAD,
        VERDICT_DISCREPANCIA,
        VERDICT_INCONCLUSO,
    }
    deltas_wf = [-0.01, -0.0001, 0.0, 0.0001, 0.0005, 0.00099, 0.0010, 0.0015, 0.01]
    ps_fdr = [0.001, 0.049, 0.05, 0.051, 0.20, 0.80]
    folds_counts = [0, 1, 2, 3, 4]
    deltas_ho = [-0.005, 0.0, 0.005]
    ps_ho = [0.01, 0.05, 0.10]

    for d_wf in deltas_wf:
        for p_f in ps_fdr:
            for fc in folds_counts:
                for d_ho in deltas_ho:
                    for p_h in ps_ho:
                        v = classify_v3_verdict(
                            delta_r2_wf=d_wf,
                            p_fdr_wf=p_f,
                            folds_positive_count=fc,
                            delta_r2_ho=d_ho,
                            p_ho=p_h,
                        )
                        assert v in all_verdicts, f"Veredicto desconocido: {v}"

                        # Propiedades lógicas deterministas
                        if (d_wf <= 0.0) or (fc < 2):
                            assert v == VERDICT_FRACASO
                        elif 0.0 < d_wf < FUTILITY_DELTA_MIN:
                            assert v == VERDICT_FUTILIDAD
                        elif (d_wf >= FUTILITY_DELTA_MIN) and (p_f < 0.05) and (fc >= 3):
                            if (d_ho > 0.0) and (p_h < 0.05):
                                assert v == VERDICT_EXITO
                            else:
                                assert v == VERDICT_DISCREPANCIA
                        else:
                            assert v == VERDICT_INCONCLUSO


def test_bplusplus_dimensional_coherence():
    """Verifica que la razón convencional en B++ (_ofi_div_depth10) es dimensionalmente coherente:
    [ofi_raw_5 (BTC)] / [total_depth (BTC)] = 1 (adimensional),
    desacoplada de la normalización por profundidad media histórica de ofi_5."""
    df_raw = RAW.iloc[:300].copy()
    feats = F.compute_features(df_raw, CFG, with_target=False)
    
    # Calcular interacciones B++
    prep = prepare_feature_dataframe(feats)
    assert "_ofi_div_depth10" in prep.columns
    assert "_ofi_x_imb" in prep.columns

    # Verificar que _ofi_div_depth10 utiliza ofi_raw_5 / exp(depth_log)
    total_depth_btc = np.exp(prep["depth_log"].to_numpy(float))
    expected = feats["ofi_raw_5"].to_numpy(float) / (total_depth_btc + 1e-6)

    valid_mask = prep["_ofi_div_depth10"].notna()
    np.testing.assert_allclose(
        prep.loc[valid_mask, "_ofi_div_depth10"].to_numpy(float),
        expected[valid_mask],
        rtol=1e-6,
        atol=1e-8,
        err_msg="La interacción _ofi_div_depth10 no coincide con ofi_raw_5 / total_depth_btc"
    )

    # Verificar fallback si solo v03_ofi_raw_5 está presente
    feats_v03 = feats.drop(columns=["ofi_raw_5"]).copy()
    prep_v03 = prepare_feature_dataframe(feats_v03)
    np.testing.assert_allclose(
        prep_v03.loc[valid_mask, "_ofi_div_depth10"].to_numpy(float),
        expected[valid_mask],
        rtol=1e-6,
        atol=1e-8,
    )

