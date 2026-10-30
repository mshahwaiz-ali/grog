"""Strict canonical BID/ASK CSV v1 parser (docs/09 Section 6, docs/03 Sections 8 and 10).

Format: UTF-8, comma separated, LF line endings, exact header
``provider_time_utc_ms,received_time_utc_ms,bid,ask``; integer UTC epoch
milliseconds and plain decimal price strings. No dialect guessing, no
seconds-vs-milliseconds guessing, no NaN/exponent coercion, no quoting.

Any invalid row rejects the **whole** file with a structured line/field/reason;
nothing is partially accepted. Rows must be in stream order: received time and
provider time are both non-decreasing (out-of-order streams belong to
adapter-specific transformations, not hidden exceptions here). Distinct quotes
with identical millisecond stamps are all retained in file order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from grog.domain.enums import IMPORTABLE_ORIGINS, ImportRejectReason, QuoteFlag, SourceOrigin
from grog.domain.ids import is_valid_source_id, sha256_hex, source_event_key
from grog.domain.models import CANONICAL_SYMBOL, NormalizedQuote

FORMAT_VERSION = "CANONICAL_CSV_V1"
HEADER = ("provider_time_utc_ms", "received_time_utc_ms", "bid", "ask")
MAX_UTC_MS = 253_402_300_799_999  # 9999-12-31T23:59:59.999Z, the datetime range limit

_INT_RE = re.compile(r"-?[0-9]+")
_DECIMAL_RE = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


class CsvImportError(ValueError):
    """Whole-file rejection. ``line`` is 1-based (header is line 1); 0 means file level."""

    def __init__(self, line: int, field: str, reason: ImportRejectReason, detail: str = "") -> None:
        self.line = line
        self.field = field
        self.reason = reason
        self.detail = detail
        super().__init__(self.describe())

    def describe(self) -> str:
        text = f"IMPORT_REJECTED line={self.line} field={self.field} reason={self.reason.value}"
        if self.detail:
            text += f" detail={self.detail}"
        return text


@dataclass(frozen=True, slots=True)
class BatchStats:
    """Facts about a parsed batch. Gap judgement is not made: thresholds are OPEN (docs/03 §3)."""

    row_count: int
    min_provider_ms: int
    max_provider_ms: int
    min_received_ms: int
    max_received_ms: int
    same_ms_quote_count: int
    provider_ahead_count: int
    max_provider_ahead_ms: int
    max_provider_interval_ms: int


@dataclass(frozen=True, slots=True)
class ParsedBatch:
    source_id: str
    source_origin: SourceOrigin
    raw_symbol: str
    file_sha256: str
    format_version: str
    quotes: tuple[NormalizedQuote, ...]
    stats: BatchStats


def _parse_utc_ms(text: str, line: int, field: str) -> int:
    if _INT_RE.fullmatch(text) is None:
        raise CsvImportError(line, field, ImportRejectReason.INVALID_UTC_MS, repr(text))
    value = int(text)
    if value < 0 or value > MAX_UTC_MS:
        raise CsvImportError(line, field, ImportRejectReason.INVALID_UTC_MS, repr(text))
    return value


def _parse_price(text: str, line: int, field: str) -> Decimal:
    if _DECIMAL_RE.fullmatch(text) is None:
        raise CsvImportError(line, field, ImportRejectReason.INVALID_DECIMAL, repr(text))
    value = Decimal(text)
    if value <= 0:
        raise CsvImportError(line, field, ImportRejectReason.NONPOSITIVE_PRICE, repr(text))
    return value


def parse_canonical_csv(
    data: bytes,
    *,
    source_id: str,
    origin: SourceOrigin | str,
    raw_symbol: str = CANONICAL_SYMBOL,
) -> ParsedBatch:
    """Parse and fully validate canonical CSV v1 bytes into normalized quotes."""
    if not is_valid_source_id(source_id):
        raise CsvImportError(
            0, "--source-id", ImportRejectReason.INVALID_SOURCE_ID, repr(source_id)
        )
    try:
        source_origin = SourceOrigin(origin)
    except ValueError as exc:
        raise CsvImportError(
            0, "--origin", ImportRejectReason.INVALID_ORIGIN, repr(origin)
        ) from exc
    if source_origin not in IMPORTABLE_ORIGINS:
        raise CsvImportError(0, "--origin", ImportRejectReason.INVALID_ORIGIN, source_origin.value)

    if not data:
        raise CsvImportError(0, "<file>", ImportRejectReason.EMPTY_FILE)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CsvImportError(0, "<file>", ImportRejectReason.INVALID_UTF8, str(exc)) from exc
    if "\r" in text:
        line = text[: text.index("\r")].count("\n") + 1
        raise CsvImportError(line, "<line>", ImportRejectReason.INVALID_LINE_ENDING, "CR found")

    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()  # a single trailing LF terminates the last row
    if not lines or tuple(lines[0].split(",")) != HEADER:
        found = lines[0] if lines else ""
        raise CsvImportError(1, "<header>", ImportRejectReason.INVALID_HEADER, repr(found[:80]))
    if len(lines) == 1:
        raise CsvImportError(0, "<file>", ImportRejectReason.NO_DATA_ROWS)

    file_sha = sha256_hex(data)
    quotes: list[NormalizedQuote] = []
    prev_provider = prev_received = -1
    same_ms = ahead = max_ahead = max_interval = 0

    for index, row in enumerate(lines[1:], start=1):
        line = index + 1
        if row == "":
            raise CsvImportError(line, "<row>", ImportRejectReason.EMPTY_ROW)
        fields = row.split(",")
        if len(fields) != len(HEADER):
            raise CsvImportError(
                line, "<row>", ImportRejectReason.WRONG_FIELD_COUNT, f"{len(fields)} fields"
            )
        provider = _parse_utc_ms(fields[0], line, HEADER[0])
        received = _parse_utc_ms(fields[1], line, HEADER[1])
        bid = _parse_price(fields[2], line, "bid")
        ask = _parse_price(fields[3], line, "ask")
        if ask < bid:
            raise CsvImportError(line, "ask", ImportRejectReason.ASK_BELOW_BID, f"{ask}<{bid}")
        if received < prev_received:
            raise CsvImportError(line, HEADER[1], ImportRejectReason.RECEIVED_TIME_OUT_OF_ORDER)
        if provider < prev_provider:
            raise CsvImportError(line, HEADER[0], ImportRejectReason.PROVIDER_TIME_OUT_OF_ORDER)

        flags: set[str] = set()
        if provider == prev_provider:
            same_ms += 1
            flags.add(QuoteFlag.SAME_MS_AS_PREVIOUS.value)
        elif prev_provider >= 0:
            max_interval = max(max_interval, provider - prev_provider)
        if provider > received:
            # Clock skew is logged as a fact; latency is never reported as negative.
            ahead += 1
            max_ahead = max(max_ahead, provider - received)
            flags.add(QuoteFlag.PROVIDER_TIME_AHEAD_OF_RECEIPT.value)

        quotes.append(
            NormalizedQuote(
                source_id=source_id,
                canonical_symbol=CANONICAL_SYMBOL,
                raw_symbol=raw_symbol,
                provider_time_ms=provider,
                received_time_ms=received,
                ingest_order=index,
                bid=bid,
                ask=ask,
                source_origin=source_origin,
                source_event_key=source_event_key(file_sha, index),
                flags=frozenset(flags),
            )
        )
        prev_provider, prev_received = provider, received

    stats = BatchStats(
        row_count=len(quotes),
        min_provider_ms=quotes[0].provider_time_ms,
        max_provider_ms=quotes[-1].provider_time_ms,
        min_received_ms=quotes[0].received_time_ms,
        max_received_ms=quotes[-1].received_time_ms,
        same_ms_quote_count=same_ms,
        provider_ahead_count=ahead,
        max_provider_ahead_ms=max_ahead,
        max_provider_interval_ms=max_interval,
    )
    return ParsedBatch(
        source_id=source_id,
        source_origin=source_origin,
        raw_symbol=raw_symbol,
        file_sha256=file_sha,
        format_version=FORMAT_VERSION,
        quotes=tuple(quotes),
        stats=stats,
    )
