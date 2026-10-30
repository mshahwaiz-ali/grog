"""Immutable domain records (docs/09 Section 3). Only market-data records exist so far."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from grog.domain.enums import SourceOrigin
from grog.domain.ids import is_valid_source_id

CANONICAL_SYMBOL = "XAUUSD"


def _require_int(name: str, value: object, minimum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int, got {value!r}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")


@dataclass(frozen=True, slots=True)
class NormalizedQuote:
    """One BID/ASK market event with full source provenance (docs/09 Section 3.1).

    Timestamps are UTC epoch milliseconds. Prices are exact Decimals. The
    provider timestamp is never an identity: ``source_event_key`` is.
    """

    source_id: str
    canonical_symbol: str
    raw_symbol: str
    provider_time_ms: int
    received_time_ms: int
    ingest_order: int
    bid: Decimal
    ask: Decimal
    source_origin: SourceOrigin
    source_event_key: str
    flags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not is_valid_source_id(self.source_id):
            raise ValueError(f"invalid source_id {self.source_id!r}")
        if self.canonical_symbol != CANONICAL_SYMBOL:
            raise ValueError(f"canonical_symbol must be {CANONICAL_SYMBOL}")
        if not isinstance(self.raw_symbol, str) or not self.raw_symbol:
            raise ValueError("raw_symbol must be a nonempty string")
        _require_int("provider_time_ms", self.provider_time_ms, 0)
        _require_int("received_time_ms", self.received_time_ms, 0)
        _require_int("ingest_order", self.ingest_order, 1)
        for name in ("bid", "ask"):
            price = getattr(self, name)
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
                raise ValueError(f"{name} must be a finite positive Decimal, got {price!r}")
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        if not isinstance(self.source_origin, SourceOrigin):
            raise ValueError("source_origin must be a SourceOrigin")
        if not isinstance(self.source_event_key, str) or not self.source_event_key:
            raise ValueError("source_event_key must be a nonempty string")
        if not isinstance(self.flags, frozenset) or not all(isinstance(f, str) for f in self.flags):
            raise ValueError("flags must be a frozenset of str")

    @property
    def spread(self) -> Decimal:
        """ASK minus BID in quote units (diagnostic only)."""
        return self.ask - self.bid
