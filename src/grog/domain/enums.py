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
