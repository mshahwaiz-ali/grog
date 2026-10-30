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
