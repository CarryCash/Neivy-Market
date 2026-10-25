"""Non-overwriting runner for isolated NAVIER V3 operational sessions.

This runner is intentionally pinned to Kraken Spot BTC/USD book depth 10. It
stores operational sessions outside the preregistered validation directory.
It is not invoked automatically by any test or preflight command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "BTC/USD"
EXCHANGE = "Kraken Spot WebSocket API v2"
CHANNEL = "book"
DEPTH = 10
EXPECTED_PROTOCOL_SHA256 = "0183b474253d5b6f50f25aba7e463a925a4ff5183da99a3648736dd93095114a"
DEFAULT_SESSION_COUNT = 3
DEFAULT_DURATION_SECONDS = 2400


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, data: dict) -> None:
    temp = path.with_name(f".{path.name}.{time.perf_counter_ns()}.partial")
    temp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def preflight_protocol(project_root: Path = PROJECT_ROOT) -> dict:
    protocol = project_root / "NAVIER_V3_PROTOCOL.md"
    actual = sha256_file(protocol)
    if actual != EXPECTED_PROTOCOL_SHA256:
        raise RuntimeError(
            f"Frozen V3 protocol hash mismatch: expected {EXPECTED_PROTOCOL_SHA256}, got {actual}"
        )
    return {"protocol_file": str(protocol), "protocol_sha256": actual}


def create_run_directory(output_root: Path, run_id: str | None = None) -> Path:
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S_%fZ")
    run_dir = output_root / run_id
    run_dir.mkdir(exist_ok=False)
    return run_dir


def create_session_directory(run_dir: Path, index: int) -> Path:
    if index < 1:
        raise ValueError("session index must be >= 1")
    session_dir = run_dir / f"session_{index:02d}_btc_usd_l2"
    session_dir.mkdir(exist_ok=False)
    return session_dir


def audit_timing_contract(timing: dict) -> dict:
    """Check presence and same-process ordering of the capture lifecycle marks."""
    lifecycle_marks = (
        "capture_started_monotonic_ns", "stream_started_monotonic_ns",
        "first_valid_frame_received_monotonic_ns", "last_valid_frame_received_monotonic_ns",
        "effective_reception_ended_monotonic_ns", "accepted_state_processing_drained_monotonic_ns",
        "raw_writer_closed_monotonic_ns", "feature_persist_started_monotonic_ns",
        "feature_persisted_monotonic_ns", "raw_finalized_monotonic_ns",
    )
    lifecycle_values = [timing.get(key) for key in lifecycle_marks]
    utc_trace_marks = (
        "first_valid_frame_received_at_utc", "last_valid_frame_received_at_utc",
        "effective_reception_ended_at_utc", "processing_drained_at_utc",
        "raw_writer_closed_at_utc", "feature_persisted_at_utc", "raw_finalized_at_utc",
    )
    return {
        "lifecycle_monotonic_marks_present": all(isinstance(value, int) for value in lifecycle_values),
        "lifecycle_monotonic_marks_ordered": (
            all(isinstance(value, int) for value in lifecycle_values)
            and lifecycle_values == sorted(lifecycle_values)
        ),
        "utc_trace_marks_present": all(timing.get(key) for key in utc_trace_marks),
        "durations_nonnegative": all(
            isinstance(timing.get(key), int) and timing[key] >= 0
            for key in ("frame_receipt_span_ns", "processing_drain_ns", "raw_write_duration_ns_total",
                        "feature_persist_duration_ns", "raw_persist_duration_ns")
        ),
    }


def build_capture_command(session_dir: Path, duration_seconds: int,
                          python_executable: str = sys.executable) -> list[str]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    output = session_dir / "btc_usd_l2.parquet"
    return [
        python_executable,
        str(PROJECT_ROOT / "scripts" / "capture_kraken_l2.py"),
        "--symbol", SYMBOL,
        "--depth", str(DEPTH),
        "--seconds", str(duration_seconds),
        "--output", str(output),
        "--progress-interval", "60",
    ]


def _percentile_summary(values_ns: list[int]) -> dict:
    if not values_ns:
        return {"count": 0}
    ms = np.asarray(values_ns, dtype=np.float64) / 1e6
    return {
        "count": len(ms), "zero_count": int(np.count_nonzero(ms == 0)),
        "zero_percent": float(np.mean(ms == 0) * 100),
        "min_ms": float(ms.min()), "median_ms": float(np.median(ms)),
        "p95_ms": float(np.quantile(ms, .95)), "p99_ms": float(np.quantile(ms, .99)),
        "max_ms": float(ms.max()),
    }


def latency_trends(raw_path: Path, feature_path: Path, block_seconds: int = 300) -> dict:
    raw = pd.read_parquet(raw_path)
    features = pd.read_parquet(feature_path)
    raw_by_id = raw.set_index("capture_row_id")
    frame0 = int(raw["frame_received_monotonic_ns"].iloc[0])

    process_bins: dict[int, list[int]] = {}
    process_delay = (raw["state_validated_monotonic_ns"]
                     - raw["frame_received_monotonic_ns"]).astype("int64")
    elapsed_sec = ((raw["frame_received_monotonic_ns"].astype("int64") - frame0) / 1e9)
    for block, delay in zip((elapsed_sec // block_seconds).astype(int), process_delay):
        process_bins.setdefault(int(block), []).append(int(delay))

    feature_bins: dict[int, list[int]] = {}
    for row in features.itertuples(index=False):
        trigger_id = int(row.feature_trigger_capture_row_id)
        trigger_received = int(raw_by_id.loc[trigger_id, "frame_received_monotonic_ns"])
        block = int((trigger_received - frame0) / 1e9 // block_seconds)
        feature_bins.setdefault(block, []).append(
            int(row.feature_ready_monotonic_ns) - trigger_received
        )
    return {
        "block_seconds": block_seconds,
        "queue_depth_or_websocket_backlog_measured": False,
        "state_receive_to_crc_validation_by_elapsed_block": {
            str(block): _percentile_summary(values) for block, values in sorted(process_bins.items())
        },
        "trigger_receive_to_feature_ready_by_elapsed_block": {
            str(block): _percentile_summary(values) for block, values in sorted(feature_bins.items())
        },
        "interpretation": "Observed latency trends only; no direct queue depth or network socket-arrival timestamp is available.",
    }


def locate_manifest(raw_path: Path) -> Path | None:
    normal = raw_path.with_suffix(raw_path.suffix + ".manifest.json")
    if normal.is_file():
        return normal
    candidates = sorted(raw_path.parent.glob(raw_path.name + ".manifest.*.incomplete.json"))
    return candidates[-1] if candidates else None


def audit_session_artifacts(session_dir: Path, duration_seconds: int,
                            child_return_code: int, child_elapsed_ns: int) -> dict:
    raw_path = session_dir / "btc_usd_l2.parquet"
    manifest_path = locate_manifest(raw_path)
    if manifest_path is None:
        return {
            "status": "INCOMPLETE", "reasons": ["capture manifest missing"],
            "child_return_code": child_return_code,
            "child_process_elapsed_ns": child_elapsed_ns,
        }

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timing = manifest.get("timing", {})
    timing_checks = audit_timing_contract(timing)
    receipt_path = session_dir / manifest.get("audit_receipt_file", "")
    checks = {
        "child_exit_zero": child_return_code == 0,
        "manifest_status_success": manifest.get("status") == "SUCCESS" and manifest.get("capture_complete") is True,
        "required_instrument": (manifest.get("exchange"), manifest.get("symbol"), manifest.get("channel"), manifest.get("depth"))
            == (EXCHANGE, SYMBOL, CHANNEL, DEPTH),
        "protocol_hash_matches": manifest.get("protocol_sha256") == EXPECTED_PROTOCOL_SHA256,
        "schema_version_3": manifest.get("capture_schema_version") == 3,
        **timing_checks,
        "manifest_exists": manifest_path.is_file(),
        "receipt_exists": receipt_path.is_file(),
    }
    receipt = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    checks["receipt_verified_manifest_hash"] = bool(
        receipt.get("status") == "VERIFIED"
        and receipt.get("manifest_sha256") == sha256_file(manifest_path)
        and receipt.get("checks", {}).get("all_checks_pass") is True
    )
    receipt_marks = [receipt.get(key) for key in (
        "manifest_write_started_monotonic_ns", "manifest_write_finished_monotonic_ns",
        "manifest_verified_monotonic_ns")]
    checks["manifest_write_and_verification_ordered"] = (
        all(isinstance(value, int) for value in receipt_marks)
        and receipt_marks == sorted(receipt_marks)
        and isinstance(receipt.get("manifest_write_duration_ns"), int)
        and receipt["manifest_write_duration_ns"] >= 0
        and isinstance(receipt.get("manifest_verification_duration_ns"), int)
        and receipt["manifest_verification_duration_ns"] >= 0
    )

    validation = None
    raw_available = raw_path.is_file()
    feature_name = manifest.get("feature_output_file")
    feature_path = session_dir / feature_name if feature_name else None
    if raw_available and feature_path and feature_path.is_file() and manifest.get("status") == "SUCCESS":
        from scripts.validate_online_v3_capture import validate

        validation = validate(raw_path, duration_limit_seconds=float(duration_seconds))
        checks["online_batch_causal_audit_pass"] = (
            validation["status"] == "PASS_ONLINE_TIMING_SMOKE"
            and all(validation["checks"].values())
        )
        checks["output_hashes_match_manifest"] = (
            sha256_file(raw_path) == manifest.get("output_sha256")
            and sha256_file(feature_path) == manifest.get("feature_output_sha256")
        )
    else:
        checks["online_batch_causal_audit_pass"] = False
        checks["output_hashes_match_manifest"] = False

    passed = all(checks.values())
    reasons = [name for name, ok in checks.items() if not ok]
    receipt_timing = {
        key: receipt.get(key) for key in (
            "manifest_write_started_monotonic_ns", "manifest_write_finished_monotonic_ns",
            "manifest_verified_monotonic_ns", "manifest_write_duration_ns",
            "manifest_verification_duration_ns")
    } if receipt else {}
    trends = latency_trends(raw_path, feature_path) if passed and feature_path else None
    return {
        "status": "PASS" if passed else ("INCOMPLETE" if manifest.get("status") != "SUCCESS" else "FAIL"),
        "checks": checks, "reasons": reasons,
        "session_id": session_dir.name,
        "instrument": {"exchange": manifest.get("exchange"), "symbol": manifest.get("symbol"),
                       "channel": manifest.get("channel"), "depth": manifest.get("depth")},
        "manifest_file": manifest_path.name,
        "manifest_sha256": sha256_file(manifest_path),
        "raw_file": raw_path.name if raw_available else None,
        "raw_sha256": sha256_file(raw_path) if raw_available else None,
        "feature_file": feature_path.name if feature_path and feature_path.is_file() else None,
        "feature_sha256": sha256_file(feature_path) if feature_path and feature_path.is_file() else None,
        "audit_receipt_file": receipt_path.name if receipt_path.is_file() else None,
        "audit_receipt_sha256": sha256_file(receipt_path) if receipt_path.is_file() else None,
        "child_return_code": child_return_code,
        "child_process_elapsed_ns_parent_clock": child_elapsed_ns,
        "requested_duration_seconds": duration_seconds,
        "capture_timing": timing,
        "manifest_write_timing_from_receipt": receipt_timing,
        "adapter_counters": manifest.get("adapter_counters", {}),
        "online_feature_counters": manifest.get("online_feature_counters", {}),
        "validation": validation,
        "latency_trends": trends,
        "queue_depth_or_websocket_backlog_measured": False,
    }


def run_session(run_dir: Path, index: int, duration_seconds: int = DEFAULT_DURATION_SECONDS,
                *, process_runner=subprocess.run, python_executable: str = sys.executable) -> dict:
    session_dir = create_session_directory(run_dir, index)
    raw_path = session_dir / "btc_usd_l2.parquet"
    command = build_capture_command(session_dir, duration_seconds, python_executable)
    stdout_path, stderr_path = session_dir / "stdout.log", session_dir / "stderr.log"
    started = time.perf_counter_ns()
    with stdout_path.open("x", encoding="utf-8") as stdout, stderr_path.open("x", encoding="utf-8") as stderr:
        result = process_runner(command, cwd=str(PROJECT_ROOT), stdout=stdout, stderr=stderr, check=False)
    ended = time.perf_counter_ns()
    audit = audit_session_artifacts(session_dir, duration_seconds, result.returncode, ended - started)
    audit["runner_subprocess_started_monotonic_ns_parent"] = started
    audit["runner_subprocess_returned_monotonic_ns_parent"] = ended
    audit["stdout_sha256"] = sha256_file(stdout_path)
    audit["stderr_sha256"] = sha256_file(stderr_path)
    write_json_atomic(session_dir / "operational_session_audit.json", audit)
    return audit


def run_sessions(session_count: int = DEFAULT_SESSION_COUNT,
                 duration_seconds: int = DEFAULT_DURATION_SECONDS,
                 output_root: Path = PROJECT_ROOT / "data" / "v3_operational_readiness") -> dict:
    if session_count < 1 or duration_seconds < 1:
        raise ValueError("session_count and duration_seconds must be positive")
    protocol_info = preflight_protocol()
    run_dir = create_run_directory(output_root)
    sessions = []
    for index in range(1, session_count + 1):
        result = run_session(run_dir, index, duration_seconds)
        sessions.append(result)
        if result["status"] != "PASS":
            break
    overall = "PASS" if len(sessions) == session_count and all(s["status"] == "PASS" for s in sessions) else "PARTIAL"
    summary = {
        "runner_manifest_schema_version": 1,
        "purpose": "operational readiness only; no predictive or economic analysis",
        "status": overall,
        "protocol": protocol_info,
        "instrument": {"exchange": EXCHANGE, "symbol": SYMBOL, "channel": CHANNEL, "depth": DEPTH},
        "requested_session_count": session_count,
        "duration_seconds_per_session": duration_seconds,
        "session_count_completed_or_attempted": len(sessions),
        "session_directory": str(run_dir),
        "sessions": sessions,
        "queue_depth_or_websocket_backlog_measured": False,
    }
    write_json_atomic(run_dir / "operational_run_manifest.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=DEFAULT_SESSION_COUNT)
    parser.add_argument("--duration-seconds", type=int, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--output-root", type=Path,
                        default=PROJECT_ROOT / "data" / "v3_operational_readiness")
    args = parser.parse_args()
    print(json.dumps(run_sessions(args.sessions, args.duration_seconds, args.output_root), indent=2, default=str))


if __name__ == "__main__":
    main()
