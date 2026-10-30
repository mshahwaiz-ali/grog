"""Causal M1/M5/M15/H1 BID/ASK bar aggregation (docs/03 Section 2, docs/04 Section 3, docs/09 3.2).

Rules implemented here:

* UTC half-open buckets ``[start, end)`` keyed by **provider** time; ``start`` is a
  multiple of the timeframe duration since the Unix epoch (so DST never matters).
* A bar is finalized only when the first valid quote with provider time ``>= end``
  is processed. Its ``available_at_ms`` is that quote's receipt time, but never
  earlier than ``end`` (provider clock skew cannot make a bar usable early).
  The last open bar of a stream is never finalized.
* Empty buckets are **missing**: no OHLC is fabricated. A jump over empty buckets
  produces a :class:`GapRecord`; bars with empty M1 sub-buckets are ``GAPPED``
  unless every empty minute lies inside an explicitly declared market closure.
* Input must be one source, in stream order (provider and receipt time
  non-decreasing). Anything else is rejected, not silently re-sorted.
* Bars finalized by, or containing, BACKFILL quotes are labeled BACKFILL.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from grog.domain.clock import ReplayClock
from grog.domain.enums import TIMEFRAMES, BarQuality, GapKind, SourceOrigin, Timeframe
from grog.domain.models import DataHealthPolicy, FinalizedBar, GapRecord, NormalizedQuote

M1_MS = Timeframe.M1.duration_ms


def bucket_start(time_ms: int, timeframe: Timeframe) -> int:
    duration = timeframe.duration_ms
    return time_ms - (time_ms % duration)


@dataclass(slots=True)
class _Building:
    timeframe: Timeframe
    start_ms: int
    open_bid: Decimal
    high_bid: Decimal
    low_bid: Decimal
    close_bid: Decimal
    open_ask: Decimal
    high_ask: Decimal
    low_ask: Decimal
    close_ask: Decimal
    first_received_ms: int
    last_received_ms: int
    tick_count: int = 1
    m1_seen: set[int] = field(default_factory=set)
    origins: set[SourceOrigin] = field(default_factory=set)

    @classmethod
    def start(cls, timeframe: Timeframe, quote: NormalizedQuote) -> _Building:
        b = cls(
            timeframe=timeframe,
            start_ms=bucket_start(quote.provider_time_ms, timeframe),
            open_bid=quote.bid,
            high_bid=quote.bid,
            low_bid=quote.bid,
            close_bid=quote.bid,
            open_ask=quote.ask,
            high_ask=quote.ask,
            low_ask=quote.ask,
            close_ask=quote.ask,
            first_received_ms=quote.received_time_ms,
            last_received_ms=quote.received_time_ms,
        )
        b.m1_seen.add(bucket_start(quote.provider_time_ms, Timeframe.M1))
        b.origins.add(quote.source_origin)
        return b

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.timeframe.duration_ms

    def add(self, quote: NormalizedQuote) -> None:
        self.high_bid = max(self.high_bid, quote.bid)
        self.low_bid = min(self.low_bid, quote.bid)
        self.close_bid = quote.bid
        self.high_ask = max(self.high_ask, quote.ask)
        self.low_ask = min(self.low_ask, quote.ask)
        self.close_ask = quote.ask
        self.last_received_ms = quote.received_time_ms
        self.tick_count += 1
        self.m1_seen.add(bucket_start(quote.provider_time_ms, Timeframe.M1))
        self.origins.add(quote.source_origin)


def _bar_origin(origins: set[SourceOrigin]) -> SourceOrigin:
    if len(origins) == 1:
        return next(iter(origins))
    if SourceOrigin.BACKFILL in origins and len(origins - {SourceOrigin.BACKFILL}) == 1:
        return SourceOrigin.BACKFILL
    raise ValueError(f"one source must not mix origins {sorted(o.value for o in origins)}")


class BarHistory:
    """Finalized bars per timeframe, queryable strictly as of a decision time."""

    def __init__(self) -> None:
        self._bars: dict[Timeframe, list[FinalizedBar]] = {tf: [] for tf in TIMEFRAMES}
        self._available: dict[Timeframe, list[int]] = {tf: [] for tf in TIMEFRAMES}

    def append(self, bar: FinalizedBar) -> None:
        avail = self._available[bar.timeframe]
        if avail and bar.available_at_ms < avail[-1]:
            raise ValueError("bars must be appended in availability order")
        self._bars[bar.timeframe].append(bar)
        avail.append(bar.available_at_ms)

    def all(self, timeframe: Timeframe) -> tuple[FinalizedBar, ...]:
        return tuple(self._bars[timeframe])

    def available(self, timeframe: Timeframe, decision_time_ms: int) -> tuple[FinalizedBar, ...]:
        """Every bar with ``available_at_ms <= decision_time_ms`` (no lookahead)."""
        count = bisect.bisect_right(self._available[timeframe], decision_time_ms)
        return tuple(self._bars[timeframe][:count])

    def last_closed(self, timeframe: Timeframe, decision_time_ms: int) -> FinalizedBar | None:
        """Most recent finalized bar knowable at ``decision_time_ms``; ``None`` if none yet."""
        count = bisect.bisect_right(self._available[timeframe], decision_time_ms)
        return self._bars[timeframe][count - 1] if count else None


BarEvent = FinalizedBar | GapRecord


class BarAggregator:
    """Streaming, deterministic aggregation of one source's ordered quotes."""

    def __init__(
        self,
        source_id: str,
        policy: DataHealthPolicy | None = None,
        clock: ReplayClock | None = None,
    ) -> None:
        self.source_id = source_id
        self.policy = policy or DataHealthPolicy()
        self.clock = clock or ReplayClock()
        self.history = BarHistory()
        self.gaps: list[GapRecord] = []
        self.last_quote: NormalizedQuote | None = None
        self.quote_count = 0
        self._building: dict[Timeframe, _Building] = {}

    def on_quote(self, quote: NormalizedQuote) -> list[BarEvent]:
        """Process one quote; return bars finalized and gaps detected by it, in fixed order."""
        if quote.source_id != self.source_id:
            raise ValueError(
                f"quote from source {quote.source_id!r} fed to aggregator for {self.source_id!r}"
            )
        last = self.last_quote
        if last is not None:
            if quote.provider_time_ms < last.provider_time_ms:
                raise ValueError(f"provider time out of order at {quote.source_event_key}")
            if quote.received_time_ms < last.received_time_ms:
                raise ValueError(f"receipt time out of order at {quote.source_event_key}")
        self.clock.advance_to(quote.received_time_ms)

        events: list[BarEvent] = []
        for tf in TIMEFRAMES:
            building = self._building.get(tf)
            start = bucket_start(quote.provider_time_ms, tf)
            if building is None:
                self._building[tf] = _Building.start(tf, quote)
                continue
            if start == building.start_ms:
                building.add(quote)
                continue
            bar = self._finalize(building, quote)
            self.history.append(bar)
            events.append(bar)
            if start > building.end_ms:
                gap = GapRecord(
                    source_id=self.source_id,
                    timeframe=tf,
                    from_ms=building.end_ms,
                    to_ms=start,
                    missing_bars=(start - building.end_ms) // tf.duration_ms,
                    kind=(
                        GapKind.MARKET_CLOSED
                        if self.policy.covered_by_closures(building.end_ms, start)
                        else GapKind.DATA_GAP
                    ),
                    detected_at_ms=quote.received_time_ms,
                )
                self.gaps.append(gap)
                events.append(gap)
            self._building[tf] = _Building.start(tf, quote)

        self.last_quote = quote
        self.quote_count += 1
        return events

    def feed(self, quotes: Iterable[NormalizedQuote]) -> list[BarEvent]:
        events: list[BarEvent] = []
        for quote in quotes:
            events.extend(self.on_quote(quote))
        return events

    def _missing_m1(self, b: _Building) -> int:
        missing = 0
        for minute in range(b.start_ms, b.end_ms, M1_MS):
            if minute not in b.m1_seen and not self.policy.covered_by_closures(
                minute, minute + M1_MS
            ):
                missing += 1
        return missing

    def _finalize(self, b: _Building, closing: NormalizedQuote) -> FinalizedBar:
        origins = set(b.origins)
        if closing.source_origin is SourceOrigin.BACKFILL:
            origins.add(SourceOrigin.BACKFILL)
        missing = self._missing_m1(b)
        return FinalizedBar(
            source_id=self.source_id,
            timeframe=b.timeframe,
            start_ms=b.start_ms,
            end_ms=b.end_ms,
            open_bid=b.open_bid,
            high_bid=b.high_bid,
            low_bid=b.low_bid,
            close_bid=b.close_bid,
            open_ask=b.open_ask,
            high_ask=b.high_ask,
            low_ask=b.low_ask,
            close_ask=b.close_ask,
            tick_count=b.tick_count,
            first_received_ms=b.first_received_ms,
            last_received_ms=b.last_received_ms,
            closed_at_received_ms=closing.received_time_ms,
            closing_event_key=closing.source_event_key,
            available_at_ms=max(b.end_ms, closing.received_time_ms),
            quality=BarQuality.GAPPED if missing else BarQuality.COMPLETE,
            missing_m1_buckets=missing,
            source_origin=_bar_origin(origins),
        )


def aggregate(
    source_id: str, quotes: Iterable[NormalizedQuote], policy: DataHealthPolicy | None = None
) -> BarAggregator:
    """Run a fresh aggregator with a fresh virtual clock over ``quotes``."""
    aggregator = BarAggregator(source_id, policy)
    aggregator.feed(quotes)
    return aggregator


def bar_to_dict(bar: FinalizedBar) -> dict[str, Any]:
    """Canonical serialization (exact decimal strings) for reproducibility checks."""
    return {
        "bar_id": bar.bar_id,
        "timeframe": bar.timeframe.value,
        "start_ms": bar.start_ms,
        "end_ms": bar.end_ms,
        "bid": [str(bar.open_bid), str(bar.high_bid), str(bar.low_bid), str(bar.close_bid)],
        "ask": [str(bar.open_ask), str(bar.high_ask), str(bar.low_ask), str(bar.close_ask)],
        "tick_count": bar.tick_count,
        "first_received_ms": bar.first_received_ms,
        "last_received_ms": bar.last_received_ms,
        "closed_at_received_ms": bar.closed_at_received_ms,
        "closing_event_key": bar.closing_event_key,
        "available_at_ms": bar.available_at_ms,
        "quality": bar.quality.value,
        "missing_m1_buckets": bar.missing_m1_buckets,
        "source_origin": bar.source_origin.value,
    }


def gap_to_dict(gap: GapRecord) -> dict[str, Any]:
    return {
        "timeframe": gap.timeframe.value,
        "from_ms": gap.from_ms,
        "to_ms": gap.to_ms,
        "missing_bars": gap.missing_bars,
        "kind": gap.kind.value,
        "detected_at_ms": gap.detected_at_ms,
    }
