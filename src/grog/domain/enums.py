"""Enumerations and reason codes shared across Grog modules."""

from __future__ import annotations

from enum import StrEnum


class SourceOrigin(StrEnum):
    """Origin of a quote stream (docs/09 Section 3.1). Never mixed within one source."""

    SYNTHETIC = "SYNTHETIC"
    HISTORICAL = "HISTORICAL"
    BACKFILL = "BACKFILL"
    REFERENCE_LIVE = "REFERENCE_LIVE"


IMPORTABLE_ORIGINS = (SourceOrigin.SYNTHETIC, SourceOrigin.HISTORICAL)
"""Origins accepted by the offline canonical CSV importer (docs/09 Section 6)."""


class ImportRejectReason(StrEnum):
    """Structured reason codes for a rejected canonical CSV v1 import."""

    EMPTY_FILE = "EMPTY_FILE"
    INVALID_UTF8 = "INVALID_UTF8"
    INVALID_LINE_ENDING = "INVALID_LINE_ENDING"
    INVALID_HEADER = "INVALID_HEADER"
    NO_DATA_ROWS = "NO_DATA_ROWS"
    EMPTY_ROW = "EMPTY_ROW"
    WRONG_FIELD_COUNT = "WRONG_FIELD_COUNT"
    INVALID_UTC_MS = "INVALID_UTC_MS"
    INVALID_DECIMAL = "INVALID_DECIMAL"
    NONPOSITIVE_PRICE = "NONPOSITIVE_PRICE"
    ASK_BELOW_BID = "ASK_BELOW_BID"
    RECEIVED_TIME_OUT_OF_ORDER = "RECEIVED_TIME_OUT_OF_ORDER"
    PROVIDER_TIME_OUT_OF_ORDER = "PROVIDER_TIME_OUT_OF_ORDER"
    INVALID_SOURCE_ID = "INVALID_SOURCE_ID"
    INVALID_ORIGIN = "INVALID_ORIGIN"
    SOURCE_METADATA_CONFLICT = "SOURCE_METADATA_CONFLICT"
    OVERLAPS_EXISTING_BATCH = "OVERLAPS_EXISTING_BATCH"
    FILE_UNREADABLE = "FILE_UNREADABLE"


class QuoteFlag(StrEnum):
    """Quality facts attached to a normalized quote (never used to alter prices)."""

    PROVIDER_TIME_AHEAD_OF_RECEIPT = "PROVIDER_TIME_AHEAD_OF_RECEIPT"
    SAME_MS_AS_PREVIOUS = "SAME_MS_AS_PREVIOUS"


class Timeframe(StrEnum):
    """Bar timeframes with UTC half-open buckets ``[start, start + duration)``."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"

    @property
    def duration_ms(self) -> int:
        return _TIMEFRAME_MS[self]


_TIMEFRAME_MS = {
    Timeframe.M1: 60_000,
    Timeframe.M5: 300_000,
    Timeframe.M15: 900_000,
    Timeframe.H1: 3_600_000,
}

TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1)


class BarQuality(StrEnum):
    """docs/09 Section 3.2. INVALID is reserved: strict CSV v1 input cannot produce it."""

    COMPLETE = "COMPLETE"
    GAPPED = "GAPPED"
    INVALID = "INVALID"


class GapKind(StrEnum):
    """Why a stretch of time had no quotes."""

    DATA_GAP = "DATA_GAP"  # no explanation available: treated as missing data
    MARKET_CLOSED = "MARKET_CLOSED"  # entirely inside an explicitly declared closure


class FinalizationTiming(StrEnum):
    """Delay between a bar's mathematical end and its first post-close quote."""

    ON_TIME = "ON_TIME"
    MISSED_DATA_GAP = "MISSED_DATA_GAP"
    MARKET_CLOSED = "MARKET_CLOSED"
    NOT_EVALUATED = "NOT_EVALUATED"  # tolerance unset (OPEN): delay is reported only


class FeedStatus(StrEnum):
    """docs/03 Section 3 feed health, plus CLOSED (MD-09) and UNKNOWN for unset policy."""

    FRESH = "FRESH"
    STALE = "STALE"
    DEGRADED = "DEGRADED"
    CLOSED = "CLOSED"
    NO_DATA = "NO_DATA"
    UNKNOWN = "UNKNOWN"


class PivotSide(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class IndicatorStatus(StrEnum):
    VALID = "VALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    ZERO_VALUE = "ZERO_VALUE"  # e.g. ATR == 0: calculations scaled by it are unavailable


class H1Bias(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class M15Context(StrEnum):
    SUPPORTIVE = "SUPPORTIVE"
    CORRECTIVE = "CORRECTIVE"
    OPPOSING = "OPPOSING"
    UNKNOWN = "UNKNOWN"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class CandidateState(StrEnum):
    """S1 candidate states owned by the detector (docs/06 Section 2 vocabulary).

    READY / SKIPPED / MISSED / ENTERED belong to signal eligibility (M05+) and are
    never produced by the strategy detector.
    """

    FORMING = "FORMING"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


TERMINAL_CANDIDATE_STATES = frozenset(
    {CandidateState.SUPERSEDED, CandidateState.EXPIRED, CandidateState.INVALIDATED}
)


class S1EventKind(StrEnum):
    PAIR_REJECTED = "PAIR_REJECTED"  # newly confirmed pivot did not form a valid impulse pair
    CANDIDATE_CREATED = "CANDIDATE_CREATED"
    CANDIDATE_UPDATED = "CANDIDATE_UPDATED"  # a completed post-impulse M5 bar was evaluated
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    TRIGGER_OBSERVED = "TRIGGER_OBSERVED"  # immutable closed-bar trigger; NOT a READY signal


class ReasonCode(StrEnum):
    """Versioned S1 reason codes (docs/06 Section 10.4 vocabulary, frozen for S1 v0.2)."""

    # Data
    DATA_GAP = "DATA_GAP"
    HISTORY_INCOMPLETE = "HISTORY_INCOMPLETE"
    # Pair formation (docs/05 Section 4)
    NO_PRECEDING_PIVOT = "NO_PRECEDING_PIVOT"
    IMPULSE_NOT_POSITIVE = "IMPULSE_NOT_POSITIVE"
    IMPULSE_BELOW_ATR = "IMPULSE_BELOW_ATR"
    IMPULSE_TOO_OLD = "IMPULSE_TOO_OLD"
    M5_ATR_UNAVAILABLE = "M5_ATR_UNAVAILABLE"
    M5_ATR_ZERO = "M5_ATR_ZERO"
    DUPLICATE_PAIR = "DUPLICATE_PAIR"
    # Setup (docs/05 Sections 3, 5, 6)
    H1_BIAS_MISMATCH = "H1_BIAS_MISMATCH"
    PULLBACK_TOO_FEW_BARS = "PULLBACK_TOO_FEW_BARS"
    PULLBACK_SHALLOW = "PULLBACK_SHALLOW"
    PULLBACK_HEALTHY = "PULLBACK_HEALTHY"
    PULLBACK_INVALID = "PULLBACK_INVALID"  # depth > 0.75
    STRUCTURE_INVALIDATED = "STRUCTURE_INVALIDATED"  # frozen L/H endpoint reached
    TRIGGER_NOT_ELIGIBLE_BAR = "TRIGGER_NOT_ELIGIBLE_BAR"  # bar closed before pair observable
    TRIGGER_CLOSE_NOT_BEYOND = "TRIGGER_CLOSE_NOT_BEYOND"  # close did not break 2-bar extreme
    TRIGGER_BODY_WRONG_DIRECTION = "TRIGGER_BODY_WRONG_DIRECTION"
    TRIGGER_ALREADY_OBSERVED = "TRIGGER_ALREADY_OBSERVED"
    TRIGGER_CONFIRMED = "TRIGGER_CONFIRMED"
    FORMING_TTL_EXPIRED = "FORMING_TTL_EXPIRED"
    SUPERSEDED_BY_NEWER_PAIR = "SUPERSEDED_BY_NEWER_PAIR"
    # Signal eligibility / execution (docs/06 Sections 3-5, docs/07)
    DATA_STALE = "DATA_STALE"
    FEED_HEALTH_UNKNOWN = "FEED_HEALTH_UNKNOWN"  # stale threshold unset (OPEN)
    QUOTE_DELAY = "QUOTE_DELAY"  # first quote later than the declared maximum
    QUOTE_DELAY_UNEVALUATED = "QUOTE_DELAY_UNEVALUATED"  # maximum delay unset (OPEN)
    MARKET_CLOSED = "MARKET_CLOSED"
    CONTRACT_UNDEFINED = "CONTRACT_UNDEFINED"  # no declared price step / contract metadata
    FX_RATE_UNAVAILABLE = "FX_RATE_UNAVAILABLE"
    ENTRY_CHASE = "ENTRY_CHASE"
    OUTSIDE_ENTRY_BAND = "OUTSIDE_ENTRY_BAND"
    CONFIRMATION_LOST = "CONFIRMATION_LOST"
    SPREAD_OVER_LIMIT = "SPREAD_OVER_LIMIT"
    SPREAD_LIMIT_UNSET = "SPREAD_LIMIT_UNSET"
    COST_UNAVAILABLE = "COST_UNAVAILABLE"
    SIGNAL_TTL_EXPIRED = "SIGNAL_TTL_EXPIRED"
    PRE_ENTRY_STOP_TOUCH = "PRE_ENTRY_STOP_TOUCH"
    CANDIDATE_NOT_ACTIVE = "CANDIDATE_NOT_ACTIVE"
    EXPOSURE_REVIEW_REQUIRED = "EXPOSURE_REVIEW_REQUIRED"
    M15_STRICT_VETO = "M15_STRICT_VETO"  # only in the separately versioned strict variant
    # Soft context only (never a veto in the base S1)
    M15_CORRECTIVE = "M15_CORRECTIVE"
    M15_OPPOSING = "M15_OPPOSING"
    M15_UNKNOWN = "M15_UNKNOWN"


class ExitOutcome(StrEnum):
    TARGET = "TARGET"  # full position at TP2
    STOP = "STOP"
    OPEN = "OPEN"  # neither touched yet
    INDETERMINATE = "INDETERMINATE"  # both inside unsequenced data; never assume the order


class GateResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SignalState(StrEnum):
    READY = "READY"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class SignalEventKind(StrEnum):
    READY_ISSUED = "READY_ISSUED"
    MISSED_DATA_GAP = "MISSED_DATA_GAP"
    MISSED_PRICE_CHASE = "MISSED_PRICE_CHASE"
    NOT_ISSUED = "NOT_ISSUED"  # any other failed or UNKNOWN hard gate on the first quote
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"  # reversible overlay set / reasons changed
    EXECUTION_UNBLOCKED = "EXECUTION_UNBLOCKED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class ExecutionFidelity(StrEnum):
    SIMULATED = "SIMULATED"  # offline replay: never broker-verified
