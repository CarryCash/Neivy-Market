import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from navier_lab.schema import ASK_PX, ASK_QTY, BID_PX, BID_QTY
from scripts.replay_v3_timing import duration_summary, run


def test_duration_summary_reports_resolution_and_zero_samples():
    result = duration_summary([0, 0, 1_000_000, 2_000_000])
    assert result["count"] == 4
    assert result["zero_count"] == 2
    assert result["zero_percent"] == 50
    assert result["median_ms"] == 0.5


def test_replay_preserves_source_and_marks_feature_readiness_as_batch(tmp_path):
    base = pd.Timestamp("2026-10-24T17:00:00Z")
    rows = []
    for i in range(3):
        row = {
            "timestamp": base + pd.Timedelta(milliseconds=100 * (i + 1)),
            "received_at": base + pd.Timedelta(milliseconds=100 * (i + 1)),
            "processed_at": base + pd.Timedelta(milliseconds=100 * (i + 1) + 1),
            "received_monotonic_ns": 1_000 + i * 10,
            "processed_monotonic_ns": 1_001 + i * 10,
            "capture_row_id": i, "symbol": "BTC/USD", "checksum": 123 + i,
        }
        for level in range(1, 11):
            row[f"bid_px_{level}"] = 100_000 - level
            row[f"ask_px_{level}"] = 100_000 + level
            row[f"bid_qty_{level}"] = 0.1
            row[f"ask_qty_{level}"] = 0.2
        rows.append(row)
    source = tmp_path / "capture.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False), source)
    before = source.read_bytes()
    result = run(source, tmp_path / "replay")

    assert source.read_bytes() == before
    assert result["source_sha256_before"] == result["source_sha256_after"]
    assert result["feature_availability"]["capture_to_feature_ready_latency_measured"] is False
    assert result["cross_clock_policy"].startswith("No subtraction")
    assert (tmp_path / "replay" / "features_v3.parquet").is_file()
    assert (tmp_path / "replay" / "feature_availability_replay.csv").is_file()


def test_replay_refuses_to_overwrite_output_directory(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with __import__("pytest").raises(FileExistsError):
        run(tmp_path / "missing.parquet", output)
