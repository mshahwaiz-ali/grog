"""Feed health and bar-finalization timing (docs/03 Sections 3 and 10; docs/08 MD-08/09/21).

Thresholds are OPEN (docs/11 Section 6.2) and arrive only through an injected
:class:`DataHealthPolicy`. An unset threshold yields ``UNKNOWN`` /
``NOT_EVALUATED`` with the measured fact, never a false all-clear. Market
closures are only those explicitly declared; no trading hours are guessed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from grog.domain.enums import BarQuality, FeedStatus, FinalizationTiming, GapKind, Timeframe
from grog.domain.models import DataHealthPolicy, FinalizedBar, GapRecord, NormalizedQuote
from grog.market_data.bars import BarHistory


@dataclass(frozen=True, slots=True)
class FeedHealth:
    status: FeedStatus
    reasons: tuple[str, ...]
    as_of_ms: int
    last_provider_ms: int | None
    last_received_ms: int | None
    quote_age_ms: int | None
    spread: Decimal | None
    unresolved_gap: GapRecord | None

    @property
    def allows_new_signals(self) -> bool:
        """Only a measured FRESH feed may ever support a new actionable signal."""
        return self.status is FeedStatus.FRESH


def classify_finalization(bar: FinalizedBar, policy: DataHealthPolicy) -> FinalizationTiming:
    """Was the first post-close quote late? (MD-21). The bar's prices are never backdated."""
    if bar.finalization_delay_ms > 0 and policy.covered_by_closures(
        bar.end_ms, bar.available_at_ms
    ):
        return FinalizationTiming.MARKET_CLOSED
    if policy.max_first_postclose_delay_ms is None:
        return FinalizationTiming.NOT_EVALUATED
    if bar.finalization_delay_ms > policy.max_first_postclose_delay_ms:
        return FinalizationTiming.MISSED_DATA_GAP
    return FinalizationTiming.ON_TIME


def unresolved_data_gap(
    gaps: Sequence[GapRecord], history: BarHistory, now_ms: int
) -> GapRecord | None:
    """Latest known M1 DATA_GAP not yet followed by a COMPLETE M5 bar starting at/after it."""
    known = [g for g in gaps if g.timeframe is Timeframe.M1 and g.detected_at_ms <= now_ms]
    data_gaps = [g for g in known if g.kind is GapKind.DATA_GAP]
    if not data_gaps:
        return None
    latest = data_gaps[-1]
    for bar in reversed(history.available(Timeframe.M5, now_ms)):
        if bar.start_ms < latest.to_ms:
            break
        if bar.quality is BarQuality.COMPLETE:
            return None
    return latest


def assess_feed(
    last_quote: NormalizedQuote | None,
    gaps: Sequence[GapRecord],
    history: BarHistory,
    now_ms: int,
    policy: DataHealthPolicy,
) -> FeedHealth:
    """Differentiate NO_DATA / CLOSED / STALE / DEGRADED / UNKNOWN / FRESH as of ``now_ms``."""
    if last_quote is None:
        return FeedHealth(FeedStatus.NO_DATA, ("NO_QUOTES",), now_ms, None, None, None, None, None)
    if now_ms < last_quote.received_time_ms:
        raise ValueError("assessment time precedes the last processed quote (lookahead)")

    age = now_ms - last_quote.received_time_ms
    reasons: list[str] = []
    gap = unresolved_data_gap(gaps, history, now_ms)
    closure = policy.closure_at(now_ms)

    if closure is not None:
        status = FeedStatus.CLOSED
        reasons.append("DECLARED_MARKET_CLOSURE")
    elif policy.max_quote_age_ms is not None and age > policy.max_quote_age_ms:
        status = FeedStatus.STALE
        reasons.append("QUOTE_AGE_EXCEEDS_POLICY")
    elif gap is not None:
        status = FeedStatus.DEGRADED
        reasons.append("UNRESOLVED_DATA_GAP")
    elif policy.max_quote_age_ms is None:
        status = FeedStatus.UNKNOWN
        reasons.append("STALE_THRESHOLD_UNSET")
    else:
        status = FeedStatus.FRESH
    if gap is not None and "UNRESOLVED_DATA_GAP" not in reasons:
        reasons.append("UNRESOLVED_DATA_GAP")
    if policy.max_quote_age_ms is None and "STALE_THRESHOLD_UNSET" not in reasons:
        reasons.append("STALE_THRESHOLD_UNSET")

    return FeedHealth(
        status=status,
        reasons=tuple(reasons),
        as_of_ms=now_ms,
        last_provider_ms=last_quote.provider_time_ms,
        last_received_ms=last_quote.received_time_ms,
        quote_age_ms=age,
        spread=last_quote.spread,
        unresolved_gap=gap,
    )
