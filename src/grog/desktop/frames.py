"""Detached, immutable presentation frames for the native desktop (no Qt import).

A frame is built on the thread that owns the engine and carries only immutable values
(str, int, bool, Decimal, None, enums, tuples and frozen dataclasses of those). It never
holds a reference to a live session, mapping, list or SQLite object, so it can cross a
Qt queued connection safely. Formatting reuses the existing pure helpers; no trading
arithmetic, eligibility or timing is decided here.

Mode awareness: every frame carries :class:`ModeLabels`, so shared shell widgets never
hard-code replay wording. Only the REPLAY labels exist today. A read-only REFERENCE mode
is gated behind M09-B (docs/10 §9) and is deliberately not defined here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from grog.desktop.diagnostics_model import source_diagnostics
from grog.desktop.overview_model import OverviewState, from_snapshot
from grog.desktop.presentation import price_text, utc_ms_text
from grog.desktop.signals_model import SignalsFacts, build_signals_facts
from grog.domain.enums import SignalState, Timeframe
from grog.journal.positions import PlanRef, observations, r_breakdown
from grog.replay.session import Playback
from grog.ui.format import pace_label, utc
from grog.ui.lanes import signal_lane
from grog.ui.manual import _clock, live_positions_panel, mark_cell, mark_for, positions_strip
from grog.ui.panels import (
    _bias_detail,
    banner,
    display_atr,
    journal_rows,
    m5_atr,
    plain,
    playback_label,
    warmup_text,
)

if TYPE_CHECKING:
    from grog.journal.positions import ManualPosition, TouchTracker
    from grog.replay.session import ReplaySession


class DisplayMode(StrEnum):
    REPLAY = "REPLAY"


@dataclass(frozen=True, slots=True)
class ModeLabels:
    """Wording owned by the data mode, not by any widget."""

    mode: DisplayMode
    fidelity: str  # execution-fidelity label that must never leave the screen
    clock_caption: str
    price_caveat: str
    has_transport: bool  # replay controls exist only for a replayable source


REPLAY_LABELS = ModeLabels(
    mode=DisplayMode.REPLAY,
    fidelity="SIMULATED",
    clock_caption="Virtual replay time",
    price_caveat="Historical replay quote — not a live or executable price",
    has_transport=True,
)


class Phase(StrEnum):
    LOADING = "LOADING"
    RUNNING = "RUNNING"
    FAULT = "FAULT"


@dataclass(frozen=True, slots=True)
class FrameTag:
    source_id: str
    generation: int
    sequence: int


@dataclass(frozen=True, slots=True)
class QuoteFacts:
    bid: Decimal | None
    ask: Decimal | None
    spread: Decimal | None
    provider_ms: int | None
    received_ms: int | None
    bid_text: str
    ask_text: str
    spread_text: str
    provider_utc: str
    received_utc: str


@dataclass(frozen=True, slots=True)
class TransportFacts:
    playback: Playback
    playback_text: str
    pace_text: str
    processed: int
    total: int
    pre_roll: int
    can_toggle: bool
    can_step: bool


@dataclass(frozen=True, slots=True)
class PositionFacts:
    journal_ok: bool
    journal_note: str
    open_count: int | None
    reconciliation_required: int | None
    off_plan: int | None
    lines: tuple[str, ...]
    advisories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticFacts:
    health: str
    health_reasons: tuple[str, ...]
    quote_age_ms: int | None
    warmup: str
    warmup_sufficient: bool
    # timeframe, confirmed count, last close UTC, exact available-at UTC (ms)
    bars: tuple[tuple[str, int, str, str], ...]
    provisional: tuple[str, ...]
    gaps: int
    triggers_observed: int
    signal_events: int
    origin: str
    raw_symbol: str
    config_hash: str
    config_version: int
    state_schema_version: int
    batch_sha256s: tuple[str, ...]
    m5_atr_exact: str


@dataclass(frozen=True, slots=True)
class CauseFacts:
    """Human explanation of the confirmed H1/M15/M5 state, from engine fields only."""

    h1: str
    m15: str
    m5: str


@dataclass(frozen=True, slots=True)
class MarkFacts:
    """Replay-side monitoring facts of one recorded open position (observations only).

    ``events`` is the journal event count of the position the facts were computed from;
    the GUI shows them only next to a journal snapshot of exactly that version."""

    position_id: str
    events: int
    closeable_side: str  # BID (BUY) / ASK (SELL)
    closeable: Decimal | None
    mark_text: str  # price, ``*`` when not FRESH, ``—`` when unavailable
    quote_ms: int | None
    freshness: str
    reason: str | None
    unrealized_units: Decimal | None
    move_r: Decimal | None
    realized_r: Decimal | None
    unrealized_r: Decimal | None
    total_r: Decimal | None
    original_risk_units: Decimal | None
    observations: tuple[str, ...]
    touched: tuple[tuple[str, int], ...]  # (STOP|TP1|TARGET, first touch replay UTC ms)


@dataclass(frozen=True, slots=True)
class EngineRow:
    """One SIM ENGINE signal event (session replay, simulated, not persisted)."""

    key: str  # the engine event ID: stable across frames
    time_ms: int  # decision (receipt) time of the causing input
    event_ms: int  # provider/bar/expiry time of the event
    kind: str
    side: str
    ref: str  # full signal or candidate ID
    cells: tuple[str, ...]  # JOURNAL_COLUMNS order (shared terminal wording)
    search: str


@dataclass(frozen=True, slots=True)
class ClockFacts:
    """Replay clock facts a manual form needs (playback is never live freshness)."""

    virtual_ms: int | None  # received time of the latest processed replay quote
    playback: Playback
    cursor: int
    h1_bias: str | None
    strategy_version: str


@dataclass(frozen=True, slots=True)
class SignalCheck:
    """Fresh engine eligibility of one signal, read on the replay owner thread."""

    token: int
    source_id: str
    generation: int
    signal_id: str
    cursor: int
    playback: Playback
    virtual_ms: int | None
    found: bool
    state: str  # READY | EXPIRED | INVALIDATED | ... or "UNKNOWN" when not found
    blocked: bool
    pre_roll: bool
    plan: PlanRef | None
    h1_bias: str | None
    reason: str = ""  # why the check could not be made

    @property
    def ready(self) -> bool:
        return self.found and self.state == SignalState.READY.value

    def same_eligibility(self, other: SignalCheck) -> bool:
        """True when nothing the form showed has changed (source, generation, cursor,
        engine state, blocked flag and the immutable plan)."""
        return (
            self.found
            and other.found
            and (self.source_id, self.generation, self.signal_id, self.cursor)
            == (other.source_id, other.generation, other.signal_id, other.cursor)
            and (self.state, self.blocked, self.plan) == (other.state, other.blocked, other.plan)
        )


@dataclass(frozen=True, slots=True)
class OverviewFrame:
    tag: FrameTag
    labels: ModeLabels
    quote: QuoteFacts
    transport: TransportFacts
    overview: OverviewState
    positions: PositionFacts
    diagnostics: DiagnosticFacts
    causes: CauseFacts
    banner: str | None
    forming: int
    ready: int
    blocked: int
    ready_ids: tuple[str, ...]  # full immutable IDs, engine order, never ranked
    blocked_ids: tuple[str, ...]
    signals: SignalsFacts  # D02 Signals page rows/details from the same snapshot
    marks: tuple[MarkFacts, ...] = ()  # D03: one per recorded open position
    engine_rows: tuple[EngineRow, ...] = ()  # D03 Journal: every session engine event
    diag: object | None = None  # D04 diagnostics_model.DiagnosticsFacts (owner-built)
    clock: ClockFacts | None = None


@dataclass(frozen=True, slots=True)
class StatusFrame:
    """Lifecycle state when no engine frame can be shown (loading or a fault)."""

    tag: FrameTag
    labels: ModeLabels
    phase: Phase
    title: str
    detail: str
    exit_code: int | None = None  # for a failure before the first engine frame
    last_virtual_utc: str | None = None


@dataclass(frozen=True, slots=True)
class PauseAck:
    token: int
    source_id: str
    generation: int
    cursor: int
    playback: Playback


Overlay = Mapping[str, tuple[str, str | None]]


def _positions(
    snap,
    positions: Sequence[ManualPosition] | None,
    tracker: TouchTracker,
    journal_note: str,
) -> PositionFacts:
    if positions is None:
        return PositionFacts(False, journal_note, None, None, None, (), ())
    rr = sum(1 for p in positions if p.state.value == "RECONCILIATION_REQUIRED")
    off = sum(1 for p in positions if p.plan_status.value == "OFF_PLAN")
    lines = tuple(plain([line]) for line in live_positions_panel(positions, snap)[1:])
    strip = positions_strip(positions, snap, tracker)
    advisories = tuple(plain([line]) for line in strip[:-1]) if positions else ()
    return PositionFacts(True, journal_note, len(positions), rr, off, lines, advisories)


def mark_facts(
    snap, positions: Sequence[ManualPosition] | None, tracker: TouchTracker
) -> tuple[MarkFacts, ...]:
    """Marks/R/observations via the shared validated helpers (no new arithmetic)."""
    if positions is None:
        return ()
    feed = snap.health.status.value if snap.health else None
    bias = snap.context.h1_bias.value if snap.context else None
    ended = snap.playback is Playback.ENDED
    out = []
    for p in positions:
        m = mark_for(p, snap)
        rb = r_breakdown(p, m)
        touched = tracker.touched(p)
        obs = observations(
            p,
            touched,
            feed_status=feed,
            h1_bias_now=bias,
            replay_ended=ended,
            clock_ms=_clock(snap, p),
        )
        out.append(
            MarkFacts(
                position_id=p.position_id,
                events=p.events,
                closeable_side=m.closeable_side,
                closeable=m.closeable,
                mark_text=mark_cell(m),
                quote_ms=m.quote_ms,
                freshness=m.freshness,
                reason=m.reason,
                unrealized_units=m.unrealized_price_units,
                move_r=rb.move_r,
                realized_r=rb.realized_r,
                unrealized_r=rb.unrealized_r,
                total_r=rb.total_r,
                original_risk_units=rb.original_risk_units,
                observations=tuple(obs),
                touched=tuple(sorted(touched.items())),
            )
        )
    return tuple(out)


def engine_rows(events: Sequence, version: str, start: int = 0) -> tuple[EngineRow, ...]:
    """SIM ENGINE rows for ``events[start:]`` using the shared terminal row wording."""
    tail = list(events[start:])
    rows = journal_rows(tail, version)
    return tuple(
        EngineRow(
            key=r.key,
            time_ms=e.decision_time_ms,
            event_ms=e.event_time_ms,
            kind=e.kind.value,
            side=e.side.value,
            ref=e.signal_id or e.candidate_id,
            cells=tuple(r.cells),
            search=r.search,
        )
        for e, r in zip(tail, rows, strict=True)
    )


def _codes(reasons: Sequence[str]) -> str:
    return ", ".join(reasons) if reasons else "no reason codes"


def _m15_side(name: str, a) -> str:
    text = f"{name} {a.context.value.lower()} ({_codes(a.reasons)})"
    if a.reference_price is not None:
        text += (
            f"; reference pivot {price_text(a.reference_price)}"
            f" available {utc_ms_text(a.reference_available_at_ms)}"
        )
    return text


def _causes(snap) -> CauseFacts:
    ctx = snap.context
    if ctx is None:
        unknown = "Not evaluated: no confirmed bars have been processed yet."
        return CauseFacts(unknown, unknown, unknown)
    detail = _bias_detail(snap)
    h1 = (
        f"Bias {ctx.h1_bias.value} from the last confirmed H1 bar: {detail}; "
        f"engine reasons: {_codes(ctx.h1_bias_reasons)}."
    )
    m15 = _m15_side("Buy side", ctx.m15_buy) + ". " + _m15_side("Sell side", ctx.m15_sell) + "."
    atr = m5_atr(snap)
    status = snap.warmup.m5_atr.value if snap.warmup.m5_atr else "UNKNOWN"
    # Same display rounding as the terminal (quote precision); exact value in diagnostics.
    shown = display_atr(atr, snap) if atr is not None else None
    atr_text = f"ATR14 ≈{shown} ({status})" if shown is not None else f"ATR14 {status}"
    if snap.forming:
        m5 = (
            f"{len(snap.forming)} candidate(s) waiting for a completed M5 BID close beyond the "
            f"trigger level (see Developing setups). {atr_text}; "
            f"triggers observed this session {snap.triggers_observed}."
        )
    else:
        m5 = (
            "No S1 candidate is forming, so no M5 trigger is pending. "
            f"{atr_text}; triggers observed this session {snap.triggers_observed}."
        )
    return CauseFacts(h1, m15, m5)


def build_overview_frame(
    session: ReplaySession,
    *,
    tag: FrameTag,
    overlay: Overlay | None,
    positions: Sequence[ManualPosition] | None,
    tracker: TouchTracker,
    journal_note: str,
    engine: tuple[EngineRow, ...] | None = None,
) -> OverviewFrame:
    """Snapshot the owner's engine once and detach every value the GUI may show.

    ``overlay``/``positions`` are ``None`` when the read-only journal could not be read;
    a READY proposal is then never shown as an unclaimed fresh opportunity.
    """
    snap = session.snapshot()
    events = tuple(session.pipeline.signals.events)
    known_overlay = dict(overlay) if overlay is not None else {}
    state = from_snapshot(
        snap,
        events,
        known_overlay,
        open_positions=len(positions) if positions is not None else 0,
    )
    ready = [v for v in snap.signals if v.status.state is SignalState.READY]
    blocked_ids = tuple(
        v.record.signal_id
        for v in ready
        if not v.pre_roll and signal_lane(v, known_overlay).blocked
    )
    ready_ids = tuple(
        v.record.signal_id for v in ready if signal_lane(v, known_overlay).fresh_opportunity
    )
    blocked, fresh_ready = len(blocked_ids), len(ready_ids)
    if overlay is None and fresh_ready:
        state = _replace(
            state,
            headline="Operator records unavailable — READY cannot be confirmed",
            description=(
                "The local journal could not be read, so it is unknown whether this proposal "
                "was already entered or skipped. Treat it as not actionable. " + journal_note
            ),
            tone="warning",
        )
    q = snap.quote
    health = snap.health
    hist_counts = snap.bar_counts
    bars = tuple(
        (
            tf.value,
            int(hist_counts.get(tf, 0)),
            utc_ms_text(None if snap.last_bars.get(tf) is None else snap.last_bars[tf].end_ms),
            utc_ms_text(
                None if snap.last_bars.get(tf) is None else snap.last_bars[tf].available_at_ms
            ),
        )
        for tf in (Timeframe.H1, Timeframe.M15, Timeframe.M5)
    )
    provisional = tuple(
        f"{tf.value} open since {utc_ms_text(b.start_ms)} · PROVISIONAL, not used for signals"
        for tf in (Timeframe.H1, Timeframe.M15, Timeframe.M5)
        if (b := snap.provisional.get(tf)) is not None
    )
    src = snap.source
    banner_line = banner(snap)
    ended = snap.playback is Playback.ENDED
    return OverviewFrame(
        tag=tag,
        labels=REPLAY_LABELS,
        quote=QuoteFacts(
            bid=None if q is None else q.bid,
            ask=None if q is None else q.ask,
            spread=None if q is None else q.spread,
            provider_ms=None if q is None else q.provider_time_ms,
            received_ms=None if q is None else q.received_time_ms,
            bid_text=price_text(None if q is None else q.bid),
            ask_text=price_text(None if q is None else q.ask),
            spread_text=price_text(None if q is None else q.spread),
            provider_utc=utc_ms_text(None if q is None else q.provider_time_ms),
            received_utc=utc_ms_text(None if q is None else q.received_time_ms),
        ),
        transport=TransportFacts(
            playback=snap.playback,
            playback_text=playback_label(snap),
            pace_text=pace_label(snap.pace),
            processed=snap.processed,
            total=snap.total,
            pre_roll=snap.pre_roll_quotes,
            can_toggle=not ended,
            can_step=snap.playback is Playback.PAUSED and snap.processed < snap.total,
        ),
        overview=state,
        positions=_positions(snap, positions, tracker, journal_note),
        diagnostics=DiagnosticFacts(
            health=health.status.value if health else "UNKNOWN",
            health_reasons=tuple(health.reasons) if health else (),
            quote_age_ms=health.quote_age_ms if health else None,
            warmup=warmup_text(snap),
            warmup_sufficient=snap.warmup.sufficient,
            bars=bars,
            provisional=provisional,
            gaps=len(snap.gaps),
            triggers_observed=snap.triggers_observed,
            signal_events=len(events),
            origin=src.origin,
            raw_symbol=src.raw_symbol,
            config_hash=src.config_hash,
            config_version=src.config_version,
            state_schema_version=src.state_schema_version,
            batch_sha256s=tuple(src.batch_sha256s),
            m5_atr_exact=price_text(m5_atr(snap)),
        ),
        causes=_causes(snap),
        banner=None if banner_line is None else _exact_times(plain([banner_line]), snap),
        forming=len(snap.forming),
        ready=fresh_ready,
        blocked=blocked,
        ready_ids=ready_ids,
        blocked_ids=blocked_ids,
        signals=build_signals_facts(snap, events, overlay, positions, journal_note),
        marks=mark_facts(snap, positions, tracker),
        engine_rows=engine if engine is not None else engine_rows(events, _version(session)),
        diag=source_diagnostics(snap, strategy_version=_version(session), cursor=session.cursor),
        clock=ClockFacts(
            virtual_ms=snap.virtual_time_ms,
            playback=snap.playback,
            cursor=session.cursor,
            h1_bias=snap.context.h1_bias.value if snap.context else None,
            strategy_version=_version(session),
        ),
    )


def _version(session) -> str:
    return session.pipeline.detector.params.strategy_version


def signal_check(
    session: ReplaySession | None,
    *,
    token: int,
    source_id: str,
    generation: int,
    signal_id: str,
    reason: str = "",
) -> SignalCheck:
    """Read one signal's current engine eligibility (owner thread only)."""
    if session is None or reason:
        return SignalCheck(
            token,
            source_id,
            generation,
            signal_id,
            -1,
            Playback.PAUSED,
            None,
            False,
            "UNKNOWN",
            False,
            False,
            None,
            None,
            reason or "replay is not loaded",
        )
    snap = session.snapshot()
    view = next((v for v in snap.signals if v.record.signal_id == signal_id), None)
    bias = snap.context.h1_bias.value if snap.context else None
    if view is None:
        return SignalCheck(
            token,
            source_id,
            generation,
            signal_id,
            session.cursor,
            snap.playback,
            snap.virtual_time_ms,
            False,
            "UNKNOWN",
            False,
            False,
            None,
            bias,
            "signal is not in this replay at the current cursor",
        )
    return SignalCheck(
        token=token,
        source_id=source_id,
        generation=generation,
        signal_id=signal_id,
        cursor=session.cursor,
        playback=snap.playback,
        virtual_ms=snap.virtual_time_ms,
        found=True,
        state=view.status.state.value,
        blocked=bool(view.status.blocked),
        pre_roll=bool(view.pre_roll),
        plan=PlanRef.from_record(view.record),
        h1_bias=bias,
    )


def _exact_times(text: str, snap) -> str:
    """The shared terminal banner prints whole seconds; the desktop shows the exact ms."""
    t = snap.virtual_time_ms
    return text if t is None else text.replace(utc(t), utc_ms_text(t))


def _replace(state: OverviewState, **changes: str) -> OverviewState:
    from dataclasses import replace

    return replace(state, **changes)


IMMUTABLE_SCALARS = (str, int, bool, Decimal, type(None), StrEnum)


def assert_detached(value: object, path: str = "frame") -> None:
    """Raise if ``value`` reaches any mutable container or non-frozen object."""
    from dataclasses import fields, is_dataclass

    if isinstance(value, IMMUTABLE_SCALARS):
        return
    if isinstance(value, tuple):
        for i, item in enumerate(value):
            assert_detached(item, f"{path}[{i}]")
        return
    if is_dataclass(value) and not isinstance(value, type):
        params = getattr(type(value), "__dataclass_params__", None)
        if params is None or not params.frozen:
            raise TypeError(f"{path}: {type(value).__name__} is not a frozen dataclass")
        for f in fields(value):
            assert_detached(getattr(value, f.name), f"{path}.{f.name}")
        return
    raise TypeError(f"{path}: {type(value).__name__} is mutable or not a detached value")
