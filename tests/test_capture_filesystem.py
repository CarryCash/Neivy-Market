import json
import pytest

import scripts.capture_kraken_l2 as capture
from scripts.capture_kraken_l2 import (
    capture_integrity_is_complete, capture_table_from_rows, finalize_capture_files,
    online_feature_table, sha256_file,
)


def test_complete_capture_promotes_partial_and_versions_manifest(tmp_path):
    output = tmp_path / "capture.parquet"
    partial = tmp_path / ".capture.parquet.random.partial"
    manifest_path = tmp_path / "capture.parquet.manifest.json"
    partial.write_bytes(b"complete-data")
    manifest_path.write_text("old-manifest", encoding="utf-8")

    final_output, final_manifest = finalize_capture_files(
        partial, output, manifest_path, {"status": "SUCCESS"}, True
    )

    assert final_output == output
    assert final_manifest == manifest_path
    assert output.read_bytes() == b"complete-data"
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["output_file"] == output.name
    assert saved["output_sha256"] == sha256_file(output)
    receipt = json.loads((tmp_path / "capture_audit_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "VERIFIED"
    assert receipt["session_status"] == "SUCCESS"
    assert receipt["manifest_sha256"] == sha256_file(manifest_path)
    assert receipt["manifest_write_finished_monotonic_ns"] >= receipt["manifest_write_started_monotonic_ns"]


def test_incomplete_capture_does_not_replace_existing_artifacts(tmp_path):
    output = tmp_path / "capture.parquet"
    partial = tmp_path / ".capture.parquet.random.partial"
    manifest_path = tmp_path / "capture.parquet.manifest.json"
    output.write_bytes(b"preserve-data")
    manifest_path.write_text("preserve-manifest", encoding="utf-8")
    partial.write_bytes(b"partial-data")

    final_output, final_manifest = finalize_capture_files(
        partial, output, manifest_path, {"status": "INCOMPLETE"}, False
    )

    assert final_output == partial
    assert final_manifest != manifest_path
    assert output.read_bytes() == b"preserve-data"
    assert manifest_path.read_text(encoding="utf-8") == "preserve-manifest"
    saved = json.loads(final_manifest.read_text(encoding="utf-8"))
    assert saved["output_file"] == partial.name
    assert saved["output_sha256"] == sha256_file(partial)
    receipt = json.loads((tmp_path / "capture_audit_receipt.json").read_text(encoding="utf-8"))
    assert receipt["session_status"] == "INCOMPLETE"


def test_audit_receipt_write_failure_downgrades_success_manifest(tmp_path, monkeypatch):
    output = tmp_path / "capture.parquet"
    partial = tmp_path / ".capture.parquet.partial"
    manifest_path = tmp_path / "capture.parquet.manifest.json"
    partial.write_bytes(b"raw")
    real_atomic_write = capture._atomic_write_text

    def fail_receipt(path, content):
        if path.name.endswith("_audit_receipt.json"):
            raise OSError("simulated receipt write failure")
        return real_atomic_write(path, content)

    monkeypatch.setattr(capture, "_atomic_write_text", fail_receipt)
    with pytest.raises(OSError, match="simulated receipt write failure"):
        capture.finalize_capture_files(partial, output, manifest_path, {"status": "SUCCESS"}, True)
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["status"] == "INCOMPLETE"
    assert saved["capture_complete"] is False


def test_capture_parquet_schema_adds_availability_fields_and_version():
    row = {
        "timestamp": "2026-10-24T12:00:00.000000Z",
        "received_at": "2026-10-24T12:00:00.001000Z",
        "received_monotonic_ns": 100,
        "capture_row_id": 0,
        "processed_at": "2026-10-24T12:00:00.002000Z",
        "processed_monotonic_ns": 200,
        "frame_received_monotonic_ns": 110,
        "state_processed_monotonic_ns": 150,
        "state_validated_monotonic_ns": 175,
        "symbol": "BTC/USDT", "checksum": 123,
    }
    for level in range(1, 11):
        row.update({f"bid_px_{level}": 100.0 - level, f"bid_qty_{level}": 1.0,
                    f"ask_px_{level}": 101.0 + level, f"ask_qty_{level}": 1.0})

    table = capture_table_from_rows([row])

    assert table.schema.metadata[b"navier_capture_schema_version"] == b"3"
    assert str(table.schema.field("timestamp").type) == "timestamp[ns, tz=UTC]"
    assert str(table.schema.field("received_at").type) == "timestamp[ns, tz=UTC]"
    assert str(table.schema.field("processed_at").type) == "timestamp[ns, tz=UTC]"
    assert table.schema.field("received_monotonic_ns").type.bit_width == 64
    assert table.schema.field("processed_monotonic_ns").type.bit_width == 64
    for name in ("frame_received_monotonic_ns", "state_processed_monotonic_ns",
                 "state_validated_monotonic_ns"):
        assert table.schema.field(name).type.bit_width == 64
    assert table.schema.field("capture_row_id").type.bit_width == 64


def test_online_feature_sidecar_schema_is_versioned_even_when_warmup_has_no_rows():
    table = online_feature_table([])
    assert table.schema.metadata[b"navier_online_feature_schema_version"] == b"1"
    assert table.num_rows == 0
    assert table.schema.field("feature_ready_monotonic_ns").type.bit_width == 64
    assert table.schema.field("feature_trigger_capture_row_id").type.bit_width == 64


def test_reconnect_or_second_snapshot_never_counts_as_a_clean_operational_session():
    clean = {"snapshots": 1, "reconnects": 0, "connection_errors": 0,
             "subscription_errors": 0, "checksum_failures": 0,
             "out_of_order_timestamps": 0, "malformed_messages": 0}
    assert capture_integrity_is_complete(100, "VALID", clean)
    assert not capture_integrity_is_complete(100, "VALID", {**clean, "reconnects": 1, "snapshots": 2})
    assert not capture_integrity_is_complete(100, "VALID", {**clean, "snapshots": 2})
    assert not capture_integrity_is_complete(100, "VALID", {**clean, "checksum_failures": 1})


