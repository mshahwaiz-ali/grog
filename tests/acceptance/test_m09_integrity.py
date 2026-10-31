"""M09-H integrity hardening acceptance (docs/08 §15.6, REF-13..24).

Ported from the read-only review's scratch repros (each failed on 667d8ef before its fix).
Every file here is FIXTURE / synthetic test data; nothing proves real MT5 behavior.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from grog.adapters.mt5_reference.feed import (
    CursorCorruptError,
    CursorLockedError,
    ReferenceReader,
    cursor_path_for,
)
from grog.live.session import LinkStatus, ReferenceSession
from reference_support import HB_AGE, OFFSET_S, POLICY, SRC, T0, StepClock, Writer, srv
from ui_support import synthetic_quotes

CATCH_UP, LIVE_END = 66_000, 66_400


def _fixture_live_run(exp: Path, **kw) -> tuple[ReferenceSession, set[str], set[str]]:
    qs = synthetic_quotes()
    w = Writer(exp)  # producer FIXTURE
    w.begin(qs[0].provider_time_ms)
    for q in qs[:CATCH_UP]:
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask), mode="B")
    w.end(qs[CATCH_UP - 1].provider_time_ms, CATCH_UP)
    w.hb(qs[CATCH_UP - 1].provider_time_ms)
    clock = StepClock(qs[CATCH_UP - 1].received_time_ms)
    s = ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, **kw)
    s.poll()
    actionable: set[str] = set()
    simulated: set[str] = set()
    for q in qs[CATCH_UP:LIVE_END]:
        clock.now = q.received_time_ms
        w.hb(q.provider_time_ms)
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask))
        st = s.poll()
        actionable.update(st.actionable)
        simulated.update(st.simulated)
    return s, actionable, simulated


# REF-21 ---------------------------------------------------------------- review #4 (f1)
def test_fixture_producer_never_reaches_actionable_lane(tmp_path: Path) -> None:
    s, actionable, simulated = _fixture_live_run(tmp_path / "exp")
    st = s.status()
    assert st.label == "FIXTURE · SIMULATED"
    assert actionable == set(), "FIXTURE data produced actionable READY"
    assert simulated, "the would-be READY is shown only in the simulated lane"
    assert simulated <= s.live_ready
    assert "FIXTURE_SIMULATED" in st.blockers


def test_exporter_producer_ready_is_actionable_only_without_blockers(tmp_path: Path) -> None:
    """Counterexample guard: the actionable path still works for a non-fixture producer."""
    exp = tmp_path / "exp"
    qs = synthetic_quotes()
    w = Writer(exp, producer="MQL5_EXPORTER")  # test-written file in exporter format
    w.begin(qs[0].provider_time_ms)
    for q in qs[:CATCH_UP]:
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask), mode="B")
    w.end(qs[CATCH_UP - 1].provider_time_ms, CATCH_UP)
    w.hb(qs[CATCH_UP - 1].provider_time_ms)
    clock = StepClock(qs[CATCH_UP - 1].received_time_ms)
    s = ReferenceSession(
        exp, SRC, POLICY, clock, HB_AGE, time_basis_verified=True, max_future_skew_ms=1_000
    )
    s.poll()
    seen: set[str] = set()
    for q in qs[CATCH_UP:LIVE_END]:
        clock.now = q.received_time_ms
        w.hb(q.provider_time_ms)
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask))
        st = s.poll()
        seen.update(st.actionable)
        assert st.simulated == ()
    assert seen and seen <= s.live_ready


# REF-17 ---------------------------------------------------------------- review #1/#2/#3
def _reader(d: Path, clock, cursor: Path | None = None, **kw) -> ReferenceReader:
    return ReferenceReader(d, SRC, clock, POLICY.health.max_quote_age_ms, cursor, **kw)


def _accepted(r: ReferenceReader) -> int:
    c = r.state.counters
    return c.get("ACCEPTED_LIVE", 0) + c.get("ACCEPTED_BACKFILL", 0)


def test_future_provider_time_is_never_live(tmp_path: Path) -> None:  # review e1
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0 + 3_600_000, "4000.00", "4000.20")  # one hour ahead of receipt
    r = _reader(tmp_path, StepClock(T0 + 100))
    ev = [e for e in r.poll() if e.kind == "QUOTE"]
    assert ev == [] or not ev[0].live
    assert all("FUTURE_TIME" in e.quote.flags for e in ev)


def test_future_time_beyond_a_declared_tolerance_is_rejected_and_latched(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0 + 50, "4000.00", "4000.20")  # 50 ms ahead: within a declared 100 ms
    w.tick(T0 + 5_000, "4000.10", "4000.30")  # 4.9 s ahead: beyond it
    r = _reader(tmp_path, StepClock(T0), max_future_skew_ms=100)
    qs = [e.quote for e in r.poll() if e.kind == "QUOTE"]
    assert [q.provider_time_ms for q in qs] == [T0 + 50]
    assert "FUTURE_TIME" in qs[0].flags and "LIVE" not in qs[0].flags
    assert "FUTURE_TIME" in r.state.faults


def test_offset_change_mid_stream_is_latched(tmp_path: Path) -> None:  # review e2
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.line(f"H,{{seq}},{srv(T0 + 1000)},1,OPEN,{OFFSET_S - 3600}")  # offset -1 h (DST)
    w.line(f"T,{{seq}},L,{srv(T0 + 2000)},4000.10,4000.30,6")
    s = ReferenceSession(tmp_path, SRC, POLICY, StepClock(T0 + 2100), HB_AGE)
    st = s.poll()
    assert "OFFSET_CHANGED" in s.reader.state.faults
    assert st.link is LinkStatus.INTEGRITY_FAULT and "INTEGRITY_FAULT" in st.blockers


def test_catch_up_history_is_offset_assumed(tmp_path: Path) -> None:  # review e3
    """MT5 gives no historical offset: catch-up ticks converted with the offset observed now
    are flagged OFFSET_ASSUMED (a DST change inside them cannot be seen offline)."""
    w = Writer(tmp_path)
    w.begin(T0)
    summer_utc = T0 - 30 * 86_400_000
    w.line(f"T,{{seq}},B,{summer_utc + 3 * 3_600_000},4000.00,4000.20,6")  # server = UTC+3
    w.end(T0, 1)
    w.hb(T0)
    w.tick(T0, "4000.10", "4000.30")
    r = _reader(tmp_path, StepClock(T0 + 100))
    qs = [e.quote for e in r.poll() if e.kind == "QUOTE"]
    assert "OFFSET_ASSUMED" in qs[0].flags
    assert "OFFSET_ASSUMED" not in qs[1].flags


def test_unverified_time_basis_and_unset_skew_tolerance_block_actionable(tmp_path: Path) -> None:
    w = Writer(tmp_path, producer="MQL5_EXPORTER")
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    st = ReferenceSession(tmp_path, SRC, POLICY, StepClock(T0 + 100), HB_AGE).poll()
    assert st.link is LinkStatus.LIVE
    assert {"TIME_BASIS_UNVERIFIED", "FUTURE_SKEW_TOLERANCE_UNSET"} <= set(st.blockers)
    st2 = ReferenceSession(
        tmp_path,
        SRC,
        POLICY,
        StepClock(T0 + 100),
        HB_AGE,
        time_basis_verified=True,
        max_future_skew_ms=1_000,
    ).poll()
    assert st2.blockers == ()


# REF-15 / REF-18 / REF-19 / REF-16 (reader side) ----------------- review #9, #11-#15
def _session(d: Path, clock) -> ReferenceSession:
    return ReferenceSession(d, SRC, POLICY, clock, HB_AGE)


def test_catch_up_end_count_mismatch_is_latched(tmp_path: Path) -> None:  # review c1
    w = Writer(tmp_path)
    w.begin(T0)
    w.tick(T0, "4000.00", "4000.20", mode="B")
    w.end(T0 + 7_200_000, 5)  # claims 5 ticks; 1 written (failed/partial window)
    w.hb(T0 + 7_200_000)
    r = _reader(tmp_path, StepClock(T0 + 7_200_100))
    r.poll()
    assert "CATCHUP_COUNT_MISMATCH" in r.state.faults


def test_explicit_gap_record_is_latched(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.begin(T0)
    w.line(f"G,{{seq}},{srv(T0)},{srv(T0 + 3_599_999)},4401")
    w.end(T0 + 3_600_000, 0)
    r = _reader(tmp_path, StepClock(T0 + 3_600_100))
    r.poll()
    assert r.state.faults["SOURCE_GAP"][1] == 3
    assert "CATCHUP_COUNT_MISMATCH" not in r.state.faults


def test_catch_up_block_sequence_errors_are_latched(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.end(T0, 0)  # E without B
    w.begin(T0)
    w.begin(T0)  # B inside an open block
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert r.state.counters["CATCHUP_SEQUENCE"] == 2


def test_seq_gap_is_not_a_healthy_live_link(tmp_path: Path) -> None:  # review g1
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.seq += 5  # 5 lines lost
    w.hb(T0 + 50)
    w.tick(T0 + 50, "4000.10", "4000.30")
    st = _session(tmp_path, StepClock(T0 + 100)).poll()
    assert st.counters.get("TRANSPORT_SEQ_GAP")
    assert st.link is LinkStatus.INTEGRITY_FAULT and st.actionable == ()


def test_unexpected_eof_without_z_is_not_healthy(tmp_path: Path) -> None:  # review g2
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.open("20261001T000100Z", 1)  # new file, previous never closed with Z
    w.hb(T0 + 50)
    w.tick(T0 + 50, "4000.10", "4000.30")
    st = _session(tmp_path, StepClock(T0 + 100)).poll()
    assert st.counters.get("FILE_ENDED_WITHOUT_Z")
    assert st.link is LinkStatus.INTEGRITY_FAULT


def test_clean_rotation_across_polls_is_not_a_fault(tmp_path: Path) -> None:
    """Counterexample: Z read in one poll, next file appearing in a later poll is clean."""
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.eof("next")
    clock = StepClock(T0 + 100)
    s = _session(tmp_path, clock)
    s.poll()
    w.open("20261001T000000Z", 2)
    w.hb(T0 + 200)
    w.tick(T0 + 200, "4000.10", "4000.30")
    clock.now = T0 + 300
    st = s.poll()
    assert st.link is LinkStatus.LIVE and s.reader.state.faults == {}


def _second_file(w: Writer, meta: str) -> None:
    w.eof()
    w.name = f"{SRC}__20261001T000100Z__000001.grogref"
    w.seq = 0
    w.line(meta)


def test_changed_server_symbol_digits_mid_stream_is_rejected(tmp_path: Path) -> None:  # g3
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    _second_file(
        w, f"M,{{seq}},GROG-MT5-REF/1,FIXTURE,{SRC},Other-Server,GOLD,3,{OFFSET_S},fixture-1"
    )
    w.hb(T0 + 50)
    w.line(f"T,{{seq}},L,{srv(T0 + 50)},4000.105,4000.305,6")
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert _accepted(r) == 1, "ticks from a different server/symbol/digits joined the series"
    assert "META_CHANGED" in r.state.faults
    assert (r.state.server, r.state.raw_symbol, r.state.digits) == (
        "Fixture-Demo-Server",
        "XAUUSD.fx",
        2,
    )


def test_invalid_meta_does_not_inherit_previous_files_meta(tmp_path: Path) -> None:  # g4
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    _second_file(w, "M,{seq},GROG-MT5-REF/1,MQL5_EXPORTER,syn,broken")
    w.hb(T0 + 50)
    w.tick(T0 + 50, "4000.10", "4000.30")
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert _accepted(r) == 1, "file with invalid META accepted under the previous file's META"
    assert "META_INVALID" in r.state.faults


def test_source_mismatch_meta_blocks_following_ticks(tmp_path: Path) -> None:  # g5
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    _second_file(w, f"M,{{seq}},GROG-MT5-REF/1,FIXTURE,other,S,XAUUSD,2,{OFFSET_S},x")
    w.tick(T0 + 50, "4000.10", "4000.30")
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert _accepted(r) == 1 and "SOURCE_MISMATCH" in r.state.faults


def test_missing_cursor_file_is_detected(tmp_path: Path) -> None:  # review g6
    exp, state = tmp_path / "exp", tmp_path / "state"
    w = Writer(exp)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    clock = StepClock(T0 + 100)
    r = _reader(exp, clock, cursor_path_for(state, SRC))
    r.poll()
    r.commit()
    first = w.path
    w.tick(T0 + 10, "4000.10", "4000.30")  # unread tail ...
    first.unlink()  # ... and the file disappears
    w.open("20261001T000100Z", 1)
    w.tick(T0 + 20, "4000.20", "4000.40")
    r2 = _reader(exp, clock, cursor_path_for(state, SRC))
    r2.poll()
    assert "CURSOR_FILE_MISSING" in r2.state.faults


def test_truncated_or_rewritten_file_is_detected(tmp_path: Path) -> None:  # review g7
    w = Writer(tmp_path)
    w.hb(T0)
    for i in range(20):
        w.tick(T0 + i, "4000.00", "4000.20")
    clock = StepClock(T0 + 100)
    r = _reader(tmp_path, clock)
    r.poll()
    w.path.unlink()
    w.open("20261001T000000Z", 1)  # same name, restarted at seq 1 (FILE_WRITE truncation)
    w.hb(T0 + 200)
    w.tick(T0 + 200, "4000.50", "4000.70")
    clock.now = T0 + 300
    r.poll()
    assert _accepted(r) == 21 or "FILE_TRUNCATED" in r.state.faults


def test_replaced_file_with_a_different_first_line_is_detected(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    text = w.path.read_text().replace("fixture-1", "fixture-2", 1) + "H,4,1,1,OPEN,7200\n"
    w.path.write_text(text)  # same name, same size or longer, different content
    r.poll()
    assert "FILE_REPLACED" in r.state.faults


def test_malformed_line_and_live_out_of_order_are_latched(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0 + 10, "4000.00", "4000.20")
    w.line(f"T,{{seq}},L,{srv(T0)},4000.10,4000.30,6")  # live tick older than the last
    w.line("T,{seq},L,notanumber,4000.10,4000.30,6")
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert {"OUT_OF_ORDER", "BAD_INT"} <= set(r.state.faults)


# REF-14 / REF-20 ------------------------------------------------------ review #5/#6/#16
def test_block_start_redelivery_is_dropped_and_distinct_same_ms_ticks_kept(
    tmp_path: Path,
) -> None:
    """Exact count and order: identical content twice in one ms is two ticks; the catch-up
    block's inclusive start re-delivers them and both copies are dropped."""
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.tick(T0, "4000.00", "4000.20")  # genuine identical second tick in the same ms
    w.tick(T0, "4000.05", "4000.20", flags=2)
    w.begin(T0)  # reconnect: inclusive re-delivery of the watermark ms
    w.tick(T0, "4000.00", "4000.20", mode="B")
    w.tick(T0, "4000.00", "4000.20", mode="B")
    w.tick(T0, "4000.05", "4000.20", flags=2, mode="B")
    w.tick(T0 + 1, "4000.10", "4000.20", flags=2, mode="B")
    w.end(T0 + 1, 4)
    r = _reader(tmp_path, StepClock(T0 + 100))
    qs = [e.quote for e in r.poll() if e.kind == "QUOTE"]
    assert [(q.provider_time_ms - T0, str(q.bid)) for q in qs] == [
        (0, "4000.00"),
        (0, "4000.00"),
        (0, "4000.05"),
        (1, "4000.10"),
    ]
    assert r.state.counters["DUPLICATE"] == 3 and r.state.faults == {}


def test_genuine_identical_same_ms_tick_after_catch_up_is_not_dropped(tmp_path: Path) -> None:
    """review b2: the live poll after E writes only NEW ticks of the watermark ms."""
    w = Writer(tmp_path)
    w.begin(T0)
    w.tick(T0, "4000.00", "4000.20", mode="B")
    w.end(T0, 1)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")  # second, genuinely distinct occurrence (live poll)
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert _accepted(r) == 2 and "DUPLICATE" not in r.state.counters


def test_unchanged_side_value_contradicting_state_is_flagged(tmp_path: Path) -> None:  # k1
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.tick(T0 + 10, "4000.05", "4000.90", flags=2)  # only BID changed, yet ASK differs
    r = _reader(tmp_path, StepClock(T0 + 100))
    q = [e.quote for e in r.poll() if e.kind == "QUOTE"][-1]
    assert "SIDE_INCONSISTENT" in q.flags and "SIDE_INCONSISTENT" in r.state.faults


def test_unchanged_side_with_the_same_value_is_consistent(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.tick(T0 + 10, "4000.05", "4000.20", flags=2)  # populated, unchanged, equal: fine
    r = _reader(tmp_path, StepClock(T0 + 100))
    q = [e.quote for e in r.poll() if e.kind == "QUOTE"][-1]
    assert "SIDE_INCONSISTENT" not in q.flags and "ASK_CARRIED" not in q.flags
    assert r.state.faults == {}


def test_rejected_older_redelivery_does_not_reset_live_occurrences(tmp_path: Path) -> None:
    """Counterexample: an old re-delivered tick must not make the next genuine tick a dup."""
    w = Writer(tmp_path)
    w.hb(T0)
    w.tick(T0 + 5, "4000.00", "4000.20")
    w.begin(T0)
    w.tick(T0, "3999.00", "3999.20", mode="B")  # older history: dropped
    w.end(T0, 1)
    w.tick(T0 + 5, "4000.00", "4000.20")  # genuine second occurrence at T0+5
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert r.state.counters["ACCEPTED_LIVE"] == 2 and "DUPLICATE" not in r.state.counters


# REF-23 ---------------------------------------------------------------- review #20/#21
_RSS_SCRIPT = """
import resource, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from reference_support import HB_AGE, POLICY, SRC, StepClock, T0
from grog.live.session import ReferenceSession
s = ReferenceSession(Path(sys.argv[1]), SRC, POLICY, StepClock(T0 + 10**9), HB_AGE)
st = s.poll()
print(st.counters.get("ACCEPTED_BACKFILL", 0), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
"""
RSS_LINES = 400_000
RSS_CEILING_KIB = 200 * 1024  # engineering guard: the unbounded reader needed ~1 KiB/line


def _large_file(d: Path, n: int) -> Path:
    d.mkdir(parents=True)
    p = d / f"{SRC}__20261001T000000Z__000001.grogref"
    off = OFFSET_S * 1000
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"M,1,GROG-MT5-REF/1,FIXTURE,{SRC},S,XAUUSD,2,{OFFSET_S},x\n")
        fh.write(f"B,2,{T0 + off}\n")
        for i in range(n):
            b = 400_000 + (i * 7_919) % 2_000
            fh.write(f"T,{i + 3},B,{T0 + off + i * 250},{b / 100:.2f},{(b + 20) / 100:.2f},6\n")
        fh.write(f"E,{n + 3},{T0 + off + n * 250},{n}\n")
    return p


def test_large_history_is_streamed_with_bounded_memory(tmp_path: Path) -> None:
    import subprocess
    import sys

    _large_file(tmp_path / "exp", RSS_LINES)
    tests_dir = str(Path(__file__).resolve().parents[1])
    out = subprocess.run(
        [sys.executable, "-c", _RSS_SCRIPT, str(tmp_path / "exp"), tests_dir],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    accepted, maxrss_kib = int(out[0]), int(out[1])
    print(f"{accepted} lines, maxRSS {maxrss_kib / 1024:.0f} MiB")
    assert accepted == RSS_LINES
    assert maxrss_kib < RSS_CEILING_KIB


def test_idle_polls_never_rewrite_the_cursor(tmp_path: Path) -> None:
    exp, state = tmp_path / "exp", tmp_path / "state"
    w = Writer(exp)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    clock = StepClock(T0 + 100)
    s = ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state)
    writes: list[int] = []
    real = s.reader.commit
    s.reader.commit = lambda: (writes.append(clock.now), real())[1]  # type: ignore[method-assign]
    s.poll()  # first progress: committed
    for i in range(1, 30):  # idle timer polls
        clock.now = T0 + 100 + i * 1_000
        s.poll()
    assert writes == [T0 + 100]
    w.hb(T0 + 31_000)
    clock.now = T0 + 31_000
    s.poll()  # progress after the commit interval: committed
    assert writes == [T0 + 100, T0 + 31_000]


# REF-22 ------------------------------------------------------ review #17/#18/#19, fence
def test_second_cursor_writer_is_refused(tmp_path: Path) -> None:  # review h1
    exp, state = tmp_path / "exp", tmp_path / "state"
    w = Writer(exp)
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    clock = StepClock(T0 + 100)
    a = ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state)
    with pytest.raises(CursorLockedError, match="CURSOR_LOCKED"):
        ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state)
    # a read-only status reader never commits and needs no lock
    ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state, commit=False).poll()
    a.shutdown()
    ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state).shutdown()


def test_corrupt_cursor_is_reported_explicitly(tmp_path: Path) -> None:  # review h2
    exp, state = tmp_path / "exp", tmp_path / "state"
    Writer(exp).hb(T0)
    p = cursor_path_for(state, SRC)
    p.parent.mkdir(parents=True)
    p.write_text('{"version": 1, "position": {"fi')  # torn write
    with pytest.raises(CursorCorruptError, match="CURSOR_CORRUPT"):
        ReferenceSession(exp, SRC, POLICY, StepClock(T0), HB_AGE, state_dir=state)


def test_restart_warm_up_is_reconstructed_and_never_actionable(tmp_path: Path) -> None:
    """review j1: receipt times are not persisted, so warm-up bars carry the restart time
    as availability; the warm-up is marked RECONSTRUCTED and its READY is historical."""
    exp, state = tmp_path / "exp", tmp_path / "state"
    qs = synthetic_quotes()[:3_000]
    w = Writer(exp)
    w.hb(qs[0].provider_time_ms)
    clock = StepClock(qs[0].received_time_ms)
    a = ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state)
    for q in qs:
        clock.now = q.received_time_ms
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask))
        a.poll()
    a.flush()
    a.shutdown()
    clock.now = qs[-1].received_time_ms + 3_600_000  # restart one hour later
    b = ReferenceSession(exp, SRC, POLICY, clock, HB_AGE, state_dir=state)
    last = b.pipeline.aggregator.last_quote
    assert last is not None and "RECONSTRUCTED" in last.flags
    st = b.status()
    assert st.reconstructed and b.live_ready == set()
    b.shutdown()


def test_startup_backlog_is_fenced_as_backfill(tmp_path: Path) -> None:
    """A restart re-reads the uncommitted tail (crash before commit). Those lines may have
    produced a READY the previous process already showed, so the first poll after start is
    BACKFILL: nothing it issues can be replayed as a new actionable opportunity."""
    w = Writer(tmp_path, producer="MQL5_EXPORTER")
    w.hb(T0)
    w.tick(T0, "4000.00", "4000.20")
    w.tick(T0 + 500, "4000.10", "4000.30")  # LIVE-eligible by age at restart time
    clock = StepClock(T0 + 1_000)
    s = ReferenceSession(tmp_path, SRC, POLICY, clock, HB_AGE)
    fed: list[bool] = []
    real = s._feed  # noqa: SLF001
    s._feed = lambda q, live: (fed.append(live), real(q, live))[1]  # type: ignore[method-assign]
    st = s.poll()
    assert st.counters["ACCEPTED_LIVE"] == 2  # the reader alone would call them live
    assert fed == [False, False]  # ... the startup fence makes them BACKFILL
    w.hb(T0 + 1_500)
    w.tick(T0 + 1_500, "4000.20", "4000.40")
    clock.now = T0 + 1_600
    s.poll()
    assert fed == [False, False, True]  # after the fence, live ticks are live again


def test_reference_status_reports_a_corrupt_cursor_without_a_traceback(
    tmp_path: Path, isolated_env: dict[str, str]
) -> None:
    import io

    from grog.cli import EXIT_CONFIG, main

    exp, state = tmp_path / "exp", tmp_path / "state"
    Writer(exp).hb(T0)
    p = cursor_path_for(state, SRC)
    p.parent.mkdir(parents=True)
    p.write_text("{")
    cfg = tmp_path / "ref.toml"
    cfg.write_text(f'config_version = 1\n[reference]\nsource_id = "syn"\nexporter_dir = "{exp}"\n')
    out, err = io.StringIO(), io.StringIO()
    argv = ["reference-status", "--config", str(cfg), "--state-dir", str(state)]
    code = main(argv, env=isolated_env, stdout=out, stderr=err)
    assert code == EXIT_CONFIG and "code=CURSOR_CORRUPT" in err.getvalue()


# REF-13..16 exporter source (H1) -------------------------- review #7-#11, #22-#24
# The exporter is uncompiled and has never run in MT5: these are SOURCE checks of the
# documented contract, not evidence of runtime behavior (M09-B).
_MQ5 = Path(__file__).resolve().parents[2] / "mql5" / "GrogReferenceExporter.mq5"


def _mq5_code() -> str:
    text = _MQ5.read_text(encoding="utf-8")
    return re.sub(r"//[^\n]*", "", text)  # comments stripped: only code counts


def _mq5_function(name: str) -> str:
    code = _mq5_code()
    m = re.search(rf"\b{name}\([^)]*\)\s*\{{", code)
    assert m, f"{name} missing"
    depth, i = 0, m.end() - 1
    for j in range(i, len(code)):
        depth += {"{": 1, "}": -1}.get(code[j], 0)
        if depth == 0:
            return code[i : j + 1]
    raise AssertionError(name)


def test_exporter_writes_binary_utf8_lf_bytes() -> None:  # review a1/a2
    code = _mq5_code()
    assert "FILE_TXT" not in code and "FILE_ANSI" not in code and "FILE_UNICODE" not in code
    assert "FILE_BIN" in code and "CP_UTF8" in code and "FileWriteArray" in code
    assert "FileWriteString" not in code and "%%d" not in code  # no nested StringFormat


def test_strict_parser_rejects_crlf_and_code_page_bytes(tmp_path: Path) -> None:
    w = Writer(tmp_path)
    w.hb(T0)
    w.raw(f"T,3,L,{srv(T0)},4000.00,4000.20,6\r\n")
    w.raw(f"T,4,L,{srv(T0)},4000.00,4000.20,6\n")
    p = w.path
    p.write_bytes(p.read_bytes() + f"H,5,{srv(T0)},1,OPEN,{OFFSET_S}\n".encode())
    r = _reader(tmp_path, StepClock(T0 + 100))
    r.poll()
    assert "BAD_LINE_END" in r.state.faults
    q = tmp_path / "cp"
    q.mkdir()
    (q / f"{SRC}__20261001T000000Z__000001.grogref").write_bytes(
        f"M,1,GROG-MT5-REF/1,MQL5_EXPORTER,{SRC},Brökér,XAUUSD,2,{OFFSET_S},v\n".encode("cp1252")
    )
    r2 = _reader(q, StepClock(T0 + 100))
    r2.poll()
    assert {"BAD_ENCODING", "META_INVALID"} <= set(r2.state.faults)


def test_exporter_windows_do_not_overlap() -> None:  # review b1 (root cause: exporter)
    body = _mq5_function("CatchUpStep")
    assert re.search(r"to_msc\s*=\s*b\s*-\s*1\s*;", body), "inclusive CopyTicksRange end"
    assert re.search(r"FetchTicks\(\s*a\s*,\s*to_msc", body)


def test_exporter_retries_then_writes_an_explicit_gap() -> None:  # review c (#9)
    code = _mq5_code()
    assert re.search(r"#define\s+EXPORT_ATTEMPTS\s+3\b", code)
    fetch = _mq5_function("FetchTicks")
    assert "ResetLastError" in fetch and "GetLastError" in fetch and "EXPORT_ATTEMPTS" in fetch
    step = _mq5_function("CatchUpStep")
    assert 'WriteRecord("G"' in step
    assert 'WriteRecord("E"' in step and "g_cu_ticks" in step


def test_exporter_checks_writes_and_never_advances_past_unwritten_data() -> None:  # #10
    write = _mq5_function("WriteRecord")
    assert re.search(r"FileWriteArray\([^;]*\)\s*!=", write) and "g_write_failed = true" in write
    save = _mq5_function("SaveState")
    assert re.search(r"if\s*\(\s*g_write_failed\s*\)\s*return", save)
    assert "FileMove(" in save and "FILE_REWRITE" in save and ".tmp" in save  # atomic
    load = _mq5_function("LoadState")
    assert "return -1" in load
    init = _mq5_function("OnInit")
    assert "INIT_PARAMETERS_INCORRECT" in init and "ValidSourceId" in init
    assert re.search(r"start\s*<\s*0\)[^;]*\{[^}]*INIT_FAILED", init, re.S)


def test_exporter_never_reuses_or_truncates_a_file_name() -> None:  # #11
    open_part = _mq5_function("OpenPart")
    assert "FileIsExist" in open_part
    assert "NewSessionStamp" in _mq5_function("OnInit") and "FileIsExist" in _mq5_function(
        "NewSessionStamp"
    )


def test_exporter_catch_up_is_timer_driven_and_sessions_may_wrap() -> None:  # #22/#23
    timer = _mq5_function("OnTimer")
    assert "CatchUpStep" in timer and "Heartbeat" in timer
    assert "CatchUpStep" not in _mq5_function("OnInit")
    session = _mq5_function("InSession")
    assert "previous_day" in session and re.search(r"f\s*<\s*t", session)
    assert "yday" in _mq5_function("SessionState")
