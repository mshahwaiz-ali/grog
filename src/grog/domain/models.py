"""Immutable domain records (docs/09 Section 3). Only market-data records exist so far."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from grog.domain.enums import (
    BarQuality,
    GapKind,
    H1Bias,
    IndicatorStatus,
    M15Context,
    PivotSide,
    Side,
    SourceOrigin,
    Timeframe,
)
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


@dataclass(frozen=True, slots=True)
class QuoteSource:
    """Catalog identity of one quote source; immutable once recorded (docs/09 Section 7)."""

    source_id: str
    kind: SourceOrigin
    symbol: str
    metadata_json: str
    created_at_ms: int


@dataclass(frozen=True, slots=True)
class ImportBatch:
    """One committed, checksummed, immutable quote batch (docs/09 Section 7)."""

    batch_id: str
    source_id: str
    sha256: str
    origin: SourceOrigin
    format_version: str
    path: str
    min_provider_ms: int
    max_provider_ms: int
    quote_count: int
    status: str
    imported_at_ms: int
    stats_json: str


@dataclass(frozen=True, slots=True)
class FinalizedBar:
    """A confirmed BID/ASK bar (docs/09 Section 3.2, docs/03 Section 2).

    ``bar_id=(source_id, timeframe, start_ms)``. BID OHLC drives indicators; ASK
    OHLC is kept in parallel for executable short-side checks. The bar became
    usable only at ``available_at_ms``: the receipt of the first valid quote at or
    after ``end_ms`` (never earlier than ``end_ms``).
    """

    source_id: str
    timeframe: Timeframe
    start_ms: int
    end_ms: int
    open_bid: Decimal
    high_bid: Decimal
    low_bid: Decimal
    close_bid: Decimal
    open_ask: Decimal
    high_ask: Decimal
    low_ask: Decimal
    close_ask: Decimal
    tick_count: int
    first_received_ms: int
    last_received_ms: int
    closed_at_received_ms: int
    closing_event_key: str
    available_at_ms: int
    quality: BarQuality
    missing_m1_buckets: int
    source_origin: SourceOrigin

    @property
    def bar_id(self) -> str:
        return f"{self.source_id}:{self.timeframe.value}:{self.start_ms}"

    @property
    def finalization_delay_ms(self) -> int:
        return self.available_at_ms - self.end_ms


@dataclass(frozen=True, slots=True)
class GapRecord:
    """Missing buckets between two observed bars; nothing is fabricated to fill them."""

    source_id: str
    timeframe: Timeframe
    from_ms: int
    to_ms: int
    missing_bars: int
    kind: GapKind
    detected_at_ms: int


@dataclass(frozen=True, slots=True)
class MarketClosure:
    """An explicitly supplied UTC closure interval ``[start_ms, end_ms)`` (no guessed hours)."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if not (isinstance(self.start_ms, int) and isinstance(self.end_ms, int)):
            raise ValueError("closure bounds must be int UTC ms")
        if self.end_ms <= self.start_ms:
            raise ValueError("closure end must be after start")


@dataclass(frozen=True, slots=True)
class DataHealthPolicy:
    """Injected data-health thresholds. All OPEN (docs/11 Section 6.2): unset by default.

    Unset values never mean "healthy": they yield UNKNOWN / NOT_EVALUATED.
    """

    max_quote_age_ms: int | None = None
    max_first_postclose_delay_ms: int | None = None
    market_closures: tuple[MarketClosure, ...] = ()

    def __post_init__(self) -> None:
        for name in ("max_quote_age_ms", "max_first_postclose_delay_ms"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"{name} must be a positive int or None")

    def covered_by_closures(self, start_ms: int, end_ms: int) -> bool:
        """True if ``[start_ms, end_ms)`` lies entirely inside declared closures."""
        if end_ms <= start_ms:
            return True
        cursor = start_ms
        for closure in sorted(self.market_closures, key=lambda c: c.start_ms):
            if closure.end_ms <= cursor:
                continue
            if closure.start_ms > cursor:
                return False
            cursor = closure.end_ms
            if cursor >= end_ms:
                return True
        return False

    def closure_at(self, time_ms: int) -> MarketClosure | None:
        for closure in self.market_closures:
            if closure.start_ms <= time_ms < closure.end_ms:
                return closure
        return None


@dataclass(frozen=True, slots=True)
class Pivot:
    """A confirmed strict pivot (docs/04 Section 6).

    ID ``(source, timeframe, pivot_bar_id, side)``. Knowable only from
    ``available_at_ms`` (availability of the k+right bar), never at pivot time.
    """

    source_id: str
    timeframe: Timeframe
    side: PivotSide
    bar_id: str
    bar_index: int
    price: Decimal
    pivot_bar_start_ms: int
    pivot_bar_end_ms: int
    confirming_bar_id: str
    confirmed_at_ms: int
    available_at_ms: int
    window_irregular: bool
    calculation_version: str

    @property
    def pivot_id(self) -> str:
        return f"{self.bar_id}:{self.side.value}"


@dataclass(frozen=True, slots=True)
class IndicatorValue:
    """One timestamped feature value (docs/04 Section 3): never used before ``available_at_ms``."""

    name: str
    timeframe: Timeframe
    source_id: str
    bar_id: str | None
    event_time_ms: int | None  # end of the bar the value was computed on
    available_at_ms: int | None
    value: Decimal | None
    status: IndicatorStatus
    bars_seen: int
    required_bars: int
    calculation_version: str


@dataclass(frozen=True, slots=True)
class M15Assessment:
    """Side-specific M15 structural context (docs/04 Section 8)."""

    side: Side
    context: M15Context
    reference_pivot_id: str | None
    reference_price: Decimal | None
    reference_available_at_ms: int | None
    close_bid: Decimal | None
    ema: Decimal | None
    ema_previous: Decimal | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """docs/09 Section 3.3, built strictly from features available at ``decision_time_ms``.

    ``m15_context`` from the contract is side-specific, so it is carried as
    ``m15_buy`` and ``m15_sell``.
    """

    source_id: str
    decision_time_ms: int
    last_confirmed_h1_id: str | None
    last_confirmed_m15_id: str | None
    last_confirmed_m5_id: str | None
    h1_bias: H1Bias
    h1_bias_reasons: tuple[str, ...]
    h1_strength_spread_atr: Decimal | None
    h1_strength_slope_atr: Decimal | None
    m15_buy: M15Assessment
    m15_sell: M15Assessment
    ema_values: tuple[IndicatorValue, ...]
    atr_values: tuple[IndicatorValue, ...]
    confirmed_pivots: tuple[Pivot, ...]
    relevant_level_ids: tuple[str, ...]
    quality_flags: tuple[str, ...]
    calculation_version: str
    parameter_set_hash: str
