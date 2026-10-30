"""Strict canonical CSV v1 parser (docs/09 §6; CL-03/05/06/07, MD-01/04/05/13/22)."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from grog.domain.enums import ImportRejectReason as R
from grog.domain.enums import QuoteFlag, SourceOrigin
from grog.market_data.import_csv import CsvImportError, parse_canonical_csv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_xauusd_v1.csv"
HEADER = "provider_time_utc_ms,received_time_utc_ms,bid,ask\n"


def parse(data: bytes, source_id: str = "syn-1", origin: str = "SYNTHETIC"):
    return parse_canonical_csv(data, source_id=source_id, origin=origin)


def rejects(data: bytes, line: int, field: str, reason: R, **kw: str) -> CsvImportError:
    with pytest.raises(CsvImportError) as info:
        parse(data, **kw)
    err = info.value
    assert (err.line, err.field, err.reason) == (line, field, reason), err.describe()
    return err


def test_fixture_parses_with_exact_decimals_and_order() -> None:
    data = FIXTURE.read_bytes()
    batch = parse(data)
    sha = hashlib.sha256(data).hexdigest()
    assert batch.file_sha256 == sha
    assert batch.format_version == "CANONICAL_CSV_V1"
    assert [q.ingest_order for q in batch.quotes] == [1, 2, 3, 4, 5, 6]
    assert [q.source_event_key for q in batch.quotes] == [f"{sha}#{i}" for i in range(1, 7)]
    first = batch.quotes[0]
    assert (first.bid, first.ask) == (Decimal("4000.00"), Decimal("4000.20"))
    assert str(first.ask) == "4000.20"  # exact decimal string preserved
    assert all(q.source_origin is SourceOrigin.SYNTHETIC for q in batch.quotes)
    assert all(q.canonical_symbol == "XAUUSD" and q.source_id == "syn-1" for q in batch.quotes)


def test_same_ms_distinct_quotes_all_retained_in_order() -> None:  # MD-01, CL-03
    batch = parse(FIXTURE.read_bytes())
    same = [q for q in batch.quotes if q.provider_time_ms == 1793440000300]
    assert [q.ingest_order for q in same] == [2, 3, 4]
    assert [(q.bid, q.ask) for q in same] == [
        (Decimal("4000.01"), Decimal("4000.21")),
        (Decimal("4000.02"), Decimal("4000.21")),
        (Decimal("4000.02"), Decimal("4000.22")),
    ]
    assert batch.stats.same_ms_quote_count == 2
    assert QuoteFlag.SAME_MS_AS_PREVIOUS in same[1].flags


def test_identical_rows_are_not_deduplicated() -> None:
    row = "1793440000000,1793440000000,4000.00,4000.20\n"
    batch = parse((HEADER + row + row).encode())
    assert len(batch.quotes) == 2
    assert batch.quotes[0].source_event_key != batch.quotes[1].source_event_key


def test_provider_ahead_of_receipt_logged_not_rejected() -> None:  # MD-05
    batch = parse(FIXTURE.read_bytes())
    ahead = [q for q in batch.quotes if QuoteFlag.PROVIDER_TIME_AHEAD_OF_RECEIPT in q.flags]
    assert [q.ingest_order for q in ahead] == [5]
    assert batch.stats.provider_ahead_count == 1 and batch.stats.max_provider_ahead_ms == 5


def test_stats_facts() -> None:
    s = parse(FIXTURE.read_bytes()).stats
    assert (s.row_count, s.min_provider_ms, s.max_provider_ms) == (6, 1793440000000, 1793440002500)
    assert (s.min_received_ms, s.max_received_ms) == (1793440000000, 1793440002510)
    assert s.max_provider_interval_ms == 1500


def test_zero_spread_boundary_accepted() -> None:
    batch = parse((HEADER + "1,1,4000.00,4000.00\n").encode())
    assert batch.quotes[0].spread == 0


def test_no_trailing_newline_accepted() -> None:
    assert len(parse((HEADER + "1,1,1.0,1.1").encode()).quotes) == 1


def test_two_sources_kept_distinct() -> None:  # MD-13, CL-06
    data = FIXTURE.read_bytes()
    a, b = parse(data, source_id="broker-a"), parse(data, source_id="broker-b")
    assert {q.source_id for q in a.quotes} == {"broker-a"}
    assert {q.source_id for q in b.quotes} == {"broker-b"}
    assert a.quotes[0] != b.quotes[0]


def test_parsing_is_deterministic() -> None:  # MD-22
    data = FIXTURE.read_bytes()
    assert parse(data) == parse(data)


def test_historical_origin() -> None:
    batch = parse(FIXTURE.read_bytes(), origin="HISTORICAL")
    assert batch.quotes[0].source_origin is SourceOrigin.HISTORICAL


@pytest.mark.parametrize(
    ("body", "line", "field", "reason"),
    [
        ("1793440000000,1793440000000,NaN,4000.2\n", 2, "bid", R.INVALID_DECIMAL),
        ("1793440000000,1793440000000,4000,inf\n", 2, "ask", R.INVALID_DECIMAL),
        ("1793440000000,1793440000000,4e3,4000.2\n", 2, "bid", R.INVALID_DECIMAL),
        ("1793440000000,1793440000000, 4000,4000.2\n", 2, "bid", R.INVALID_DECIMAL),
        ("1793440000000,1793440000000,4000.,4000.2\n", 2, "bid", R.INVALID_DECIMAL),
        ("1793440000000,1793440000000,,4000.2\n", 2, "bid", R.INVALID_DECIMAL),
        ("1793440000000,1793440000000,-4000.00,4000.20\n", 2, "bid", R.NONPOSITIVE_PRICE),
        ("1793440000000,1793440000000,0,0\n", 2, "bid", R.NONPOSITIVE_PRICE),
        ("1793440000000,1793440000000,4000.20,4000.10\n", 2, "ask", R.ASK_BELOW_BID),
        (
            "1793440000000.5,1793440000000,4000,4000.2\n",
            2,
            "provider_time_utc_ms",
            R.INVALID_UTC_MS,
        ),
        ("2026-10-31T10:00:00Z,1,4000,4000.2\n", 2, "provider_time_utc_ms", R.INVALID_UTC_MS),
        ("-1,1,4000,4000.2\n", 2, "provider_time_utc_ms", R.INVALID_UTC_MS),
        ("1,253402300800000,4000,4000.2\n", 2, "received_time_utc_ms", R.INVALID_UTC_MS),
        ("1,1,4000,4000.2,extra\n", 2, "<row>", R.WRONG_FIELD_COUNT),
        ("1,1,4000\n", 2, "<row>", R.WRONG_FIELD_COUNT),
        ('"1",1,4000,4000.2\n', 2, "provider_time_utc_ms", R.INVALID_UTC_MS),
        ("1,1,4000,4000.2\n\n2,2,4000,4000.2\n", 3, "<row>", R.EMPTY_ROW),
        (
            "5,5,4000,4000.2\n4,6,4000,4000.2\n",
            3,
            "provider_time_utc_ms",
            R.PROVIDER_TIME_OUT_OF_ORDER,
        ),
        (
            "5,5,4000,4000.2\n6,4,4000,4000.2\n",
            3,
            "received_time_utc_ms",
            R.RECEIVED_TIME_OUT_OF_ORDER,
        ),
    ],
)
def test_invalid_rows_reject_whole_batch(body: str, line: int, field: str, reason: R) -> None:
    rejects((HEADER + body).encode(), line, field, reason)


def test_single_invalid_row_inside_valid_batch_rejects_all() -> None:  # CL-07
    lines = FIXTURE.read_text().splitlines(keepends=True)
    lines.insert(4, "1793440000300,1793440000313,4000.30,4000.10\n")
    err = rejects("".join(lines).encode(), 5, "ask", R.ASK_BELOW_BID)
    assert err.describe().startswith("IMPORT_REJECTED line=5 field=ask reason=ASK_BELOW_BID")


@pytest.mark.parametrize(
    ("data", "line", "field", "reason"),
    [
        (b"", 0, "<file>", R.EMPTY_FILE),
        (HEADER.encode(), 0, "<file>", R.NO_DATA_ROWS),
        (b"time,bid,ask\n1,4000,4000.2\n", 1, "<header>", R.INVALID_HEADER),
        (b"1793440000000,1793440000000,4000.00,4000.20\n", 1, "<header>", R.INVALID_HEADER),
        (
            b"provider_time_utc_ms,received_time_utc_ms,ask,bid\n1,1,2,1\n",
            1,
            "<header>",
            R.INVALID_HEADER,
        ),
        (b"\xef\xbb\xbf" + HEADER.encode() + b"1,1,1,1\n", 1, "<header>", R.INVALID_HEADER),
        (
            HEADER.replace("\n", "\r\n").encode() + b"1,1,1,1\r\n",
            1,
            "<line>",
            R.INVALID_LINE_ENDING,
        ),
        (HEADER.encode() + b"1,1,\xff,1\n", 0, "<file>", R.INVALID_UTF8),
    ],
)
def test_file_level_rejections(data: bytes, line: int, field: str, reason: R) -> None:
    rejects(data, line, field, reason)


def test_invalid_source_and_origin_rejected() -> None:
    data = FIXTURE.read_bytes()
    rejects(data, 0, "--source-id", R.INVALID_SOURCE_ID, source_id="../x")
    rejects(data, 0, "--origin", R.INVALID_ORIGIN, origin="LIVE")
    rejects(data, 0, "--origin", R.INVALID_ORIGIN, origin="REFERENCE_LIVE")
    rejects(data, 0, "--origin", R.INVALID_ORIGIN, origin="BACKFILL")


def test_large_ordered_stream() -> None:
    rows = "".join(
        f"{1793440000000 + i // 3},{1793440000000 + i},4000.{i % 100:02d},4001.00\n"
        for i in range(30000)
    )
    batch = parse((HEADER + rows).encode())
    assert batch.stats.row_count == 30000 and batch.quotes[-1].ingest_order == 30000
