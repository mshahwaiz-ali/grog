"""D03 manual-record model (Qt-free): forms, commands and records against real journals.

Every write goes through ``PositionJournal`` on a disposable tmp database; expected
values come from the validated domain helpers, never from re-implemented arithmetic.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from decimal import Decimal

import pytest

from grog.desktop.frames import (
    FrameTag,
    assert_detached,
    build_overview_frame,
    mark_facts,
    signal_check,
)
from grog.desktop.journal_model import (
    OUTCOME_UNKNOWN,
    Command,
    CommandKind,
    JournalMode,
    execute,
    read_snapshot,
)
from grog.desktop.manual_forms import (
    confirm_open_spec,
    entry_spec,
    exit_spec,
    modify_spec,
    off_plan_spec,
    skip_spec,
)
from grog.desktop.records_model import (
    ENGINE_PROVENANCE,
    OPERATOR_PROVENANCE,
    STREAM_ENGINE,
    STREAM_OPERATOR,
    engine_entries,
    filter_entries,
    operator_entries,
    position_detail,
    position_rows,
)
from grog.domain.enums import Side, SignalEventKind, SignalState
from grog.journal.positions import (
    EntryRequest,
    JournalError,
    PlanRef,
    PositionJournal,
    PositionState,
    TouchTracker,
    current_risk,
    entry_preview,
    new_action_id,
    r_breakdown,
)
from grog.ui.format import iso_utc
from grog.ui.manual import _fees_line, _preview_entry_lines, manual_journal_rows
from ui_support import open_journal, session, step_until

SRC, GEN = "syn", 1


def ready(nth: int = 1):
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED, nth)
    return s, sid, signal_check(s, token=1, source_id=SRC, generation=GEN, signal_id=sid)


def defaults(spec) -> dict[str, str]:
    return {f.key: spec.prefill.get(f.key, f.default) for f in spec.fields}


def snap_of(journal, seq: int = 1):
    return read_snapshot(
        journal, generation=GEN, sequence=seq, source_id=SRC, mode=JournalMode.WRITABLE,
        reason="test",
    )  # fmt: skip


def save(spec, values, journal, action_id=None, fresh=None):
    parsed = spec.parse(values)
    assert not parsed.errors, parsed.errors
    cmd = spec.build(7, action_id or new_action_id(), parsed.values, fresh)
    return cmd, execute(journal, cmd)


def entered(tmp_path, qty="0.10"):
    s, sid, chk = ready()
    store, j = open_journal(tmp_path)
    spec = entry_spec(chk)
    v = defaults(spec) | {"price": str(chk.plan.e0), "qty": qty}
    _cmd, res = save(spec, v, j)
    assert res.saved and res.created
    return s, chk, store, j, j.get(res.position_id)


# --------------------------------------------------------------------------- GUI-30 / 31


def test_gui30_entry_form_shows_immutable_plan_and_domain_preview_and_saves_one_event(tmp_path):
    s, sid, chk = ready()
    view = next(v for v in s.snapshot().signals if v.record.signal_id == sid)
    assert chk.plan == PlanRef.from_record(view.record)  # immutable PlanRef, exact Decimals
    assert chk.state == SignalState.READY.value and not chk.blocked
    spec = entry_spec(chk)
    text = "\n".join(t for t, _ in (*spec.identity, *spec.context))
    assert sid in text and "SIMULATED (REPLAY)" in text and f"source {SRC}" in text
    assert "Grog sends no order" in text and "Paused while recording" in text
    v = defaults(spec) | {"price": str(chk.plan.e0), "qty": "0.10"}
    assert v["time"] == iso_utc(chk.virtual_ms)  # editable suggested replay time
    assert any("editable suggested replay time" in f.hint for f in spec.fields)
    lines, errors = spec.render_preview(v)
    assert errors == {}
    prev = entry_preview(
        chk.plan.side, chk.plan.e0, chk.virtual_ms, chk.plan, signal_ready=True,
        signal_blocked=False, known_clock_ms=chk.virtual_ms,
    )  # fmt: skip
    expected = [*_preview_entry_lines(prev, chk.plan.side, chk.plan), _fees_line(None)]
    assert [t for t, _ in lines] == ["".join(t for t, _ in line) for line in expected]
    store, j = open_journal(tmp_path)
    before = len(j.events())
    cmd, res = save(spec, v, j)
    assert res.saved and res.created and "SAVED LOCALLY" in res.message
    assert len(j.events()) == before + 1  # exactly one local event
    pos = j.get(res.position_id)
    assert pos.plan == chk.plan and pos.plan_status.value == "ON_PLAN"
    assert j.signal_actions(SRC) == {sid: ("ENTERED", pos.position_id)}
    assert_detached(cmd)
    store.close()


@pytest.mark.parametrize(
    ("field", "text", "code"),
    [
        ("price", "", "MISSING_VALUE"),
        ("qty", "", "MISSING_VALUE"),
        ("time", "", "MISSING_VALUE"),
        ("price", "-1", "INVALID_NUMBER"),
        ("qty", "0", "INVALID_NUMBER"),
        ("price", "NaN", "INVALID_NUMBER"),
        ("qty", "Infinity", "INVALID_NUMBER"),
        ("price", "4,001.5", "INVALID_NUMBER"),
        ("time", "2026-13-01T00:00:00Z", "INVALID_TIME"),
        ("time", "yesterday", "INVALID_TIME"),
        ("fees", "-0.01", "INVALID_NUMBER"),
    ],
)
def test_gui31_invalid_inputs_are_per_field_errors_and_never_written(tmp_path, field, text, code):
    _s, _sid, chk = ready()
    spec = entry_spec(chk)
    v = defaults(spec) | {"price": "4000.5", "qty": "0.1", field: text}
    parsed = spec.parse(v)
    assert list(parsed.errors) == [field] and parsed.errors[field].startswith(code)
    lines, errors = spec.render_preview(v)
    assert errors and lines[0][0].startswith("NOT READY TO SAVE")
    store, j = open_journal(tmp_path)
    assert j.events() == []  # an invalid form never reaches the journal
    store.close()


def test_gui31_fees_blank_is_unknown_and_zero_is_a_known_zero(tmp_path):
    _s, _sid, chk = ready()
    spec = entry_spec(chk)
    base = defaults(spec) | {"price": str(chk.plan.e0), "qty": "0.1"}
    assert spec.parse(base).values["fees"] is None
    assert spec.parse(base | {"fees": "0"}).values["fees"] == Decimal("0")
    assert spec.parse(base | {"fees": "+1.250"}).values["fees"] == Decimal("1.250")
    assert any("Fees: UNKNOWN" in t for t, _ in spec.render_preview(base)[0])
    assert any(t.startswith("Fees: 0 ") for t, _ in spec.render_preview(base | {"fees": "0"})[0])
    store, j = open_journal(tmp_path)
    _c, unknown = save(spec, base, j)
    _c, zero = save(spec, base | {"fees": "0"}, j)  # same signal, new action ID
    pos_unknown = j.get(unknown.position_id)
    assert pos_unknown.fees_text == "UNKNOWN" and pos_unknown.fees_unknown_count == 1
    assert not zero.saved and zero.code == "SIGNAL_ALREADY_ENTERED"  # first claim holds
    store.close()


# --------------------------------------------------------------------------- GUI-32


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("late", "AFTER_SIGNAL_EXPIRY"),
        ("outside", "OUTSIDE_ENTRY_BAND"),
        ("stop", "STOP_DIFFERS_FROM_PLAN"),
        ("target", "TARGET_DIFFERS_FROM_PLAN"),
        ("early", "BEFORE_FIRST_READY"),
    ],
)
def test_gui32_off_plan_reasons_are_domain_classified_and_plan_never_mutated(
    tmp_path, change, reason
):
    _s, _sid, chk = ready()
    plan = chk.plan
    spec = entry_spec(chk)
    v = defaults(spec) | {"price": str(plan.e0), "qty": "0.1"}
    if change == "late":
        v["time"] = iso_utc(plan.expiry_ms + 1)
    elif change == "early":
        v["time"] = iso_utc(plan.first_ready_ms - 1)
    elif change == "outside":
        v["price"] = str(plan.entry_high + 1)
    elif change == "stop":
        v["stop"] = str(plan.sl0 + (1 if plan.side is Side.SELL else -1))
    else:
        v["target"] = str(plan.tp2 + (-1 if plan.side is Side.SELL else 1))
    lines, _ = spec.render_preview(v)
    assert any(reason in t and "Plan status: OFF_PLAN" in t for t, _ in lines)
    store, j = open_journal(tmp_path)
    _c, res = save(spec, v, j)
    pos = j.get(res.position_id)
    assert pos.plan_status.value == "OFF_PLAN" and reason in pos.off_plan_reasons
    assert pos.plan == plan  # the frozen original plan is stored unchanged
    store.close()


def test_gui32_blocked_ready_is_recorded_off_plan_never_on_plan(tmp_path):
    _s, _sid, chk = ready()
    blocked = dataclasses.replace(chk, blocked=True)
    spec = entry_spec(blocked)
    assert any("EXECUTION BLOCKED" in t for t, _ in spec.warnings)
    v = defaults(spec) | {"price": str(chk.plan.e0), "qty": "0.1"}
    store, j = open_journal(tmp_path)
    _c, res = save(spec, v, j, fresh=blocked)
    pos = j.get(res.position_id)
    assert pos.plan_status.value == "OFF_PLAN"
    assert "EXECUTION_BLOCKED_AT_RECORD" in pos.off_plan_reasons
    store.close()


# --------------------------------------------------------------------------- GUI-33 / 07


def test_gui33_eligibility_comparison_detects_every_change():
    s, _sid, chk = ready()
    same = dataclasses.replace(chk, token=99)
    assert chk.same_eligibility(same)
    for changed in (
        dataclasses.replace(chk, cursor=chk.cursor + 1),
        dataclasses.replace(chk, state="EXPIRED"),
        dataclasses.replace(chk, blocked=True),
        dataclasses.replace(chk, generation=GEN + 1),
        dataclasses.replace(chk, source_id="other"),
        dataclasses.replace(chk, found=False),
        dataclasses.replace(chk, plan=dataclasses.replace(chk.plan, sl0=chk.plan.sl0 + 1)),
    ):
        assert not chk.same_eligibility(changed)
    # a terminal state read from the real engine is never READY again
    while s.step():
        later = signal_check(s, token=2, source_id=SRC, generation=GEN, signal_id=chk.signal_id)
        if later.state != "READY":
            break
    assert not later.ready and not chk.same_eligibility(later)
    missing = signal_check(s, token=3, source_id=SRC, generation=GEN, signal_id="SIG-nope")
    assert not missing.found and not missing.ready and missing.reason


# --------------------------------------------------------------------------- GUI-34 / 35


def test_gui34_skip_once_stable_retry_and_entry_after_skip_rejected_on_second_connection(
    tmp_path,
):
    _s, sid, chk = ready()
    store, j = open_journal(tmp_path)
    spec = skip_spec(chk)
    cmd, res = save(spec, {"reason": "news risk"}, j)
    assert res.saved and res.created
    again = execute(j, cmd)  # same action ID, same payload: no second decision
    assert again.saved and not again.created and len(j.decisions()) == 1
    changed = execute(j, dataclasses.replace(cmd, note="other reason"))
    assert not changed.saved and changed.code == "DUPLICATE_ACTION_ID"
    store2, j2 = open_journal(tmp_path)  # a second local instance on the same database
    entry = entry_spec(chk)
    _c, res2 = save(entry, defaults(entry) | {"price": str(chk.plan.e0), "qty": "1"}, j2)
    assert not res2.saved and res2.code == "SIGNAL_ALREADY_SKIPPED"
    assert j.positions() == [] and j.signal_actions(SRC) == {sid: ("USER_SKIPPED", None)}
    store.close(), store2.close()


def test_gui34_skip_racing_entry_from_other_connection_keeps_first_claim(tmp_path):
    _s, _sid, chk = ready()
    store, j = open_journal(tmp_path)
    store2, j2 = open_journal(tmp_path)
    entry = entry_spec(chk)
    _c, first = save(entry, defaults(entry) | {"price": str(chk.plan.e0), "qty": "1"}, j2)
    assert first.saved
    _c, skip = save(skip_spec(chk), {"reason": ""}, j)
    assert not skip.saved and skip.code == "SIGNAL_ALREADY_ENTERED"
    assert j.decisions() == []
    store.close(), store2.close()


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_gui35_off_plan_external_fill_needs_ack_and_never_claims_a_signal(tmp_path, side):
    _s, sid, chk = ready()
    spec = off_plan_spec(SRC, GEN, None)
    v = defaults(spec) | {
        "side": side, "price": "4000.10", "qty": "0.2", "time": iso_utc(chk.virtual_ms),
        "signal": sid,
    }  # fmt: skip
    assert spec.parse(v).errors == {"ack": "ACK_REQUIRED: explicit acknowledgement is required"}
    v["ack"] = "yes"
    text = "\n".join(t for t, _ in spec.identity)
    assert "OFF_PLAN" in text and "Grog did not recommend or execute it" in text
    store, j = open_journal(tmp_path)
    _c, res = save(spec, v, j)
    pos = j.get(res.position_id)
    assert pos.plan is None and pos.plan_status.value == "OFF_PLAN"
    assert pos.linked_signal_id == sid and pos.signal_link == "INFORMATIONAL"
    assert pos.side.value == side and pos.fidelity == "SIMULATED" and pos.source_id == SRC
    assert j.signal_actions(SRC) == {}  # the READY signal is not claimed or resurrected
    store.close()


# --------------------------------------------------------------------------- GUI-36 / 37


def exit_values(spec, price, qty, time_ms):
    return defaults(spec) | {"price": str(price), "qty": qty, "time": iso_utc(time_ms)}


def test_gui36_partial_rules_and_stale_quantity_are_enforced_transactionally(tmp_path):
    _s, chk, store, j, pos = entered(tmp_path, qty="1")
    t = chk.virtual_ms
    spec = exit_spec(pos, None, close=False, source_id=SRC, generation=GEN)
    for qty, code in (("1", "PARTIAL_IS_FULL"), ("1.5", "QTY_EXCEEDS_REMAINING")):
        lines, _ = spec.render_preview(exit_values(spec, pos.entry_price, qty, t))
        assert any(tone == "error" for _t, tone in lines)
        _c, res = save(spec, exit_values(spec, pos.entry_price, qty, t), j)
        assert not res.saved and res.code == code
    _c, early = save(spec, exit_values(spec, pos.entry_price, "0.1", t - 1), j)
    assert not early.saved and early.code == "TIME_BEFORE_ENTRY"
    _c, ok = save(spec, exit_values(spec, pos.entry_price, "0.4", t + 5), j)
    assert ok.saved and j.get(pos.position_id).remaining_qty == Decimal("0.6")
    # a form built before that partial is stale: it says so and writes nothing
    _c, stale = save(spec, exit_values(spec, pos.entry_price, "0.5", t + 6), j)
    assert not stale.saved and stale.code == "POSITION_CHANGED"
    fresh = exit_spec(j.get(pos.position_id), None, close=False, source_id=SRC, generation=GEN)
    _c, second = save(fresh, exit_values(fresh, pos.entry_price, "0.5", t + 6), j)
    assert second.saved and j.get(pos.position_id).remaining_qty == Decimal("0.1")
    assert [e.action.value for e in j.events(pos.position_id)] == [
        "ENTRY", "PARTIAL_CLOSE", "PARTIAL_CLOSE",
    ]  # fmt: skip
    store.close()


def test_gui37_close_needs_current_remaining_after_other_process_partial(tmp_path):
    _s, chk, store, j, pos = entered(tmp_path, qty="1")
    t = chk.virtual_ms
    spec = exit_spec(pos, None, close=True, source_id=SRC, generation=GEN)
    assert defaults(spec)["qty"] == "1"  # close starts with the current remaining
    store2, j2 = open_journal(tmp_path)
    j2.record_partial(new_action_id(), pos.position_id, price=pos.entry_price,
                      qty=Decimal("0.3"), fill_ms=t + 1)  # fmt: skip
    cmd, res = save(spec, exit_values(spec, pos.entry_price, "1", t + 2), j)
    assert not res.saved and res.code in ("POSITION_CHANGED", "CLOSE_QTY_MISMATCH")
    # even without the early hint the service itself refuses the stale quantity
    raw = execute(j, dataclasses.replace(cmd, expected_events=None, action_id=new_action_id()))
    assert not raw.saved and raw.code == "QTY_EXCEEDS_REMAINING"
    less = execute(
        j,
        dataclasses.replace(
            raw_cmd := cmd, expected_events=None, action_id=new_action_id(), qty=Decimal("0.5")
        ),
    )
    assert raw_cmd.kind is CommandKind.CLOSE
    assert not less.saved and less.code == "CLOSE_QTY_MISMATCH"  # a close is all remaining
    fresh = exit_spec(j.get(pos.position_id), None, close=True, source_id=SRC, generation=GEN)
    _c, ok = save(fresh, exit_values(fresh, pos.entry_price, "0.7", t + 2), j)
    final = j.get(pos.position_id)
    assert ok.saved and final.state is PositionState.CLOSED and final.remaining_qty == 0
    _c, twice = save(fresh, exit_values(fresh, pos.entry_price, "0.7", t + 3), j)
    assert not twice.saved and twice.code in ("POSITION_CHANGED", "POSITION_CLOSED")
    store.close(), store2.close()


# --------------------------------------------------------------------------- GUI-38 / 41


def test_gui38_modify_preview_uses_domain_risk_warns_farther_and_keeps_initial_risk(tmp_path):
    _s, chk, store, j, pos = entered(tmp_path)
    spec = modify_spec(pos, None, source_id=SRC, generation=GEN)
    t = iso_utc(chk.virtual_ms)
    lines, errors = spec.render_preview(defaults(spec) | {"time": t})
    text = "\n".join(t for t, _tone in lines)  # blank = unchanged, needs one level
    assert "_rejected" in errors and "REJECTED MISSING_VALUE" in text
    away = pos.current_sl + (1 if pos.side is Side.SELL else -1)
    lines, _ = spec.render_preview(defaults(spec) | {"time": t, "stop": str(away)})
    text = "\n".join(x for x, _ in lines)
    assert "FURTHER AWAY" in text
    assert f"{current_risk(pos, pos.current_sl)} -> {current_risk(pos, away)}" in text
    _c, bad = save(spec, defaults(spec) | {"time": iso_utc(pos.entry_ms - 1), "stop": str(away)},
                   j)  # fmt: skip
    assert not bad.saved and bad.code == "TIME_BEFORE_ENTRY"
    _c, ok = save(spec, defaults(spec) | {"time": t, "stop": str(away)}, j)
    after = j.get(pos.position_id)
    assert ok.saved and after.current_sl == away and after.initial_risk == pos.initial_risk
    assert [e.action.value for e in j.events(pos.position_id)].count("MODIFY") == 1
    store.close()


def test_gui41_r_denominator_is_the_same_original_full_risk_after_partial(tmp_path):
    s, chk, store, j, pos = entered(tmp_path, qty="1")
    tracker = TouchTracker()
    snap = s.snapshot()
    before = mark_facts(snap, [pos], tracker)[0]
    j.record_partial(new_action_id(), pos.position_id, price=pos.entry_price, qty=Decimal("0.5"),
                     fill_ms=chk.virtual_ms)  # fmt: skip
    after_pos = j.get(pos.position_id)
    after = mark_facts(snap, [after_pos], tracker)[0]
    assert before.original_risk_units == after.original_risk_units == pos.initial_risk * 1
    assert after.events == 2 and before.events == 1  # the version guard of the GUI
    rb = r_breakdown(after_pos, None)
    assert after.realized_r == rb.realized_r
    detail = "\n".join(position_detail(snap_of(j), after_pos, (after,))[2])
    assert "Net R: UNKNOWN" in detail and "P&L UNKNOWN" in detail
    store.close()


# --------------------------------------------------------------------------- GUI-39 / 40


def test_gui39_touches_are_observations_and_never_change_the_record(tmp_path):
    s, chk, store, j, pos = entered(tmp_path)
    tracker = TouchTracker()
    tracker.track([pos])
    s.quote_observers.append(tracker.on_quote)
    events_before = j.events(pos.position_id)
    for _ in range(20_000):
        if tracker.touched(pos) or not s.step():
            break
    facts = mark_facts(s.snapshot(), [pos], tracker)[0]
    assert facts.touched, "the synthetic replay reaches a stop or target"
    assert any("TOUCHED" in o for o in facts.observations)
    assert j.events(pos.position_id) == events_before  # no automatic partial/close
    assert j.get(pos.position_id).remaining_qty == pos.remaining_qty
    store.close()


def test_gui40_mark_side_source_and_prefill_unavailability(tmp_path):
    s, chk, store, j, pos = entered(tmp_path)
    snap = s.snapshot()
    m = mark_facts(snap, [pos], TouchTracker())[0]
    q = snap.quote
    assert m.closeable_side == ("BID" if pos.side is Side.BUY else "ASK")
    assert m.closeable == (q.bid if pos.side is Side.BUY else q.ask)
    other = dataclasses.replace(pos, source_id="elsewhere")
    assert mark_facts(snap, [other], TouchTracker())[0].closeable is None
    future = dataclasses.replace(pos, entry_ms=q.received_time_ms + 1)
    fm = mark_facts(snap, [future], TouchTracker())[0]
    assert fm.closeable is None and "before the recorded fill" in fm.reason
    store.close()


# --------------------------------------------------------------------------- GUI-43


def test_gui43_confirm_open_once_with_concurrent_duplicate(tmp_path):
    _s, chk, store, j, pos = entered(tmp_path)
    j.restore_on_startup()
    rr = j.get(pos.position_id)
    assert rr.state is PositionState.RECONCILIATION_REQUIRED
    spec = confirm_open_spec(rr, None, source_id=SRC, generation=GEN)
    v = defaults(spec) | {"time": iso_utc(chk.virtual_ms + 10)}
    assert spec.parse(v).errors.keys() == {"ack"}  # explicit broker verification required
    store2, j2 = open_journal(tmp_path)
    spec2 = confirm_open_spec(rr, None, source_id=SRC, generation=GEN)
    _c, first = save(spec, v | {"ack": "yes"}, j)
    _c, second = save(spec2, v | {"ack": "yes"}, j2)
    assert first.saved and not second.saved and second.code in ("POSITION_CHANGED",
                                                                 "NOT_REQUIRED")  # fmt: skip
    acts = [e.action.value for e in j.events(pos.position_id)]
    assert acts.count("CONFIRMED_OPEN") == 1 and j.get(pos.position_id).state.value == "MONITORING"
    store.close(), store2.close()


# --------------------------------------------------------------------------- GUI-45


def test_gui45_retry_same_payload_injected_failure_and_changed_payload(tmp_path):
    _s, chk, store, j, pos = entered(tmp_path, qty="1")
    spec = exit_spec(pos, None, close=False, source_id=SRC, generation=GEN)
    v = exit_values(spec, pos.entry_price, "0.25", chk.virtual_ms + 1)
    parsed = spec.parse(v).values
    cmd = spec.build(1, new_action_id(), parsed, None)
    j._inject_failure = "after_event"  # SQLite fault after the event insert: rolled back
    failed = execute(j, cmd)
    assert not failed.saved and failed.code == "NOT_SAVED"
    assert len(j.events(pos.position_id)) == 1
    j._inject_failure = None
    ok = execute(j, cmd)  # retry: same action ID and payload
    assert ok.saved and ok.created
    dup = execute(j, cmd)
    assert dup.saved and not dup.created and len(j.events(pos.position_id)) == 2
    changed = execute(j, dataclasses.replace(cmd, qty=Decimal("0.3")))
    assert not changed.saved and changed.code == "DUPLICATE_ACTION_ID"
    assert len(j.events(pos.position_id)) == 2
    store.close()


def test_gui45_unexpected_fault_after_commit_is_outcome_unknown_and_retry_is_safe(tmp_path):
    _s, sid, chk = ready()
    store, j = open_journal(tmp_path)
    real = j.record_skip

    def commit_then_fail(*a, **kw):
        real(*a, **kw)
        raise sqlite3.OperationalError("disk I/O error after commit")

    j.record_skip = commit_then_fail  # type: ignore[method-assign]
    spec = skip_spec(chk)
    cmd = spec.build(1, new_action_id(), spec.parse({"reason": ""}).values, None)
    res = execute(j, cmd)
    assert not res.saved and res.code == OUTCOME_UNKNOWN and "may or may not" in res.message
    j.record_skip = real  # type: ignore[method-assign]
    retry = execute(j, cmd)
    assert retry.saved and not retry.created and len(j.decisions()) == 1
    store.close()


# --------------------------------------------------------------------------- GUI-48 / 49


def test_gui48_49_journal_rows_provenance_stable_order_and_filters(tmp_path):
    s, chk, store, j, pos = entered(tmp_path)
    same_ms = pos.entry_ms
    for note in ("a", "b"):  # two operator events at the SAME millisecond
        j.record_modify(new_action_id(), pos.position_id, effective_ms=same_ms,
                        new_target=pos.current_tp, note=note)  # fmt: skip
    j.record_entry(
        EntryRequest(action_id=new_action_id(), side=Side.BUY, price=Decimal("1"),
                     qty=Decimal("1"), fill_ms=same_ms, source_id=SRC)
    )  # fmt: skip
    snap = snap_of(j)
    ops = operator_entries(snap)
    terminal_rows = [r for _t, r in manual_journal_rows(j)]
    assert [e.key for e in ops] == [r.key for r in terminal_rows]  # same records/wording
    assert [e.cells[2:] for e in ops] == [r.cells[1:] for r in terminal_rows]
    keys = [e.key for e in ops]
    assert len(set(keys)) == len(keys) == 4
    for e in ops:
        assert e.recorded_ms is not None  # durable recording time, separate from event UTC
        assert OPERATOR_PROVENANCE in e.detail and any(d.startswith("RECORDED UTC") for d in
                                                       e.detail)  # fmt: skip
    frame = build_overview_frame(s, tag=FrameTag(SRC, 1, 1), overlay=snap.overlay(),
                                 positions=snap.open_positions(), tracker=TouchTracker(),
                                 journal_note="n")  # fmt: skip
    eng = engine_entries(frame.engine_rows)
    assert len(eng) == len(s.pipeline.signals.events)
    assert all(ENGINE_PROVENANCE in e.detail and e.recorded_ms is None for e in eng)
    both = filter_entries(ops + eng)
    assert len(both) == len(ops) + len(eng)  # nothing dropped
    assert [e.order for e in both] == sorted((e.order for e in both), reverse=True)
    again = filter_entries(tuple(reversed(ops + eng)))
    assert [e.key for e in again] == [e.key for e in both]  # total order, input-independent
    assert {e.producer for e in filter_entries(both, stream=STREAM_OPERATOR)} == {"OPERATOR"}
    assert {e.producer for e in filter_entries(both, stream=STREAM_ENGINE)} == {"SIM ENGINE"}
    assert [e.key for e in filter_entries(both, text=chk.signal_id, stream=STREAM_OPERATOR)]
    modifies = filter_entries(both, action="MODIFY")
    assert len(modifies) == 2 and modifies[0].time_ms == modifies[1].time_ms
    assert filter_entries(both, from_ms=same_ms + 10**9) == []
    assert {e.side for e in filter_entries(both, side="BUY")} == {"BUY"}
    rows = position_rows(snap, frame.marks, "All")
    assert len(rows) == 2 and len({r.key for r in rows}) == 2
    store.close()


def test_commands_and_snapshots_are_detached_values(tmp_path):
    _s, chk, store, j, pos = entered(tmp_path)
    snap = snap_of(j)
    assert_detached(snap)
    payload = snap.events[0].payload()
    payload["price"] = "0"  # a caller mutating its copy never changes the snapshot
    assert snap.events[0].payload()["price"] != "0"
    cmd = Command(CommandKind.CONFIRM_OPEN, 1, GEN, SRC, "x", position_id=pos.position_id,
                  time_ms=1)  # fmt: skip
    assert_detached(cmd)
    store.close()


# --------------------------------------------------------------------------- audit fixes


def test_confirm_open_chronology_is_rejected_by_rules_build_and_journal_owner(tmp_path):
    """Audit defect 1: a verification dated before the fill was saved because only the
    preview rejected it. Now the structured rule, the command build and the journal
    owner (execute) each refuse it; nothing is written."""
    _s, chk, store, j, pos = entered(tmp_path)
    j.restore_on_startup()
    rr = j.get(pos.position_id)
    spec = confirm_open_spec(rr, None, source_id=SRC, generation=GEN)
    early = defaults(spec) | {"time": iso_utc(rr.entry_ms - 1), "ack": "yes"}
    parsed = spec.parse(early)
    assert not parsed.errors
    assert [c for c, _m in spec.rejections(parsed.values)] == ["TIME_BEFORE_ENTRY"]
    lines, errors = spec.render_preview(early)
    assert "_rejected" in errors and any("REJECTED TIME_BEFORE_ENTRY" in t for t, _ in lines)
    with pytest.raises(JournalError) as exc:
        spec.build(1, new_action_id(), parsed.values, None)
    assert exc.value.code == "TIME_BEFORE_ENTRY"
    # a command that skipped every form check is still refused on the journal owner
    ok_values = spec.parse(early | {"time": iso_utc(rr.entry_ms)}).values
    good = spec.build(1, new_action_id(), ok_values, None)
    forged = dataclasses.replace(good, action_id=new_action_id(), time_ms=rr.entry_ms - 1)
    res = execute(j, forged)
    assert not res.saved and res.code == "TIME_BEFORE_ENTRY"
    assert len(j.events(rr.position_id)) == rr.events
    assert j.get(rr.position_id).state is PositionState.RECONCILIATION_REQUIRED
    saved = execute(j, good)  # the same instant as the fill is allowed
    assert saved.saved and j.get(rr.position_id).state is PositionState.MONITORING
    again = execute(j, good)  # exact retry: the service's idempotency answers
    assert again.saved and not again.created
    store.close()


def test_service_confirm_open_alone_does_not_check_time_hence_the_owner_check(tmp_path):
    """Control documenting the gap the desktop closes (the R0 service is unchanged)."""
    _s, _chk, store, j, pos = entered(tmp_path)
    j.restore_on_startup()
    saved, created = j.confirm_open(new_action_id(), pos.position_id, effective_ms=0)
    assert created and saved.state is PositionState.MONITORING
    store.close()


def _racing_partial(j, j2, pos):
    real = j.events

    def racing(*a, **kw):
        if not getattr(racing, "done", False):
            racing.done = True
            j2.record_partial(
                new_action_id(), pos.position_id, price=pos.entry_price,
                qty=Decimal("0.03"), fill_ms=pos.entry_ms + 10, fees=None, note=None,
            )  # fmt: skip
        return real(*a, **kw)

    j.events = racing  # type: ignore[method-assign]
    return real


def test_snapshot_is_one_consistent_read_and_later_reads_see_the_racing_write(tmp_path):
    """Audit defect 3: another instance committing between the snapshot's reads mixed
    two moments (position with 1 event next to 2 event rows)."""
    _s, _chk, store, j, pos = entered(tmp_path)
    store2, j2 = open_journal(tmp_path)
    real = _racing_partial(j, j2, pos)
    snap = snap_of(j)
    p = snap.position(pos.position_id)
    rows = [e for e in snap.events if e.position_id == pos.position_id]
    assert p.events == len(rows) == 1 and p.remaining_qty == Decimal("0.10")
    assert not j._conn.in_transaction  # only our own read transaction, and it ended
    j.events = real  # type: ignore[method-assign]
    later = snap_of(j, 2)  # nothing was lost: the next snapshot shows the partial
    p2 = later.position(pos.position_id)
    rows2 = [e for e in later.events if e.position_id == pos.position_id]
    assert p2.events == len(rows2) == 2 and p2.remaining_qty == Decimal("0.07")
    store.close(), store2.close()


def test_snapshot_joins_a_callers_transaction_and_never_ends_it(tmp_path):
    _s, _chk, store, j, _pos = entered(tmp_path)
    store._conn.execute("CREATE TABLE audit_probe (x INTEGER)")
    with store.transaction() as conn:
        conn.execute("INSERT INTO audit_probe VALUES (1)")
        snap_of(j)
        assert conn.in_transaction  # not rolled back or committed by the snapshot
        conn.execute("INSERT INTO audit_probe VALUES (2)")
    assert [r[0] for r in store._conn.execute("SELECT x FROM audit_probe")] == [1, 2]
    store.close()


def test_snapshot_on_read_only_wal_connection_sees_new_commits(tmp_path):
    from grog.domain.clock import SystemClock
    from grog.journal.store import STATE_DB_FILENAME, Store

    _s, _chk, store, j, pos = entered(tmp_path)  # writer stays open: WAL has content
    ro = Store.open_read_only(tmp_path / "state" / STATE_DB_FILENAME, SystemClock())
    rj = PositionJournal(ro)
    first = read_snapshot(
        rj, generation=GEN, sequence=1, source_id=SRC, mode=JournalMode.READ_ONLY, reason="t"
    )
    assert first.position(pos.position_id).events == 1 and not ro._conn.in_transaction
    j.record_partial(
        new_action_id(), pos.position_id, price=pos.entry_price, qty=Decimal("0.04"),
        fill_ms=pos.entry_ms + 1, fees=None, note=None,
    )  # fmt: skip
    second = read_snapshot(
        rj, generation=GEN, sequence=2, source_id=SRC, mode=JournalMode.READ_ONLY, reason="t"
    )
    assert second.position(pos.position_id).events == 2  # no stale read transaction kept
    ro.close(), store.close()
