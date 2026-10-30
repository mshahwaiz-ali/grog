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
