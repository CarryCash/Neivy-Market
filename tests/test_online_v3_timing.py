import math

import numpy as np
import pandas as pd

from navier_lab.features import NAVIER_V3, compute_features
from navier_lab.online_v3 import OnlineV3FeaturePublisher
from navier_lab.resampler import resample_l2_to_1s
from navier_lab.schema import ASK_PX, ASK_QTY, BID_PX, BID_QTY
from scripts.validate_online_v3_capture import compare_online_to_batch


def _event(i):
    ts = pd.Timestamp("2026-10-24T18:00:00Z") + pd.Timedelta(seconds=i, milliseconds=200)
    mid = 100_000.0 + 0.2 * i + 0.03 * math.sin(i / 3)
    event = {
        "timestamp": ts,
        "received_at": ts + pd.Timedelta(milliseconds=1),
        "processed_at": ts + pd.Timedelta(milliseconds=2),
        "received_monotonic_ns": 1_000_000_000 + i * 1_000_000_000,
        "processed_monotonic_ns": 1_000_000_001 + i * 1_000_000_000,
        "frame_received_monotonic_ns": 10_000_000_000 + i * 1_000_000_000,
        "state_processed_monotonic_ns": 10_000_000_010 + i * 1_000_000_000,
        "state_validated_monotonic_ns": 10_000_000_020 + i * 1_000_000_000,
        "capture_row_id": i, "symbol": "BTC/USD", "checksum": i + 100,
    }
    for level in range(1, 11):
        event[f"bid_px_{level}"] = mid - 0.05 - (level - 1) * 0.1
        event[f"ask_px_{level}"] = mid + 0.05 + (level - 1) * 0.1
        event[f"bid_qty_{level}"] = 0.5 + 0.01 * level + 0.03 * math.sin((i + level) / 5)
        event[f"ask_qty_{level}"] = 0.6 + 0.015 * level + 0.02 * math.cos((i + level) / 7)
    return event


def test_online_publisher_is_causal_and_matches_frozen_batch_v3():
    events = [_event(i) for i in range(100)]
    publisher = OnlineV3FeaturePublisher()
    published = []
    for event in events:
        publisher.consume(event, published.append)

    raw = pd.DataFrame(events)
    resampled = resample_l2_to_1s(raw)
    batch = compute_features(resampled, with_target=False)
    batch_ready = batch[NAVIER_V3].notna().all(axis=1)
    expected = batch.loc[batch_ready & (batch["timestamp"] <= published[-1]["feature_time_utc"])]

    assert len(published) > 0
    assert [row["feature_row_id"] for row in published] == list(range(len(published)))
    assert len({row["capture_row_id"] for row in published}) == len(published)
    by_time = {row["feature_time_utc"]: row for row in published}
    assert set(by_time) == set(expected["timestamp"])
    for _, row in expected.iterrows():
        online = by_time[row["timestamp"]]
        for name in NAVIER_V3:
            # Both paths call the same frozen formulas; 1e-12 only allows
            # floating reduction noise if pandas changes reduction order.
            assert np.isclose(online[name], row[name], rtol=1e-12, atol=1e-12), name
        assert online["feature_ready_monotonic_ns"] >= online["feature_compute_started_monotonic_ns"]
        assert online["state_selection_started_monotonic_ns"] <= online["state_selected_monotonic_ns"]
        assert online["state_selected_monotonic_ns"] <= online["feature_compute_started_monotonic_ns"]
        assert online["state_processed_monotonic_ns"] <= online["state_validated_monotonic_ns"]
        assert online["frame_received_monotonic_ns"] <= online["state_processed_monotonic_ns"]
        trigger = events[online["feature_trigger_capture_row_id"]]
        assert trigger["timestamp"] > online["feature_time_utc"]
        assert trigger["state_validated_monotonic_ns"] <= online["state_selection_started_monotonic_ns"]

    # Each feature interval only cites source events at or before its market close.
    row_by_id = {event["capture_row_id"]: event for event in events}
    for row in published:
        source = row_by_id[row["capture_row_id"]]
        assert source["timestamp"] <= row["feature_time_utc"]
        assert row["state_source"] in {"OBSERVED", "CARRIED_FORWARD"}


def test_online_publisher_never_publishes_invalid_or_unwarmed_rows():
    publisher = OnlineV3FeaturePublisher()
    output = []
    for event in [_event(i) for i in range(20)]:
        publisher.consume(event, output.append)
    assert output == []
    assert publisher.counters()["warmup_or_na_rows_not_published"] > 0


def test_batch_audit_detects_value_interval_and_source_id_discrepancies():
    events = [_event(i) for i in range(100)]
    publisher = OnlineV3FeaturePublisher()
    records = []
    for event in events:
        publisher.consume(event, records.append)
    resampled = resample_l2_to_1s(pd.DataFrame(events))
    batch = compute_features(resampled, with_target=False)
    online = pd.DataFrame(records)
    online["feature_time_utc"] = pd.to_datetime(online["feature_time_utc"], utc=True)

    assert compare_online_to_batch(resampled, batch, online)["all_match"]

    wrong_value = online.copy()
    wrong_value.loc[0, "v03_pnpc_k3"] += 1e-6
    assert not compare_online_to_batch(resampled, batch, wrong_value)["feature_values_match"]

    wrong_interval = online.copy()
    wrong_interval.loc[0, "feature_time_utc"] += pd.Timedelta(seconds=1)
    assert not compare_online_to_batch(resampled, batch, wrong_interval)["interval_coverage_matches"]

    wrong_source = online.copy()
    wrong_source.loc[0, "capture_row_id"] += 1
    assert not compare_online_to_batch(resampled, batch, wrong_source)["source_state_ids_match"]
