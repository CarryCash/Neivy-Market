"""Read-only deterministic timing replay for the existing NAVIER smoke capture.

Replay timings are local compute timings, not production or exchange latency.
The source capture is never modified; all outputs go to a new, caller-selected
directory. Features are calculated by the frozen existing V3 implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from navier_lab.features import NAVIER_V3, compute_features
from navier_lab.resampler import resample_l2_to_1s
from navier_lab.schema import DEFAULT_CONFIG


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def duration_summary(samples_ns: list[int]) -> dict:
    if not samples_ns:
        return {"count": 0}
    ordered = sorted(samples_ns)

    def pct(p: float) -> float:
        return ordered[round((len(ordered) - 1) * p)] / 1e6

    result = {
        "count": len(ordered),
        "zero_count": sum(value == 0 for value in ordered),
        "zero_percent": 100.0 * sum(value == 0 for value in ordered) / len(ordered),
        "min_ms": ordered[0] / 1e6,
        "median_ms": statistics.median(ordered) / 1e6,
        "max_ms": ordered[-1] / 1e6,
    }
    if len(ordered) == 1:
        result["elapsed_ms"] = ordered[0] / 1e6
        result["percentiles_omitted"] = "single timing observation"
    elif len(ordered) < 20:
        result["percentiles_omitted"] = "fewer than 20 observations"
    else:
        result.update({"p90_ms": pct(.90), "p95_ms": pct(.95), "p99_ms": pct(.99)})
    return result


def empirical_clock(clock, n: int = 100_000) -> dict:
    readings = [clock() for _ in range(n + 1)]
    diffs = [right - left for left, right in zip(readings, readings[1:])]
    positive = sorted(value for value in diffs if value > 0)
    return {
        "samples": len(diffs),
        "zero_count": sum(value == 0 for value in diffs),
        "min_positive_ns": min(positive) if positive else None,
        "median_positive_ns": statistics.median(positive) if positive else None,
        "max_ns": max(diffs),
    }


def run(source: Path, out_dir: Path) -> dict:
    if out_dir.exists():
        raise FileExistsError(f"Output directory already exists: {out_dir}")
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash_before = sha256(source)
    out_dir.mkdir(parents=True)

    start = time.perf_counter_ns()
    raw = pq.read_table(source).to_pandas()
    read_end = time.perf_counter_ns()

    required = {"timestamp", "symbol", "checksum", "capture_row_id", "received_at",
                "received_monotonic_ns", "processed_at", "processed_monotonic_ns"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Capture missing required columns: {missing}")
    if not raw["capture_row_id"].is_monotonic_increasing or raw["capture_row_id"].duplicated().any():
        raise ValueError("capture_row_id must be unique and in capture order")
    for column in ("timestamp", "received_at", "processed_at"):
        raw[column] = pd.to_datetime(raw[column], utc=True)
    if not raw["timestamp"].is_monotonic_increasing:
        raise ValueError("Exchange timestamps regress; causal replay refused")
    if (raw["processed_monotonic_ns"] < raw["received_monotonic_ns"]).any():
        raise ValueError("Capture has processing marks earlier than receipt marks")
    validation_end = time.perf_counter_ns()

    resampled = resample_l2_to_1s(raw)
    resample_end = time.perf_counter_ns()
    if not resampled.empty:
        source_ids = resampled["capture_row_id"].dropna().astype("int64")
        source_times = raw.set_index("capture_row_id")["timestamp"]
        chosen_times = source_times.reindex(source_ids).reset_index(drop=True)
        bins = resampled.loc[resampled["capture_row_id"].notna(), "timestamp"].reset_index(drop=True)
        if not (chosen_times <= bins).all():
            raise AssertionError("A resampled state uses an event later than its bin close")

    features = compute_features(resampled, DEFAULT_CONFIG, with_target=False)
    feature_end = time.perf_counter_ns()
    ready = features[NAVIER_V3].notna().all(axis=1)
    linked = features.loc[ready, ["timestamp"]].copy()
    linked["capture_row_id"] = resampled.loc[ready, "capture_row_id"].to_numpy()
    # Batch readiness means the consumer could access these outputs after this
    # replay stage ended; it is intentionally not represented as capture latency.
    linked["feature_ready_replay_elapsed_ns"] = feature_end - start
    linked["feature_ready_definition"] = "batch V3 output returned by compute_features(with_target=False)"

    resampled.to_parquet(out_dir / "resampled_l2_1s.parquet", index=False)
    features.to_parquet(out_dir / "features_v3.parquet", index=False)
    linked.to_csv(out_dir / "feature_availability_replay.csv", index=False)
    source_hash_after = sha256(source)
    if source_hash_after != source_hash_before:
        raise AssertionError("Source Parquet changed during read-only replay")

    clock_names = ("monotonic", "perf_counter", "time")
    clock_info = {
        name: {key: getattr(time.get_clock_info(name), key)
               for key in ("implementation", "resolution", "monotonic", "adjustable")}
        for name in clock_names
    }
    mono = raw["processed_monotonic_ns"].to_numpy() - raw["received_monotonic_ns"].to_numpy()
    report = {
        "status": "PARTIAL_TIMING_DIAGNOSTIC",
        "source": str(source), "source_sha256_before": source_hash_before,
        "source_sha256_after": source_hash_after,
        "rows_in": len(raw), "rows_resampled": len(resampled),
        "resampled_state_counts": resampled["state_source"].value_counts(dropna=False).to_dict(),
        "valid_v3_rows": int(ready.sum()), "v3_columns": NAVIER_V3,
        "config": {"horizon": DEFAULT_CONFIG.horizon, "vol_window": DEFAULT_CONFIG.vol_window,
                   "ofi_window": DEFAULT_CONFIG.ofi_window},
        "clock_info": clock_info,
        "perf_counter_empirical": empirical_clock(time.perf_counter_ns),
        "capture_receive_to_process_monotonic_ns": {
            "count": int(len(mono)),
            "zero_count": int((mono == 0).sum()),
            "zero_percent": 100.0 * float((mono == 0).sum()) / len(mono),
            "min_ms": float(mono.min()) / 1e6,
            "max_ms": float(mono.max()) / 1e6,
            "percentiles_omitted": "15.625 ms declared clock resolution is too coarse for these processing delays",
        },
        "replay_stages": {
            "parquet_read": duration_summary([read_end - start]),
            "input_validation": duration_summary([validation_end - read_end]),
            "book_resampling": duration_summary([resample_end - validation_end]),
            "v3_feature_batch": duration_summary([feature_end - resample_end]),
            "end_to_end": duration_summary([feature_end - start]),
        },
        "feature_availability": {
            "ready_semantics": "all V3 feature columns are non-null after batch compute returns",
            "source_link": "capture_row_id of the 1s resampled state; same row's features use only current/past resampled rows",
            "capture_to_feature_ready_latency_measured": False,
            "reason": "Capture has no high-resolution perf_counter mark at receipt and the existing feature pipeline is batch, not online.",
            "valid_v3_rows": int(ready.sum()),
        },
        "cross_clock_policy": "No subtraction between exchange UTC, local wall UTC, monotonic_ns and perf_counter_ns.",
        "outputs": ["resampled_l2_1s.parquet", "features_v3.parquet", "feature_availability_replay.csv"],
        "limitations": [
            "Replay duration is local offline compute cost, not production feature latency.",
            "Historical monotonic marks use the coarse GetTickCount64 clock and cannot resolve most sub-15.625 ms delays.",
            "There is no measured per-row online feature-ready time or capture-to-feature latency.",
            "The 110-second smoke does not provide the full independent validation sample or predictive evidence.",
        ],
    }
    (out_dir / "timing_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.out_dir), indent=2, default=str))


if __name__ == "__main__":
    main()
