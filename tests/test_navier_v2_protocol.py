"""Pruebas unitarias y de integración para el Protocolo Experimental NAVIER V2 (Fases 3, 4 y 5)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.evaluate_models_oos import (
    make_walk_forward_splits,
    fit_and_predict_wf,
    paired_oos_r2,
    diebold_mariano_test,
    stationary_block_bootstrap_ci,
)
from navier_lab.analysis import nw_lrv, bh_adjust


def test_walk_forward_purging_and_embargo():
    n = 1000
    k_folds = 5
    purge = 10
    embargo = 10
    splits = make_walk_forward_splits(n, k_folds=k_folds, purge=purge, embargo=embargo)
    assert len(splits) == k_folds - 1

    for tr, te in splits:
        # 1. El set de test debe ser estrictamente posterior al set de train
        assert tr.max() < te.min()
        # 2. La separación entre el último punto de train y el primer punto de test debe ser >= purge + embargo
        gap = te.min() - tr.max()
        assert gap >= (purge + embargo)
        # 3. No debe haber ningún índice en común (cero fuga de información)
        assert len(set(tr).intersection(set(te))) == 0


def test_diebold_mariano_hac():
    n = 200
    rng = np.random.default_rng(42)
    y = rng.normal(0, 1, n)
    # Modelo 1 con error normal
    p1 = y + rng.normal(0, 1.0, n)
    # Modelo 2 con peor error
    p2 = y + rng.normal(0, 2.0, n)
    mask = np.ones(n, dtype=bool)

    # Comparar Modelo 1 (alt) vs Modelo 2 (base): Modelo 1 es mejor => d > 0, t > 0
    res = diebold_mariano_test(y, p2, p1, mask, lags=10)
    assert res["mean_diff"] > 0
    assert res["t_stat"] > 2.0
    assert res["p_value"] < 0.05


def test_benjamini_hochberg_fdr():
    # P-valores con algunos significativos y otros nulos
    p_vals = np.array([0.001, 0.008, 0.03, 0.45, 0.85])
    q_vals = bh_adjust(p_vals)
    # Monotonicidad y control de multiplicidad
    assert np.all(q_vals >= p_vals)
    assert q_vals[0] == pytest.approx(0.001 * 5 / 1, abs=1e-5)
    assert np.all(q_vals <= 1.0)


def test_stationary_block_bootstrap():
    n = 150
    rng = np.random.default_rng(123)
    y = rng.normal(0, 1, n)
    p_base = y + rng.normal(0, 1.5, n)
    p_alt = y + rng.normal(0, 1.0, n)
    mask = np.ones(n, dtype=bool)

    low, high = stationary_block_bootstrap_ci(y, p_base, p_alt, mask, avg_block_len=10, n_boot=200, seed=42)
    assert low < high
    # Si p_alt es sustancialmente mejor, el delta R2 debe ser positivo en el IC
    delta_r2, _, _ = paired_oos_r2(y, p_base, p_alt, mask)
    assert low <= delta_r2 <= high
