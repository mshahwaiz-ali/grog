"""M09-H integrity hardening acceptance (docs/08 §15.6, REF-13..24).

Ported from the read-only review's scratch repros (each failed on 667d8ef before its fix).
Every file here is FIXTURE / synthetic test data; nothing proves real MT5 behavior.
"""

from __future__ import annotations

from pathlib import Path

from grog.adapters.mt5_reference.feed import ReferenceReader
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
