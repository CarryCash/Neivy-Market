"""Validate an online-timing smoke against its raw Parquet and frozen batch V3."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from navier_lab.features import NAVIER_V3, compute_features
from navier_lab.resampler import resample_l2_to_1s


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timing_stats(ns: np.ndarray) -> dict:
    values = np.asarray(ns, dtype=np.int64)
    if len(values) == 0:
        return {"count": 0}
    ms = values / 1e6
    return {
        "count": int(len(ms)), "zero_count": int(np.count_nonzero(values == 0)),
        "zero_percent": float(np.mean(values == 0) * 100),
        "min_ms": float(ms.min()), "median_ms": float(np.median(ms)),
        "p90_ms": float(np.quantile(ms, .90)), "p95_ms": float(np.quantile(ms, .95)),
        "p99_ms": float(np.quantile(ms, .99)), "max_ms": float(ms.max()),
    }


def compare_online_to_batch(resampled: pd.DataFrame, batch: pd.DataFrame,
                            online: pd.DataFrame, *, rtol: float = 1e-12,
                            atol: float = 1e-12) -> dict:
    """Compare interval coverage, source-state IDs and frozen V3 values."""
    from navier_lab.features import NAVIER_V3

    state_ids = dict(zip(resampled["timestamp"], resampled["capture_row_id"]))
    expected = batch.loc[batch[NAVIER_V3].notna().all(axis=1)]
    if not online.empty:
        expected = expected.loc[expected["timestamp"] <= online["feature_time_utc"].max()]
    expected_times = set(expected["timestamp"])
    online_times = set(online["feature_time_utc"])
    coverage_ok = len(online_times) == len(online) and online_times == expected_times
    source_ok, values_ok = True, True
    max_abs_diff = {name: 0.0 for name in NAVIER_V3}
    for row in online.itertuples(index=False):
        if state_ids.get(row.feature_time_utc) != row.capture_row_id:
            source_ok = False
        matches = batch.loc[batch["timestamp"] == row.feature_time_utc]
        if len(matches) != 1:
            values_ok = False
            continue
        expected_row = matches.iloc[0]
        for name in NAVIER_V3:
            diff = abs(float(getattr(row, name)) - float(expected_row[name]))
            max_abs_diff[name] = max(max_abs_diff[name], diff)
            if not np.isclose(float(getattr(row, name)), float(expected_row[name]),
                              rtol=rtol, atol=atol):
                values_ok = False
    return {
        "interval_coverage_matches": coverage_ok,
        "source_state_ids_match": source_ok,
        "feature_values_match": values_ok,
        "all_match": coverage_ok and source_ok and values_ok,
        "rtol": rtol, "atol": atol,
        "max_absolute_difference": max_abs_diff,
    }


def validate(capture: Path, duration_limit_seconds: float = 120.0) -> dict:
    manifest_path = capture.with_suffix(capture.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    feature_path = capture.with_name(manifest["feature_output_file"])
    raw_sha, feature_sha = sha256(capture), sha256(feature_path)
    raw = pq.read_table(capture).to_pandas()
    online = pq.read_table(feature_path).to_pandas()
    for column in ("timestamp", "received_at", "processed_at"):
        raw[column] = pd.to_datetime(raw[column], utc=True)
    online["feature_time_utc"] = pd.to_datetime(online["feature_time_utc"], utc=True)

    checks = {
        "manifest_success": manifest["status"] == "SUCCESS" and manifest["capture_complete"],
        "instrument_channel_depth": (manifest["symbol"], manifest["channel"], manifest["depth"])
            == ("BTC/USD", "book", 10),
        "raw_sha_matches_manifest": raw_sha == manifest["output_sha256"],
        "feature_sha_matches_manifest": feature_sha == manifest["feature_output_sha256"],
        "schema_v3": pq.read_schema(capture).metadata[b"navier_capture_schema_version"] == b"3",
        "row_count_matches": len(raw) == manifest["valid_rows_written"],
        "capture_ids_unique_consecutive": raw["capture_row_id"].is_unique
            and raw["capture_row_id"].tolist() == list(range(len(raw))),
        "exchange_event_time_monotonic": raw["timestamp"].is_monotonic_increasing,
        "perf_clock_ordered": bool((raw["frame_received_monotonic_ns"]
            <= raw["state_processed_monotonic_ns"]).all()
            and (raw["state_processed_monotonic_ns"]
            <= raw["state_validated_monotonic_ns"]).all()),
        "perf_clock_row_order_monotonic": all(raw[name].is_monotonic_increasing for name in (
            "frame_received_monotonic_ns", "state_processed_monotonic_ns",
            "state_validated_monotonic_ns")),
        "no_integrity_transport_failures": all(manifest["adapter_counters"].get(name, 0) == 0
            for name in ("checksum_failures", "malformed_messages", "reconnects",
                         "out_of_order_timestamps", "connection_errors", "subscription_errors")),
        "feature_ids_unique_consecutive": online["feature_row_id"].is_unique
            and online["feature_row_id"].tolist() == list(range(len(online))),
        "feature_source_ids_exist": bool(online["capture_row_id"].isin(raw["capture_row_id"]).all()),
        "feature_trigger_ids_exist": bool(online["feature_trigger_capture_row_id"].isin(raw["capture_row_id"]).all()),
        "feature_timing_ordered": bool((online["feature_compute_started_monotonic_ns"]
            <= online["feature_ready_monotonic_ns"]).all()),
        "feature_source_is_not_future": True,
        "feature_dependency_rows_are_causal": True,
        "feature_source_row_matches_resampler": True,
        "feature_trigger_precedes_compute": True,
        "batch_online_equivalent": True,
    }

    resampled = resample_l2_to_1s(raw)
    batch = compute_features(resampled, with_target=False)
    batch_comparison = compare_online_to_batch(resampled, batch, online)
    state_id_by_time = dict(zip(resampled["timestamp"], resampled["capture_row_id"]))
    raw_by_id = raw.set_index("capture_row_id")
    max_abs_diff = batch_comparison["max_absolute_difference"]
    checks["batch_online_equivalent"] = batch_comparison["all_match"]
    checks["feature_source_row_matches_resampler"] = batch_comparison["source_state_ids_match"]
    source_frame_to_ready = []
    trigger_frame_to_ready = []
    trigger_receive_to_compute = []
    compute_to_ready = []
    trigger_to_selection = []
    state_selection_duration = []
    selection_to_compute = []
    trigger_ids = []

    for row in online.itertuples(index=False):
        ts = row.feature_time_utc
        source_id = int(row.capture_row_id)
        checks["feature_source_is_not_future"] = bool(checks["feature_source_is_not_future"]
            and raw_by_id.loc[source_id, "timestamp"] <= ts)
        checks["feature_source_row_matches_resampler"] = bool(checks["feature_source_row_matches_resampler"]
            and state_id_by_time.get(ts) == source_id)
        dependency_ids = json.loads(row.dependency_capture_row_ids_json)
        dependency_rows_exist = all(dep_id in raw_by_id.index for dep_id in dependency_ids)
        dependency_rows_causal = dependency_rows_exist and all(
            raw_by_id.loc[dep_id, "timestamp"] <= ts for dep_id in dependency_ids
        )
        checks["feature_dependency_rows_are_causal"] = bool(
            checks["feature_dependency_rows_are_causal"]
            and dependency_ids and source_id in dependency_ids and dependency_rows_causal
        )
        prior_valid = raw.loc[raw["timestamp"] > ts]
        if prior_valid.empty:
            checks["feature_trigger_precedes_compute"] = False
            continue
        expected_trigger = prior_valid.iloc[0]
        trigger_id = int(row.feature_trigger_capture_row_id)
        trigger = raw_by_id.loc[trigger_id]
        trigger_ids.append(trigger_id)
        checks["feature_trigger_precedes_compute"] = bool(
            checks["feature_trigger_precedes_compute"]
            and trigger_id == int(expected_trigger["capture_row_id"])
            and trigger["timestamp"] > ts
            and trigger["state_validated_monotonic_ns"] <= row.state_selection_started_monotonic_ns
            and row.state_selection_started_monotonic_ns <= row.state_selected_monotonic_ns
            and row.state_selected_monotonic_ns <= row.feature_compute_started_monotonic_ns
            and row.feature_compute_started_monotonic_ns <= row.feature_ready_monotonic_ns
        )
        batch_row = batch.loc[batch["timestamp"] == ts]
        if len(batch_row) != 1:
            checks["batch_online_equivalent"] = False
        source_frame_to_ready.append(row.feature_ready_monotonic_ns
                                     - raw_by_id.loc[source_id, "frame_received_monotonic_ns"])
        trigger_frame_to_ready.append(row.feature_ready_monotonic_ns
                                      - trigger["frame_received_monotonic_ns"])
        trigger_receive_to_compute.append(row.feature_compute_started_monotonic_ns
                                          - trigger["frame_received_monotonic_ns"])
        trigger_to_selection.append(row.state_selection_started_monotonic_ns
                                    - trigger["frame_received_monotonic_ns"])
        state_selection_duration.append(row.state_selected_monotonic_ns
                                        - row.state_selection_started_monotonic_ns)
        selection_to_compute.append(row.feature_compute_started_monotonic_ns
                                    - row.state_selected_monotonic_ns)
        compute_to_ready.append(row.feature_ready_monotonic_ns
                                - row.feature_compute_started_monotonic_ns)
    checks["all_durations_nonnegative"] = all(min(values) >= 0 for values in (
        source_frame_to_ready, trigger_frame_to_ready, trigger_receive_to_compute,
        trigger_to_selection, state_selection_duration, selection_to_compute, compute_to_ready))
    feature_span = (int(raw["frame_received_monotonic_ns"].iloc[-1])
                    - int(raw["frame_received_monotonic_ns"].iloc[0])) / 1e9
    checks["frame_receipt_span_within_limit"] = feature_span <= duration_limit_seconds

    return {
        "status": "PASS_ONLINE_TIMING_SMOKE" if all(checks.values()) else "PARTIAL_ONLINE_TIMING_SMOKE",
        "checks": checks,
        "capture_sha256": raw_sha, "feature_sha256": feature_sha,
        "raw_rows": len(raw), "feature_rows": len(online),
        "frame_receipt_span_seconds_perf_counter": feature_span,
        "requested_duration_seconds": manifest["requested_capture_seconds"],
        "duration_limit_seconds": duration_limit_seconds,
        "manifest_elapsed_seconds_including_finalization": manifest["elapsed_seconds"],
        "online_feature_counters": manifest["online_feature_counters"],
        "adapter_counters": manifest["adapter_counters"],
        "clock": manifest["clock"],
        "timings": {
            "frame_received_to_candidate_processed": timing_stats(
                raw["state_processed_monotonic_ns"].to_numpy() - raw["frame_received_monotonic_ns"].to_numpy()),
            "frame_received_to_state_validated": timing_stats(
                raw["state_validated_monotonic_ns"].to_numpy() - raw["frame_received_monotonic_ns"].to_numpy()),
            "source_frame_received_to_feature_ready": timing_stats(np.asarray(source_frame_to_ready)),
            "trigger_frame_received_to_state_selection_started": timing_stats(np.asarray(trigger_to_selection)),
            "state_selection_duration": timing_stats(np.asarray(state_selection_duration)),
            "state_selected_to_feature_compute_started": timing_stats(np.asarray(selection_to_compute)),
            "trigger_frame_received_to_feature_compute": timing_stats(np.asarray(trigger_receive_to_compute)),
            "trigger_frame_received_to_feature_ready": timing_stats(np.asarray(trigger_frame_to_ready)),
            "feature_compute_to_ready": timing_stats(np.asarray(compute_to_ready)),
        },
        "max_absolute_feature_difference": max_abs_diff,
        "batch_online_comparison": batch_comparison,
        "distinct_feature_trigger_rows": len(set(trigger_ids)),
        "limitations": [
            "Kraken feed has no sequence number; CRC and transport counters cannot prove zero silent loss.",
            "feature_ready is the in-process synchronous sink handoff; Parquet sidecar is persisted at session end.",
            "No predictive or economic performance was evaluated.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration-limit-seconds", type=float, default=120.0)
    args = parser.parse_args()
    report = validate(args.capture, args.duration_limit_seconds)
    out = args.output or args.capture.parent / "online_timing_validation.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
