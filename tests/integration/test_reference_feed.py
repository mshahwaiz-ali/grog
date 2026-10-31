"""M09-A reference feed: normalizer + durable reader over recorded-format fixtures (docs/09 §5.1).

Behavioral tests: exact UTC/prices, same-millisecond ticks, BID-only / ASK-only updates,
invalid / crossed / duplicate / out-of-order events, rotation, torn lines and restart recovery.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from grog.adapters.mt5_reference.feed import ReferenceReader, cursor_path_for
from reference_support import OFFSET_S, SRC, T0, StepClock, Writer, srv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reference"
AGE = 60_000


def quotes(events):
    return [e.quote for e in events if e.kind == "QUOTE"]


def reader(d: Path, clock, state: Path | None = None, age: int | None = AGE) -> ReferenceReader:
    cursor = cursor_path_for(state, SRC) if state is not None else None
    return ReferenceReader(d, SRC, clock, age, cursor)


def test_recorded_fixture_integrity(tmp_path: Path) -> None:
    d = tmp_path / "x"
    shutil.copytree(FIXTURES, d)
    r = reader(d, StepClock(T0 + 1_000))
    events = r.poll()
    qs = quotes(events)
    # UTC = server time_msc - exporter offset; prices exact Decimals as written.
    assert [q.provider_time_ms for q in qs] == [T0 + 100, T0 + 100, T0 + 100, T0 + 200, T0 + 300]
    assert [(str(q.bid), str(q.ask)) for q in qs] == [
        ("4000.10", "4000.35"),
        ("4000.12", "4000.35"),
        ("4000.12", "4000.35"),  # identical same-ms tick kept: occurrence 1, not a duplicate
        ("4000.12", "4000.40"),  # ASK-only: BID carried
        ("4000.20", "4000.40"),  # BID-only: ASK carried
    ]
    assert len({q.source_event_key for q in qs}) == 5
    assert qs[1].source_event_key.endswith(":0") and qs[2].source_event_key.endswith(":1")
    assert "BID_CARRIED" in qs[3].flags and "ASK_CHANGED" in qs[3].flags
    assert "ASK_CARRIED" in qs[4].flags and "BID_CHANGED" in qs[4].flags
    assert all("LIVE" in q.flags and "FIXTURE" in q.flags for q in qs)
    assert [q.ingest_order for q in qs] == [1, 2, 3, 4, 5]
    c = r.state.counters
    assert c["CROSSED"] == 1 and c["NON_QUOTE"] == 1 and c["PRICE_PRECISION"] == 1
    assert c["INVALID_PRICE"] == 1 and c["OUT_OF_ORDER"] == 2  # late live tick + older catch-up
    assert c["DUPLICATE"] == 3  # catch-up overlap re-delivering the three ms-100 ticks
    assert c["ACCEPTED_LIVE"] == 5 and "TRANSPORT_SEQ_GAP" not in c
    assert r.state.heartbeat is not None and r.state.heartbeat.connected


def test_unchanged_side_before_any_value_is_held_out(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.tick(T0, "", "4000.30", flags=4)  # ASK-only first tick: BID never seen
    w.tick(T0 + 1, "4000.00", "", flags=2)  # BID-only: ASK still unknown (first was held out)
    w.tick(T0 + 2, "4000.00", "4000.30", flags=6)
    r = reader(tmp_path, StepClock(T0 + 10))
    qs = quotes(r.poll())
    assert r.state.counters["SIDE_UNKNOWN"] == 2  # never a guessed side
    assert [q.provider_time_ms for q in qs] == [T0 + 2]


def test_heartbeat_offset_change_applies_forward_only(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.tick(T0, "4000.00", "4000.20")
    w.offset_s = OFFSET_S + 3600  # server moved (e.g. DST): exporter reports the new offset
    w.hb(T0 + 500)
    w.line(f"T,{{seq}},L,{T0 + 1_000 + (OFFSET_S + 3600) * 1000},4000.10,4000.30,6")
    r = reader(tmp_path, StepClock(T0 + 2_000))
    qs = quotes(r.poll())
    assert [q.provider_time_ms for q in qs] == [T0, T0 + 1_000]
    assert "OFFSET_CHANGED" in r.state.faults  # history across two offsets blocks READY


def test_backfill_vs_live_tagging(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.begin(T0)
    w.tick(T0, "4000.00", "4000.20", mode="B")
    w.end(T0, 1)
    w.tick(T0 + 1_000, "4000.10", "4000.30")  # old live line read late (backlog)
    w.tick(T0 + 200_000, "4000.20", "4000.40")  # fresh live line
    clock = StepClock(T0 + 200_500)
    qs = quotes(reader(tmp_path, clock).poll())
    assert ["LIVE" in q.flags for q in qs] == [False, False, True]
    assert ["BACKFILL" in q.flags for q in qs] == [True, True, False]
    # With the freshness threshold unset nothing can ever be LIVE.
    qs2 = quotes(reader(tmp_path, clock, age=None).poll())
    assert not any("LIVE" in q.flags for q in qs2)


def test_restart_recovers_every_tick_exactly_once(tmp_path: Path) -> None:
    exp, state = tmp_path / "exp", tmp_path / "state"
    w = Writer(exp)
    for i in range(5):
        w.tick(T0 + i * 100, f"4000.{i:02d}", f"4001.{i:02d}")
    w.raw(f"T,7,L,{srv(T0 + 600)},4000.06,4001")  # torn line: exporter still writing
    clock = StepClock(T0 + 1_000)
    a = reader(exp, clock, state)
    first = quotes(a.poll())
    a.commit()
    assert len(first) == 5
    # Crash before commit of a later poll: lines after the committed cursor are re-delivered.
    w.raw(".06,6\n")
    w.seq = 7
    w.tick(T0 + 600, "4000.07", "4001.07")
    lost = reader(exp, clock, state)
    assert len(quotes(lost.poll())) == 2  # read, but never committed (simulated crash)
    b = reader(exp, clock, state)
    w.tick(T0 + 700, "4000.08", "4001.08")
    second = quotes(b.poll())
    b.commit()
    keys = [q.source_event_key for q in first + second]
    assert len(keys) == len(set(keys)) == 8
    assert [q.provider_time_ms for q in second] == [T0 + 600, T0 + 600, T0 + 700]
    assert [q.ingest_order for q in second] == [6, 7, 8]
    assert "TRANSPORT_SEQ_GAP" not in b.state.counters
    c = reader(exp, clock, state)
    assert quotes(c.poll()) == []  # nothing re-emitted after a clean commit


def test_rotation_partial_line_and_sequence_gap(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.tick(T0, "4000.00", "4000.20")
    w.eof("next")
    w.open("20261001T000000Z", 2)
    w.tick(T0 + 100, "4000.01", "4000.21")
    w.raw("T,3,L,999")  # crash mid-line, exporter restarted with a new session file
    w.open("20261001T010000Z", 1)
    w.seq = 2  # one line lost in transport
    w.tick(T0 + 200, "4000.02", "4000.22")
    r = reader(tmp_path, StepClock(T0 + 1_000))
    qs = quotes(r.poll())
    assert [q.provider_time_ms for q in qs] == [T0, T0 + 100, T0 + 200]
    c = r.state.counters
    assert c["PARTIAL_LINE_DISCARDED"] == 1 and c["FILE_ENDED_WITHOUT_Z"] == 1
    assert c["TRANSPORT_SEQ_GAP"] == 1


def test_wrong_source_meta_is_rejected(tmp_path: Path) -> None:
    w = Writer(tmp_path, source=SRC)
    path = w.path
    text = path.read_text().replace(f"FIXTURE,{SRC},", "FIXTURE,other,", 1)
    path.write_text(text)
    w.tick(T0, "4000.00", "4000.20")
    r = reader(tmp_path, StepClock(T0 + 1_000))
    assert quotes(r.poll()) == []
    assert r.state.counters["SOURCE_MISMATCH"] == 1 and r.state.counters["NO_META"] == 1
