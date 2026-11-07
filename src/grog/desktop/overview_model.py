"""Pure read model for the native replay Overview.

The engine, signal lane and current terminal presenter remain the authorities
for eligibility. No Qt import, journal writes or repricing occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from grog.desktop.presentation import price_text, trigger_explanation, utc_ms_text
from grog.domain.enums import FeedStatus, SignalState
from grog.replay.session import Playback
from grog.ui.lanes import signal_lane
from grog.ui.panels import candidate_condition, entry_labels, no_trade_reason

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from grog.domain.models import SignalEvent
    from grog.replay.session import Snapshot


@dataclass(frozen=True, slots=True)
class OverviewState:
    source: str
    source_health: str
    source_health_detail: str
    virtual_utc: str
    playback: str
    bid: str
    ask: str
    spread: str
    headline: str
    description: str
    tone: str  # neutral | warning | ready; presentation only
    h1: str
    m15: str
    m5: str
    context_note: str
    watchlist: tuple[str, ...]
    recent: tuple[str, ...]
    progress: str
    open_positions: str


def _human_condition(snap: Snapshot, candidate) -> str:
    """Translate the existing canonical candidate condition, not replace it."""
    status, requirement = candidate_condition(snap, candidate)
    if status == "WAIT":
        return f"Waiting for trend alignment: {requirement}. No confirmed trade signal."
    if status == "FORMING" and "UNKNOWN" in requirement:
        return "The 5-minute trigger level is unavailable; no confirmed trade signal."
    level = snap.trigger_thresholds.get(candidate.candidate_id)
    return trigger_explanation(candidate.side.value, level)


def from_snapshot(
    snap: Snapshot,
    events: Sequence[SignalEvent],
    operator_overlay: Mapping[str, tuple[str, str | None]],
    *,
    open_positions: int,
) -> OverviewState:
    """Make one immutable overview without changing replay or journal state.

    operator_overlay must originate from PositionJournal.signal_actions. The caller
    must fail closed rather than passing an invented empty overlay if journal reads
    are unavailable.
    """
    quote = snap.quote
    health = snap.health
    health_value = health.status.value if health else "UNKNOWN"
    health_detail = ", ".join(health.reasons) if health else "No data-health assessment"
    if not health_detail:
        health_detail = "No health warnings reported for this replay"

    context = snap.context
    if context is None:
        h1 = "Unavailable"
        m15 = "Unavailable"
        m5 = "Unavailable"
        context_note = "No completed market context is available yet."
    else:
        bias = context.h1_bias.value
        h1 = {"UP": "Upward", "DOWN": "Downward"}.get(bias, bias.title())
        buy = context.m15_buy.context.value.lower().replace("_", " ")
        sell = context.m15_sell.context.value.lower().replace("_", " ")
        m15 = f"Buy: {buy}  |  Sell: {sell}"
        m5 = f"{len(snap.forming)} developing setup(s)" if snap.forming else "No developing setup"
        context_note = "H1/M15 evidence uses confirmed bars; an unfinished bar is not a trigger."

    watchlist = tuple(
        f"{candidate.side.value}: {_human_condition(snap, candidate)}" for candidate in snap.forming
    )
    latest = tuple(
        f"{utc_ms_text(item.time_ms)}  |  {item.state}"
        + ("  |  historical pre-roll" if item.pre_roll else "")
        for item in reversed(snap.feed)
    )[:4]

    origin = snap.source.origin
    status = f"REPLAY  ·  {origin}  ·  SIMULATED"
    fresh = health is not None and health.status is FeedStatus.FRESH
    usable = [
        v
        for v in snap.signals
        if v.status.state is SignalState.READY
        and signal_lane(v, operator_overlay).fresh_opportunity
    ]
    blocked = [
        v
        for v in snap.signals
        if v.status.state is SignalState.READY
        and not v.pre_roll
        and signal_lane(v, operator_overlay).blocked
    ]

    if quote is None:
        headline = "No market data"
        description = "Import a source before running a replay. No trade proposal is available."
        tone = "warning"
    elif not fresh:
        headline = "No trade — source status needs review"
        description = (
            f"Feed health: {health_value}. {health_detail}. "
            "Do not treat historical or unverified quotes as live prices."
        )
        tone = "warning"
    elif not snap.warmup.sufficient:
        headline = "No trade — insufficient history"
        description = "The confirmed H1/M15/M5 history is insufficient for a valid signal."
        tone = "warning"
    elif snap.playback is Playback.ENDED:
        headline = "Replay complete"
        description = "The data window has ended. No new signals can be issued from this replay."
        tone = "neutral"
    elif len(usable) == 1:
        rec = usable[0].record
        entry_side, exit_side = entry_labels(rec.side)
        headline = f"{rec.side.value} proposal ready in simulation"
        description = (
            f"Research-only levels: {entry_side} entry {price_text(rec.e0)}; "
            f"{exit_side} stop {price_text(rec.sl0)}, "
            f"TP1 {price_text(rec.tp1)}, TP2 {price_text(rec.tp2)}. "
            "Prices are simulated and not verified at any execution broker."
        )
        tone = "ready"
    elif len(usable) > 1:
        headline = f"{len(usable)} simulated proposals ready"
        description = (
            "More than one engine proposal is READY. No ranking or automatic selection "
            "is implied. Review exact levels and exposure in Signals before any manual action."
        )
        tone = "ready"
    elif blocked:
        headline = "No trade — existing proposal blocked"
        description = (
            "An issued proposal is currently execution-blocked. "
            "It is not a fresh actionable signal; details remain in Signals."
        )
        tone = "warning"
    elif len(snap.forming) == 1:
        candidate = snap.forming[0]
        headline = f"{candidate.side.value} setup developing — no trade yet"
        description = _human_condition(snap, candidate)
        tone = "neutral"
    elif snap.forming:
        headline = f"{len(snap.forming)} setups developing — no trade yet"
        description = (
            "Multiple candidates are forming. None is automatically selected or READY; "
            "check the conditions below."
        )
        tone = "neutral"
    else:
        headline = "No confirmed trade signal"
        reason = no_trade_reason(snap, events, operator_overlay)
        description = (
            f"Current research conditions do not permit a new proposal. Engine reason: {reason}."
        )
        tone = "neutral"

    return OverviewState(
        source=status + f"  ·  Source {snap.source.source_id}",
        source_health=health_value,
        source_health_detail=health_detail,
        virtual_utc=utc_ms_text(snap.virtual_time_ms) + "  ·  virtual",
        playback="REPLAY " + snap.playback.value,
        bid=price_text(quote.bid if quote else None),
        ask=price_text(quote.ask if quote else None),
        spread=price_text(quote.spread if quote else None),
        headline=headline,
        description=description,
        tone=tone,
        h1=h1,
        m15=m15,
        m5=m5,
        context_note=context_note,
        watchlist=watchlist,
        recent=latest,
        progress=(
            f"{snap.processed:,} / {snap.total:,} quote events · {snap.pre_roll_quotes:,} pre-roll"
        ),
        open_positions=(
            f"{open_positions} stored open position(s) · view-only; "
            "reconciliation has not been performed in this desktop preview"
        ),
    )
