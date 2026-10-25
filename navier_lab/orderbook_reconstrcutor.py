
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Optional

LevelInput = Iterable[tuple[float, float]]

@dataclass(frozen=True)
class BookView:
    sequence: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]

class OrderBookReconstructor:
    WAITING_SNAPSHOT = "WAITING_SNAPSHOT"
    VALID = "VALID"
    OUT_OF_SYNC = "OUT_OF_SYNC"

    def __init__(self, depth: int = 10) -> None:
        if not isinstance(depth, int) or depth < 1:
            raise ValueError("depth debe ser un entero > 1")
        self.depth = depth
        self.status = self.WAITING_SNAPSHOT
        self.last_sequence: Optional[int] = None
        self._bids: dict[float, float] = {}
        self._asks: dict[float, float] = {}

    @staticmethod
    def _normalise_levels(levels: LevelInput) -> dict[float, float]:
        result: dict[float, float] = {}
        for pair in levels:
            if len(pair) != 2:
                raise ValueError("cada nivel debe ser (price, quantity)")
            price, qty = float(pair[0]), float(pair[1])
            if not math.isfinite(price) or not math.isfinite(qty):
                raise ValueError("precio/cantidad no finitos")
            if price <= 0 or qty <= 0:
                raise ValueError("precio y cantidad del snapshot deben ser > 0")
            if price in result:
                raise ValueError(f"precio duplicado en snapshot: {price}")
            result[price] = qty
        return result

    def _invalidate(self, status: str = OUT_OF_SYNC) -> None:
        self.status = status
        self.last_sequence = None
        self._bids.clear()
        self._asks.clear()

    def _validate_book(self) -> None:
        if len(self._bids) < self.depth or len(self._asks) < self.depth:
            raise ValueError(f"se requieren al menos {self.depth} niveles por lado")
        bids = sorted(self._bids, reverse=True)
        asks = sorted(self._asks)
        if any(bids[i] <= bids[i+1] for i in range(len(bids) - 1)):
            raise ValueError("orden bid invalido")
        if any(asks[i] >= asks[i+1] for i in range(len(asks) - 1)):
            raise ValueError("orden ask invalido")
        if bids[0] >= asks[0]:
            raise ValueError("libro cruzado o bloqueado: best_bid >= best_ask")

    def load_snapshot(
        self, sequence: int, bids: LevelInput, asks: LevelInput
    ) -> BookView:
        self._invalidate(self.WAITING_SNAPSHOT)
        try:
            if not isinstance(sequence, int) or sequence < 0:
                raise ValueError("Sequence debe ser entero >= 0")
            self._bids = self._normalise_levels(bids)
            self._asks = self._normalise_levels(asks)
            self._validate_book()
        except (TypeError, ValueError):
            self._invalidate(self.OUT_OF_SYNC)
            raise
        self.last_sequence = sequence
        self.status = self.VALID
        return self.view()

    def apply_delta(
        self, sequence: int, bids: LevelInput = (), asks: LevelInput = ()
    ) -> bool:
        if self.status != self.VALID or self.last_sequence is None:
            return False
        if not isinstance(sequence, int) or sequence != self.last_sequence + 1:
            self._invalidate(self.OUT_OF_SYNC)
            return False
        try:
            for side_name, updates in (("bid", bids), ("ask", asks)):
                side = self._bids if side_name == "bid" else self._asks
                for pair in updates:
                    if len(pair) != 2:
                        raise ValueError("cada delta debe ser (price, quantity)")
                    price, qty = float(pair[0]), float(pair[1])
                    if not math.isfinite(price) or not math.isfinite(qty) or price <= 0 or qty < 0:
                        raise ValueError("precio/cantidad no finitos o inválidos")
                    if qty == 0:
                        side.pop(price, None)
                    else:
                        side[price] = qty
            self._validate_book()
        except (TypeError, ValueError):
            self._invalidate(self.OUT_OF_SYNC)
            return False
        self.last_sequence = sequence
        return True

    def view(self) -> BookView:
        if self.status != self.VALID or self.last_sequence is None:
            raise RuntimeError(f"libro no válido: {self.status}")
        bids = sorted(self._bids.items(), key=lambda x: x[0], reverse=True)[:self.depth]
        asks = sorted(self._asks.items(), key=lambda x: x[0])[:self.depth]

        return BookView(
            self.last_sequence, tuple(bids), tuple(asks)
        )

    def to_record(self, timestamp) -> dict:
        view = self.view()
        record = {"timestamp": timestamp}
        for side, levels in (("bid", view.bids), ("ask", view.asks)):
            for i, (price, qty) in enumerate(levels, start=1):
                record[f"{side}_px_{i}"] = price
                record[f"{side}_qty_{i}"] = qty
        return record

class OneSecondResampler:
    def __init__(self) -> None:
        self._pending = None
        self._next_second = None
        self._carry = None
        self._last_input_ts = None
        self._columns = None
    
    @staticmethod
    def _empty(columns):
        import pandas as pd 
        return pd.DataFrame(columns=columns)
    
    def reset(self) -> None:
        self._pending = None
        self._next_second = None
        self._carry = None
        self._last_input_ts = None
        self._columns = None
    
    def process_chunk(self, events):
        import pandas as pd 

        if events is None or len(events) == 0:
            return self._empty(self._columns or list(getattr(events, "columns", [])))
        if "timestamp" not in events.columns:
            raise ValueError("events require columna timestamp")
        chunk = events.copy()
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], utc=True, errors="raise")
        if not chunk["timestamp"].is_monotonic_increasing:
            raise ValueError("timestamps no monótonos dentro del chunk")
        if self._last_input_ts is not None and chunk["timestamp"].iloc[0] < self._last_input_ts:
            raise ValueError("timestamp retrocede entre chunks")
        if self._columns is not None and list(chunk.columns) != self._columns:
            raise ValueError("el esquema cambió entre chunks")
        self._columns = list(chunk.columns)
        self._last_input_ts = chunk["timestamp"].iloc[-1]
        combined = chunk if self._pending is None else pd.concat([self._pending, chunk], ignore_index=True)
        combined["_second"] = combined["timestamp"].dt.floor("1s")
        latest_second = combined["_second"].iloc[-1]
        # Keep every event in the latest second until a later second proves it complete.
        pending_mask = combined["_second"] == latest_second
        self._pending = combined.loc[pending_mask, self._columns].copy().reset_index(drop=True)
        completed = combined.loc[~pending_mask, self._columns].copy()
        if completed.empty:
            return self._empty(self._columns)
        completed["_second"] = completed["timestamp"].dt.floor("1s")
        # Last whole event row per second (not per-column last-non-null aggregation).
        per_second = completed.drop_duplicates("_second", keep="last").set_index("_second")
        first_second = self._next_second if self._next_second is not None else per_second.index.min()
        end_exclusive = latest_second
        out = []
        second = first_second
        while second < end_exclusive:
            if second in per_second.index:
                row = per_second.loc[second, self._columns].to_dict()
                self._carry = row.copy()
            elif self._carry is None:
                # There cannot normally be a leading gap, but fail rather than invent state.
                raise ValueError("hueco inicial sin estado válido para carry-forward")
            else:
                row = self._carry.copy()
            row["timestamp"] = second
            out.append(row)
            second = second + pd.Timedelta(seconds=1)
        self._next_second = end_exclusive
        return pd.DataFrame(out, columns=self._columns)

    def flush(self):
        """Emit the final pending second at end-of-capture."""
        import pandas as pd

        if self._pending is None or self._pending.empty:
            return self._empty(self._columns or [])
        pending = self._pending.copy()
        pending["_second"] = pending["timestamp"].dt.floor("1s")
        per_second = pending.drop_duplicates("_second", keep="last").set_index("_second")
        final_second = per_second.index.max()
        if self._next_second is None:
            self._next_second = per_second.index.min()
        out = []
        second = self._next_second
        while second <= final_second:
            if second in per_second.index:
                row = per_second.loc[second, self._columns].to_dict()
                self._carry = row.copy()
            elif self._carry is None:
                raise ValueError("hueco inicial sin estado válido para carry-forward")
            else:
                row = self._carry.copy()
            row["timestamp"] = second
            out.append(row)
            second = second + pd.Timedelta(seconds=1)
        self._next_second = second
        self._pending = None
        return pd.DataFrame(out, columns=self._columns)
