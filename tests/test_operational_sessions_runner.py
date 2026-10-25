from types import SimpleNamespace

import pytest

from scripts.run_operational_sessions import (
    audit_timing_contract, build_capture_command, create_run_directory, create_session_directory,
    run_session,
)


def test_capture_command_is_pinned_to_protocol_instrument_and_never_overwrites(tmp_path):
    command = build_capture_command(tmp_path, 2400, "python-test")
    assert command[0] == "python-test"
    assert command[command.index("--symbol") + 1] == "BTC/USD"
    assert command[command.index("--depth") + 1] == "10"
    assert command[command.index("--seconds") + 1] == "2400"
    assert "--overwrite" not in command
    assert "BTC/USDT" not in command


def test_run_and_session_directories_fail_safely_on_collisions(tmp_path):
    run_dir = create_run_directory(tmp_path, "run-fixed")
    with pytest.raises(FileExistsError):
        create_run_directory(tmp_path, "run-fixed")
    session_dir = create_session_directory(run_dir, 1)
    with pytest.raises(FileExistsError):
        create_session_directory(run_dir, 1)
    assert session_dir.is_dir()


def test_timing_contract_separates_ordered_monotonic_marks_from_utc_trace():
    timing = {
        "capture_started_monotonic_ns": 1,
        "stream_started_monotonic_ns": 2,
        "first_valid_frame_received_monotonic_ns": 3,
        "last_valid_frame_received_monotonic_ns": 4,
        "effective_reception_ended_monotonic_ns": 5,
        "accepted_state_processing_drained_monotonic_ns": 6,
        "raw_writer_closed_monotonic_ns": 7,
        "feature_persist_started_monotonic_ns": 8,
        "feature_persisted_monotonic_ns": 9,
        "raw_finalized_monotonic_ns": 10,
        "first_valid_frame_received_at_utc": "2026-10-24T00:00:00+00:00",
        "last_valid_frame_received_at_utc": "2026-10-24T00:00:01+00:00",
        "effective_reception_ended_at_utc": "2026-10-24T00:00:02+00:00",
        "processing_drained_at_utc": "2026-10-24T00:00:02+00:00",
        "raw_writer_closed_at_utc": "2026-10-24T00:00:03+00:00",
        "feature_persisted_at_utc": "2026-10-24T00:00:04+00:00",
        "raw_finalized_at_utc": "2026-10-24T00:00:05+00:00",
        "frame_receipt_span_ns": 1, "processing_drain_ns": 1,
        "raw_write_duration_ns_total": 1, "feature_persist_duration_ns": 1,
        "raw_persist_duration_ns": 1,
    }
    assert all(audit_timing_contract(timing).values())
    timing["feature_persisted_monotonic_ns"] = 0
    assert not audit_timing_contract(timing)["lifecycle_monotonic_marks_ordered"]


def test_failed_child_is_preserved_as_incomplete_and_never_promoted_to_success(tmp_path):
    run_dir = create_run_directory(tmp_path, "run-failed")

    def failed_process(command, *, cwd, stdout, stderr, check):
        stdout.write("attempted capture\n")
        stderr.write("connection unavailable\n")
        return SimpleNamespace(returncode=1)

    result = run_session(run_dir, 1, 5, process_runner=failed_process, python_executable="python-test")
    session = run_dir / "session_01_btc_usd_l2"
    assert result["status"] == "INCOMPLETE"
    assert result["child_return_code"] == 1
    assert (session / "stdout.log").read_text(encoding="utf-8") == "attempted capture\n"
    assert (session / "stderr.log").read_text(encoding="utf-8") == "connection unavailable\n"
    assert (session / "operational_session_audit.json").is_file()
