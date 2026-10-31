"""M09-H integrity hardening acceptance (docs/08 §15.6, REF-13..24).

Ported from the read-only review's scratch repros (each failed on 667d8ef before its fix).
Every file here is FIXTURE / synthetic test data; nothing proves real MT5 behavior.
"""

from __future__ import annotations

from pathlib import Path

from grog.adapters.mt5_reference.feed import ReferenceReader, cursor_path_for
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
