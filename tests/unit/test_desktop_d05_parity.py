"""GUI-62: the Textual R0 forms and the desktop forms record the SAME local journal
projection for the same operator facts (entry, partial, modify, close; skip), apart from
the expected action IDs / record times. Both go through the one PositionJournal service;
exact Decimals and UTC milliseconds must match byte for byte."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from grog.desktop.frames import ClockFacts, signal_check
from grog.desktop.journal_model import execute
from grog.desktop.manual_forms import entry_spec, exit_spec, modify_spec, skip_spec
from grog.domain.enums import SignalEventKind
from grog.journal.positions import _content_hash, new_action_id
from grog.replay.session import Playback
from grog.ui import manual
from grog.ui.format import iso_utc
from ui_support import open_journal, session, step_until


def _desktop(spec, journal, values, token, action_id, check=None):
    parsed = spec.parse({f.key: values.get(f.key, "") for f in spec.fields})
    assert not parsed.errors, parsed.errors
    res = execute(journal, spec.build(token, action_id, parsed.values, check))
    assert res.saved, res
    return res


def _tui(form, values, action_id):
    return form.submit_fn(action_id, {f.key: values.get(f.key, "") for f in form.fields})


def _events(journal):
    """Event projection; ``content_sha256`` is verified to be the service's own hash of
    the identical payload (it embeds the action-derived position ID) and then omitted."""
    out = []
    for e in journal.events():
        payload = {k: v for k, v in e.payload.items() if "action" not in k}
        body = {k: v for k, v in payload.items() if k != "content_sha256"}
        kind = {
            "ENTRY": "ENTRY",
            "MODIFY": "MODIFY" + e.position_id,
        }.get(e.action.value, e.action.value + e.position_id)
        if e.action.value != "ENTRY":
            hashed = {k: v for k, v in body.items() if k != "further_away"}  # added after
            assert payload["content_sha256"] == _content_hash(kind, hashed), e
        payload = body if e.action.value != "ENTRY" else payload
        out.append((e.sequence, e.action, e.effective_at_ms, e.qty, e.price, e.fees, payload))
    return out


def _positions(journal):
    keep = []
    for p in journal.positions():
        d = {k: getattr(p, k) for k in p.__dataclass_fields__}
        for k in list(d):
            if k.endswith(("_id", "_at_ms")) and k not in ("signal_id", "source_id"):
                d.pop(k)  # IDs derived from action IDs; record (wall) times
        keep.append(d)
    return keep


def test_gui62_textual_and_desktop_forms_write_identical_journal_projections(tmp_path):
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    snap = s.snapshot()
    view = next(v for v in snap.signals if v.record.signal_id == sid)
    rec = view.record
    t = iso_utc(snap.clock.virtual_ms if hasattr(snap, "clock") else manual.known_clock(snap))
    sa, ja = open_journal(tmp_path / "textual")
    sb, jb = open_journal(tmp_path / "desktop")
    try:
        entry = {"price": str(rec.e0 + Decimal("0.07")), "qty": "0.10", "time": t,
                 "stop": "", "target": "", "fees": "", "broker": "B", "note": "parity"}  # fmt: skip
        _tui(manual.entry_form(ja, snap, view), entry, new_action_id())
        chk = signal_check(s, token=1, source_id="syn", generation=1, signal_id=sid)
        _desktop(entry_spec(chk), jb, entry, 1, new_action_id(), chk)

        clock = ClockFacts(manual.known_clock(snap), Playback.PAUSED, s.cursor, None, "v")
        (pa,), (pb,) = ja.positions(), jb.positions()
        part = {"price": str(rec.tp1), "qty": "0.04", "time": t, "fees": "0", "note": "half"}
        _tui(manual.partial_form(ja, snap, pa), part, new_action_id())
        spec = exit_spec(pb, clock, close=False, source_id="syn", generation=1)
        _desktop(spec, jb, part, 2, new_action_id())

        (pa,), (pb,) = ja.positions(), jb.positions()
        mod = {"stop": str(rec.e0), "target": "", "time": t, "note": "be"}
        _tui(manual.modify_form(ja, snap, pa), mod, new_action_id())
        _desktop(modify_spec(pb, clock, source_id="syn", generation=1), jb, mod, 3, new_action_id())

        (pa,), (pb,) = ja.positions(), jb.positions()
        close = {"price": str(rec.tp2), "qty": str(pa.remaining_qty), "time": t, "fees": "",
                 "note": "done"}  # fmt: skip
        _tui(manual.close_form(ja, snap, pa), close, new_action_id())
        spec = exit_spec(pb, clock, close=True, source_id="syn", generation=1)
        _desktop(spec, jb, close, 4, new_action_id())

        assert _events(ja) == _events(jb) and len(_events(ja)) == 4
        assert _positions(ja) == _positions(jb)
        (pa,) = ja.positions()
        assert pa.remaining_qty == Decimal("0") and pa.entry_price == rec.e0 + Decimal("0.07")
        prices = [e.price for e in ja.events() if e.action.value != "MODIFY"]
        assert [type(p) for p in prices] == [Decimal] * 3  # exact Decimals, no floats

        sid2 = step_until(s, SignalEventKind.READY_ISSUED)
        snap2 = s.snapshot()
        view2 = next(v for v in snap2.signals if v.record.signal_id == sid2)
        _tui(manual.skip_form(ja, snap2, view2), {"reason": "spread"}, new_action_id())
        chk2 = signal_check(s, token=5, source_id="syn", generation=1, signal_id=sid2)
        _desktop(skip_spec(chk2), jb, {"reason": "spread"}, 5, new_action_id(), chk2)

        def decisions(j):
            return [replace(d, decision_id="", recorded_at_ms=0, action_id="")
                    if hasattr(d, "action_id") else replace(d, decision_id="", recorded_at_ms=0)
                    for d in j.decisions()]  # fmt: skip

        assert decisions(ja) == decisions(jb) and len(decisions(ja)) == 1

        def claims(j):  # position IDs derive from action IDs: compare the claim kinds
            return {k: (v[0], v[1] is not None) for k, v in j.signal_actions("syn").items()}

        assert claims(ja) == claims(jb) == {sid: ("ENTERED", True), sid2: ("USER_SKIPPED", False)}
    finally:
        sa.close()
        sb.close()


def _plain_events(journal):
    """All events minus action/record-derived identity (IDs, record time, content hash)."""
    out = []
    for e in journal.events():
        payload = {
            k: v for k, v in e.payload.items() if "action" not in k and k != "content_sha256"
        }
        out.append((e.sequence, e.action, e.effective_at_ms, e.qty, e.price, e.fees, payload))
    return out


def _real_clock(s):
    from grog.desktop.frames import FrameTag, build_overview_frame
    from grog.journal.positions import TouchTracker

    tag = FrameTag("syn", 1, 1)
    frame = build_overview_frame(
        s, tag=tag, overlay={}, positions=[], tracker=TouchTracker(), journal_note=""
    )
    return frame.clock


def test_gui62_unlinked_idempotent_retry_restart_and_confirm_open_match(tmp_path):
    """Remaining journal services through both frontends: OFF_PLAN unlinked entry, an
    identical retry with the SAME action ID (no second record), program restart
    (RESTORED_UNVERIFIED once) and the broker-verified confirm-open."""
    from grog.desktop.manual_forms import confirm_open_spec, off_plan_spec
    from grog.journal.positions import PositionState

    s = session()
    step_until(s, SignalEventKind.READY_ISSUED)
    snap = s.snapshot()
    t = iso_utc(manual.known_clock(snap))
    clock = _real_clock(s)  # exactly what the replay owner hands the desktop forms
    values = {"side": "SELL", "price": "4119.9600", "qty": "0.10", "time": t, "stop": "4125.5",
              "target": "", "fees": "", "signal": "", "broker": "B", "note": "off"}  # fmt: skip
    roots = {"textual": tmp_path / "textual", "desktop": tmp_path / "desktop"}
    a_id, b_id = new_action_id(), new_action_id()
    sa, ja = open_journal(roots["textual"])
    sb, jb = open_journal(roots["desktop"])
    try:
        form = manual.unlinked_form(ja, snap)
        _tui(form, values, a_id)
        _tui(form, values, a_id)  # duplicate submit (retry) with the same action ID
        spec = off_plan_spec("syn", 1, clock)
        acked = {**values, "ack": "yes"}  # the desktop form adds an explicit OFF_PLAN ack
        first = _desktop(spec, jb, acked, 1, b_id)
        again = _desktop(spec, jb, acked, 2, b_id)
        assert first.created and not again.created and "already saved" in again.message
        assert len(ja.events()) == len(jb.events()) == 1
        assert _plain_events(ja) == _plain_events(jb)
        (pa,), (pb,) = ja.positions(), jb.positions()
        assert pa.entry_price == Decimal("4119.9600") and str(pa.entry_price) == "4119.9600"
        assert str(pb.entry_price) == "4119.9600" and pa.plan_status == pb.plan_status
    finally:
        sa.close()
        sb.close()

    # restart: both journals reopened, restore runs once; a second restore adds nothing
    sa, ja = open_journal(roots["textual"])
    sb, jb = open_journal(roots["desktop"])
    try:
        for j in (ja, jb):
            (p,) = j.restore_on_startup()
            assert p.state is PositionState.RECONCILIATION_REQUIRED
            count = len(j.events())
            j.restore_on_startup()  # an already-unverified position gets no second event
            assert len(j.events()) == count == 2
        (pa,), (pb,) = ja.positions(), jb.positions()
        eff = manual.parse_time(t)
        ja.confirm_open(new_action_id(), pa.position_id, effective_ms=eff)  # Textual path
        spec = confirm_open_spec(pb, clock, source_id="syn", generation=1)
        _desktop(spec, jb, {"time": t, "note": "", "ack": "yes"}, 3, new_action_id())
        assert _plain_events(ja) == _plain_events(jb) and len(ja.events()) == 3
        assert [p.state for p in ja.positions()] == [p.state for p in jb.positions()]
        assert ja.positions()[0].state is PositionState.MONITORING
        assert _positions(ja) == _positions(jb)
    finally:
        sa.close()
        sb.close()
