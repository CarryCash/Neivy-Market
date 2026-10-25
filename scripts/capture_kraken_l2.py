"""Capture validated Kraken Spot L2 book states to Parquet; no trading commands."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from navier_lab.kraken_ws_v2 import KrakenSpotBookV2Adapter
from navier_lab.online_v3 import OnlineV3FeaturePublisher


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _empirical_perf_counter(samples: int = 100_000) -> dict:
    readings = [time.perf_counter_ns() for _ in range(samples + 1)]
    deltas = [right - left for left, right in zip(readings, readings[1:])]
    positive = [delta for delta in deltas if delta > 0]
    return {
        "successive_call_differences": samples,
        "zero_count": sum(delta == 0 for delta in deltas),
        "min_positive_ns": min(positive) if positive else None,
        "median_positive_ns": sorted(positive)[len(positive) // 2] if positive else None,
        "max_ns": max(deltas),
    }


def _atomic_write_text(path: Path, content: str) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def capture_integrity_is_complete(total_rows: int, book_status: str, counters: dict) -> bool:
    """Strictly accept only one uninterrupted snapshot-based capture session."""
    return bool(
        total_rows > 0
        and book_status == "VALID"
        and counters.get("snapshots", 0) == 1
        and counters.get("reconnects", 0) == 0
        and counters.get("connection_errors", 0) == 0
        and counters.get("subscription_errors", 0) == 0
        and counters.get("checksum_failures", 0) == 0
        and counters.get("out_of_order_timestamps", 0) == 0
        and counters.get("malformed_messages", 0) == 0
    )


def finalize_capture_files(partial_output: Path, output: Path, manifest_path: Path,
                           manifest: dict, capture_completed: bool) -> tuple[Path | None, Path]:
    """Promote a complete capture atomically; keep incomplete artifacts separate."""
    final_output = output if capture_completed else (partial_output if partial_output.exists() else None)
    timing = manifest.setdefault("timing", {})
    raw_finalize_started = time.perf_counter_ns()
    if capture_completed:
        os.replace(partial_output, output)
    manifest["output_file"] = final_output.name if final_output else None
    manifest["output_sha256"] = sha256_file(final_output) if final_output else None
    final_manifest = (manifest_path if capture_completed else
                      manifest_path.with_name(f"{manifest_path.stem}.{uuid.uuid4().hex}.incomplete.json"))
    receipt_path = output.with_name(f"{output.stem}_audit_receipt.json")
    manifest["manifest_file"] = final_manifest.name
    manifest["audit_receipt_file"] = receipt_path.name
    timing["raw_finalized_monotonic_ns"] = time.perf_counter_ns()
    timing["raw_finalize_duration_ns"] = timing["raw_finalized_monotonic_ns"] - raw_finalize_started
    timing["raw_persist_duration_ns"] = (
        timing["raw_finalized_monotonic_ns"] - timing["raw_persist_started_monotonic_ns"]
        if timing.get("raw_persist_started_monotonic_ns") is not None else None
    )
    timing["raw_finalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["ended_at_utc"] = timing["raw_finalized_at_utc"]
    if timing.get("capture_started_monotonic_ns") is not None:
        timing["capture_through_raw_persisted_ns"] = (
            timing["raw_finalized_monotonic_ns"] - timing["capture_started_monotonic_ns"]
        )
        manifest["elapsed_seconds"] = round(timing["capture_through_raw_persisted_ns"] / 1e9, 6)
    if (timing.get("stream_started_monotonic_ns") is not None
            and timing.get("effective_reception_ended_monotonic_ns") is not None):
        manifest["collection_elapsed_seconds"] = round(
            (timing["effective_reception_ended_monotonic_ns"]
             - timing["stream_started_monotonic_ns"]) / 1e9, 6
        )
    timing["manifest_write_started_monotonic_ns"] = time.perf_counter_ns()
    _atomic_write_text(final_manifest, json.dumps(manifest, indent=2))
    manifest_write_finished = time.perf_counter_ns()
    try:
        readback = json.loads(final_manifest.read_text(encoding="utf-8"))
        checks = {
            "manifest_json_readable": isinstance(readback, dict),
            "manifest_status_matches": readback.get("status") == manifest.get("status"),
            "output_hash_matches": bool(final_output and final_output.is_file()
                                         and sha256_file(final_output) == manifest.get("output_sha256")),
        }
        if "feature_output_file" not in manifest:
            checks["feature_hash_matches"] = True  # legacy helper call without a sidecar contract
        else:
            feature_file = output.with_name(manifest.get("feature_output_file") or "")
            checks["feature_hash_matches"] = bool(
                manifest.get("feature_output_file") and feature_file.is_file()
                and sha256_file(feature_file) == manifest.get("feature_output_sha256")
            )
        verified = time.perf_counter_ns()
        checks["all_checks_pass"] = all(checks.values())
        receipt = {
            "audit_receipt_schema_version": 1,
            "status": "VERIFIED" if checks["all_checks_pass"] else "FAILED",
            "session_status": manifest.get("status"),
            "manifest_file": final_manifest.name,
            "manifest_sha256": sha256_file(final_manifest),
            "manifest_write_started_monotonic_ns": timing["manifest_write_started_monotonic_ns"],
            "manifest_write_finished_monotonic_ns": manifest_write_finished,
            "manifest_verified_monotonic_ns": verified,
            "manifest_write_duration_ns": manifest_write_finished - timing["manifest_write_started_monotonic_ns"],
            "manifest_verification_duration_ns": verified - manifest_write_finished,
            "clock": "time.perf_counter_ns; same capture process/session",
            "checks": checks,
        }
        _atomic_write_text(receipt_path, json.dumps(receipt, indent=2))
        if json.loads(receipt_path.read_text(encoding="utf-8")).get("status") != "VERIFIED":
            raise IOError("audit receipt readback failed")
    except Exception as exc:
        # A failed receipt must not leave a successful session manifest.
        manifest["status"] = "INCOMPLETE"
        manifest["capture_complete"] = False
        manifest["error"] = f"audit_receipt_failure: {type(exc).__name__}: {exc}"
        _atomic_write_text(final_manifest, json.dumps(manifest, indent=2))
        raise
    return final_output, final_manifest


def capture_table_from_rows(rows):
    """Build the additive/versioned Parquet batch schema for a capture chunk."""
    import pandas as pd
    import pyarrow as pa

    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["received_at"] = pd.to_datetime(frame["received_at"], utc=True)
    frame["processed_at"] = pd.to_datetime(frame["processed_at"], utc=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"navier_capture_schema_version"] = b"3"
    return table.replace_schema_metadata(metadata)


def online_feature_table(rows):
    """Build a versioned sidecar schema, including a typed empty capture."""
    import pandas as pd
    import pyarrow as pa

    from navier_lab.features import NAVIER_V3

    columns = ["feature_row_id", "feature_time_utc", "capture_row_id",
               "feature_trigger_capture_row_id", "dependency_capture_row_ids_json", "state_source",
               "state_selection_started_monotonic_ns", "state_selected_monotonic_ns",
               "feature_compute_started_monotonic_ns", "feature_ready_monotonic_ns",
               "frame_received_monotonic_ns", "state_processed_monotonic_ns",
               "state_validated_monotonic_ns", *NAVIER_V3]
    schema = pa.schema([
        pa.field("feature_row_id", pa.int64()),
        pa.field("feature_time_utc", pa.timestamp("ns", tz="UTC")),
        pa.field("capture_row_id", pa.int64()),
        pa.field("feature_trigger_capture_row_id", pa.int64()),
        pa.field("dependency_capture_row_ids_json", pa.string()),
        pa.field("state_source", pa.string()),
        *[pa.field(name, pa.int64()) for name in (
            "state_selection_started_monotonic_ns", "state_selected_monotonic_ns",
            "feature_compute_started_monotonic_ns", "feature_ready_monotonic_ns",
            "frame_received_monotonic_ns", "state_processed_monotonic_ns",
            "state_validated_monotonic_ns")],
        *[pa.field(name, pa.float64()) for name in NAVIER_V3],
    ], metadata={b"navier_online_feature_schema_version": b"1"})
    frame = pd.DataFrame(rows, columns=columns)
    if not frame.empty:
        frame["feature_time_utc"] = pd.to_datetime(frame["feature_time_utc"], utc=True)
    return pa.Table.from_pandas(frame, schema=schema, preserve_index=False)


async def run(args) -> None:
    import pyarrow.parquet as pq

    output = Path(args.output).expanduser().resolve()
    feature_output = (Path(args.features_output).expanduser().resolve()
                      if args.features_output else
                      output.with_name(f"{output.stem}_features_v3_online.parquet"))
    output.parent.mkdir(parents=True, exist_ok=True)
    feature_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    audit_receipt_path = output.with_name(f"{output.stem}_audit_receipt.json")
    if any(path.exists() for path in (output, manifest_path, feature_output, audit_receipt_path)) and not args.overwrite:
        raise FileExistsError("Capture output, feature output, manifest, or audit receipt already exists; choose unique paths or pass --overwrite")
    partial_output = output.with_name(f".{output.name}.{uuid.uuid4().hex}.partial")

    adapter = KrakenSpotBookV2Adapter(args.symbol, args.depth)
    started = datetime.now(timezone.utc)
    monotonic_start = time.monotonic()
    collection_monotonic_start = time.monotonic()
    capture_started_perf_ns = time.perf_counter_ns()
    stream_started_perf_ns = None
    reception_ended_perf_ns = None
    processing_drained_perf_ns = None
    reception_ended_at_utc = None
    processing_drained_at_utc = None
    first_frame_received_perf_ns = None
    last_frame_received_perf_ns = None
    first_frame_received_at_utc = None
    last_frame_received_at_utc = None
    raw_write_duration_ns_total = 0
    raw_write_count = 0
    raw_write_first_started_perf_ns = None
    raw_write_last_finished_perf_ns = None
    rows, writer, total = [], None, 0
    feature_rows = []
    feature_publisher = OnlineV3FeaturePublisher()
    error = None
    capture_completed = False

    def flush():
        nonlocal rows, writer, raw_write_duration_ns_total, raw_write_count
        nonlocal raw_write_first_started_perf_ns, raw_write_last_finished_perf_ns
        if not rows: return
        table = capture_table_from_rows(rows)
        if writer is None: writer = pq.ParquetWriter(partial_output, table.schema, compression="zstd")
        write_started = time.perf_counter_ns()
        if raw_write_first_started_perf_ns is None:
            raw_write_first_started_perf_ns = write_started
        writer.write_table(table)
        write_finished = time.perf_counter_ns()
        raw_write_duration_ns_total += write_finished - write_started
        raw_write_count += 1
        raw_write_last_finished_perf_ns = write_finished
        rows = []

    last_heartbeat = time.monotonic()
    try:
        stream_started_perf_ns = time.perf_counter_ns()
        async for row in adapter.stream(args.seconds):
            if first_frame_received_perf_ns is None:
                first_frame_received_perf_ns = int(row["frame_received_monotonic_ns"])
                first_frame_received_at_utc = row["received_at"].isoformat()
            last_frame_received_perf_ns = int(row["frame_received_monotonic_ns"])
            last_frame_received_at_utc = row["received_at"].isoformat()
            row["capture_row_id"] = total
            feature_publisher.consume(row, feature_rows.append)
            rows.append(row); total += 1
            if len(rows) >= args.batch_size: flush()
            now = time.monotonic()
            if now - last_heartbeat >= args.progress_interval:
                elapsed = now - monotonic_start
                pct = min(100.0, elapsed / args.seconds * 100)
                label = f"[progress] elapsed={elapsed:.0f}s/{args.seconds:.0f}s ({pct:.1f}pct) rows={total}"
                print(label, flush=True)
                last_heartbeat = now
        reception_ended_perf_ns = time.perf_counter_ns()
        reception_ended_at_utc = datetime.now(timezone.utc).isoformat()
        # All yielded valid rows are synchronously consumed before requesting
        # the next frame, so accepted-row work is drained when this loop ends.
        processing_drained_perf_ns = time.perf_counter_ns()
        processing_drained_at_utc = datetime.now(timezone.utc).isoformat()
        integrity_counters = adapter.counters
        capture_completed = capture_integrity_is_complete(total, adapter.status, integrity_counters)
        if not capture_completed and error is None:
            error = "no_valid_book_rows" if total == 0 else "integrity_or_transport_errors_observed"
    except KeyboardInterrupt:
        error = "interrupted_by_user"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        persistence_error = None
        try:
            flush()
        except Exception as exc:
            persistence_error = f"raw_flush_failure: {type(exc).__name__}: {exc}"
        try:
            if writer is not None:
                writer.close()
        except Exception as exc:
            persistence_error = f"raw_close_failure: {type(exc).__name__}: {exc}"
        raw_writer_closed_perf_ns = time.perf_counter_ns()
        raw_writer_closed_at_utc = datetime.now(timezone.utc).isoformat()
        if persistence_error:
            capture_completed = False
            error = persistence_error

        feature_persistence_started_perf_ns = time.perf_counter_ns()
        feature_partial = feature_output.with_name(f".{feature_output.name}.{uuid.uuid4().hex}.partial")
        feature_final = feature_output if capture_completed else feature_output.with_name(
            f"{feature_output.stem}.{uuid.uuid4().hex}.incomplete{feature_output.suffix}"
        )
        feature_persistence_error = None
        feature_persisted_perf_ns = None
        feature_persisted_at_utc = None
        feature_sha = None
        try:
            feature_table = online_feature_table(feature_rows)
            pq.write_table(feature_table, feature_partial, compression="zstd")
            os.replace(feature_partial, feature_final)
            feature_sha = sha256_file(feature_final)
            feature_persisted_perf_ns = time.perf_counter_ns()
            feature_persisted_at_utc = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            feature_persistence_error = f"feature_persistence_failure: {type(exc).__name__}: {exc}"
            capture_completed = False
            error = feature_persistence_error
            if feature_partial.exists():
                feature_final = feature_output.with_name(
                    f"{feature_output.stem}.{uuid.uuid4().hex}.incomplete{feature_output.suffix}"
                )
                os.replace(feature_partial, feature_final)
                feature_sha = sha256_file(feature_final)

        ended = datetime.now(timezone.utc)
        timing = {
            "clock": "time.perf_counter_ns; values are local to this capture process/session",
            "capture_started_monotonic_ns": capture_started_perf_ns,
            "stream_started_monotonic_ns": stream_started_perf_ns,
            "first_valid_frame_received_monotonic_ns": first_frame_received_perf_ns,
            "last_valid_frame_received_monotonic_ns": last_frame_received_perf_ns,
            "effective_reception_ended_monotonic_ns": reception_ended_perf_ns,
            "accepted_state_processing_drained_monotonic_ns": processing_drained_perf_ns,
            "frame_receipt_span_ns": (last_frame_received_perf_ns - first_frame_received_perf_ns
                                      if first_frame_received_perf_ns is not None
                                      and last_frame_received_perf_ns is not None else None),
            "processing_drain_ns": (processing_drained_perf_ns - reception_ended_perf_ns
                                    if processing_drained_perf_ns is not None
                                    and reception_ended_perf_ns is not None else None),
            "raw_write_first_started_monotonic_ns": raw_write_first_started_perf_ns,
            "raw_write_last_finished_monotonic_ns": raw_write_last_finished_perf_ns,
            "raw_write_duration_ns_total": raw_write_duration_ns_total,
            "raw_write_batches": raw_write_count,
            "raw_writer_closed_monotonic_ns": raw_writer_closed_perf_ns,
            "raw_persist_started_monotonic_ns": raw_write_first_started_perf_ns,
            "feature_persist_started_monotonic_ns": feature_persistence_started_perf_ns,
            "feature_persisted_monotonic_ns": feature_persisted_perf_ns,
            "feature_persist_duration_ns": (
                feature_persisted_perf_ns - feature_persistence_started_perf_ns
                if feature_persisted_perf_ns is not None else None
            ),
            "first_valid_frame_received_at_utc": first_frame_received_at_utc,
            "last_valid_frame_received_at_utc": last_frame_received_at_utc,
            "effective_reception_ended_at_utc": reception_ended_at_utc,
            "processing_drained_at_utc": processing_drained_at_utc,
            "raw_writer_closed_at_utc": raw_writer_closed_at_utc,
            "feature_persisted_at_utc": feature_persisted_at_utc,
        }
        manifest = {
            "project": "NAVIER", "version": "001.12", "manifest_schema_version": 2,
            "capture_schema_version": 3,
            "status": "SUCCESS" if capture_completed else "INCOMPLETE",
            "exchange": "Kraken Spot WebSocket API v2", "endpoint": "wss://ws.kraken.com/v2",
            "channel": "book", "symbol": args.symbol, "depth": args.depth,
            "mode": "public_market_data_only_no_orders", "started_at_utc": started.isoformat(),
            "protocol_sha256": sha256_file(PROJECT_ROOT / "NAVIER_V3_PROTOCOL.md"),
            "ended_at_utc": ended.isoformat(), "elapsed_seconds": round(time.monotonic()-monotonic_start, 3),
            "requested_capture_seconds": args.seconds,
            "collection_elapsed_seconds": round(time.monotonic()-collection_monotonic_start, 3),
            "valid_rows_written": total, "capture_complete": capture_completed,
            "adapter_counters": adapter.counters, "final_book_status": adapter.status,
            "adapter_last_connection_error": adapter.last_connection_error,
            "error": error, "checksum": "CRC32: top 10 asks ascending then top 10 bids descending",
            "feature_output_file": None,
            "feature_output_sha256": feature_sha,
            "feature_output_incomplete_file": feature_final.name if not capture_completed else None,
            "online_feature_counters": feature_publisher.counters(),
            "timing": timing,
            "clock": {
                "capture_and_features_same_process": True,
                "perf_counter": {key: getattr(time.get_clock_info("perf_counter"), key)
                                 for key in ("implementation", "resolution", "monotonic", "adjustable")},
                "perf_counter_empirical": _empirical_perf_counter(),
                "perf_counter_nanoseconds": "frame receipt, candidate state processed/CRC validated, feature compute and synchronous in-process feature sink; comparable within this process/session",
            },
            "timestamp_fields": {
                "timestamp": "exchange RFC3339 event time, UTC",
                "received_at": "local UTC wall clock sampled immediately after websocket frame receipt",
                "received_monotonic_ns": "local monotonic nanoseconds sampled at frame receipt; session-local",
                "processed_at": "local UTC wall clock after parse, book update, and checksum validation",
                "processed_monotonic_ns": "local monotonic nanoseconds after validation; session-local",
                "frame_received_monotonic_ns": "time.perf_counter_ns at WebSocket frame receipt",
                "state_processed_monotonic_ns": "time.perf_counter_ns after candidate L2 update and shape validation, before CRC check",
                "state_validated_monotonic_ns": "time.perf_counter_ns after successful CRC and state commit; absent on invalid messages",
                "state_selection_started_monotonic_ns": "time.perf_counter_ns before the causal resampler selects the interval state",
                "state_selected_monotonic_ns": "time.perf_counter_ns after causal resampling has selected interval states",
                "feature_compute_started_monotonic_ns": "time.perf_counter_ns immediately before frozen V3 batch function on current causal resample",
                "feature_ready_monotonic_ns": "time.perf_counter_ns immediately before synchronous in-process feature sink receives a valid V3 row; sidecar is persisted at capture finalization",
            },
        }
        manifest["feature_output_file"] = feature_final.name
        if feature_persistence_error:
            manifest["status"] = "INCOMPLETE"
            manifest["capture_complete"] = False
            manifest["error"] = feature_persistence_error
        finalize_capture_files(partial_output, output, manifest_path, manifest, capture_completed)
        print(json.dumps(manifest, indent=2))
    if not capture_completed:
        raise RuntimeError(error or "capture_incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--output", default="data/kraken/btc_usdt_l2.parquet")
    parser.add_argument("--features-output", default=None,
                        help="Versioned online V3 feature sidecar; defaults beside --output")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--progress-interval", type=float, default=120.0,
                        help="Print a heartbeat line every N seconds (default: 120)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0: parser.error("--seconds must be > 0")
    if args.batch_size < 1: parser.error("--batch-size must be >= 1")
    asyncio.run(run(args))


if __name__ == "__main__": main()
