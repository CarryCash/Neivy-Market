"""Online V3 row publisher using the frozen batch implementation as reference.

Each resampled second is finalized only after a later valid exchange event
proves its right-closed interval has ended. The existing causal resampler and
compute_features implementation remain the sole calculation path.
"""
from __future__ import annotations

import json
import time

import pandas as pd

from .features import NAVIER_V3, compute_features
from .resampler import ResamplerConfig, resample_l2_to_1s
from .schema import DEFAULT_CONFIG


class OnlineV3FeaturePublisher:
    """Finalize closed buckets and synchronously publish valid V3 rows."""

    def __init__(self, *, cfg=DEFAULT_CONFIG, resampler_cfg=ResamplerConfig()):
        self.cfg = cfg
        self.resampler_cfg = resampler_cfg
        self._events: list[dict] = []
        self._last_published_ns: int | None = None
        self._last_closed_end_ns: int | None = None
        self._next_feature_row_id = 0
        self.finalized_intervals = 0
        self.published_rows = 0
        self.warmup_or_na_rows = 0
        self.gap_rows = 0

    def consume(self, event: dict, publish) -> list[dict]:
        """Consume one checksum-valid state and call `publish` for ready rows.

        No row is fabricated for an invalid frame: the adapter does not pass
        invalid messages here. `feature_ready_monotonic_ns` is sampled directly
        before the synchronous consumer callback is invoked.
        """
        self._events.append(dict(event))
        exchange_time = pd.to_datetime(event["timestamp"], utc=True)
        floor = exchange_time.floor("1s")
        closed_end = floor - pd.Timedelta(seconds=1) if exchange_time == floor else floor
        close_ns = int(closed_end.value)

        # Most frames arrive inside the same one-second interval. Do no batch
        # resampling/feature work until exchange time advances past a close.
        if self._last_closed_end_ns is not None and close_ns <= self._last_closed_end_ns:
            return []
        self._last_closed_end_ns = close_ns

        state_selection_started = time.perf_counter_ns()
        resampled = resample_l2_to_1s(pd.DataFrame(self._events), self.resampler_cfg)
        state_selected = time.perf_counter_ns()
        if resampled.empty:
            return []
        bucket_ns = pd.to_datetime(resampled["timestamp"], utc=True).astype("int64").to_numpy()
        if self._last_published_ns is None:
            is_new = bucket_ns <= close_ns
        else:
            is_new = (bucket_ns > self._last_published_ns) & (bucket_ns <= close_ns)
        new_positions = list(map(int, is_new.nonzero()[0]))
        if not new_positions:
            self._trim_events(exchange_time)
            return []

        compute_started = time.perf_counter_ns()
        features = compute_features(resampled, self.cfg, with_target=False)
        published = []
        for pos in new_positions:
            state = resampled.iloc[pos]
            feature = features.iloc[pos]
            self.finalized_intervals += 1
            self._last_published_ns = int(bucket_ns[pos])
            source_id = state.get("capture_row_id")
            feature_values = feature[NAVIER_V3]
            if feature_values.isna().any() or pd.isna(source_id):
                if state.get("state_source") == "GAP_DISCONTINUITY":
                    self.gap_rows += 1
                else:
                    self.warmup_or_na_rows += 1
                continue

            ts = pd.Timestamp(state["timestamp"])
            window_start = ts - pd.Timedelta(seconds=self.cfg.max_window - 1)
            dependency_mask = (
                (pd.to_datetime(resampled["timestamp"], utc=True) >= window_start)
                & (pd.to_datetime(resampled["timestamp"], utc=True) <= ts)
            )
            dependency_ids = resampled.loc[dependency_mask, "capture_row_id"].dropna().astype("int64").unique().tolist()
            ready_ns = time.perf_counter_ns()
            record = {
                "feature_row_id": self._next_feature_row_id,
                "feature_time_utc": ts,
                "capture_row_id": int(source_id),
                "feature_trigger_capture_row_id": int(event["capture_row_id"]),
                "dependency_capture_row_ids_json": json.dumps(dependency_ids),
                "state_source": str(state["state_source"]),
                "state_selection_started_monotonic_ns": state_selection_started,
                "state_selected_monotonic_ns": state_selected,
                "feature_compute_started_monotonic_ns": compute_started,
                "feature_ready_monotonic_ns": ready_ns,
                "frame_received_monotonic_ns": int(state["frame_received_monotonic_ns"]),
                "state_processed_monotonic_ns": int(state["state_processed_monotonic_ns"]),
                "state_validated_monotonic_ns": int(state["state_validated_monotonic_ns"]),
                **{name: float(feature[name]) for name in NAVIER_V3},
            }
            self._next_feature_row_id += 1
            publish(record)
            self.published_rows += 1
            published.append(record)

        self._trim_events(exchange_time)
        return published

    def _trim_events(self, newest: pd.Timestamp) -> None:
        # Keep more than the maximum causal feature window so the existing
        # resampler always receives adequate history after buffer trimming.
        cutoff = newest - pd.Timedelta(seconds=self.cfg.max_window + 5)
        self._events = [row for row in self._events
                        if pd.to_datetime(row["timestamp"], utc=True) >= cutoff]

    def counters(self) -> dict:
        return {
            "intervals_finalized": self.finalized_intervals,
            "feature_rows_published": self.published_rows,
            "warmup_or_na_rows_not_published": self.warmup_or_na_rows,
            "gap_rows_not_published": self.gap_rows,
        }
