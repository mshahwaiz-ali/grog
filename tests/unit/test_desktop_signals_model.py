"""D02 Signals read model (GUI-23..27, GUI-29) against the real engine and journal service.

Rows and details come from ``build_overview_frame`` exactly as the replay owner publishes
them; expected values are read from engine records, events and snapshots, never typed in.
Journal writes happen only in disposable test databases through ``PositionJournal``.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

from grog.desktop.frames import FrameTag, assert_detached, build_overview_frame
from grog.desktop.loading import LoadRequest, read_journal
from grog.desktop.presentation import price_text, trigger_explanation, utc_ms_text
from grog.desktop.signals_model import Section
from grog.domain.enums import Side, SignalEventKind, SignalState
from grog.journal.positions import EntryRequest, PlanRef, TouchTracker, new_action_id
from grog.ui.panels import candidate_condition
from ui_support import open_journal, record_unlinked, session, step_until, synthetic_quotes

TAG = FrameTag("syn", 1, 1)


def _facts(s, overlay=None, positions=()):
    frame = build_overview_frame(
        s,
        tag=TAG,
        overlay={} if overlay is None else overlay,
        positions=list(positions),
        tracker=TouchTracker(),
        journal_note="test journal",
    )
    assert_detached(frame)
    return frame.signals


def _field(row, name: str) -> str:
    return dict(row.detail.fields)[name]


def _rows(facts):
    return [*facts.developing, *facts.current, *facts.history]


# ------------------------------------------------------------------ GUI-23 developing


def test_gui23_forming_row_explains_exact_next_bid_close_and_is_not_tradable() -> None:
    s = session()
    while not (s.snapshot().forming and any(s.snapshot().trigger_thresholds.values())):
        assert s.step()
    snap = s.snapshot()
    facts = _facts(s)
    assert [r.key for r in facts.developing] == [c.candidate_id for c in snap.forming]
    for c, row in zip(snap.forming, facts.developing, strict=True):
        status, needs = candidate_condition(snap, c)
        assert row.cells[3:5] == (status, needs) and row.state == status
        level = snap.trigger_thresholds.get(c.candidate_id)
        if level is not None and status == "FORMING":
            assert _field(row, "Trigger level (exact)") == price_text(level)
            assert trigger_explanation(c.side.value, level) in row.detail.notes
        assert row.detail.status == "NOT TRADABLE — developing"
        assert all(not a.enabled for a in row.detail.actions)
        assert _field(row, "First detected") == utc_ms_text(c.first_detected_ms)


def test_gui23_unknown_threshold_is_unavailable_not_zero() -> None:
    s = session()
    while not s.snapshot().forming:
        assert s.step()
    snap = s.snapshot()
    unknown = dataclasses.replace(
        snap, trigger_thresholds={c.candidate_id: None for c in snap.forming}
    )
    from types import SimpleNamespace

    owner = SimpleNamespace(snapshot=lambda: unknown, pipeline=s.pipeline, cursor=s.cursor)
    facts = _facts(owner)
    for row in facts.developing:
        assert _field(row, "Trigger level (exact)") == "UNAVAILABLE — not 0"
        assert "0.00" not in _field(row, "Trigger level (exact)")
        assert row.state in ("WAIT", "FORMING")
        if row.state == "FORMING":
            assert "UNKNOWN" in row.cells[4]


# ------------------------------------------------------------------ GUI-24 READY plans


def _exact_plan(row, r) -> None:
    ent, ex = ("ASK", "BID") if r.side is Side.BUY else ("BID", "ASK")
    assert _field(row, f"E0 = {ent} (entry side)") == price_text(r.e0)
    assert _field(row, "Original BID / ASK") == (
        f"{price_text(r.original_bid)} / {price_text(r.original_ask)}"
    )
    assert _field(row, "Entry band") == f"{price_text(r.entry_low)} – {price_text(r.entry_high)}"
    assert _field(row, f"SL0 ({ex} closes)") == price_text(r.sl0)
    assert _field(row, f"TP1 ({ex} closes)") == price_text(r.tp1)
    assert _field(row, f"TP2 ({ex} closes)") == price_text(r.tp2)
    assert _field(row, "Frozen ATR") == price_text(r.frozen_atr)
    assert _field(row, "Original gross risk") == price_text(r.original_risk_price)
    assert _field(row, "Expiry") == utc_ms_text(r.expiry_ms)
    assert _field(row, "Strategy / rules") == f"{r.strategy_version} · {r.signal_rules_version}"
    assert _field(row, "Signal ID") == r.signal_id and _field(row, "Trigger ID") == r.trigger_id
    assert _field(row, "Fidelity") == "SIMULATED — not broker-verified"


def test_gui24_ready_sell_then_buy_use_engine_sides_and_exact_immutable_plan() -> None:
    s = session()
    seen = set()
    for nth in (1, 2):
        sid = step_until(s, SignalEventKind.READY_ISSUED, 1)
        r = s.pipeline.signals.signals[sid]
        seen.add(r.side)
        facts = _facts(s)
        (row,) = facts.current
        assert row.key == sid and row.section is Section.CURRENT
        _exact_plan(row, r)
        ent, ex = ("ASK", "BID") if r.side is Side.BUY else ("BID", "ASK")
        assert row.cells[4] == f"{ent} {price_text(r.e0)}"
        assert row.cells[6] == f"{ex} {price_text(r.sl0)}"
        q = s.snapshot().quote
        assert _field(row, f"Current {ent}") == price_text(q.ask if r.side is Side.BUY else q.bid)
        issued = next(e for e in s.pipeline.signals.events if e.signal_id == sid)
        assert row.detail.lifecycle[0].startswith(f"#{issued.sequence} READY_ISSUED at ")
        assert ", ".join(c.value for c in issued.reason_codes) in row.detail.lifecycle[0]
        # D03: an unclaimed READY is eligible for the local entry/skip forms (the window
        # additionally requires a writable journal); the kinds carry the full signal ID.
        assert [(a.kind, a.signal_id, a.enabled) for a in row.detail.actions] == [
            ("entry", sid, True),
            ("skip", sid, True),
        ]
        assert nth == len(seen)
    assert seen == {Side.BUY, Side.SELL}


# ------------------------------------------------------------------ GUI-25 transitions


def test_gui25_issued_plan_is_immutable_while_current_state_changes_and_never_resurrects():
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    first = _facts(s).current[0]
    frozen = [(k, v) for k, v in first.detail.fields if k in FROZEN_FIELDS]
    events = s.pipeline.signals.events
    seen_states, n, terminal_seen = [], len(events), False
    while s.step():
        if len(events) == n:
            continue
        n = len(events)
        facts = _facts(s)
        row = facts.find(sid)
        assert row is not None
        assert [(k, v) for k, v in row.detail.fields if k in FROZEN_FIELDS] == frozen
        assert _field(row, "Issued").startswith("READY at ")
        state = s.snapshot().signals[0].status
        seen_states.append(row.state)
        if state.state is SignalState.READY:
            assert not terminal_seen and row.section is Section.CURRENT
            assert row.state == ("EXECUTION BLOCKED" if state.blocked else "READY")
        else:
            terminal_seen = True
            assert row.section is Section.HISTORY and row.state == state.state.value
            assert any("never resurrected" in note for note in row.detail.notes)
        # D03: eligible only while READY (blocked => OFF_PLAN entry); terminal never again.
        assert all(a.enabled is (not terminal_seen) for a in row.detail.actions)
        if terminal_seen:
            assert all("terminal" in a.reason for a in row.detail.actions)
        if terminal_seen and len(seen_states) > 6:
            break
    assert {"READY", "EXECUTION BLOCKED"} <= set(seen_states) and terminal_seen
    kinds = [e.kind.value for e in events if e.signal_id == sid]
    assert len(row.detail.lifecycle) == len(kinds)
    assert all(k in line for k, line in zip(kinds, row.detail.lifecycle, strict=True))


FROZEN_FIELDS = (
    "Signal ID",
    "Issued",
    "E0 = BID (entry side)",
    "E0 = ASK (entry side)",
    "Original BID / ASK",
    "Entry band",
    "SL0 (ASK closes)",
    "SL0 (BID closes)",
    "TP1 (ASK closes)",
    "TP2 (ASK closes)",
    "Frozen ATR",
    "Original gross risk",
    "Expiry",
)


# ------------------------------------------------------------------ GUI-26 pre-roll/exposure


def test_gui26_pre_roll_signals_are_history_only_and_engine_ids_unique() -> None:
    quotes = synthetic_quotes()
    s = session(from_ms=quotes[110_700].provider_time_ms)
    snap = s.snapshot()
    assert snap.signals and all(v.pre_roll for v in snap.signals)
    facts = _facts(s)
    assert facts.current == ()
    signal_rows = [r for r in facts.history if r.kind == "SIGNAL"]
    assert len(signal_rows) == len(snap.signals)
    assert all("PRE-ROLL" in r.state for r in signal_rows)
    assert all(any("PRE-ROLL" in n for n in r.detail.notes) for r in signal_rows)
    keys = [r.key for r in _rows(facts)]
    assert len(keys) == len(set(keys))  # one row per engine ID, no duplicate
    candidates = [r.candidate_id for r in signal_rows]
    assert len(candidates) == len(set(candidates))  # engine suppresses duplicate pairs


def test_gui26_exposure_is_a_factual_warning_without_limit(tmp_path: Path) -> None:
    s = session()
    step_until(s, SignalEventKind.READY_ISSUED)  # SELL
    store, journal = open_journal(tmp_path)
    try:
        held = record_unlinked(journal)  # fixture BUY
    finally:
        store.close()
    sell = _facts(s, positions=[held]).current[0]
    assert any("OPPOSITE side" in n for n in sell.detail.notes)
    step_until(s, SignalEventKind.READY_ISSUED)  # BUY
    buy = _facts(s, positions=[held]).current[0]
    assert any("SAME side" in n for n in buy.detail.notes)
    for row in (sell, buy):
        assert not any("max" in n.lower() for n in row.detail.notes)  # no invented limit
        assert "Overlap/exposure policy is OPEN: Grog shows this, it applies no limit." in (
            row.detail.notes
        )
        # exposure is a warning only: it never disables the eligible local forms
        assert all(a.enabled for a in row.detail.actions)


# ------------------------------------------------------------------ GUI-27 operator overlay


def test_gui27_claim_in_second_connection_moves_signal_out_of_current(tmp_path: Path) -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    r = s.pipeline.signals.signals[sid]
    request = LoadRequest("syn", state_dir=str(tmp_path / "state"))
    store, journal = open_journal(tmp_path)  # the "second connection" writer
    try:
        pos, _ = journal.record_entry(
            EntryRequest(
                action_id=new_action_id(),
                side=r.side,
                price=r.e0,
                qty=Decimal("0.10"),
                fill_ms=r.first_ready_ms,
                source_id="syn",
                plan=PlanRef.from_record(r),
                signal_ready=True,
                stop=r.sl0,
            )
        )
    finally:
        store.close()
    overlay, positions, _note = read_journal(request)  # the desktop's read-only refresh
    facts = _facts(s, overlay, positions)
    assert facts.current == ()
    row = facts.find(sid)
    assert row.section is Section.HISTORY and row.state == "ENTERED · READY"
    assert _field(row, "Operator (local journal)") == f"ENTERED ({pos.position_id})"
    assert _field(row, "Source") == f"{r.original_source_id} [SYNTHETIC]"
    assert all(not a.enabled and "already ENTERED" in a.reason for a in row.detail.actions)


def test_gui27_unreadable_journal_never_claims_unclaimed() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    frame = build_overview_frame(
        s, tag=TAG, overlay=None, positions=None, tracker=TouchTracker(), journal_note="x"
    )
    row = frame.signals.find(sid)
    assert not frame.signals.journal_ok
    assert _field(row, "Operator (local journal)") == "UNKNOWN — operator records unreadable"
    assert row.detail.tone == "warning"


# ------------------------------------------------------------------ GUI-29 history events


def test_gui29_history_labels_actual_event_kinds_without_fabricated_records() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED, 1)
    events = s.pipeline.signals.events
    while not any(e.kind is SignalEventKind.MISSED_PRICE_CHASE for e in events):
        assert s.step()
    snap = s.snapshot()
    facts = _facts(s)
    records = s.pipeline.signals.signals
    assert facts.current == () and all(
        v.status.state is not SignalState.READY for v in snap.signals
    )
    misses = [e for e in events if e.signal_id is None]
    event_rows = [r for r in facts.history if r.kind != "SIGNAL"]
    assert [r.key for r in event_rows] == [e.event_id for e in reversed(misses)]
    for e in misses:
        row = facts.find(e.event_id)
        assert row.kind == e.kind.value and row.cells[1] == e.kind.value
        assert row.key not in records and _field(row, "Signal ID") == "none — not issued"
        assert "READY" not in row.state
        assert _field(row, "Decision (receipt) time") == utc_ms_text(e.decision_time_ms)
    expired = facts.find(sid)
    assert expired.section is Section.HISTORY and expired.state in ("EXPIRED", "INVALIDATED")
    # A NOT_ISSUED / MISSED_DATA_GAP event is labelled with its own kind too.
    for kind in (SignalEventKind.NOT_ISSUED, SignalEventKind.MISSED_DATA_GAP):
        from grog.desktop.signals_model import build_signals_facts

        relabelled = dataclasses.replace(misses[0], kind=kind)
        other = build_signals_facts(snap, (relabelled,), {}, [], "n")
        (row,) = [r for r in other.history if r.kind != "SIGNAL"]
        assert row.kind == kind.value and row.detail.title == f"EVENT {kind.value}"
