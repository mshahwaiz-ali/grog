"""Panel content built from engine snapshots (docs/02 §4-§10). No Textual import.

Every value shown comes from :class:`grog.replay.session.Snapshot` (real engine state);
missing inputs are shown as UNKNOWN/—, never as 0, and there is no score or probability.
A *line* is a list of ``(text, style)`` segments; styles are semantic palette names.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from grog.domain.enums import FeedStatus, H1Bias, Side, SignalEventKind, SignalState, Timeframe
from grog.domain.models import S1Candidate, SignalEvent
from grog.replay.session import Playback, SignalView, Snapshot
from grog.ui.format import DASH, UNKNOWN, duration, hms, pace_label, price, short_id, utc
from grog.ui.lanes import OperatorOverlay, exposure, signal_lane

Line = list[tuple[str, str]]

DIAG_LABEL = {  # docs/02 §8 source status presentation labels (not the signal FSM)
    FeedStatus.FRESH: "FRESH",
    FeedStatus.STALE: "STALE",
    FeedStatus.DEGRADED: "DEGRADED",
    FeedStatus.UNKNOWN: "UNKNOWN",
    FeedStatus.CLOSED: "MARKET_CLOSED",
    FeedStatus.NO_DATA: "OFFLINE",
}


def plain(lines: Sequence[Line]) -> str:
    return "\n".join("".join(t for t, _ in line) for line in lines)


def _side_style(side: Side) -> str:
    return "buy" if side is Side.BUY else "sell"


def mode_badge(snap: Snapshot) -> str:
    return f"REPLAY • {snap.source.origin}"


def playback_label(snap: Snapshot) -> str:
    if snap.playback is Playback.ENDED:
        return "REPLAY ENDED"
    if snap.playback is Playback.PAUSED:
        return "REPLAY PAUSED"
    return f"PLAYING {pace_label(snap.pace)}"


def header(snap: Snapshot, compact: bool = False) -> list[Line]:
    """Title, mode/fidelity badge, playback state, virtual UTC time, source and quote."""
    q, h = snap.quote, snap.health
    status = h.status.value if h else UNKNOWN
    status_style = "ok" if h and h.status is FeedStatus.FRESH else "caution"
    play_style = "caution" if snap.playback is not Playback.PLAYING else "ok"
    gap = "  " if compact else "   "
    title: Line = [
        ("GROG / GOLD WORKSTATION", "gold"),
        (f"{gap}XAUUSD{gap}", "primary"),
        (mode_badge(snap), "gold"),
        (f"{gap}SIMULATED{gap}", "caution"),
        (playback_label(snap), play_style),
    ]
    clock: Line = [(f"{gap}{utc(snap.virtual_time_ms)} (virtual)", "primary")]
    source: Line = [(f"Source: {snap.source.source_id} ", "primary"), (f"[{status}]", status_style)]
    quote: Line = []
    if q is None:
        quote.append(("DATA NOT LOADED — import/replay data", "error"))
    else:
        quote += [
            ("BID ", "muted"),
            (price(q.bid), "primary"),
            ("  ASK ", "muted"),
            (price(q.ask), "primary"),
            ("  Spread ", "muted"),
            (price(q.spread), "primary"),
        ]
    tail: Line = [
        (f"{gap}Pace {pace_label(snap.pace)}", "muted"),
        (
            f"{gap}PRE-ROLL {snap.pre_roll_quotes}"
            + (" (history)" if compact else " quotes (history)"),
            "caution",
        ),
    ]
    if compact:
        return [title, [*source, *clock], [*quote, *tail]]
    return [[*title, *clock], [*source, ("   ", "muted"), *quote, *tail]]


def banner(snap: Snapshot) -> Line | None:
    """Highest-precedence critical state (docs/02 §11 status precedence)."""
    h = snap.health
    if snap.quote is None:
        return [("DATA NOT LOADED — import/replay data. Next: grog import-ticks ...", "error")]
    if h is not None and h.status is not FeedStatus.FRESH:
        why = ", ".join(h.reasons) or h.status.value
        return [(f"FEED {DIAG_LABEL[h.status]} ({h.status.value}: {why}) — no new READY", "error")]
    if not snap.warmup.sufficient:
        return [("INSUFFICIENT HISTORY — " + warmup_text(snap) + " — see 5 Diagnostics", "error")]
    if snap.playback is Playback.ENDED:
        return [
            (f"REPLAY ENDED at {utc(snap.virtual_time_ms)} — no new quotes or signals", "caution")
        ]
    return None


def warmup_text(snap: Snapshot) -> str:
    w = snap.warmup
    atr = w.m5_atr.value if w.m5_atr else UNKNOWN
    return f"H1 {w.h1_bars}/{w.h1_required}  M15 {w.m15_bars}/{w.m15_required}  M5 ATR14 {atr}"


def _bias_detail(snap: Snapshot) -> str:
    ctx = snap.context
    if ctx is None:
        return ""
    ema = {(v.name, v.timeframe): v.value for v in ctx.ema_values}
    fast, slow = ema.get(("EMA20", Timeframe.H1)), ema.get(("EMA50", Timeframe.H1))
    if fast is None or slow is None:
        return "EMA UNKNOWN"
    return "EMA20>EMA50" if fast > slow else "EMA20<EMA50" if fast < slow else "EMA20=EMA50"


def _closed(snap: Snapshot, tf: Timeframe) -> str:
    bar = snap.last_bars.get(tf)
    if bar is None:
        return "[no closed bar]"
    return "[closed]"


def _closed_at(snap: Snapshot, tf: Timeframe) -> str:
    bar = snap.last_bars.get(tf)
    return DASH if bar is None else hms(bar.end_ms)[:5]


def band_text(r, sep: str = "-") -> str:
    """Entry band rounded *inward* to the declared price step (display only)."""
    step = r.price_step
    low = (r.entry_low / step).to_integral_value(rounding=ROUND_CEILING) * step
    high = (r.entry_high / step).to_integral_value(rounding=ROUND_FLOOR) * step
    return f"{price(low)}{sep}{price(high)}"


def m5_atr(snap: Snapshot) -> Decimal | None:
    if snap.context is None:
        return None
    for v in snap.context.atr_values:
        if v.timeframe is Timeframe.M5:
            return v.value
    return None


def context_panel(snap: Snapshot) -> list[Line]:
    ctx = snap.context
    lines: list[Line] = [[("MARKET CONTEXT", "gold")]]
    if ctx is None:
        return [*lines, [("DATA UNKNOWN — no quotes processed", "caution")]]
    bias = ctx.h1_bias
    bstyle = "buy" if bias is H1Bias.UP else "sell" if bias is H1Bias.DOWN else "caution"
    lines.append(
        [
            ("H1  ", "muted"),
            (f"{bias.value:<8}", bstyle),
            (f" {_bias_detail(snap):<12} ", "primary"),
            (_closed(snap, Timeframe.H1), "muted"),
        ]
    )
    m15 = f"BUY {ctx.m15_buy.context.value}  SELL {ctx.m15_sell.context.value}"
    lines.append(
        [("M15 ", "muted"), (m15, "primary"), ("  " + _closed(snap, Timeframe.M15), "muted")]
    )
    m5_state = "Recovery watch" if snap.forming else "No candidate"
    lines.append(
        [("M5  ", "muted"), (m5_state, "primary"), ("  " + _closed(snap, Timeframe.M5), "muted")]
    )
    lines.append(
        [
            (
                f"Last closed UTC: H1 {_closed_at(snap, Timeframe.H1)}  "
                f"M15 {_closed_at(snap, Timeframe.M15)}  M5 {_closed_at(snap, Timeframe.M5)}",
                "muted",
            )
        ]
    )
    atr = m5_atr(snap)
    lines.append(
        [
            ("Volatility ATR14 M5 ", "muted"),
            (display_atr(atr, snap) if atr is not None else "DATA UNKNOWN", "primary"),
        ]
    )
    prov = snap.provisional.get(Timeframe.H1)
    if prov is not None:
        move = prov.last_bid - prov.open_bid
        lines.append(
            [
                (
                    f"H1 now {move:+} BID [provisional, not used]",
                    "muted",
                )
            ]
        )
    if not snap.warmup.sufficient:
        lines.append([("INSUFFICIENT HISTORY: " + warmup_text(snap), "error")])
    return lines


def display_atr(value: Decimal, snap: Snapshot) -> str:
    """ATR rounded to the source quote precision for display; exact in details/reports."""
    exp = snap.quote.bid.as_tuple().exponent if snap.quote is not None else -2
    if not isinstance(exp, int):
        return price(value)
    return price(value.quantize(Decimal(1).scaleb(exp)))


def _needs(snap: Snapshot, c: S1Candidate) -> tuple[str, str]:
    ctx = snap.context
    want = H1Bias.UP if c.side is Side.BUY else H1Bias.DOWN
    if ctx is None or ctx.h1_bias is not want:
        now = ctx.h1_bias.value if ctx else UNKNOWN
        return "WAIT", f"H1 {want.value} required (H1 {now})"
    level = snap.trigger_thresholds.get(c.candidate_id)
    if level is None:
        return "FORMING", "M5 trigger level UNKNOWN (history)"
    op = ">" if c.side is Side.BUY else "<"
    body = "bull" if c.side is Side.BUY else "bear"
    return "FORMING", f"M5 close{op}{price(level)} {body}"


FORMING_COLUMNS = ("ID", "SIDE", "STRATEGY", "STATUS", "NEEDS")
FORMING_COLUMNS_COMPACT = ("ID", "SIDE", "STATUS", "NEEDS")


def forming_rows(snap: Snapshot, compact: bool = False) -> list[tuple[str, tuple[str, ...]]]:
    rows = []
    for c in snap.forming:
        status, needs = _needs(snap, c)
        cells = (short_id(c.candidate_id), c.side.value, "S1", status, needs)
        if compact:
            cells = (cells[0], cells[1], cells[3], cells[4])
        rows.append((c.candidate_id, cells))
    return rows


def lanes_summary(snap: Snapshot, entered: int = 0) -> str:
    """``entered`` = open positions in the local manual journal (never inferred)."""
    return (
        f"{len(snap.forming)} forming | {len(snap.ready)} ready | {entered} entered | "
        f"{snap.triggers_observed} triggers observed"
    )


def no_trade_reason(
    snap: Snapshot, events: Sequence[SignalEvent], overlay: OperatorOverlay | None = None
) -> str:
    """Single highest-priority reason (docs/02 §10-11 precedence)."""
    h = snap.health
    if h is None or snap.quote is None:
        return "DATA NOT LOADED"
    if h.status is not FeedStatus.FRESH:
        return f"FEED {h.status.value}: " + (", ".join(h.reasons) or "unsafe")
    if not snap.warmup.sufficient:
        return "INSUFFICIENT HISTORY: " + warmup_text(snap)
    last = next((e for e in reversed(events) if e.kind is not SignalEventKind.READY_ISSUED), None)
    if last is not None and last.kind in (
        SignalEventKind.EXPIRED,
        SignalEventKind.INVALIDATED,
        SignalEventKind.NOT_ISSUED,
        SignalEventKind.MISSED_DATA_GAP,
        SignalEventKind.MISSED_PRICE_CHASE,
    ):
        reasons = ", ".join(r.value for r in last.reason_codes[:3])
        return f"last decision {last.kind.value} ({reasons})"
    live = [signal_lane(v, overlay) for v in snap.ready if not v.pre_roll]
    if any(ln.blocked for ln in live):
        return "READY signal currently EXECUTION BLOCKED (see 2 Signals)"
    if any(ln.operator for ln in live):
        return "open READY signal already acted on in the local journal"
    if snap.forming:
        return "WAIT FOR TRIGGER: M5 trigger not confirmed"
    return "No developing opportunities"


def entry_labels(side: Side) -> tuple[str, str]:
    """(entry side, exit/SL/TP side) labels (docs/02 §11)."""
    return ("ASK", "BID") if side is Side.BUY else ("BID", "ASK")


def state_label(v: SignalView) -> str:
    st = v.status
    if st.state is SignalState.READY:
        label = "EXECUTION BLOCKED" if st.blocked else "READY"
    else:
        label = st.state.value
    return label + (" PRE-ROLL" if v.pre_roll else "")


def proposals_panel(
    snap: Snapshot,
    events: Sequence[SignalEvent],
    overlay: OperatorOverlay | None = None,
    positions: Sequence = (),
) -> list[Line]:
    """Actionable lane: only READY, unblocked, unused, in-window signals (docs/14 F-01).
    Signals already ENTERED/SKIPPED in the local journal are listed as recorded, never as
    a fresh opportunity; blocked ones say so."""
    lines: list[Line] = [[("ACTIONABLE PROPOSALS (SIMULATED)", "gold")]]
    lanes = [(v, signal_lane(v, overlay)) for v in snap.signals if not v.pre_roll]
    live = [(v, ln) for v, ln in lanes if not ln.terminal]
    fresh = [(v, ln) for v, ln in live if ln.fresh_opportunity]
    if not fresh:
        lines.append([("NO TRADE — conditions not met", "caution")])
        lines.append([("Reason: " + no_trade_reason(snap, events, overlay), "muted")])
    for v, ln in live:
        r = v.record
        ent, ex = entry_labels(r.side)
        ttl = r.expiry_ms - (snap.virtual_time_ms or r.expiry_ms)
        style = "ok" if ln.fresh_opportunity else "caution"
        lines.append(
            [
                (f"{short_id(r.signal_id)} ", "primary"),
                (r.side.value, _side_style(r.side)),
                (f"  {ln.label}", style),
                (f"  TTL {duration(ttl)}", "muted"),
            ]
        )
        if ln.fresh_opportunity:
            lines.append(
                [
                    (
                        f"  {ent} entry {price(r.e0)}  SL {ex} {price(r.sl0)}  "
                        f"TP2 {ex} {price(r.tp2)}",
                        "primary",
                    )
                ]
            )
            for w in exposure(positions, r.side).warnings()[:1]:
                lines.append([("  " + w, "caution")])
        else:
            lines.append([(f"  {ln.why_not_actionable}", "muted")])
    return lines


def feed_lines(snap: Snapshot, limit: int) -> list[Line]:
    lines: list[Line] = [[("EVENT FEED (latest state transitions, virtual UTC)", "gold")]]
    if not snap.feed:
        lines.append([("No state transitions yet.", "muted")])
    for item in list(reversed(snap.feed))[:limit]:
        tag = " PRE-ROLL" if item.pre_roll else ""
        lines.append(
            [
                (f"{hms(item.time_ms)}  ", "muted"),
                (f"{short_id(item.ref):<16}", "primary"),
                (f"{item.state:<20}", "caution"),
                (f"{item.text}{tag}", "muted"),
            ]
        )
    return lines


READY_COLUMNS = ("ID", "SIDE", "READY UTC", "ENTRY", "BAND", "SL", "TP2", "NET R", "TTL", "STATE")
READY_COLUMNS_COMPACT = ("ID", "SIDE", "ENTRY", "SL", "TP2", "STATE")


def ready_rows(
    snap: Snapshot, compact: bool = False, overlay: OperatorOverlay | None = None
) -> list[tuple[str, tuple[str, ...]]]:
    """``overlay`` maps signal ID -> first local journal action; it is shown *beside* the
    engine state (e.g. ``ENTERED · EXPIRED``) and never changes the signal record."""
    rows = []
    now = snap.virtual_time_ms
    for v in reversed(snap.signals):
        r = v.record
        ent, ex = entry_labels(r.side)
        if v.status.state is SignalState.READY and now is not None:
            ttl = duration(r.expiry_ms - now)
        else:
            ttl = DASH
        cells = (
            short_id(r.signal_id),
            r.side.value,
            hms(r.first_ready_ms),
            f"{ent} {price(r.e0)}",
            band_text(r),
            f"{ex} {price(r.sl0)}",
            f"{ex} {price(r.tp2)}",
            UNKNOWN if r.estimated_cost_model_id is None else "SEE DETAIL",
            ttl,
            lane_label(v, overlay) + " SIMULATED",
        )
        if compact:
            label = lane_label(v, overlay)
            cells = (cells[0], cells[1], cells[3], cells[5], cells[6], label)
        rows.append((r.signal_id, cells))
    return rows


def lane_label(v: SignalView, overlay: OperatorOverlay | None = None) -> str:
    return signal_lane(v, overlay).label + (" PRE-ROLL" if v.pre_roll else "")


def gross_target_r(v: SignalView) -> Decimal:
    r = v.record
    move = r.tp2 - r.e0 if r.side is Side.BUY else r.e0 - r.tp2
    return move / r.original_risk_price


def signal_detail(
    snap: Snapshot,
    v: SignalView,
    current_ask: Decimal | None,
    current_bid: Decimal | None,
    overlay: OperatorOverlay | None = None,
    positions: Sequence = (),
) -> list[Line]:
    """Issued plan (immutable) and current state are separate lines, so an original READY
    that is now EXECUTION BLOCKED or terminal is never shown as eligible (docs/14 F-08)."""
    r = v.record
    ln = signal_lane(v, overlay)
    ev = json.loads(r.evidence_snapshot_json)
    ent, ex = entry_labels(r.side)
    cur = current_ask if r.side is Side.BUY else current_bid
    gates = ev.get("gates", [])
    unknown = [g["gate"] for g in gates if g["result"] == "UNKNOWN"]
    h1_id = (ev.get("last_confirmed") or [None])[0] or DASH
    now_style = "error" if ln.terminal else "caution" if ln.blocked else "ok"
    lines: list[Line] = [
        [
            (f"SIGNAL {r.signal_id} / ", "gold"),
            (r.side.value, _side_style(r.side)),
            (f"   SIMULATED   Source: {r.original_source_id} [{snap.source.origin}]", "primary"),
        ],
        [
            (f"Issued: READY at {utc(r.first_ready_ms)} (immutable plan)   ", "primary"),
            (f"Now: {ln.current}", now_style),
        ],
        [
            (
                f"Expires {utc(r.expiry_ms)} / first-quote delay "
                f"{ev.get('first_quote_delay_ms')} ms",
                "primary",
            )
        ],
        [
            (
                f"H1: {ev.get('h1_bias')} [last confirmed {h1_id}]   "
                f"M15: {ev.get('m15_context')}   "
                "M5: Closed trigger confirmed",
                "primary",
            )
        ],
        [
            (
                f"First entry {ent}: {price(r.e0)}    Current {ent}: {price(cur)}    "
                f"Valid band: [{band_text(r, ' - ')}] (inward to step {price(r.price_step)})",
                "primary",
            )
        ],
        [
            (
                f"SL {ex}: {price(r.sl0)}   TP1 {ex}: {price(r.tp1)}   TP2 {ex}: {price(r.tp2)}   "
                f"Gross target: {gross_target_r(v):.1f}R   Risk {price(r.original_risk_price)}",
                "primary",
            )
        ],
        [("Net risk/return: UNKNOWN (execution broker fees/contract not confirmed)", "caution")],
        [
            (
                "Eligibility at issuance: PASS (all blocking gates, simulated research rules)   "
                f"UNKNOWN non-blocking: {', '.join(unknown) or 'none'}",
                "muted",
            )
        ],
    ]
    if ln.blocked:
        lines.append(
            [
                (
                    "EXECUTION BLOCKED now: "
                    + ", ".join(x.value for x in v.status.blocked_reasons)
                    + " — a fill now is recorded OFF_PLAN",
                    "caution",
                )
            ]
        )
    if v.status.terminal_reason is not None:
        lines.append([(f"Terminal: {v.status.terminal_reason.value} — never resurrected", "error")])
    if ln.operator is not None:
        where = f" ({ln.position_id})" if ln.position_id else ""
        lines.append([(f"Local journal: {ln.operator}{where} — not a new opportunity", "caution")])
    if v.pre_roll:
        lines.append([("PRE-ROLL history signal — not a new alert", "caution")])
    if ln.can_record:
        for w in exposure(positions, r.side).warnings():
            lines.append([(w, "caution")])
        fill = "[e] Record external fill (OFF_PLAN)" if ln.blocked else "[e] Record external fill"
        lines.append([(f"Action: {fill}   [s] Skip   [Esc] Back", "muted")])
    else:
        lines.append([(f"No on-plan action: {ln.why_not_actionable}.   [Esc] Back", "muted")])
    lines.append([("No automatic broker order is created.", "muted")])
    return lines


def candidate_detail(snap: Snapshot, c: S1Candidate) -> list[Line]:
    status, needs = _needs(snap, c)
    pair = c.pair
    return [
        [
            (f"CANDIDATE {c.candidate_id} / ", "gold"),
            (c.side.value, _side_style(c.side)),
            (f"   {c.state.value}   NOT TRADABLE YET", "caution"),
        ],
        [
            (
                f"Pair {pair.direction}: L {price(pair.low.price)} ({pair.low.bar_id})  "
                f"H {price(pair.high.price)} ({pair.high.bar_id})",
                "primary",
            )
        ],
        [
            (
                f"Impulse {price(pair.impulse)}  ATR14 M5 at pair {price(pair.atr_m5)}  "
                f"Pullback extreme {price(c.pullback_extreme)}  Depth {price(c.depth)}",
                "primary",
            )
        ],
        [
            (
                f"Post-pivot M5 bars {c.post_pivot_bars}  "
                f"First detected {utc(c.first_detected_ms)}",
                "primary",
            )
        ],
        [(f"Status {status}: needs {needs}", "caution")],
        [("Reasons: " + (", ".join(r.value for r in c.reason_codes) or DASH), "muted")],
        [("No entry can be recorded on a FORMING candidate. No broker order exists.", "muted")],
    ]


def _playback_state(snap: Snapshot) -> str:
    """Playback is shown next to, never instead of, the source status (docs/14 F-05)."""
    if snap.playback is Playback.ENDED:
        return "REPLAY_ENDED"
    if snap.playback is Playback.PAUSED:
        return "REPLAY_PAUSED"
    return f"PLAYING {pace_label(snap.pace)}"


def diagnostics_lines(snap: Snapshot) -> list[Line]:
    q, h = snap.quote, snap.health
    label = DIAG_LABEL[h.status] if h else "OFFLINE"
    s = snap.source
    out: list[Line] = [
        [("SOURCE DIAGNOSTICS", "gold")],
        [
            (
                f"Mode: REPLAY   Fidelity: SIMULATED / {s.origin}   Source status: {label}   "
                f"Playback: {_playback_state(snap)}",
                "primary",
            )
        ],
        [
            (
                f"Feed health: {h.status.value if h else UNKNOWN}  reasons: "
                f"{', '.join(h.reasons) if h and h.reasons else DASH}",
                "caution" if not h or h.status is not FeedStatus.FRESH else "ok",
            )
        ],
        [
            (
                "Freshness thresholds: NOT CONFIGURED (max_quote_age_ms unset) — health "
                "UNKNOWN, marks UNVERIFIED, no READY issued"
                if h and "STALE_THRESHOLD_UNSET" in h.reasons
                else "Freshness thresholds: declared in config",
                "caution" if h and "STALE_THRESHOLD_UNSET" in h.reasons else "muted",
            )
        ],
        [
            (
                f"source_id: {s.source_id}   "
                f"dataset: local import ({len(s.batch_sha256s)} batch)   "
                f"symbol: {s.raw_symbol} -> canonical=XAUUSD",
                "primary",
            )
        ],
        [
            (
                f"Latest provider UTC: {utc(q.provider_time_ms) if q else DASH}   "
                f"received UTC: {utc(q.received_time_ms) if q else DASH}",
                "primary",
            )
        ],
        [
            (
                f"Quote age (virtual): {duration(h.quote_age_ms) if h else DASH}   "
                f"BID {price(q.bid) if q else DASH}  ASK {price(q.ask) if q else DASH}  "
                f"Spread {price(q.spread) if q else DASH}",
                "primary",
            )
        ],
    ]
    for tf in (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1):
        bar = snap.last_bars.get(tf)
        out.append(
            [
                (
                    f"Last finalized {tf.value:<3}: "
                    f"{utc(bar.start_ms) if bar else DASH}  ({snap.bar_counts[tf]} bars)",
                    "primary",
                )
            ]
        )
    m1_gaps = [g for g in snap.gaps if g.timeframe is Timeframe.M1]
    out.append(
        [
            (
                f"Gaps (M1): {len(m1_gaps)} records, "
                f"{sum(g.missing_bars for g in m1_gaps)} missing bars "
                "(missing ticks are not fabricated)",
                "primary",
            )
        ]
    )
    out.append(
        [
            (
                f"Warm-up: {'SUFFICIENT' if snap.warmup.sufficient else 'INSUFFICIENT HISTORY'}"
                f" — {warmup_text(snap)}",
                "ok" if snap.warmup.sufficient else "error",
            )
        ]
    )
    out.append(
        [
            (
                f"Replay: {snap.processed}/{snap.total} quotes processed, pre-roll "
                f"{snap.pre_roll_quotes} (history), window from {utc(snap.window_start_ms)}",
                "primary",
            )
        ]
    )
    for sha in s.batch_sha256s:
        out.append([(f"Batch sha256: {sha}", "muted")])
    out.append([("Adapter: offline replay file (no live adapter, no broker)", "muted")])
    out.append(
        [
            (
                f"Config sha256: {s.config_hash[:16]}  config schema v{s.config_version}  "
                f"state schema v{s.state_schema_version}",
                "muted",
            )
        ]
    )
    return out


@dataclass(frozen=True, slots=True)
class JournalRow:
    key: str
    cells: tuple[str, ...]

    def matches(self, text: str) -> bool:
        needle = text.strip().lower()
        return not needle or any(needle in c.lower() for c in self.cells)


JOURNAL_COLUMNS = (
    "UTC",
    "SIGNAL/POSITION",
    "STRATEGY VER",
    "SIDE",
    "ACTION",
    "STATE",
    "FILL SOURCE",
    "REALIZED R",
    "FIDELITY",
    "REASON",
)
JOURNAL_COLUMNS_COMPACT = ("UTC", "SIGNAL", "SIDE", "STATE", "REASON")


def journal_rows(
    events: Sequence[SignalEvent], version: str, compact: bool = False, mode: str = "REPLAY"
) -> list[JournalRow]:
    rows = []
    for e in events:
        state = e.state.value if e.state else e.kind.value
        reason = ", ".join(r.value for r in e.reason_codes[:3]) or DASH
        ref = e.signal_id or e.candidate_id
        cells = (
            utc(e.decision_time_ms),
            ref,
            version,
            e.side.value,
            e.kind.value,
            state,
            DASH,
            DASH,
            f"SIMULATED {mode}",
            reason,
        )
        if compact:
            cells = (cells[0], short_id(ref), cells[3], state, reason)
        rows.append(JournalRow(f"{e.event_id}", cells))
    return rows
