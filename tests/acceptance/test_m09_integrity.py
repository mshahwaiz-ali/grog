"""M09-H integrity hardening acceptance (docs/08 §15.6, REF-13..24).

Ported from the read-only review's scratch repros (each failed on 667d8ef before its fix).
Every file here is FIXTURE / synthetic test data; nothing proves real MT5 behavior.
"""

from __future__ import annotations

from pathlib import Path

from grog.live.session import ReferenceSession
from reference_support import HB_AGE, POLICY, SRC, StepClock, Writer
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
    s = ReferenceSession(exp, SRC, POLICY, clock, HB_AGE)
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
