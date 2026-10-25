from decimal import Decimal
from datetime import datetime, timezone
import pandas as pd
import pytest
from navier_lab.kraken_ws_v2 import (
    KrakenSpotBookV2Adapter, _remaining_capture_seconds, kraken_book_checksum,
)


def _book():
    bids = {Decimal(str(45283.5 - i * 0.1)): Decimal("1.00000000") for i in range(10)}
    asks = {Decimal(str(45285.2 + i * 0.1)): Decimal("2.00000000") for i in range(10)}
    return bids, asks


def _msg(kind, bids, asks, symbol="BTC/USDT", checksum=None,
         timestamp="2026-10-19T12:00:00.000000Z"):
    return {"channel": "book", "type": kind, "data": [{
        "symbol": symbol, "timestamp": timestamp,
        "bids": [{"price": str(p), "qty": str(q)} for p, q in bids.items()],
        "asks": [{"price": str(p), "qty": str(q)} for p, q in asks.items()],
        "checksum": kraken_book_checksum(bids, asks) if checksum is None else checksum,
    }]}


def test_subscription_is_public_market_data_only():
    adapter = KrakenSpotBookV2Adapter()
    msg = adapter.subscription_message()
    assert msg["method"] == "subscribe"
    assert msg["params"] == {"channel": "book", "symbol": ["BTC/USDT"], "depth": 10, "snapshot": True}


def test_snapshot_checksum_and_navier_columns():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    row = adapter.process_message(_msg("snapshot", bids, asks))
    assert row and adapter.valid
    assert row["bid_px_1"] == float(max(bids))
    assert row["ask_px_1"] == float(min(asks))
    assert row["symbol"] == "BTC/USDT"
    assert pd.Timestamp(row["received_at"]).tz is not None
    assert pd.Timestamp(row["processed_at"]).tz is not None
    assert row["processed_monotonic_ns"] >= row["received_monotonic_ns"]


def test_capture_timestamps_are_additive_and_arrival_clock_is_injected():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    received = datetime(2026, 10, 19, 12, 0, 1, tzinfo=timezone.utc)
    row = adapter.process_message(
        _msg("snapshot", bids, asks), received_at=received,
        received_monotonic_ns=123456789,
    )
    assert row["timestamp"] == "2026-10-19T12:00:00.000000Z"
    assert row["received_at"] == received
    assert row["received_monotonic_ns"] == 123456789
    assert row["processed_at"] >= received
    assert row["processed_monotonic_ns"] >= 123456789
    assert row["frame_received_monotonic_ns"] > 0
    assert row["state_processed_monotonic_ns"] >= row["frame_received_monotonic_ns"]
    assert row["state_validated_monotonic_ns"] >= row["state_processed_monotonic_ns"]


def test_exchange_timestamp_regression_invalidates_until_new_snapshot():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    assert adapter.process_message(_msg("snapshot", bids, asks))
    later = "2026-10-19T12:00:01.000000Z"
    checksum = kraken_book_checksum(bids, asks)
    assert adapter.process_message(_msg("update", {}, {}, checksum=checksum, timestamp=later))
    assert adapter.process_message(_msg("update", {}, {}, checksum=checksum, timestamp="2026-10-19T12:00:00.500000Z")) is None
    assert adapter.status == "OUT_OF_ORDER_TIMESTAMP"
    assert adapter.counters["out_of_order_timestamps"] == 1
    assert adapter.process_message(_msg("update", {}, {}, timestamp="2026-10-19T12:00:02.000000Z")) is None
    assert adapter.process_message(_msg("snapshot", bids, asks, timestamp="2026-10-19T12:00:02.100000Z"))


def test_exchange_timestamp_equal_is_counted_but_allowed():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    assert adapter.process_message(_msg("snapshot", bids, asks))
    assert adapter.process_message(_msg("update", {}, {}, checksum=kraken_book_checksum(bids, asks)))
    assert adapter.counters["exchange_timestamp_ties"] == 1


def test_capture_deadline_bounds_remaining_connect_read_and_backoff_budget():
    assert _remaining_capture_seconds(100.0, 120.0, 219.5) == 0.5
    assert _remaining_capture_seconds(100.0, 120.0, 220.0) == 0.0
    assert _remaining_capture_seconds(100.0, None, 500.0) is None


def test_update_deletes_qty_zero_and_applies_all_changes_before_checksum():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    assert adapter.process_message(_msg("snapshot", bids, asks))
    bid_updates = {Decimal("45283.5"): Decimal("0"), Decimal("45283.45"): Decimal("3.00000000")}
    ask_updates = {Decimal("45285.2"): Decimal("4.00000000")}
    next_bids, next_asks = bids.copy(), asks.copy()
    next_bids.pop(Decimal("45283.5")); next_bids[Decimal("45283.45")] = Decimal("3.00000000")
    next_asks[Decimal("45285.2")] = Decimal("4.00000000")
    update = _msg("update", bid_updates, ask_updates, checksum=kraken_book_checksum(next_bids, next_asks))
    row = adapter.process_message(update)
    assert row and row["bid_px_1"] == float(max(next_bids)) and row["ask_qty_1"] == 4.0


def test_bad_checksum_invalidates_and_requires_new_snapshot():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    assert adapter.process_message(_msg("snapshot", bids, asks, checksum=123)) is None
    assert adapter.status == "CHECKSUM_FAILED"
    assert adapter.process_message(_msg("update", bids, asks)) is None
    assert adapter.counters["checksum_failures"] == 1
    assert adapter.process_message(_msg("snapshot", bids, asks)) is not None


def test_reconnection_invalidation_requires_a_fresh_snapshot_before_updates():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    assert adapter.process_message(_msg("snapshot", bids, asks)) is not None
    adapter.invalidate("DISCONNECTED")
    assert not adapter.valid
    assert adapter.process_message(_msg("update", {}, {}, checksum=kraken_book_checksum(bids, asks))) is None
    assert adapter.process_message(_msg("snapshot", bids, asks,
                                        timestamp="2026-10-19T12:00:01.000000Z")) is not None
    assert adapter.valid


def test_subscription_rejection_is_counted_and_invalidates():
    adapter = KrakenSpotBookV2Adapter()
    assert adapter.process_message({"method": "subscribe", "success": False,
                                    "error": "Unknown symbol"}) is None
    assert adapter.status == "SUBSCRIPTION_ERROR"
    assert adapter.counters["subscription_errors"] == 1


def test_other_symbol_is_ignored():
    adapter = KrakenSpotBookV2Adapter()
    bids, asks = _book()
    assert adapter.process_message(_msg("snapshot", bids, asks, symbol="BTC/USD")) is None
    assert not adapter.valid


def test_official_kraken_checksum_fixture():
    bids_raw = [
        ("45283.5", "0.10000000"), ("45283.4", "1.54582015"),
        ("45282.1", "0.10000000"), ("45281.0", "0.10000000"),
        ("45280.3", "1.54592586"), ("45279.0", "0.07990000"),
        ("45277.6", "0.03310103"), ("45277.5", "0.30000000"),
        ("45277.3", "1.54602737"), ("45276.6", "0.15445238"),
    ]
    asks_raw = [
        ("45285.2", "0.00100000"), ("45286.4", "1.54571953"),
        ("45286.6", "1.54571109"), ("45289.6", "1.54560911"),
        ("45290.2", "0.15890660"), ("45291.8", "1.54553491"),
        ("45294.7", "0.04454749"), ("45296.1", "0.35380000"),
        ("45297.5", "0.09945542"), ("45299.5", "0.18772827"),
    ]
    bids = {Decimal(p): Decimal(q) for p, q in bids_raw}
    asks = {Decimal(p): Decimal(q) for p, q in asks_raw}
    assert kraken_book_checksum(bids, asks) == 3310070434
