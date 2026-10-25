
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import time
import zlib
from typing import Any, Optional

WS_URL = "wss://ws.kraken.com/v2"
DEFAULT_SYMBOL = "BTC/USDT"
DEFAULT_DEPTH = 10


class KrakenBookError(RuntimeError):
    """Raised for invalid or untrustworthy book data."""


def _decimal(value: Any, *, allow_zero: bool = False) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenBookError(f"invalid decimal value: {value!r}") from exc
    if not result.is_finite() or result < 0 or (result == 0 and not allow_zero):
        raise KrakenBookError(f"price/quantity out of range: {value!r}")
    return result


def _checksum_component(value: Decimal) -> str:
    """Kraken format: remove decimal point, then leading zeros; keep trailing zeros."""
    text = format(value, "f").replace(".", "")
    text = text.lstrip("0")
    return text or "0"


def kraken_book_checksum(
    bids: Mapping[Decimal, Decimal], asks: Mapping[Decimal, Decimal], depth: int = 10
) -> int:
    """CRC32 of top 10 asks (low-to-high) followed by top 10 bids (high-to-low)."""
    ask_levels = sorted(asks.items(), key=lambda item: item[0])[:depth]
    bid_levels = sorted(bids.items(), key=lambda item: item[0], reverse=True)[:depth]
    parts: list[str] = []
    for price, qty in ask_levels:
        parts.append(_checksum_component(price) + _checksum_component(qty))
    for price, qty in bid_levels:
        parts.append(_checksum_component(price) + _checksum_component(qty))
    return zlib.crc32("".join(parts).encode("ascii")) & 0xFFFFFFFF


def _parse_levels(levels: Any) -> list[tuple[Decimal, Decimal]]:
    if not isinstance(levels, list):
        raise KrakenBookError("bids/asks must be lists")
    result = []
    for item in levels:
        if not isinstance(item, Mapping) or "price" not in item or "qty" not in item:
            raise KrakenBookError("malformed L2 level")
        result.append((_decimal(item["price"]), _decimal(item["qty"], allow_zero=True)))
    return result


def _remaining_capture_seconds(started: float, duration_seconds: Optional[float], now: float) -> Optional[float]:
    """Bound each connect/read/sleep by the remaining session budget."""
    if duration_seconds is None:
        return None
    return max(0.0, duration_seconds - (now - started))


class KrakenSpotBookV2Adapter:
    """Maintain and validate one Kraken Spot WS v2 book subscription."""

    def __init__(self, symbol: str = DEFAULT_SYMBOL, depth: int = DEFAULT_DEPTH):
        if depth not in (10, 25, 100, 500, 1000):
            raise ValueError("depth must be one of 10, 25, 100, 500, 1000")
        if not symbol or "/" not in symbol:
            raise ValueError("symbol must use BASE/QUOTE form, e.g. BTC/USDT")
        self.symbol, self.depth = symbol, depth
        self.status = "WAITING_SNAPSHOT"
        self.last_checksum: Optional[int] = None
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._last_exchange_timestamp: Optional[datetime] = None
        self.counters = {
            "frames_received": 0, "messages": 0, "snapshots": 0, "valid_updates": 0,
            "checksum_failures": 0, "malformed_messages": 0,
            "ignored_messages": 0, "reconnects": 0,
            "exchange_timestamp_ties": 0, "out_of_order_timestamps": 0,
            "connection_errors": 0, "subscription_errors": 0,
        }
        self.last_connection_error: Optional[str] = None

    @property
    def valid(self) -> bool:
        return self.status == "VALID"

    def invalidate(self, reason: str = "OUT_OF_SYNC") -> None:
        self.status = reason
        self.last_checksum = None
        self._bids.clear()
        self._asks.clear()

    def subscription_message(self, req_id: int = 18001) -> dict:
        return {
            "method": "subscribe",
            "params": {"channel": "book", "symbol": [self.symbol],
                       "depth": self.depth, "snapshot": True},
            "req_id": req_id,
        }

    def _apply_levels(self, bids, asks, bid_updates, ask_updates) -> None:
        for side, updates in ((bids, bid_updates), (asks, ask_updates)):
            for price, qty in updates:
                if qty == 0:
                    side.pop(price, None)
                else:
                    side[price] = qty
        # Kraken instructs clients to truncate to subscribed depth after each message.
        if len(bids) > self.depth:
            for price, _ in sorted(bids.items(), reverse=True)[self.depth:]:
                bids.pop(price, None)
        if len(asks) > self.depth:
            for price, _ in sorted(asks.items())[self.depth:]:
                asks.pop(price, None)

    def _validate_shape(self, bids, asks) -> None:
        needed = min(self.depth, 10)
        if len(bids) < needed or len(asks) < needed:
            raise KrakenBookError("insufficient book depth")
        if max(bids) >= min(asks):
            raise KrakenBookError("crossed or locked book")

    def _row(self, exchange_timestamp: Any, received_at: datetime,
             received_monotonic_ns: int, processed_at: datetime,
             processed_monotonic_ns: int, frame_received_monotonic_ns: int,
             state_processed_monotonic_ns: int,
             state_validated_monotonic_ns: int) -> dict:
        bids = sorted(self._bids.items(), reverse=True)[:self.depth]
        asks = sorted(self._asks.items())[:self.depth]
        row = {"timestamp": exchange_timestamp, "received_at": received_at,
               "received_monotonic_ns": received_monotonic_ns,
               "frame_received_monotonic_ns": frame_received_monotonic_ns,
               "state_processed_monotonic_ns": state_processed_monotonic_ns,
               "state_validated_monotonic_ns": state_validated_monotonic_ns,
               "processed_at": processed_at,
               "processed_monotonic_ns": processed_monotonic_ns,
               "symbol": self.symbol, "checksum": self.last_checksum}
        for i in range(self.depth):
            for prefix, levels in (("bid", bids), ("ask", asks)):
                row[f"{prefix}_px_{i+1}"] = float(levels[i][0]) if i < len(levels) else None
                row[f"{prefix}_qty_{i+1}"] = float(levels[i][1]) if i < len(levels) else None
        return row

    def process_message(self, message: str | bytes | Mapping[str, Any], *,
                        received_at: Optional[datetime] = None,
                        received_monotonic_ns: Optional[int] = None,
                        frame_received_monotonic_ns: Optional[int] = None) -> Optional[dict]:
        """Return a row only when the resulting local book passes Kraken CRC32."""
        self.counters["messages"] += 1
        received_at = received_at or datetime.now(timezone.utc)
        received_monotonic_ns = (time.monotonic_ns() if received_monotonic_ns is None
                                 else int(received_monotonic_ns))
        frame_received_monotonic_ns = (
            time.perf_counter_ns() if frame_received_monotonic_ns is None
            else int(frame_received_monotonic_ns)
        )
        try:
            if isinstance(message, (str, bytes, bytearray)):
                message = json.loads(message, parse_float=Decimal, parse_int=int)
            if not isinstance(message, Mapping):
                raise KrakenBookError("WS message is not a JSON object")
            if message.get("channel") != "book":
                if message.get("success") is False or message.get("error"):
                    self.invalidate("SUBSCRIPTION_ERROR")
                    self.counters["malformed_messages"] += 1
                    self.counters["subscription_errors"] += 1
                else:
                    self.counters["ignored_messages"] += 1
                return None
            data = message.get("data")
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], Mapping):
                raise KrakenBookError("unexpected book payload")
            item = data[0]
            if item.get("symbol") != self.symbol:
                self.counters["ignored_messages"] += 1
                return None
            kind = message.get("type")
            if kind not in ("snapshot", "update"):
                self.counters["ignored_messages"] += 1
                return None
            if kind == "snapshot":
                bids, asks = {}, {}
            else:
                if not self.valid:
                    self.counters["ignored_messages"] += 1
                    return None
                bids, asks = self._bids.copy(), self._asks.copy()

            # Kraken Spot WS v2 book messages have no sequence number. Preserve
            # WebSocket arrival order and reject exchange-time regressions instead
            # of silently sorting states downstream. Equal timestamps are legal.
            raw_timestamp = item.get("timestamp")
            if not isinstance(raw_timestamp, str):
                raise KrakenBookError("book message has no RFC3339 timestamp")
            try:
                exchange_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise KrakenBookError("invalid RFC3339 exchange timestamp") from exc
            if exchange_timestamp.tzinfo is None:
                raise KrakenBookError("exchange timestamp must include timezone")
            if self._last_exchange_timestamp is not None:
                if exchange_timestamp < self._last_exchange_timestamp:
                    self.counters["out_of_order_timestamps"] += 1
                    self.invalidate("OUT_OF_ORDER_TIMESTAMP")
                    return None
                if exchange_timestamp == self._last_exchange_timestamp:
                    self.counters["exchange_timestamp_ties"] += 1

            self._apply_levels(bids, asks,
                               _parse_levels(item.get("bids", [])),
                               _parse_levels(item.get("asks", [])))
            self._validate_shape(bids, asks)
            state_processed_monotonic_ns = time.perf_counter_ns()
            if "checksum" not in item:
                raise KrakenBookError("book message has no checksum")
            expected = int(item["checksum"])
            actual = kraken_book_checksum(bids, asks, depth=10)
            if actual != expected:
                self.counters["checksum_failures"] += 1
                self.invalidate("CHECKSUM_FAILED")
                return None
            self._bids, self._asks = bids, asks
            self._last_exchange_timestamp = exchange_timestamp
            self.last_checksum = actual
            self.status = "VALID"
            state_validated_monotonic_ns = time.perf_counter_ns()
            if kind == "snapshot":
                self.counters["snapshots"] += 1
            else:
                self.counters["valid_updates"] += 1
            processed_at = datetime.now(timezone.utc)
            processed_monotonic_ns = time.monotonic_ns()
            return self._row(raw_timestamp, received_at, received_monotonic_ns,
                             processed_at, processed_monotonic_ns,
                             frame_received_monotonic_ns,
                             state_processed_monotonic_ns,
                             state_validated_monotonic_ns)
        except (KrakenBookError, TypeError, ValueError, KeyError, InvalidOperation):
            self.counters["malformed_messages"] += 1
            self.invalidate("OUT_OF_SYNC")
            return None

    async def stream(self, duration_seconds: Optional[float] = None) -> AsyncIterator[dict]:
        """Yield validated states; reconnects invalidate state until a fresh snapshot."""
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("Install dependency 'websockets' first") from exc
        started = time.monotonic()
        backoff = 1.0
        connected_once = False
        while True:
            remaining = _remaining_capture_seconds(started, duration_seconds, time.monotonic())
            if remaining is not None and remaining <= 0:
                break
            try:
                async with websockets.connect(
                    WS_URL, ping_interval=20, ping_timeout=20,
                    close_timeout=5,
                    open_timeout=min(10.0, remaining) if remaining is not None else 10.0,
                    max_size=2**20,
                ) as ws:
                    if connected_once:
                        self.counters["reconnects"] += 1
                    connected_once = True
                    self.invalidate("WAITING_SNAPSHOT")
                    await ws.send(json.dumps(self.subscription_message()))
                    backoff = 1.0
                    while True:
                        remaining = _remaining_capture_seconds(started, duration_seconds, time.monotonic())
                        if remaining is not None and remaining <= 0:
                            return
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                        except asyncio.TimeoutError:
                            return
                        self.counters["frames_received"] += 1
                        received_at = datetime.now(timezone.utc)
                        received_monotonic_ns = time.monotonic_ns()
                        frame_received_monotonic_ns = time.perf_counter_ns()
                        row = self.process_message(raw, received_at=received_at,
                                                   received_monotonic_ns=received_monotonic_ns,
                                                   frame_received_monotonic_ns=frame_received_monotonic_ns)
                        if row is not None:
                            yield row
                        elif self.status in {
                            "CHECKSUM_FAILED", "OUT_OF_ORDER_TIMESTAMP", "OUT_OF_SYNC",
                            "SUBSCRIPTION_ERROR",
                        }:
                            # A fresh snapshot is required to re-establish a valid
                            # state; close this subscription and reconnect promptly.
                            break
                    self.invalidate("DISCONNECTED")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.counters["connection_errors"] += 1
                self.last_connection_error = f"{type(exc).__name__}: {exc}"[:500]
                self.invalidate("DISCONNECTED")
            remaining = _remaining_capture_seconds(started, duration_seconds, time.monotonic())
            if remaining is not None and remaining <= 0:
                break
            await asyncio.sleep(min(backoff, 15.0, remaining) if remaining is not None else min(backoff, 15.0))
            backoff = min(backoff * 2.0, 15.0)
