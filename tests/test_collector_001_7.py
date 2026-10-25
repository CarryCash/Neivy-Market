from __future__ import annotations
import pandas as pd 
import pytest

from navier_lab.orderbook_reconstrcutor import OneSecondResampler, OrderBookReconstructor

def book_levels():
    bids = [(100.0 - i * 0.1, 5.0 + i) for i in range(12)]
    asks = [(100.2 + i * 0.1, 6.0 + i) for i in range(12)]
    return bids, asks


def test_reconstruct_snapshot_and_deltas_including_delete():
    bids, asks = book_levels()
    book = OrderBookReconstructor(depth=10)
    view = book.load_snapshot(100, bids, asks)
    assert book.status == book.VALID
    assert view.sequence == 100
    assert len(view.bids) == len(view.asks) == 10
    assert view.bids[0][0] == 100.0
    assert view.asks[0][0] == 100.2

    # Quantity update and deletion at a deep price preserve the valid top 10.
    assert book.apply_delta(101, bids=[(99.9, 99.0)], asks=[(101.1, 0.0)])
    view2 = book.view()
    assert view2.sequence == 101
    assert dict(view2.bids)[99.9] == 99.0
    assert all(price != 101.1 for price, _ in view2.asks)


def test_sequence_gap_invalidates_and_requires_fresh_snapshot():
    bids, asks = book_levels()
    book = OrderBookReconstructor(depth=10)
    book.load_snapshot(500, bids, asks)
    assert book.apply_delta(501, bids=[(100.0, 7.0)])
    assert book.apply_delta(503, bids=[(100.0, 8.0)]) is False
    assert book.status == book.OUT_OF_SYNC
    with pytest.raises(RuntimeError, match="libro no válido"):
        book.view()
    assert book.apply_delta(504, bids=[(100.0, 9.0)]) is False

    recovered = book.load_snapshot(900, bids, asks)
    assert recovered.sequence == 900
    assert book.status == book.VALID


def test_crossed_book_invalidates_state():
    bids, asks = book_levels()
    book = OrderBookReconstructor(depth=10)
    book.load_snapshot(1, bids, asks)
    # Best ask becomes equal to best bid: locked/crossed book is rejected.
    assert book.apply_delta(2, asks=[(100.0, 2.0)]) is False
    assert book.status == book.OUT_OF_SYNC


def event_frame():
    # Multiple events in second 0 and a gap at second 2; last event per second wins.
    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01T00:00:00.100Z",
            "2026-01-01T00:00:00.800Z",
            "2026-01-01T00:00:01.200Z",
            "2026-01-01T00:00:03.100Z",
            "2026-01-01T00:00:03.900Z",
            "2026-01-01T00:00:04.100Z",
        ], utc=True),
        "bid_px_1": [100.0, 100.1, 100.2, 100.3, 100.4, 100.5],
        "state_id": [1, 2, 3, 4, 5, 6],
    })

def batch_reference(events):
    work = events.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work["_second"] = work["timestamp"].dt.floor("1s")
    per_second = work.drop_duplicates("_second", keep="last").set_index("_second")
    grid = pd.date_range(per_second.index.min(), per_second.index.max(), freq="1s", tz="UTC")
    out = per_second.drop(columns="timestamp").reindex(grid).ffill()
    out.index.name = "timestamp"
    return out.reset_index()[["timestamp", "bid_px_1", "state_id"]]


def test_resampler_chunk_invariance_and_subsecond_carry():
    events = event_frame()
    expected = batch_reference(events)
    for chunk_size in (1, 2, 3, 4, len(events)):
        resampler = OneSecondResampler()
        outputs = []
        for start in range(0, len(events), chunk_size):
            outputs.append(resampler.process_chunk(events.iloc[start:start + chunk_size]))
        outputs.append(resampler.flush())
        actual = pd.concat([frame for frame in outputs if not frame.empty], ignore_index=True)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False)

def test_resampler_rejects_timestamp_reversal_across_chunks():
    events = event_frame()
    resampler = OneSecondResampler()
    resampler.process_chunk(events.iloc[:3])
    reversed_chunk = events.iloc[2:4].copy()
    reversed_chunk.loc[reversed_chunk.index[-1], "timestamp"] = pd.Timestamp("2025-12-31T23:59:59Z")
    with pytest.raises(ValueError, match="no monótonos|retrocede"):
        resampler.process_chunk(reversed_chunk)

