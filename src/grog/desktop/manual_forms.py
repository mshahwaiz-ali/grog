"""Manual-record form specifications for the desktop (D03, no Qt import).

Each spec describes one local-journal form: identity and immutable plan/position lines,
labelled fields with their exact parser, a live preview computed by the existing domain
helpers (``parse_amount``, ``parse_time``, ``entry_preview``, ``exit_preview``,
``current_risk``, ``stop_further_away``) and a command builder. Wording reuses the
terminal's ``grog.ui.manual`` text. Nothing here writes; the journal owner thread runs
the command through ``PositionJournal`` and decides.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from grog.desktop.frames import ClockFacts, SignalCheck
from grog.desktop.journal_model import Command, CommandKind
from grog.domain.enums import H1Bias, Side
from grog.journal.positions import (
    EntryRequest,
    JournalError,
    ManualPosition,
    PlanRef,
    current_risk,
    entry_preview,
    exit_preview,
    parse_amount,
    stop_further_away,
)
from grog.ui.format import UNKNOWN, iso_utc, price, r_long, utc
from grog.ui.lanes import exposure
from grog.ui.manual import (
    EXTERNAL,
    NO_ORDER,
    PNL_UNKNOWN,
    _fees_line,
    _preview_entry_lines,
    _q,
    parse_time,
    signed,
)
from grog.ui.panels import entry_labels

SUGGESTED_TIME = "editable suggested replay time — not a broker confirmation"
MODE_LABEL = "SIMULATED (REPLAY)"

# parser kinds
AMOUNT, AMOUNT_OPT, FEE, TIME, TEXT, SIDE, ACK = (
    "amount",
    "opt",
    "fee",
    "time",
    "text",
    "side",
    "ack",
)

Values = Mapping[str, str]
Tone = str  # primary | muted | caution | error | ok | gold
PreviewLine = tuple[str, Tone]


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    kind: str
    default: str = ""
    placeholder: str = ""
    hint: str = ""  # shown under the field (e.g. the suggested-time caveat)


@dataclass(frozen=True, slots=True)
class Parsed:
    values: dict
    errors: dict  # key -> "CODE: message"


def parse_fields(fields: Sequence[FieldSpec], v: Values) -> Parsed:
    """Per-field exact parsing with the validated domain parsers; inputs are untouched."""
    out: dict = {}
    errors: dict = {}
    for f in fields:
        raw = v.get(f.key, "")
        name = f.label.rstrip(" *").lower()
        try:
            if f.kind == AMOUNT:
                out[f.key] = parse_amount(raw, name)
            elif f.kind == AMOUNT_OPT:
                out[f.key] = parse_amount(raw, name, required=False)
            elif f.kind == FEE:
                out[f.key] = parse_amount(raw, name, required=False, allow_zero=True)
            elif f.kind == TIME:
                if not raw.strip():
                    raise JournalError("MISSING_VALUE", f"{name} is required")
                out[f.key] = parse_time(raw, name)
            elif f.kind == SIDE:
                text = raw.strip().upper()
                if text not in ("BUY", "SELL"):
                    raise JournalError("INVALID_SIDE", "side must be BUY or SELL")
                out[f.key] = Side(text)
            elif f.kind == ACK:
                if raw != "yes":
                    raise JournalError("ACK_REQUIRED", "explicit acknowledgement is required")
                out[f.key] = True
            else:
                out[f.key] = raw.strip() or None
        except JournalError as exc:
            errors[f.key] = f"{exc.code}: {exc.message}"
    return Parsed(out, errors)


@dataclass(slots=True)
class FormSpec:
    kind: CommandKind
    form_id: str
    title: str
    identity: tuple[PreviewLine, ...]
    context: tuple[PreviewLine, ...]  # immutable plan / position
    warnings: tuple[PreviewLine, ...]
    fields: tuple[FieldSpec, ...]
    preview: Callable[[dict], list[PreviewLine]]
    build: Callable[..., Command]  # (token, action_id, parsed values, fresh check|None)
    confirm_label: str = "Confirm local record"
    signal_id: str | None = None
    position_id: str | None = None
    opened: SignalCheck | None = None  # engine eligibility the form was opened with
    expected_events: int | None = None
    source_id: str = ""
    generation: int = 0
    offer_off_plan: bool = False  # entry forms: on a changed signal offer a separate path
    prefill: dict = field(default_factory=dict)
    # Structured pre-save rejections (code, message) on parsed values. The dialog disables
    # Confirm on them AND the controller re-runs them on the fresh values at Save, so no
    # rule depends on a button state or on preview text.
    reject: Callable[[dict], Sequence[Rejection]] = field(default=lambda _p: ())

    def parse(self, v: Values) -> Parsed:
        return parse_fields(self.fields, v)

    def rejections(self, values: dict) -> tuple[Rejection, ...]:
        """Rejections for already parsed values (empty = may be submitted)."""
        try:
            return tuple(self.reject(values))
        except JournalError as exc:
            return ((exc.code, exc.message),)

    def render_preview(self, v: Values) -> tuple[list[PreviewLine], dict]:
        p = self.parse(v)
        if p.errors:
            lines = [("NOT READY TO SAVE — fix the marked field(s):", "error")]
            lines += [(f"• {msg}", "error") for msg in p.errors.values()]
            return lines, p.errors
        rejected = self.rejections(p.values)
        if rejected:
            lines = [("NOT READY TO SAVE — rejected before saving:", "error")]
            lines += [(f"REJECTED {code}: {msg}", "error") for code, msg in rejected]
            return lines, {"_rejected": "; ".join(f"{c}: {m}" for c, m in rejected)}
        try:
            return self.preview(p.values), {}
        except JournalError as exc:
            return [(f"{exc.code}: {exc.message}", "error")], {"_form": exc.message}


Rejection = tuple[str, str]  # (journal error code, message)


def _before_entry(pos: ManualPosition, time_ms: int, what: str) -> list[Rejection]:
    """Event chronology: nothing about a position can precede its recorded fill."""
    if time_ms < pos.entry_ms:
        return [("TIME_BEFORE_ENTRY", f"{what} is before the entry ({utc(pos.entry_ms)})")]
    return []


def _lines(lines) -> list[PreviewLine]:
    """Terminal ``Line`` lists → (text, tone) using the first segment's style."""
    out = []
    for line in lines:
        text = "".join(t for t, _ in line)
        out.append((text, line[0][1] if line else "primary"))
    return out


def _clock_default(clock: ClockFacts | None) -> str:
    return iso_utc(clock.virtual_ms) if clock and clock.virtual_ms is not None else ""


def _h1(text: str | None) -> H1Bias | None:
    try:
        return H1Bias(text) if text else None
    except ValueError:
        return None


def plan_lines(plan: PlanRef) -> tuple[PreviewLine, ...]:
    ent, ex = entry_labels(plan.side)
    return (
        (
            f"Original plan (immutable): E0 {ent} {price(plan.e0)}  band "
            f"[{price(plan.entry_low)} - {price(plan.entry_high)}]  SL {ex} "
            f"{price(plan.sl0)}  TP1 {price(plan.tp1)}  TP2 {ex} {price(plan.tp2)}",
            "muted",
        ),
        (
            f"Risk {price(plan.original_risk)}  first READY {utc(plan.first_ready_ms)}  "
            f"expires {utc(plan.expiry_ms)}  strategy {plan.strategy_version}  "
            f"fidelity {plan.fidelity}  source {plan.source_id}",
            "muted",
        ),
    )


# --------------------------------------------------------------------------- entry / skip


def entry_spec(
    check: SignalCheck,
    open_positions: Sequence[ManualPosition] = (),
) -> FormSpec:
    """Record Entry on a READY signal (on-plan candidate; blocked => OFF_PLAN linked)."""
    plan = check.plan
    assert plan is not None
    ent, ex = entry_labels(plan.side)
    identity = (
        (f"Signal {plan.signal_id}  {plan.side.value}  (read-only)", "primary"),
        (
            f"Trade label: {MODE_LABEL}   Source {check.source_id}   Replay "
            f"{check.playback.value} at {utc(check.virtual_ms)} (cursor {check.cursor}) — "
            "Paused while recording",
            "primary",
        ),
        (NO_ORDER, "caution"),
    )
    warnings = []
    if check.blocked:
        warnings.append(
            ("Signal is EXECUTION BLOCKED now: a fill is recorded OFF_PLAN.", "caution")
        )
    if check.pre_roll:
        warnings.append(("PRE-ROLL history signal — issued before the replay window.", "caution"))
    warnings += [(w, "caution") for w in exposure(open_positions, plan.side).warnings()]
    clock_text = _clock_default_ms(check.virtual_ms)
    fields = (
        FieldSpec(
            "price", f"Actual fill price ({ent}) *", AMOUNT, placeholder="required, e.g. 4000.25"
        ),
        FieldSpec("qty", "Filled quantity/lots *", AMOUNT, placeholder="required, > 0"),
        FieldSpec("time", "Actual fill UTC time *", TIME, clock_text, hint=SUGGESTED_TIME),
        FieldSpec(
            "stop",
            "Actual stop (if different)",
            AMOUNT_OPT,
            placeholder=f"blank = {price(plan.sl0)}",
        ),
        FieldSpec(
            "target",
            "Actual target (if different)",
            AMOUNT_OPT,
            placeholder=f"blank = {price(plan.tp2)}",
        ),
        FieldSpec(
            "fees", "Commission (optional)", FEE, placeholder="blank = UNKNOWN; 0 = known zero"
        ),
        FieldSpec("broker", "Broker name (optional)", TEXT),
        FieldSpec("note", "Operator note (optional)", TEXT),
    )

    def preview(p: dict) -> list[PreviewLine]:
        prev = entry_preview(
            plan.side,
            p["price"],
            p["time"],
            plan,
            stop=p["stop"],
            target=p["target"],
            signal_ready=check.ready,
            signal_blocked=check.blocked,
            known_clock_ms=check.virtual_ms,
        )
        return _lines([*_preview_entry_lines(prev, plan.side, plan), _fees_line(p["fees"])])

    def build(token: int, action_id: str, p: dict, fresh: SignalCheck | None) -> Command:
        f = fresh or check
        return Command(
            CommandKind.ENTRY,
            token,
            check.generation,
            check.source_id,
            action_id,
            entry=EntryRequest(
                action_id=action_id,
                side=plan.side,
                price=p["price"],
                qty=p["qty"],
                fill_ms=p["time"],
                source_id=plan.source_id,
                plan=f.plan or plan,
                signal_ready=f.ready,
                signal_blocked=f.blocked,
                stop=p["stop"],
                target=p["target"],
                fees=p["fees"],
                broker=p["broker"],
                note=p["note"],
                known_clock_ms=f.virtual_ms,
                h1_bias_at_entry=_h1(f.h1_bias),
            ),
        )

    return FormSpec(
        CommandKind.ENTRY,
        "record-entry",
        "RECORD ENTRY — LOCAL JOURNAL",
        identity,
        plan_lines(plan),
        tuple(warnings),
        fields,
        preview,
        build,
        signal_id=plan.signal_id,
        opened=check,
        source_id=check.source_id,
        generation=check.generation,
        offer_off_plan=True,
    )


def _clock_default_ms(ms: int | None) -> str:
    return iso_utc(ms) if ms is not None else ""


def skip_spec(check: SignalCheck) -> FormSpec:
    plan = check.plan
    assert plan is not None
    identity = (
        (
            f"Signal {plan.signal_id}  {plan.side.value}   original expiry {utc(plan.expiry_ms)}",
            "primary",
        ),
        ("Marks USER_SKIPPED (distinct from system EXPIRED/MISSED). Status only.", "muted"),
        (
            f"Replay {check.playback.value} at {utc(check.virtual_ms)} — Paused while recording",
            "muted",
        ),
    )
    fields = (FieldSpec("reason", "Reason (optional)", TEXT),)

    def preview(p: dict) -> list[PreviewLine]:
        return [(f"Will record USER_SKIPPED at {utc(check.virtual_ms)} (replay time).", "primary")]

    def build(token: int, action_id: str, p: dict, fresh: SignalCheck | None) -> Command:
        f = fresh or check
        if f.virtual_ms is None:
            raise JournalError("NO_CLOCK", "no replay time is known yet; nothing was saved")
        return Command(
            CommandKind.SKIP,
            token,
            check.generation,
            check.source_id,
            action_id,
            plan=f.plan or plan,
            time_ms=f.virtual_ms,
            note=p["reason"],
        )

    return FormSpec(
        CommandKind.SKIP,
        "record-skip",
        "SKIP SIGNAL — LOCAL JOURNAL",
        identity,
        plan_lines(plan),
        (),
        fields,
        preview,
        build,
        confirm_label="Confirm skip (local)",
        signal_id=plan.signal_id,
        opened=check,
        source_id=check.source_id,
        generation=check.generation,
    )


def off_plan_spec(
    source_id: str,
    generation: int,
    clock: ClockFacts | None,
    *,
    prefill: Mapping[str, str] | None = None,
    reason: str = "",
) -> FormSpec:
    """Unlinked external fill: always OFF_PLAN, never claims or resurrects a signal."""
    identity = [
        ("OFF_PLAN / UNVERIFIED manual XAUUSD position record", "caution"),
        (EXTERNAL, "gold"),
        (f"Trade label: {MODE_LABEL}   Source: {source_id}", "muted"),
        ("A historical signal link is informational and never makes it READY.", "muted"),
    ]
    if reason:
        identity.insert(0, (reason, "error"))
    fields = (
        FieldSpec("side", "Side (BUY/SELL) *", SIDE, placeholder="BUY or SELL"),
        FieldSpec(
            "price", "Actual fill price *", AMOUNT, placeholder="BUY = ASK fill, SELL = BID fill"
        ),
        FieldSpec("qty", "Filled quantity/lots *", AMOUNT, placeholder="required, > 0"),
        FieldSpec(
            "time", "Actual fill UTC time *", TIME, _clock_default(clock), hint=SUGGESTED_TIME
        ),
        FieldSpec(
            "stop",
            "Stop at broker (optional)",
            AMOUNT_OPT,
            placeholder="blank = no stop / risk UNKNOWN",
        ),
        FieldSpec("target", "Target at broker (optional)", AMOUNT_OPT),
        FieldSpec(
            "fees", "Commission (optional)", FEE, placeholder="blank = UNKNOWN; 0 = known zero"
        ),
        FieldSpec(
            "signal", "Historical signal ID (opt.)", TEXT, placeholder="informational link only"
        ),
        FieldSpec("broker", "Broker name (optional)", TEXT),
        FieldSpec("note", "Operator note (optional)", TEXT),
        FieldSpec("ack", "I made this trade myself; Grog did not recommend or execute it *", ACK),
    )

    def preview(p: dict) -> list[PreviewLine]:
        prev = entry_preview(
            p["side"],
            p["price"],
            p["time"],
            None,
            stop=p["stop"],
            target=p["target"],
            known_clock_ms=None if clock is None else clock.virtual_ms,
        )
        return _lines([*_preview_entry_lines(prev, p["side"], None), _fees_line(p["fees"])])

    def build(token: int, action_id: str, p: dict, fresh: SignalCheck | None) -> Command:
        return Command(
            CommandKind.ENTRY,
            token,
            generation,
            source_id,
            action_id,
            entry=EntryRequest(
                action_id=action_id,
                side=p["side"],
                price=p["price"],
                qty=p["qty"],
                fill_ms=p["time"],
                source_id=source_id,
                plan=None,
                informational_signal_id=p["signal"],
                stop=p["stop"],
                target=p["target"],
                fees=p["fees"],
                broker=p["broker"],
                note=p["note"],
                known_clock_ms=None if clock is None else clock.virtual_ms,
                h1_bias_at_entry=_h1(None if clock is None else clock.h1_bias),
            ),
        )

    return FormSpec(
        CommandKind.ENTRY,
        "record-unlinked",
        "RECORD EXTERNAL FILL — OFF_PLAN",
        tuple(identity),
        (),
        (),
        fields,
        preview,
        build,
        confirm_label="Confirm OFF_PLAN local record",
        source_id=source_id,
        generation=generation,
        prefill=dict(prefill or {}),
    )


# ------------------------------------------------------------- position forms


def position_lines(pos: ManualPosition) -> tuple[PreviewLine, ...]:
    ent, ex = entry_labels(pos.side)
    return (
        (
            f"Position {pos.position_id}  {pos.side.value}  {pos.state.value}  "
            f"{pos.fidelity} {pos.mode}  plan {pos.plan_status.value}",
            "primary",
        ),
        (
            f"entry {ent} {price(pos.entry_price)} at {utc(pos.entry_ms)}  remaining "
            f"{_q(pos.remaining_qty)} of {_q(pos.initial_qty)}  SL {ex} {price(pos.current_sl)}  "
            f"TP {ex} {price(pos.current_tp)}  initial risk "
            f"{price(pos.initial_risk) if pos.initial_risk else UNKNOWN}",
            "primary",
        ),
        (NO_ORDER, "caution"),
    )


def exit_spec(
    pos: ManualPosition, clock: ClockFacts | None, *, close: bool, source_id: str, generation: int
) -> FormSpec:
    _, ex = entry_labels(pos.side)
    fields = (
        FieldSpec("price", f"Actual exit price ({ex}) *", AMOUNT, placeholder="required"),
        FieldSpec(
            "qty",
            "Quantity closed *",
            AMOUNT,
            _q(pos.remaining_qty) if close else "",
            f"must equal remaining {_q(pos.remaining_qty)}"
            if close
            else f"< remaining {_q(pos.remaining_qty)}",
        ),
        FieldSpec(
            "time", "Actual exit UTC time *", TIME, _clock_default(clock), hint=SUGGESTED_TIME
        ),
        FieldSpec("fees", "Fees (optional)", FEE, placeholder="blank = UNKNOWN; 0 = known zero"),
        FieldSpec("note", "Note (optional)", TEXT),
    )

    def reject(p: dict) -> list[Rejection]:
        qty = p["qty"]
        if qty > pos.remaining_qty:
            return [
                ("QTY_EXCEEDS_REMAINING", f"quantity exceeds remaining {_q(pos.remaining_qty)}")
            ]
        if close and qty != pos.remaining_qty:
            return [
                (
                    "CLOSE_QTY_MISMATCH",
                    f"a close must equal remaining {_q(pos.remaining_qty)}; "
                    "use Partial close for less",
                )
            ]
        if not close and qty == pos.remaining_qty:
            return [("PARTIAL_IS_FULL", "this is the whole remaining quantity; use Close")]
        return _before_entry(pos, p["time"], "exit time")

    def preview(p: dict) -> list[PreviewLine]:
        qty = p["qty"]
        lines: list[PreviewLine] = [("PREVIEW (before saving)", "gold")]
        remaining, units, r = exit_preview(pos, p["price"], qty)
        lines.append(
            (
                f"Remaining after record: {_q(remaining)}   Realized gross price move x qty: "
                f"{signed(units)}   Realized gross {r_long(r)} (of initial risk)",
                "primary",
            )
        )
        lines.append((f"Estimated realized {PNL_UNKNOWN}; net R UNKNOWN.", "muted"))
        lines.append(_lines([_fees_line(p["fees"])])[0])
        return lines

    def build(token: int, action_id: str, p: dict, fresh: SignalCheck | None) -> Command:
        return Command(
            CommandKind.CLOSE if close else CommandKind.PARTIAL,
            token,
            generation,
            source_id,
            action_id,
            position_id=pos.position_id,
            price=p["price"],
            qty=p["qty"],
            time_ms=p["time"],
            fees=p["fees"],
            note=p["note"],
            expected_events=pos.events,
        )

    title = "RECORD CLOSURE — LOCAL JOURNAL" if close else "RECORD PARTIAL CLOSE — LOCAL JOURNAL"
    return FormSpec(
        CommandKind.CLOSE if close else CommandKind.PARTIAL,
        "record-close" if close else "record-partial",
        title,
        position_lines(pos),
        (),
        (),
        fields,
        preview,
        build,
        position_id=pos.position_id,
        expected_events=pos.events,
        source_id=source_id,
        generation=generation,
        reject=reject,
    )


def modify_spec(
    pos: ManualPosition, clock: ClockFacts | None, *, source_id: str, generation: int
) -> FormSpec:
    _, ex = entry_labels(pos.side)
    fields = (
        FieldSpec(
            "stop",
            f"New stop ({ex})",
            AMOUNT_OPT,
            placeholder=f"blank = keep {price(pos.current_sl)}",
        ),
        FieldSpec(
            "target",
            f"New target ({ex})",
            AMOUNT_OPT,
            placeholder=f"blank = keep {price(pos.current_tp)}",
        ),
        FieldSpec("time", "Effective UTC time *", TIME, _clock_default(clock), hint=SUGGESTED_TIME),
        FieldSpec("note", "Note (optional)", TEXT),
    )

    def reject(p: dict) -> list[Rejection]:
        if p["stop"] is None and p["target"] is None:
            return [("MISSING_VALUE", "enter a new stop and/or target (blank = keep)")]
        return _before_entry(pos, p["time"], "effective time")

    def preview(p: dict) -> list[PreviewLine]:
        sl, tp = p["stop"], p["target"]
        if sl is None and tp is None:
            raise JournalError("MISSING_VALUE", "enter a new stop and/or target (blank = keep)")
        before = current_risk(pos, pos.current_sl)
        after = current_risk(pos, sl if sl is not None else pos.current_sl)
        lines: list[PreviewLine] = [
            ("PREVIEW (before saving)", "gold"),
            (
                f"SL {price(pos.current_sl)} -> {price(sl) if sl else 'unchanged'}   "
                f"TP {price(pos.current_tp)} -> {price(tp) if tp else 'unchanged'}",
                "primary",
            ),
            (
                f"Current risk per unit from actual entry: {price(before) if before else UNKNOWN} "
                f"-> {price(after) if after else UNKNOWN}  (initial R snapshot "
                f"{price(pos.initial_risk) if pos.initial_risk else UNKNOWN} never rewritten)",
                "primary",
            ),
        ]
        if stop_further_away(pos, sl):
            lines.append(("WARNING: stop is being moved FURTHER AWAY (more risk).", "error"))
        lines.append(("Records the broker-side edit locally; cannot change the broker.", "muted"))
        return lines

    def build(token: int, action_id: str, p: dict, fresh: SignalCheck | None) -> Command:
        return Command(
            CommandKind.MODIFY,
            token,
            generation,
            source_id,
            action_id,
            position_id=pos.position_id,
            time_ms=p["time"],
            new_stop=p["stop"],
            new_target=p["target"],
            note=p["note"],
            expected_events=pos.events,
        )

    return FormSpec(
        CommandKind.MODIFY,
        "record-modify",
        "RECORD STOP/TARGET MODIFICATION — LOCAL JOURNAL",
        position_lines(pos),
        (),
        (),
        fields,
        preview,
        build,
        position_id=pos.position_id,
        expected_events=pos.events,
        source_id=source_id,
        generation=generation,
        reject=reject,
    )


def confirm_open_spec(
    pos: ManualPosition, clock: ClockFacts | None, *, source_id: str, generation: int
) -> FormSpec:
    fields = (
        FieldSpec(
            "time", "Verified at UTC time *", TIME, _clock_default(clock), hint=SUGGESTED_TIME
        ),
        FieldSpec("note", "Note (optional)", TEXT),
        FieldSpec("ack", "I checked my broker: this position is open exactly as recorded *", ACK),
    )
    warnings = (
        (
            "RECONCILIATION REQUIRED — restored after a program restart. Verify it at your "
            "broker. If it changed there, cancel and record the partial/close/modification "
            "instead.",
            "caution",
        ),
        ("Grog reads no broker data: this only records your own verification.", "muted"),
    )

    def reject(p: dict) -> list[Rejection]:
        return _before_entry(pos, p["time"], "verification time")

    def preview(p: dict) -> list[PreviewLine]:
        return [
            ("PREVIEW (before saving)", "gold"),
            (
                f"{pos.position_id}: RECONCILIATION REQUIRED -> MONITORING (verified open by you "
                f"at {utc(p['time'])}). Quantities, levels and plan are unchanged.",
                "primary",
            ),
        ]

    def build(token: int, action_id: str, p: dict, fresh: SignalCheck | None) -> Command:
        for code, msg in reject(p):  # never build a command the rules reject
            raise JournalError(code, msg)
        return Command(
            CommandKind.CONFIRM_OPEN,
            token,
            generation,
            source_id,
            action_id,
            position_id=pos.position_id,
            time_ms=p["time"],
            note=p["note"],
            expected_events=pos.events,
        )

    return FormSpec(
        CommandKind.CONFIRM_OPEN,
        "confirm-open",
        "CONFIRM STILL OPEN AT BROKER — LOCAL JOURNAL",
        position_lines(pos),
        (),
        warnings,
        fields,
        preview,
        build,
        confirm_label="Confirm verified open (local)",
        position_id=pos.position_id,
        expected_events=pos.events,
        source_id=source_id,
        generation=generation,
        reject=reject,
    )


def decimal_text(v: Decimal | None) -> str:
    return "" if v is None else format(v, "f")
