"""GROG-MT5-REF/1 record parsing (docs/09 §5.1): exact Decimal prices, strict fields."""

from __future__ import annotations

from decimal import Decimal

import pytest

from grog.adapters.mt5_reference.format import (
    CatchUpBegin,
    CatchUpEnd,
    EndOfFile,
    HeartbeatRecord,
    MetaRecord,
    RecordError,
    TickRecord,
    parse_line,
)


def test_meta_tick_heartbeat_and_blocks_parse_exactly() -> None:
    m = parse_line("M,1,GROG-MT5-REF/1,FIXTURE,syn,Demo-Srv,XAUUSD.fx,2,7200,fixture-1")
    assert m == MetaRecord(1, "FIXTURE", "syn", "Demo-Srv", "XAUUSD.fx", 2, 7200, "fixture-1")
    t = parse_line("T,2,L,1790820000100,4000.10,4000.35,6", digits=2)
    assert isinstance(t, TickRecord) and t.bid == Decimal("4000.10") and str(t.bid) == "4000.10"
    assert t.bid_changed and t.ask_changed and t.time_msc == 1790820000100
    only_ask = parse_line("T,3,B,1790820000200,,4000.40,4", digits=2)
    assert only_ask.bid is None and not only_ask.bid_changed and only_ask.ask_changed
    zero = parse_line("T,4,L,1790820000200,0,4000.40,4", digits=2)
    assert zero.bid is None  # MT5 leaves an unchanged side 0
    assert parse_line("H,5,1790820001000,0,CLOSED,10800") == HeartbeatRecord(
        5, 1790820001000, False, "CLOSED", 10800
    )
    assert parse_line("B,6,1790820000100") == CatchUpBegin(6, 1790820000100)
    assert parse_line("E,7,1790820000300,4") == CatchUpEnd(7, 1790820000300, 4)
    assert parse_line("Z,8,-") == EndOfFile(8, None)


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("X,1,foo", "UNKNOWN_RECORD"),
        ("T,1,L,1,4000.10,4000.35", "BAD_ARITY"),
        ("T,0,L,1,4000.10,4000.35,6", "BAD_INT"),
        ("T,1,Q,1,4000.10,4000.35,6", "BAD_MODE"),
        ("T,1,L,1,4000.1x,4000.35,6", "BAD_PRICE"),
        ("T,1,L,1,-4000.10,4000.35,6", "BAD_PRICE"),
        ("T,1,L,1,4000.123,4000.35,6", "PRICE_PRECISION"),
        ("T,1,L,1,1e3,4000.35,6", "BAD_PRICE"),
        ("T,1,L,abc,4000.10,4000.35,6", "BAD_INT"),
        ("H,1,1,2,OPEN,0", "BAD_HEARTBEAT"),
        ("H,1,1,1,MAYBE,0", "BAD_HEARTBEAT"),
        ("M,1,GROG-MT5-REF/2,FIXTURE,syn,s,X,2,0,v", "BAD_FORMAT"),
        ("M,1,GROG-MT5-REF/1,ROBOT,syn,s,X,2,0,v", "BAD_PRODUCER"),
        ("M,1,GROG-MT5-REF/1,FIXTURE,../etc,s,X,2,0,v", "BAD_SOURCE_ID"),
        ("T,1,L,1,4000.10,4000.35,6\r", "BAD_LINE_END"),
    ],
)
def test_invalid_records_are_rejected_with_codes(line: str, code: str) -> None:
    with pytest.raises(RecordError) as exc:
        parse_line(line, digits=2)
    assert exc.value.code == code
