"""R0 audit regressions F-01..F-03, F-08 (docs/14): engine lane vs local operator lane.

A signal already ENTERED or USER_SKIPPED in the local journal is never shown as a fresh
opportunity; an original READY that is now EXECUTION BLOCKED or terminal never reads as
eligible; exposure is a factual warning that never blocks and invents no limit.
Fixture fills use declared test values only.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from grog.domain.enums import Side, SignalEventKind
from grog.journal.positions import EntryRequest, PlanRef, new_action_id
from grog.ui import manual, panels
from grog.ui.lanes import exposure, signal_lane
from ui_support import open_journal, record_unlinked, session, step_until


def _text(lines) -> str:
    return "\n".join("".join(seg for seg, _ in line) for line in lines)


def _ready(tmp_path: Path):
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    _, journal = open_journal(tmp_path)
    return s, sid, journal


def _enter(journal, s, sid):
    snap = s.snapshot()
    view = next(v for v in snap.signals if v.record.signal_id == sid)
    r = view.record
    q = snap.quote
    fill = q.ask if r.side is Side.BUY else q.bid
    return journal.record_entry(
        EntryRequest(
            action_id=new_action_id(),
            side=r.side,
            price=fill,
            qty=Decimal("0.10"),
            fill_ms=q.received_time_ms,
            source_id="syn",
            plan=PlanRef.from_record(r),
            signal_ready=True,
            stop=r.sl0,
        )
    )[0]


def test_entered_signal_is_not_a_fresh_opportunity(tmp_path: Path) -> None:
    s, sid, journal = _ready(tmp_path)
    snap = s.snapshot()
    before = _text(
        panels.proposals_panel(snap, s.pipeline.signals.events, journal.signal_actions("syn"))
    )
    assert "NO TRADE" not in before and "entry" in before
    pos = _enter(journal, s, sid)
    overlay = journal.signal_actions("syn")
    assert overlay[sid] == ("ENTERED", pos.position_id)
    text = _text(panels.proposals_panel(snap, s.pipeline.signals.events, overlay, (pos,)))
    assert "NO TRADE" in text and "already acted on" in text
    assert "ENTERED · READY" in text
    assert " entry " not in text  # no actionable entry line for a used signal
    row = dict(panels.ready_rows(snap, overlay=overlay))[sid]
    assert row[-1] == "ENTERED · READY SIMULATED"
    detail = _text(panels.signal_detail(snap, snap.signals[0], None, None, overlay, (pos,)))
    assert "Local journal: ENTERED" in detail and "[e]" not in detail
    assert "No on-plan action: already ENTERED locally" in detail


def test_skipped_signal_is_not_a_fresh_opportunity(tmp_path: Path) -> None:
    s, sid, journal = _ready(tmp_path)
    r = s.pipeline.signals.signals[sid]
    journal.record_skip(new_action_id(), PlanRef.from_record(r), effective_ms=r.first_ready_ms)
    overlay = journal.signal_actions("syn")
    snap = s.snapshot()
    lane = signal_lane(snap.signals[0], overlay)
    assert lane.operator == "USER_SKIPPED" and not lane.can_record
    assert not lane.fresh_opportunity
    text = _text(panels.proposals_panel(snap, s.pipeline.signals.events, overlay))
    assert "USER_SKIPPED · READY" in text and "NO TRADE" in text


def test_blocked_detail_never_reads_as_eligible(tmp_path: Path) -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    assert step_until(s, SignalEventKind.EXECUTION_BLOCKED) == sid
    snap = s.snapshot()
    v = next(v for v in snap.signals if v.record.signal_id == sid)
    d = _text(panels.signal_detail(snap, v, None, None))
    assert "Eligibility: PASS" not in d
    assert "Eligibility at issuance: PASS" in d
    assert "Now: EXECUTION BLOCKED" in d and "EXECUTION BLOCKED now:" in d
    assert "Record external fill (OFF_PLAN)" in d
    prop = _text(panels.proposals_panel(snap, s.pipeline.signals.events))
    assert "EXECUTION BLOCKED" in prop and "NO TRADE" in prop and " entry " not in prop


def test_terminal_signal_has_no_actions_and_is_not_resurrected() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    events = s.pipeline.signals.events
    while not any(
        e.signal_id == sid and e.kind in (SignalEventKind.EXPIRED, SignalEventKind.INVALIDATED)
        for e in events
    ):
        assert s.step()
    snap = s.snapshot()
    v = next(v for v in snap.signals if v.record.signal_id == sid)
    lane = signal_lane(v)
    assert lane.terminal and not lane.can_record and lane.current in ("EXPIRED", "INVALIDATED")
    d = _text(panels.signal_detail(snap, v, None, None))
    assert "[e]" not in d and "[s]" not in d and "never resurrected" in d
    assert "Now: READY" not in d


def test_exposure_warns_without_limit_or_blocking(tmp_path: Path) -> None:
    s, sid, journal = _ready(tmp_path)
    open_pos = record_unlinked(journal)  # fixture BUY
    snap = s.snapshot()
    view = next(v for v in snap.signals if v.record.signal_id == sid)
    side = view.record.side
    exp = exposure((open_pos,), side)
    w = exp.warnings()
    assert exp.open_count == 1
    assert any("SAME side" in x for x in w) == (side is Side.BUY)
    assert any("OPPOSITE side" in x for x in w) == (side is Side.SELL)
    assert w[-1].startswith("Overlap/exposure policy is OPEN")
    assert not any("max" in x.lower() for x in w)
    assert exposure((), side).warnings() == []
    # Live, detail and entry form all show it; the action stays available.
    overlay = journal.signal_actions("syn")
    live = _text(panels.proposals_panel(snap, s.pipeline.signals.events, overlay, (open_pos,)))
    assert "EXPOSURE:" in live and "NO TRADE" not in live
    detail = _text(panels.signal_detail(snap, view, None, None, overlay, (open_pos,)))
    assert "EXPOSURE:" in detail and "[e] Record external fill" in detail
    form = manual.entry_form(journal, snap, view, (open_pos,))
    assert any("EXPOSURE:" in str(x) for x in form.info)
