"""M09-A ReferenceSession: timer-driven link/feed state, backfill vs live READY, restart,
no journal side effects, deterministic engine compatibility (docs/09 §5.1).

All data are FIXTURE files (synthetic prices) and are labeled FIXTURE · SIMULATED.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from grog.domain.enums import FeedStatus, SignalEventKind, SignalState
from grog.live.session import LinkStatus, ReferenceSession, not_configured
from grog.signals.pipeline import S1ResearchPipeline
from reference_support import HB_AGE, POLICY, SRC, T0, StepClock, Writer
from ui_support import synthetic_quotes

CATCH_UP = 66_000  # synthetic quotes delivered as catch-up history (first READY is later)
LIVE_END = 66_400


def session(exp: Path, clock, state: Path | None = None, hb: int | None = HB_AGE):
    return ReferenceSession(exp, SRC, POLICY, clock, hb, state_dir=state)


def _hb_tick(w: Writer, t: int) -> None:
    w.hb(t)
    w.tick(t, "4000.00", "4000.20")


def test_link_states_are_evaluated_on_the_timer_without_new_ticks(tmp_path: Path) -> None:
    clock = StepClock(T0)
    s = session(tmp_path, clock)
    assert s.poll().link is LinkStatus.NO_DATA
    w = Writer(tmp_path)
    _hb_tick(w, T0)
    clock.now = T0 + 100
    st = s.poll()
    assert st.link is LinkStatus.LIVE and st.feed.status is FeedStatus.FRESH
    assert st.label == "FIXTURE · SIMULATED" and not st.broker_verified
    clock.now = T0 + HB_AGE + 101  # nothing new written: the timer alone detects silence
    st = s.poll()
    assert st.link is LinkStatus.OFFLINE and "HEARTBEAT_AGE_EXCEEDS_POLICY" in st.reasons
    clock.now = T0 + 61_000
    assert s.poll().feed.status is FeedStatus.STALE  # quote age, also without a new tick
    w.hb(T0 + 61_000)
    w.line("H,{seq}," + str(T0 + 61_500 + 7_200_000) + ",0,OPEN,7200")
    st = s.poll()
    assert st.link is LinkStatus.DISCONNECTED
    w.hb(T0 + 62_000)
    w.line("H,{seq}," + str(T0 + 62_000 + 7_200_000) + ",1,CLOSED,7200")
    assert s.poll().link is LinkStatus.MARKET_CLOSED
    w.begin(T0 + 62_000)
    w.hb(T0 + 62_000)
    assert s.poll().link is LinkStatus.CATCHING_UP


def test_unset_heartbeat_threshold_is_unknown_never_live(tmp_path: Path) -> None:
    clock = StepClock(T0 + 100)
    w = Writer(tmp_path)
    _hb_tick(w, T0)
    st = session(tmp_path, clock, hb=None).poll()
    assert st.link is LinkStatus.UNKNOWN and st.reasons == ("HEARTBEAT_THRESHOLD_UNSET",)
    assert st.actionable == ()


def test_not_configured_status() -> None:
    st = not_configured(T0)
    assert st.link is LinkStatus.NOT_CONFIGURED and st.last_quote is None
    assert st.label == "NOT CONFIGURED" and st.actionable == ()


@cache
def _replay_ready() -> dict:
    pipe = S1ResearchPipeline(SRC, POLICY)
    out = {}
    for q in synthetic_quotes()[:LIVE_END]:
        for e in pipe.on_quote(q).signal_events:
            if e.kind is SignalEventKind.READY_ISSUED:
                out[e.signal_id] = pipe.signals.signals[e.signal_id]
    return out


def _catch_up(exp: Path, n: int) -> Writer:
    """History delivered as one CopyTicksRange-style catch-up block."""
    qs = synthetic_quotes()
    w = Writer(exp)
    w.begin(qs[0].provider_time_ms)
    for q in qs[:n]:
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask), mode="B")
    w.end(qs[n - 1].provider_time_ms, n)
    w.hb(qs[n - 1].provider_time_ms)
    return w


def test_live_ready_matches_replay_and_backfill_ready_is_never_actionable(tmp_path: Path) -> None:
    exp = tmp_path / "exp"
    qs = synthetic_quotes()
    w = _catch_up(exp, CATCH_UP)
    clock = StepClock(qs[CATCH_UP - 1].received_time_ms)
    s = session(exp, clock)
    assert s.poll().link is LinkStatus.LIVE
    seen_actionable: set[str] = set()
    for q in qs[CATCH_UP:LIVE_END]:  # live ticks, polled by the timer as they arrive
        clock.now = q.received_time_ms
        w.hb(q.provider_time_ms)
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask))
        seen_actionable.update(s.poll().actionable)
    # Exact prices and timestamps reach the engine unchanged.
    last = s.pipeline.aggregator.last_quote
    ref = qs[LIVE_END - 1]
    assert (last.provider_time_ms, last.bid, last.ask) == (ref.provider_time_ms, ref.bid, ref.ask)
    replay = _replay_ready()
    live_ids = s.live_ready - s.historical_ready
    assert live_ids, "a READY must be issued from live fixture ticks"
    for sid in live_ids:  # same immutable plan as the REPLAY pipeline on the same ticks
        a, b = s.pipeline.signals.signals[sid], replay[sid]
        assert (a.side, a.e0, a.sl0, a.tp1, a.tp2, a.expiry_ms) == (
            b.side,
            b.e0,
            b.sl0,
            b.tp1,
            b.tp2,
            b.expiry_ms,
        )
    assert seen_actionable and seen_actionable <= live_ids
    assert s.reader.state.counters.get("TRANSPORT_SEQ_GAP", 0) == 0
    assert s.reader.state.counters["ACCEPTED_LIVE"] == LIVE_END - CATCH_UP


def test_catch_up_ready_is_historical(tmp_path: Path) -> None:
    exp = tmp_path / "exp"
    qs = synthetic_quotes()
    _catch_up(exp, LIVE_END)  # the READY moment arrives only via catch-up
    clock = StepClock(qs[LIVE_END - 1].received_time_ms)
    s = session(exp, clock)
    st = s.poll()
    assert st.link is LinkStatus.LIVE and st.feed.status is FeedStatus.FRESH
    assert s.live_ready == set() and st.actionable == ()  # no retrospective LIVE READY
    assert s.reader.state.counters.get("ACCEPTED_LIVE", 0) == 0
    print("historical READY from catch-up:", st.historical)


def test_ready_issued_on_backfill_quotes_is_never_actionable(tmp_path: Path) -> None:
    """Even if the engine issues READY while BACKFILL quotes are processed (e.g. a restart
    backlog), the session keeps it historical: still READY in the engine, never actionable."""
    qs = synthetic_quotes()
    w = Writer(tmp_path)
    w.hb(qs[0].provider_time_ms)
    clock = StepClock(qs[0].received_time_ms)
    s = session(tmp_path, clock)
    s.poll()
    for q in qs[:LIVE_END]:
        s._feed(q, live=False)  # noqa: SLF001 - exercising the BACKFILL path directly
        if s.historical_ready:
            break
    clock.now = q.received_time_ms
    w.hb(q.provider_time_ms)
    s.poll()
    ready_now = [
        sid for sid, v in s.pipeline.signals.status.items() if v.state is SignalState.READY
    ]
    st = s.status()
    assert st.link is LinkStatus.LIVE and st.feed.status is FeedStatus.FRESH
    assert set(st.historical) == set(ready_now) == set(_replay_ready())
    assert st.actionable == ()


def test_restart_warms_up_from_retained_files_and_never_writes_journal(tmp_path: Path) -> None:
    exp, state = tmp_path / "exp", tmp_path / "state"
    qs = synthetic_quotes()
    w = Writer(exp)
    for q in qs[:2_000]:
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask), mode="B")
    clock = StepClock(qs[1_999].received_time_ms)
    a = session(exp, clock, state)
    a.poll()
    bars_before = {
        tf: a.pipeline.aggregator.history.count(tf) for tf in a.pipeline.aggregator.history._bars
    }  # noqa: SLF001
    for q in qs[2_000:2_100]:
        w.tick(q.provider_time_ms, str(q.bid), str(q.ask), mode="B")
    b = session(exp, clock, state)  # restart: history up to the cursor is replayed first
    assert b.pipeline.aggregator.last_quote.provider_time_ms == qs[1_999].provider_time_ms
    assert {tf: b.pipeline.aggregator.history.count(tf) for tf in bars_before} == bars_before
    b.poll()
    assert b.pipeline.aggregator.last_quote.provider_time_ms == qs[2_099].provider_time_ms
    assert b.reader.state.counters.get("DUPLICATE", 0) == 0
    # Prices never create journal records: the only file written is the reference cursor.
    written = sorted(p.relative_to(state).as_posix() for p in state.rglob("*") if p.is_file())
    assert written == [f"reference/{SRC}.cursor.json"]
