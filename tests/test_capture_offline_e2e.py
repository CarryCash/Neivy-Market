"""End-to-end deterministic capture tests without Kraken or socket access."""
from __future__ import annotations

import asyncio
import heapq
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

import scripts.capture_kraken_l2 as capture
from navier_lab.kraken_ws_v2 import KrakenSpotBookV2Adapter, kraken_book_checksum
from scripts.run_operational_sessions import audit_session_artifacts


class OfflineSelectorLoop(asyncio.SelectorEventLoop):
    """Selector loop that avoids Windows socketpair setup for socket-free tests."""
    def _make_self_pipe(self):
        self._ssock = self._csock = None

    def _write_to_self(self):
        return None

    def _close_self_pipe(self):
        self._ssock = self._csock = None

    def _run_once(self):
        """Run ready/timed callbacks without polling a selector (no sockets in tests)."""
        if self._scheduled:
            end_time = time.monotonic() + self._clock_resolution
            while self._scheduled and self._scheduled[0]._when <= end_time:
                handle = heapq.heappop(self._scheduled)
                handle._scheduled = False
                self._ready.append(handle)
        for _ in range(len(self._ready)):
            handle = self._ready.popleft()
            if not handle._cancelled:
                handle._run()


class OfflineSelectorPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        return OfflineSelectorLoop()


@contextmanager
def offline_event_loop_policy():
    original = asyncio.get_event_loop_policy()
    asyncio.set_event_loop_policy(OfflineSelectorPolicy())
    try:
        yield
    finally:
        asyncio.set_event_loop_policy(original)


def _levels(tick: int):
    mid = Decimal("60000.0") + Decimal(tick % 9) / Decimal("10")
    bids = {mid - Decimal("0.1") - Decimal(i) * Decimal("0.1"):
            Decimal("0.4") + Decimal((tick + i) % 9) / Decimal("100") for i in range(10)}
    asks = {mid + Decimal("0.1") + Decimal(i) * Decimal("0.1"):
            Decimal("0.5") + Decimal((tick + 2 * i) % 7) / Decimal("100") for i in range(10)}
    return bids, asks


class SyntheticProtocolAdapter(KrakenSpotBookV2Adapter):
    """Feed deterministic protocol-shaped messages through the real L2 adapter."""
    failure_mode = None

    async def stream(self, duration_seconds=None):
        base = datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc)
        previous_bids = previous_asks = None
        for tick in range(110):
            bids, asks = _levels(tick)
            kind = "snapshot" if tick == 0 else "update"
            timestamp = (base + timedelta(seconds=tick)).isoformat().replace("+00:00", "Z")
            checksum = kraken_book_checksum(bids, asks, depth=self.depth)
            if self.failure_mode == "bad_checksum" and tick == 4:
                checksum ^= 1
            if kind == "snapshot":
                bid_updates = [{"price": str(p), "qty": str(q)} for p, q in bids.items()]
                ask_updates = [{"price": str(p), "qty": str(q)} for p, q in asks.items()]
            else:
                bid_updates = ([{"price": str(p), "qty": "0"} for p in previous_bids]
                               + [{"price": str(p), "qty": str(q)} for p, q in bids.items()])
                ask_updates = ([{"price": str(p), "qty": "0"} for p in previous_asks]
                               + [{"price": str(p), "qty": str(q)} for p, q in asks.items()])
            message = {
                "channel": "book", "type": kind,
                "data": [{"symbol": self.symbol, "timestamp": timestamp,
                          "bids": bid_updates, "asks": ask_updates,
                          "checksum": checksum}],
            }
            self.counters["frames_received"] += 1
            row = self.process_message(message)
            if row is not None:
                yield row
            previous_bids, previous_asks = bids, asks
            if self.failure_mode == "bad_checksum" and tick == 4:
                break
            if self.failure_mode == "interrupted" and tick == 70:
                raise RuntimeError("synthetic interrupted stream")


def _args(output, *, overwrite=False):
    return SimpleNamespace(output=str(output), features_output=None, symbol="BTC/USD", depth=10,
                           seconds=110, batch_size=37, progress_interval=9999,
                           overwrite=overwrite)


def _run_capture(output, monkeypatch, failure_mode=None):
    class Adapter(SyntheticProtocolAdapter):
        pass
    Adapter.failure_mode = failure_mode
    monkeypatch.setattr(capture, "KrakenSpotBookV2Adapter", Adapter)
    with offline_event_loop_policy():
        try:
            asyncio.run(capture.run(_args(output)))
        except (RuntimeError, OSError):
            return False
    return True


def test_loop_workaround_runs_socket_free_coroutines_without_changing_production():
    original = asyncio.get_event_loop_policy()
    with offline_event_loop_policy():
        asyncio.run(asyncio.sleep(0))
    assert asyncio.get_event_loop_policy() is original


def test_valid_synthetic_protocol_flow_reconstructs_features_persists_and_audits(tmp_path, monkeypatch):
    output = tmp_path / "valid" / "btc_usd_l2.parquet"
    assert _run_capture(output, monkeypatch)
    session_dir = output.parent
    audit = audit_session_artifacts(session_dir, 110, 0, 1)
    assert audit["status"] == "PASS", audit["reasons"]
    raw = pq.read_table(output).to_pandas()
    online = pq.read_table(session_dir / "btc_usd_l2_features_v3_online.parquet").to_pandas()
    assert len(raw) == 110
    assert raw["capture_row_id"].tolist() == list(range(110))
    assert len(online) > 0
    assert audit["validation"]["checks"]["batch_online_equivalent"]
    assert audit["online_feature_counters"]["warmup_or_na_rows_not_published"] > 0
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        with offline_event_loop_policy():
            asyncio.run(capture.run(_args(output)))
    assert output.read_bytes() == before


@pytest.mark.parametrize("failure_mode", ["bad_checksum", "interrupted"])
def test_invalid_or_interrupted_synthetic_capture_is_never_clean(tmp_path, monkeypatch, failure_mode):
    output = tmp_path / failure_mode / "btc_usd_l2.parquet"
    assert not _run_capture(output, monkeypatch, failure_mode)
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if not manifest_path.is_file():
        manifests = list(output.parent.glob("*.incomplete.json"))
        assert manifests
        manifest_path = manifests[0]
    audit = audit_session_artifacts(output.parent, 110, 1, 1)
    assert audit["status"] in {"INCOMPLETE", "FAIL"}
    assert audit["status"] != "PASS"


def test_batch_online_discrepancy_is_detected_by_session_auditor(tmp_path, monkeypatch):
    output = tmp_path / "discrepancy" / "btc_usd_l2.parquet"
    assert _run_capture(output, monkeypatch)
    feature_path = output.with_name("btc_usd_l2_features_v3_online.parquet")
    features = pq.read_table(feature_path).to_pandas()
    features.loc[0, "v03_pnpc_k3"] += 0.01
    pq.write_table(__import__("pyarrow").Table.from_pandas(features, preserve_index=False), feature_path)
    audit = audit_session_artifacts(output.parent, 110, 0, 1)
    assert audit["status"] == "FAIL"
    assert not audit["checks"]["online_batch_causal_audit_pass"]


def test_sidecar_write_failure_leaves_incomplete_manifest_and_no_success(tmp_path, monkeypatch):
    output = tmp_path / "write-failure" / "btc_usd_l2.parquet"
    import pyarrow.parquet as parquet
    original_write = parquet.write_table

    def fail_sidecar(table, where, *args, **kwargs):
        if "features_v3_online" in str(where):
            raise OSError("synthetic sidecar write failure")
        return original_write(table, where, *args, **kwargs)

    monkeypatch.setattr(parquet, "write_table", fail_sidecar)
    assert not _run_capture(output, monkeypatch)
    manifests = list(output.parent.glob("*.incomplete.json"))
    assert manifests
    manifest = __import__("json").loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["capture_complete"] is False
