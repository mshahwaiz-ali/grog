"""Shared synthetic quote-stream builder for tests (synthetic values only)."""

from __future__ import annotations

from decimal import Decimal

from grog.domain.enums import SourceOrigin
from grog.domain.models import NormalizedQuote

T10 = 1793440800000  # 2026-10-31T10:00:00Z
S = 1000
MIN = 60 * S


class Stream:
    """Builds an ordered synthetic quote stream for one source."""

    def __init__(self, source_id: str = "syn-1") -> None:
        self.source_id = source_id
        self.quotes: list[NormalizedQuote] = []

    def add(
        self,
        provider_ms: int,
        bid: str = "4000.00",
        ask: str | None = None,
        received_ms: int | None = None,
        origin: SourceOrigin = SourceOrigin.SYNTHETIC,
    ) -> Stream:
        n = len(self.quotes) + 1
        bid_d = Decimal(bid)
        self.quotes.append(
            NormalizedQuote(
                source_id=self.source_id,
                canonical_symbol="XAUUSD",
                raw_symbol="XAUUSD",
                provider_time_ms=provider_ms,
                received_time_ms=provider_ms if received_ms is None else received_ms,
                ingest_order=n,
                bid=bid_d,
                ask=Decimal(ask) if ask is not None else bid_d + Decimal("0.20"),
                source_origin=origin,
                source_event_key=f"test#{n}",
            )
        )
        return self

    def every(self, start_ms: int, end_ms: int, step_ms: int, **kw: object) -> Stream:
        for t in range(start_ms, end_ms, step_ms):
            self.add(t, **kw)  # type: ignore[arg-type]
        return self


def make_bar(
    timeframe,
    index: int,
    high: str,
    low: str,
    close: str | None = None,
    open_: str | None = None,
    *,
    base_ms: int = T10,
    source_id: str = "syn-1",
    available_delay_ms: int = 0,
    quality=None,
    ask_offset: str = "0.20",
):
    """A finalized synthetic BID/ASK bar at series position ``index`` (no gaps)."""
    from grog.domain.enums import BarQuality
    from grog.domain.models import FinalizedBar

    start = base_ms + index * timeframe.duration_ms
    end = start + timeframe.duration_ms
    hi, lo = Decimal(high), Decimal(low)
    cl = Decimal(close) if close is not None else (hi + lo) / 2
    op = Decimal(open_) if open_ is not None else cl
    off = Decimal(ask_offset)
    return FinalizedBar(
        source_id=source_id,
        timeframe=timeframe,
        start_ms=start,
        end_ms=end,
        open_bid=op,
        high_bid=hi,
        low_bid=lo,
        close_bid=cl,
        open_ask=op + off,
        high_ask=hi + off,
        low_ask=lo + off,
        close_ask=cl + off,
        tick_count=1,
        first_received_ms=start,
        last_received_ms=start,
        closed_at_received_ms=end + available_delay_ms,
        closing_event_key=f"bar#{index}",
        available_at_ms=end + available_delay_ms,
        quality=quality or BarQuality.COMPLETE,
        missing_m1_buckets=0,
        source_origin=SourceOrigin.SYNTHETIC,
    )


DAYS = 11


def stress_stream(seed: int = 7, days: int = DAYS) -> Stream:
    """~11 days of 1-minute quotes: LCG random walk, a trend, an outage and late receipts."""
    s = Stream()
    state, cents = seed, 400_000
    for i in range(days * 24 * 60):
        if 5000 <= i < 5040:  # 40-minute data outage -> GAPPED bars
            continue
        state = (state * 1103515245 + 12345) % 2**31
        cents += (state >> 16) % 61 - 30 + (3 if (i // 1440) % 2 == 0 else -2)
        t = T10 + i * MIN
        late = 50_000 if i % 997 == 0 else (state >> 8) % 3  # some late receipts
        spread = 15 + (state >> 4) % 20
        s.add(
            t,
            bid=f"{cents // 100}.{cents % 100:02d}",
            ask=f"{(cents + spread) // 100}.{(cents + spread) % 100:02d}",
            received_ms=t + late if not s.quotes else max(t + late, s.quotes[-1].received_time_ms),
        )
    return s
