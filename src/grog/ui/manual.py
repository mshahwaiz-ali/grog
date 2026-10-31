"""Manual-journal UI glue (docs/02 §6, §7, §9): builds forms, previews and read models
from the validated :class:`PositionJournal` service and the current replay snapshot.

Nothing here writes to SQLite directly or contains any broker/order code path: every
mutation goes through a ``PositionJournal`` method (docs/10 M08).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from grog.domain.enums import Side, SignalState
from grog.journal.positions import (
    EntryRequest,
    JournalError,
    ManualPosition,
    PlanRef,
    PositionAction,
    PositionEventRecord,
    PositionJournal,
    PositionState,
    TouchTracker,
    current_risk,
    entry_preview,
    exit_preview,
    mark_position,
    observations,
    parse_amount,
    stop_further_away,
)
from grog.replay.session import Playback, SignalView, Snapshot
from grog.settings import ConfigError, parse_utc_timestamp_ms
from grog.ui.format import DASH, UNKNOWN, hms, iso_utc, price, r_long, r_short, short_id, utc
from grog.ui.forms import Field, JournalForm, Values
from grog.ui.panels import JournalRow, Line, band_text, entry_labels

NO_ORDER = "Local journal record only — Grog sends no order and changes no broker position."
EXTERNAL = "This records your external trade; Grog did not recommend or execute it."
PNL_UNKNOWN = "P&L UNKNOWN (contract/lot value unverified)"


def parse_time(text: str, field: str = "UTC time") -> int:
    try:
        return parse_utc_timestamp_ms(text, field)
    except ConfigError as exc:
        raise JournalError("INVALID_TIME", f"{field}: {exc}") from exc


def signed(v: Decimal | None) -> str:
    if v is None:
        return UNKNOWN
    return f"{abs(v):+f}" if v == 0 else f"{v:+f}"


def _opt_text(v: str) -> str | None:
    return v.strip() or None


def known_clock(snap: Snapshot) -> int | None:
    return snap.virtual_time_ms


def mode_label(snap: Snapshot) -> str:
    return "SIMULATED (REPLAY)"


def _fees_line(fees: Decimal | None) -> Line:
    if fees is None:
        return [("Fees: UNKNOWN (left blank — not assumed zero)", "caution")]
    return [(f"Fees: {fees} (stated by operator, kept separate from price P/L)", "muted")]


def _preview_entry_lines(prev, side: Side, plan: PlanRef | None) -> list[Line]:
    ent, ex = entry_labels(side)
    lines: list[Line] = [[("PREVIEW (before saving)", "gold")]]
    if plan is not None:
        lines.append(
            [
                (
                    f"Original E0 {ent} {price(plan.e0)} -> actual {price(prev.actual_price)} "
                    f"(adverse move {signed(prev.entry_difference)})",
                    "primary",
                )
            ]
        )
        lines.append(
            [
                (
                    f"Original risk {price(plan.original_risk)} / target "
                    f"{r_long(prev.original_target_r)} gross  ->  actual risk "
                    f"{price(prev.actual_risk) if prev.actual_risk else UNKNOWN} / target "
                    f"{r_long(prev.actual_target_r)} gross before fees",
                    "primary",
                )
            ]
        )
    else:
        lines.append(
            [
                (
                    f"Actual {ent} {price(prev.actual_price)}   SL {ex} {price(prev.stop)}   "
                    f"TP {ex} {price(prev.target)}   risk "
                    f"{price(prev.actual_risk) if prev.actual_risk else UNKNOWN}   target "
                    f"{r_long(prev.actual_target_r)} gross",
                    "primary",
                )
            ]
        )
    status = prev.plan_status.value
    why = ", ".join(prev.off_plan_reasons)
    lines.append(
        [
            (
                f"Plan status: {status}" + (f" / REVALIDATE ({why})" if why else ""),
                "caution" if why else "ok",
            )
        ]
    )
    for w in prev.warnings:
        lines.append([(f"WARNING: {w}", "caution")])
    lines.append([(PNL_UNKNOWN + "; net R UNKNOWN.", "muted")])
    return lines


# --------------------------------------------------------------------------- entry / skip


def entry_form(journal: PositionJournal, snap: Snapshot, view: SignalView) -> JournalForm:
    r = view.record
    plan = PlanRef.from_record(r)
    ready = view.status.state is SignalState.READY
    blocked = view.status.blocked
    opened = known_clock(snap)
    ent, ex = entry_labels(r.side)
    info: list[Line] = [
        [
            (f"Signal {r.signal_id}  ", "primary"),
            (r.side.value, "buy" if r.side is Side.BUY else "sell"),
            (f"  (read-only)   Trade label: {mode_label(snap)}", "primary"),
        ],
        [
            (
                f"Original plan (immutable): E0 {ent} {price(r.e0)}  band "
                f"[{band_text(r, ' - ')}]  SL {ex} {price(r.sl0)}  "
                f"TP1 {price(r.tp1)}  TP2 {ex} {price(r.tp2)}  expires {utc(r.expiry_ms)}",
                "muted",
            )
        ],
        [(NO_ORDER, "caution")],
    ]
    if blocked:
        info.append([("Signal is EXECUTION BLOCKED now: a fill is recorded OFF_PLAN.", "caution")])
    fields = [
        Field("price", f"Actual fill price ({ent}) *", placeholder="required, e.g. 4000.25"),
        Field("qty", "Filled quantity/lots *", placeholder="required, > 0"),
        Field("time", "Actual fill UTC time *", iso_utc(opened) if opened else ""),
        Field("stop", "Actual stop (if different)", placeholder=f"blank = {price(r.sl0)}"),
        Field("target", "Actual target (if different)", placeholder=f"blank = {price(r.tp2)}"),
        Field("fees", "Commission (optional)", placeholder="blank = UNKNOWN"),
        Field("broker", "Broker name (optional)"),
        Field("note", "Operator note (optional)"),
    ]

    def build(action_id: str, v: Values) -> EntryRequest:
        return EntryRequest(
            action_id=action_id,
            side=r.side,
            price=parse_amount(v["price"], "fill price"),
            qty=parse_amount(v["qty"], "quantity"),
            fill_ms=parse_time(v["time"], "fill time"),
            source_id=r.original_source_id,
            plan=plan,
            signal_ready=ready,
            signal_blocked=blocked,
            stop=parse_amount(v["stop"], "stop", required=False),
            target=parse_amount(v["target"], "target", required=False),
            fees=parse_amount(v["fees"], "commission", required=False, allow_zero=True),
            broker=_opt_text(v["broker"]),
            note=_opt_text(v["note"]),
            known_clock_ms=known_clock(snap),
            h1_bias_at_entry=snap.context.h1_bias if snap.context else None,
        )

    def preview(v: Values) -> list[Line]:
        req = build("preview", v)
        prev = entry_preview(
            r.side,
            req.price,
            req.fill_ms,
            plan,
            stop=req.stop,
            target=req.target,
            signal_ready=ready,
            signal_blocked=blocked,
            known_clock_ms=req.known_clock_ms,
        )
        return [*_preview_entry_lines(prev, r.side, plan), _fees_line(req.fees)]

    def submit(action_id: str, v: Values) -> str:
        pos, _ = journal.record_entry(build(action_id, v))
        return (
            f"Saved locally: {pos.position_id} {pos.side.value} {pos.plan_status.value}. "
            "No broker order was sent."
        )

    return JournalForm(
        "record-entry", "RECORD ENTRY — LOCAL JOURNAL", info, fields, preview, submit
    )


def skip_form(journal: PositionJournal, snap: Snapshot, view: SignalView) -> JournalForm:
    r = view.record
    plan = PlanRef.from_record(r)
    info: list[Line] = [
        [
            (f"Signal {r.signal_id}  ", "primary"),
            (r.side.value, "buy" if r.side is Side.BUY else "sell"),
            (f"   original expiry {utc(r.expiry_ms)}", "primary"),
        ],
        [("Marks USER_SKIPPED (distinct from system EXPIRED/MISSED). Status only.", "muted")],
    ]
    fields = [Field("reason", "Reason (optional)")]

    def preview(v: Values) -> list[Line]:
        return [[(f"Will record USER_SKIPPED at {utc(known_clock(snap))}.", "primary")]]

    def submit(action_id: str, v: Values) -> str:
        eff = known_clock(snap) or journal.store.now_ms()
        journal.record_skip(action_id, plan, effective_ms=eff, reason=_opt_text(v["reason"]))
        return f"Saved locally: {r.signal_id} USER_SKIPPED."

    return JournalForm(
        "record-skip", "SKIP SIGNAL — LOCAL JOURNAL", info, fields, preview, submit, "Mark skipped"
    )


def unlinked_form(journal: PositionJournal, snap: Snapshot) -> JournalForm:
    opened = known_clock(snap)
    info: list[Line] = [
        [("OFF_PLAN / UNVERIFIED manual XAUUSD position record", "caution")],
        [(EXTERNAL, "gold")],
        [(f"Trade label: {mode_label(snap)}   Source: {snap.source.source_id}", "muted")],
        [("A historical signal link is informational and never makes it READY.", "muted")],
    ]
    fields = [
        Field("side", "Side (BUY/SELL) *", placeholder="BUY or SELL"),
        Field("price", "Actual fill price *", placeholder="BUY = ASK fill, SELL = BID fill"),
        Field("qty", "Filled quantity/lots *", placeholder="required, > 0"),
        Field("time", "Actual fill UTC time *", iso_utc(opened) if opened else ""),
        Field("stop", "Stop at broker (optional)", placeholder="blank = no stop / risk UNKNOWN"),
        Field("target", "Target at broker (optional)"),
        Field("fees", "Commission (optional)", placeholder="blank = UNKNOWN"),
        Field("signal", "Historical signal ID (opt.)", placeholder="informational link only"),
        Field("broker", "Broker name (optional)"),
        Field("note", "Operator note (optional)"),
    ]

    def build(action_id: str, v: Values) -> EntryRequest:
        side_text = v["side"].strip().upper()
        if side_text not in ("BUY", "SELL"):
            raise JournalError("INVALID_SIDE", "side must be BUY or SELL")
        return EntryRequest(
            action_id=action_id,
            side=Side(side_text),
            price=parse_amount(v["price"], "fill price"),
            qty=parse_amount(v["qty"], "quantity"),
            fill_ms=parse_time(v["time"], "fill time"),
            source_id=snap.source.source_id,
            plan=None,
            informational_signal_id=_opt_text(v["signal"]),
            stop=parse_amount(v["stop"], "stop", required=False),
            target=parse_amount(v["target"], "target", required=False),
            fees=parse_amount(v["fees"], "commission", required=False, allow_zero=True),
            broker=_opt_text(v["broker"]),
            note=_opt_text(v["note"]),
            known_clock_ms=known_clock(snap),
            h1_bias_at_entry=snap.context.h1_bias if snap.context else None,
        )

    def preview(v: Values) -> list[Line]:
        req = build("preview", v)
        prev = entry_preview(
            req.side,
            req.price,
            req.fill_ms,
            None,
            stop=req.stop,
            target=req.target,
            known_clock_ms=req.known_clock_ms,
        )
        return [*_preview_entry_lines(prev, req.side, None), _fees_line(req.fees)]

    def submit(action_id: str, v: Values) -> str:
        pos, _ = journal.record_entry(build(action_id, v))
        return f"Saved locally: {pos.position_id} OFF_PLAN external trade. No broker order sent."

    return JournalForm(
        "record-unlinked", "RECORD UNLINKED MANUAL ENTRY — OFF_PLAN", info, fields, preview, submit
    )


# ------------------------------------------------------------- partial / modify / close


def _position_info(pos: ManualPosition) -> list[Line]:
    ent, ex = entry_labels(pos.side)
    return [
        [
            (f"{pos.position_id}  ", "primary"),
            (pos.side.value, "buy" if pos.side is Side.BUY else "sell"),
            (
                f"  entry {ent} {price(pos.entry_price)}  remaining {_q(pos.remaining_qty)} of "
                f"{_q(pos.initial_qty)}  SL {ex} {price(pos.current_sl)}  TP {ex} "
                f"{price(pos.current_tp)}  {pos.state.value}",
                "primary",
            ),
        ],
        [(NO_ORDER, "caution")],
    ]


def _q(v: Decimal) -> str:
    return format(v.normalize(), "f") if v else "0"


def _exit_form(
    journal: PositionJournal, snap: Snapshot, pos: ManualPosition, close: bool
) -> JournalForm:
    _, ex = entry_labels(pos.side)
    opened = known_clock(snap)
    fields = [
        Field("price", f"Actual exit price ({ex}) *", placeholder="required"),
        Field(
            "qty",
            "Quantity closed *",
            _q(pos.remaining_qty) if close else "",
            f"<= remaining {_q(pos.remaining_qty)}",
        ),
        Field("time", "Actual exit UTC time *", iso_utc(opened) if opened else ""),
        Field("fees", "Fees (optional)", placeholder="blank = UNKNOWN"),
        Field("note", "Note (optional)"),
    ]

    def parsed(v: Values):
        return (
            parse_amount(v["price"], "exit price"),
            parse_amount(v["qty"], "quantity"),
            parse_time(v["time"], "exit time"),
            parse_amount(v["fees"], "fees", required=False, allow_zero=True),
        )

    def preview(v: Values) -> list[Line]:
        px, qty, _t, fees = parsed(v)
        lines: list[Line] = [[("PREVIEW (before saving)", "gold")]]
        if qty > pos.remaining_qty:
            lines.append(
                [(f"REJECTED: quantity exceeds remaining {_q(pos.remaining_qty)}", "error")]
            )
            return lines
        remaining, units, r = exit_preview(pos, px, qty)
        lines.append(
            [
                (
                    f"Remaining after record: {_q(remaining)}   Realized gross price move x qty: "
                    f"{signed(units)}   Realized gross {r_long(r)} (of initial risk)",
                    "primary",
                )
            ]
        )
        lines.append([(f"Estimated realized {PNL_UNKNOWN}; net R UNKNOWN.", "muted")])
        lines.append(_fees_line(fees))
        return lines

    def submit(action_id: str, v: Values) -> str:
        px, qty, t, fees = parsed(v)
        fn = journal.record_close if close else journal.record_partial
        p, _ = fn(action_id, pos.position_id, price=px, qty=qty, fill_ms=t, fees=fees,
                  note=_opt_text(v["note"]))  # fmt: skip
        what = "CLOSED" if close else f"partial close, remaining {_q(p.remaining_qty)}"
        return f"Saved locally: {pos.position_id} {what}. Broker position not touched."

    title = "RECORD CLOSURE — LOCAL JOURNAL" if close else "RECORD PARTIAL CLOSE — LOCAL JOURNAL"
    form_id = "record-close" if close else "record-partial"
    return JournalForm(form_id, title, _position_info(pos), fields, preview, submit)


def partial_form(journal: PositionJournal, snap: Snapshot, pos: ManualPosition) -> JournalForm:
    return _exit_form(journal, snap, pos, close=False)


def close_form(journal: PositionJournal, snap: Snapshot, pos: ManualPosition) -> JournalForm:
    return _exit_form(journal, snap, pos, close=True)


def modify_form(journal: PositionJournal, snap: Snapshot, pos: ManualPosition) -> JournalForm:
    _, ex = entry_labels(pos.side)
    opened = known_clock(snap)
    fields = [
        Field("stop", f"New stop ({ex})", placeholder=f"blank = keep {price(pos.current_sl)}"),
        Field("target", f"New target ({ex})", placeholder=f"blank = keep {price(pos.current_tp)}"),
        Field("time", "Effective UTC time *", iso_utc(opened) if opened else ""),
        Field("note", "Note (optional)"),
    ]

    def preview(v: Values) -> list[Line]:
        sl = parse_amount(v["stop"], "stop", required=False)
        tp = parse_amount(v["target"], "target", required=False)
        before = current_risk(pos, pos.current_sl)
        after = current_risk(pos, sl if sl is not None else pos.current_sl)
        lines: list[Line] = [
            [("PREVIEW (before saving)", "gold")],
            [
                (
                    f"SL {price(pos.current_sl)} -> {price(sl) if sl else 'unchanged'}   "
                    f"TP {price(pos.current_tp)} -> {price(tp) if tp else 'unchanged'}",
                    "primary",
                )
            ],
            [
                (
                    f"Current risk per unit from actual entry: "
                    f"{price(before) if before else UNKNOWN} -> "
                    f"{price(after) if after else UNKNOWN}  (initial R snapshot "
                    f"{price(pos.initial_risk) if pos.initial_risk else UNKNOWN} never rewritten)",
                    "primary",
                )
            ],
        ]
        if stop_further_away(pos, sl):
            lines.append([("WARNING: stop is being moved FURTHER AWAY (more risk).", "error")])
        lines.append([("Records the broker-side edit locally; cannot change the broker.", "muted")])
        return lines

    def submit(action_id: str, v: Values) -> str:
        journal.record_modify(
            action_id,
            pos.position_id,
            effective_ms=parse_time(v["time"], "effective time"),
            new_stop=parse_amount(v["stop"], "stop", required=False),
            new_target=parse_amount(v["target"], "target", required=False),
            note=_opt_text(v["note"]),
        )
        return f"Saved locally: {pos.position_id} modification. Broker position not touched."

    return JournalForm(
        "record-modify", "RECORD MODIFICATION — LOCAL JOURNAL", _position_info(pos), fields,
        preview, submit,
    )  # fmt: skip


# --------------------------------------------------------------------------- positions view

POSITION_COLUMNS = (
    "POSITION",
    "SIGNAL",
    "SIDE",
    "QTY",
    "ENTRY",
    "MARK",
    "SL",
    "TP",
    "P&L",
    "R",
    "UPD",
    "STATE",
)
POSITION_COLUMNS_COMPACT = ("POSITION", "SIDE", "QTY", "ENTRY", "R", "STATE")


def state_text(pos: ManualPosition) -> str:
    return pos.state.value.replace("_", " ")


def _clock(snap: Snapshot, p: ManualPosition) -> int | None:
    """Virtual time of the latest quote from the position's own source, if any."""
    q = snap.quote
    return q.received_time_ms if q is not None and q.source_id == p.source_id else None


def _stale(snap: Snapshot) -> bool:
    return snap.health is not None and snap.health.status.value == "STALE"


def position_rows(
    positions: Sequence[ManualPosition],
    snap: Snapshot,
    tracker: TouchTracker,
    compact: bool = False,
) -> list[tuple[str, tuple[str, ...]]]:
    rows = []
    for p in positions:
        m = mark_position(p, snap.quote, stale=_stale(snap))
        touched = tracker.touched(p)
        sl = price(p.current_sl) + ("*" if p.current_sl != p.initial_sl else "")
        tp = "TOUCHED" if "TARGET" in touched else price(p.current_tp)
        sig = DASH if not p.linked_signal_id else p.linked_signal_id[-6:]
        if p.plan_status.value == "OFF_PLAN":
            sig = f"{sig} OFF" if p.linked_signal_id else "OFF_PLAN"
        r = r_short(m.unrealized_r) if m.closeable is not None else DASH
        cells = (
            p.position_id,
            sig,
            p.side.value,
            _q(p.remaining_qty),
            price(p.entry_price),
            price(m.closeable),
            sl,
            tp,
            UNKNOWN,
            r,
            hms(p.last_event_ms)[:5],
            state_text(p),
        )
        if compact:
            cells = (cells[0], cells[2], cells[3], cells[4], cells[9], cells[11])
        rows.append((p.position_id, cells))
    return rows


def positions_strip(
    positions: Sequence[ManualPosition], snap: Snapshot, tracker: TouchTracker
) -> list[Line]:
    lines: list[Line] = []
    if not positions:
        lines.append([("No manually confirmed positions. Nothing is assumed executed.", "muted")])
        lines.append([("Advisory events: none (no recorded positions).", "muted")])
        return lines
    rr = [p for p in positions if p.state is PositionState.RECONCILIATION_REQUIRED]
    if rr:
        lines.append(
            [
                (
                    f"RECONCILIATION REQUIRED: {len(rr)} position(s) restored after restart — "
                    "verify at broker (Enter: details/confirm, or record p/m/x).",
                    "error",
                )
            ]
        )
    feed = snap.health.status.value if snap.health else None
    bias = snap.context.h1_bias.value if snap.context else None
    ended = snap.playback is Playback.ENDED
    for p in positions:
        obs = observations(
            p,
            tracker.touched(p),
            feed_status=feed,
            h1_bias_now=bias,
            replay_ended=ended,
            clock_ms=_clock(snap, p),
        )
        lines.append(
            [
                (f"{p.position_id}: ", "primary"),
                (" | ".join(obs) or "no advisory events", "caution"),
            ]
        )
    lines.append(
        [
            (
                "MARK = closeable BID (BUY) / ASK (SELL) from SIMULATED replay quotes. "
                + PNL_UNKNOWN
                + "; R is gross price R vs initial risk. No hold/exit advice.",
                "muted",
            )
        ]
    )
    return lines


def live_positions_panel(positions: Sequence[ManualPosition], snap: Snapshot) -> list[Line]:
    lines: list[Line] = [[("ACTIVE MANUAL POSITIONS", "gold")]]
    if not positions:
        lines.append([("No manually confirmed positions.", "primary")])
        lines.append([("Nothing is assumed executed by Grog.", "muted")])
        return lines
    for p in positions[:4]:
        m = mark_position(p, snap.quote)
        r = r_short(m.unrealized_r) if m.closeable is not None else DASH
        style = "error" if p.state is PositionState.RECONCILIATION_REQUIRED else "primary"
        lines.append(
            [
                (
                    f"{p.position_id} {p.side.value} {_q(p.remaining_qty)} @ "
                    f"{price(p.entry_price)} {r} {state_text(p)}",
                    style,
                )
            ]
        )
    if len(positions) > 4:
        lines.append([(f"+{len(positions) - 4} more (3 Positions)", "muted")])
    lines.append([(PNL_UNKNOWN, "muted")])
    return lines


def position_detail(
    pos: ManualPosition,
    events: Sequence[PositionEventRecord],
    snap: Snapshot,
    tracker: TouchTracker,
) -> list[Line]:
    ent, ex = entry_labels(pos.side)
    m = mark_position(pos, snap.quote, stale=_stale(snap))
    lines: list[Line] = [
        [
            (f"POSITION {pos.position_id} / ", "gold"),
            (pos.side.value, "buy" if pos.side is Side.BUY else "sell"),
            (f"   {state_text(pos)}   {pos.fidelity} {pos.mode} — local record", "primary"),
        ],
        [
            (
                f"Signal: {pos.linked_signal_id or 'none'} ({pos.signal_link})   Plan status: "
                f"{pos.plan_status.value} {', '.join(pos.off_plan_reasons)}",
                "caution" if pos.off_plan_reasons else "primary",
            )
        ],
        [
            (
                f"Fill {ent} {price(pos.entry_price)} at {utc(pos.entry_ms)} (recorded "
                f"{utc(pos.entry_recorded_ms)})   qty {_q(pos.remaining_qty)} of "
                f"{_q(pos.initial_qty)}",
                "primary",
            )
        ],
        [
            (
                f"SL {ex} initial {price(pos.initial_sl)} / current {price(pos.current_sl)}   "
                f"TP1 {price(pos.tp1)}   TP {ex} {price(pos.current_tp)}   initial risk "
                f"{price(pos.initial_risk) if pos.initial_risk else UNKNOWN}",
                "primary",
            )
        ],
    ]
    if pos.plan is not None:
        pl = pos.plan
        lines.append(
            [
                (
                    f"Original plan (unchanged): E0 {price(pl.e0)} SL {price(pl.sl0)} "
                    f"TP2 {price(pl.tp2)} risk {price(pl.original_risk)} expires "
                    f"{utc(pl.expiry_ms)}",
                    "muted",
                )
            ]
        )
    if m.closeable is not None:
        lines.append(
            [
                (
                    f"Mark {m.closeable_side} {price(m.closeable)} at {utc(m.quote_ms)}   "
                    f"unrealized gross price x qty {signed(m.unrealized_price_units)}   "
                    f"{r_long(m.unrealized_r)} gross",
                    "primary",
                )
            ]
        )
    if m.reason:
        lines.append([(m.reason, "caution")])
    lines.append(
        [
            (
                f"Realized gross {r_long(pos.realized_r)}   Fees {pos.fees_text}   {PNL_UNKNOWN}",
                "muted",
            )
        ]
    )
    feed = snap.health.status.value if snap.health else None
    bias = snap.context.h1_bias.value if snap.context else None
    obs = observations(
        pos,
        tracker.touched(pos),
        feed_status=feed,
        h1_bias_now=bias,
        replay_ended=snap.playback is Playback.ENDED,
        clock_ms=_clock(snap, pos),
    )
    lines.append([("Observations: " + (" | ".join(obs) or "none"), "caution")])
    lines.append([("EVENTS (append-only)", "gold")])
    for e in events[-8:]:
        detail = ""
        if e.qty is not None:
            detail = f" qty {_q(e.qty)} @ {price(e.price)}"
        if e.action is PositionAction.MODIFY:
            detail = (
                f" SL {e.payload.get('new_stop') or '='} TP {e.payload.get('new_target') or '='}"
            )
        fees = (
            ""
            if e.action not in _FEE_ACTIONS
            else f" fees {e.fees if e.fees is not None else UNKNOWN}"
        )
        lines.append([(f"{utc(e.effective_at_ms)}  {e.action.value}{detail}{fees}", "muted")])
    if pos.state is PositionState.RECONCILIATION_REQUIRED:
        lines.append(
            [
                (
                    "Verify at your broker. If it is open exactly as recorded, confirm below; "
                    "otherwise record the partial/close/modification (p/m/x).",
                    "caution",
                )
            ]
        )
    lines.append([("No automatic broker order is created.", "muted")])
    return lines


_FEE_ACTIONS = (PositionAction.ENTRY, PositionAction.PARTIAL_CLOSE, PositionAction.CLOSE)


# --------------------------------------------------------------------------- journal rows


def manual_journal_rows(
    journal: PositionJournal, compact: bool = False
) -> list[tuple[int, JournalRow]]:
    """Persisted local journal rows with their sort time."""
    out: list[tuple[int, JournalRow]] = []
    positions = {p.position_id: p for p in journal.positions()}
    for e in journal.events():
        p = positions[e.position_id]
        state = {
            PositionAction.ENTRY: f"ENTERED {p.plan_status.value}",
            PositionAction.PARTIAL_CLOSE: "PARTIAL",
            PositionAction.MODIFY: "MODIFIED",
            PositionAction.CLOSE: "CLOSED",
            PositionAction.RESTORED_UNVERIFIED: "RECONCILIATION_REQUIRED",
            PositionAction.CONFIRMED_OPEN: "MONITORING",
        }[e.action]
        realized = DASH
        if e.action in (PositionAction.PARTIAL_CLOSE, PositionAction.CLOSE) and p.initial_risk:
            _, _, r = exit_preview(p, e.price, e.qty)
            realized = r_short(r) + " gross"
        reason = ", ".join(p.off_plan_reasons) if e.action is PositionAction.ENTRY else ""
        reason = reason or e.payload.get("note") or e.payload.get("reason") or DASH
        cells = (
            utc(e.effective_at_ms),
            f"{p.position_id}/{short_id(p.linked_signal_id)}",
            p.plan.strategy_version if p.plan else DASH,
            p.side.value,
            e.action.value,
            state,
            "MANUAL (operator)",
            realized,
            f"{p.fidelity} {p.mode}",
            reason,
        )
        if compact:
            cells = (cells[0], p.position_id, cells[3], state, reason)
        out.append((e.effective_at_ms, JournalRow(f"pe-{e.event_id}", cells)))
    for d in journal.decisions():
        cells = (
            utc(d.effective_at_ms),
            d.signal_id,
            DASH,
            DASH,
            "SKIP",
            d.decision,
            "OPERATOR",
            DASH,
            f"SIMULATED {d.mode}",
            d.reason or DASH,
        )
        if compact:
            cells = (cells[0], short_id(d.signal_id), DASH, d.decision, d.reason or DASH)
        out.append((d.effective_at_ms, JournalRow(f"sd-{d.decision_id}", cells)))
    return out
