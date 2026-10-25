"""Temporal leakage and dependence-aware inference regression tests for V3."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from navier_lab.features import NAVIER_V3_REPLENISH
from scripts.evaluate_models_oos_v3 import MODEL_SPECS_V3, evaluate_dataset_v3
from scripts.evaluate_models_oos_v3_temporal import (
    _eligible_training_indices,
    make_temporal_walk_forward_splits,
    time_block_bootstrap_indices,
    validate_temporal_dataframe,
)
from scripts.run_phase5_evaluation_purged import validate_dataframe


def make_frame(times, endpoints=None, horizon=10, sessions=None, index=None):
    times = pd.DatetimeIndex(times)
    if times.tz is None:
        times = times.tz_localize("UTC")
    if endpoints is None:
        endpoints = times + pd.Timedelta(seconds=horizon)
    else:
        endpoints = pd.DatetimeIndex(endpoints)
        if endpoints.tz is None:
            endpoints = endpoints.tz_localize("UTC")
    if sessions is None:
        sessions = np.repeat("s1", len(times))
    frame = pd.DataFrame(index=index if index is not None else pd.RangeIndex(len(times)))
    frame["timestamp"] = times
    frame["feature_time"] = times
    frame["label_start_time"] = times
    frame["label_end_time"] = endpoints
    frame["label_horizon_seconds"] = horizon
    frame["session_id"] = sessions
    frame["label_end_session_id"] = sessions
    frame["y"] = np.zeros(len(times))
    return frame


def test_strict_label_endpoint_rule_and_reported_boundary_regression():
    ts = pd.Timestamp("2026-10-23 17:57:42", tz="UTC")
    ends = pd.DatetimeIndex([
        ts - pd.Timedelta(seconds=1),
        ts,
        ts + pd.Timedelta(seconds=9),
    ])
    frame = make_frame(
        pd.DatetimeIndex([ts - pd.Timedelta(seconds=11), ts - pd.Timedelta(seconds=10), ts - pd.Timedelta(seconds=1)]),
        endpoints=ends,
    )
    admitted, rejected_count = _eligible_training_indices(frame, np.arange(3), ts)
    assert admitted.tolist() == [0]
    assert rejected_count == 2

    # Regression from the previous report: a label ending at 17:57:51 must not
    # train a model whose test period begins at 17:57:42.
    assert ends[2] == pd.Timestamp("2026-10-23 17:57:51", tz="UTC")
    assert ends[2] >= ts
    assert 2 not in admitted


def test_irregular_timestamps_purge_by_elapsed_label_end_not_row_count():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    times = pd.DatetimeIndex([start, start + pd.Timedelta(seconds=1),
                              start + pd.Timedelta(seconds=4), start + pd.Timedelta(seconds=20)])
    ends = pd.DatetimeIndex([start + pd.Timedelta(seconds=2), start + pd.Timedelta(seconds=3),
                             start + pd.Timedelta(seconds=14), start + pd.Timedelta(seconds=30)])
    frame = make_frame(times, endpoints=ends)
    splits = make_temporal_walk_forward_splits(
        frame, k_folds=2, embargo_seconds=0, min_train_obs=1, min_test_obs=1,
    )
    assert splits[0]["train_idx"].tolist() == [0, 1]
    assert splits[0]["test_idx"].tolist() == [2, 3]
    assert splits[0]["audit"]["purged_train_obs"] == 0
    assert splits[0]["audit"]["label_overlap"] is False


def test_configurable_label_horizon_is_validated():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    frame = make_frame(pd.date_range(start, periods=5, freq="1s"), horizon=3)
    checked = validate_temporal_dataframe(frame, expected_horizon_seconds=3)
    assert (checked.label_end_time - checked.label_start_time).dt.total_seconds().eq(3).all()
    with pytest.raises(ValueError, match="se esperaba H=10s"):
        validate_temporal_dataframe(frame, expected_horizon_seconds=10)


def test_label_crossing_session_is_rejected():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    frame = make_frame(pd.date_range(start, periods=5, freq="1s"), sessions=np.repeat("s1", 5))
    frame.loc[2, "label_end_session_id"] = "s2"
    with pytest.raises(ValueError, match="fuera de su sesión"):
        validate_temporal_dataframe(frame, expected_horizon_seconds=10)


def test_duplicate_index_missing_times_and_duplicate_times_fail_explicitly():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    times = pd.date_range(start, periods=5, freq="1s")
    duplicate_index = make_frame(times, index=[0, 1, 1, 3, 4])
    with pytest.raises(ValueError, match="índice.*duplicados"):
        validate_temporal_dataframe(duplicate_index)

    missing = make_frame(times).drop(columns="label_end_time")
    with pytest.raises(ValueError, match="Faltan metadatos"):
        validate_temporal_dataframe(missing)

    absent_value = make_frame(times)
    absent_value.loc[2, "label_end_time"] = pd.NaT
    with pytest.raises(ValueError, match="label_end_time contiene timestamps ausentes"):
        validate_temporal_dataframe(absent_value)

    duplicate_time = make_frame(pd.DatetimeIndex([times[0], times[1], times[1], times[3], times[4]]))
    with pytest.raises(ValueError, match="feature_time duplicados"):
        validate_temporal_dataframe(duplicate_time)


def test_unsorted_input_is_stably_sorted_and_temporal_splits_reproduce():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    times = pd.date_range(start, periods=100, freq="1s")
    frame = make_frame(times).sample(frac=1, random_state=7)
    sorted_frame = validate_temporal_dataframe(frame)
    assert sorted_frame.feature_time.is_monotonic_increasing
    first = make_temporal_walk_forward_splits(
        sorted_frame, k_folds=5, embargo_seconds=3, min_train_obs=5, min_test_obs=10
    )
    second = make_temporal_walk_forward_splits(
        sorted_frame, k_folds=5, embargo_seconds=3, min_train_obs=5, min_test_obs=10
    )
    assert len(first) == len(second) == 4
    for a, b in zip(first, second):
        np.testing.assert_array_equal(a["train_idx"], b["train_idx"])
        np.testing.assert_array_equal(a["test_idx"], b["test_idx"])


def test_small_or_empty_temporal_folds_fail_instead_of_returning_metrics():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    too_small = make_frame(pd.date_range(start, periods=30, freq="1s"))
    with pytest.raises(ValueError, match="Muestra insuficiente"):
        make_temporal_walk_forward_splits(too_small, k_folds=5, min_test_obs=10)

    enough = make_frame(pd.date_range(start, periods=100, freq="1s"))
    with pytest.raises(ValueError, match="solo .* filas train tras purga"):
        make_temporal_walk_forward_splits(
            enough, k_folds=5, embargo_seconds=0, min_train_obs=1000, min_test_obs=1,
        )
    with pytest.raises(ValueError, match="solo 0 filas test tras embargo"):
        make_temporal_walk_forward_splits(
            enough, k_folds=2, embargo_seconds=10_000, min_train_obs=1, min_test_obs=1,
        )


def test_block_bootstrap_is_reproducible_and_keeps_draws_in_range():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    times = pd.Series(pd.date_range(start, periods=100, freq="1s"))
    sessions = np.repeat(["s1", "s2"], 50)
    folds = np.repeat([1, 2], 50)
    a = time_block_bootstrap_indices(times, sessions, folds, 15, n_boot=10, seed=22)
    b = time_block_bootstrap_indices(times, sessions, folds, 15, n_boot=10, seed=22)
    np.testing.assert_array_equal(a, b)
    assert a.shape == (10, 100)
    assert a.min() >= 0 and a.max() < 100


def test_actual_evaluator_uses_timestamp_purge_and_reports_no_overlap():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    n = 900
    times = pd.date_range(start, periods=n, freq="1s")
    rng = np.random.default_rng(4)
    frame = make_frame(times, horizon=10)
    frame["session_id"] = "s1"
    frame["label_end_session_id"] = "s1"
    frame["ofi_raw_5"] = rng.normal(size=n)
    frame["ofi_5"] = rng.normal(size=n)
    frame["imb_full"] = rng.normal(size=n)
    frame["depth_log"] = np.log(4.0)
    for cols in MODEL_SPECS_V3.values():
        for col in cols:
            if col not in frame:
                frame[col] = rng.normal(size=n)
    for col in NAVIER_V3_REPLENISH:
        frame[col] = rng.normal(size=n)
    frame["y"] = rng.normal(size=n)

    result = evaluate_dataset_v3(
        frame, holdout_ratio=0.20, k_folds=5, embargo_seconds=10, seed=42,
        expected_horizon_seconds=10, n_boot=20, min_train_obs=50, min_test_obs=20,
    )
    audit = result["temporal_audit"]
    assert result["evidence_status"] == "POST_HOC_DIAGNOSTIC_NOT_CONFIRMATORY"
    assert audit["all_train_labels_end_before_test"] is True
    holdout = audit["holdout"]
    assert holdout["purged_train_obs"] == 10
    assert pd.Timestamp(holdout["max_train_label_end_time"]) < pd.Timestamp(holdout["nominal_test_start_time"])
    for split in audit["walk_forward_splits"]:
        assert split["label_overlap"] is False
        assert pd.Timestamp(split["max_train_label_end_time"]) < pd.Timestamp(split["nominal_test_start_time"])
    c1 = result["walk_forward_comparisons"]["Model_E_vs_Model_B_tripleplus"]
    assert set(c1["block_bootstrap_sensitivity"]) == {"10", "15", "30"}
    assert "block_bootstrap_p_fdr_adjusted" in c1


def test_evaluator_rejects_absent_temporal_schema():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    frame = make_frame(pd.date_range(start, periods=10, freq="1s"))
    frame["ofi_5"] = 0.0
    frame["imb_full"] = 0.0
    frame["depth_log"] = 0.0
    with pytest.raises(ValueError, match="metadatos temporales obligatorios"):
        evaluate_dataset_v3(frame.drop(columns="label_end_time"))


def test_runner_accepts_model_interactions_that_are_created_at_evaluation_time():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    frame = make_frame(pd.date_range(start, periods=25, freq="1s"))
    for cols in MODEL_SPECS_V3.values():
        for col in cols:
            if not col.startswith("_") and col not in frame:
                frame[col] = 0.0
    audit = validate_dataframe(frame, horizon_seconds=10)
    assert audit["temporal_schema_validated"] is True
    assert audit["num_rows"] == 25
