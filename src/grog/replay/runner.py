"""Deterministic research replay and outcome accounting (docs/08 Sections 2-3, 9-10, 13.2).

Pure: quotes + frozen config in, a :class:`ReplayResult` out. No wall clock, no I/O.

* Every quote is processed in stable source order with a virtual clock (the quote's own
  timestamps). Quotes before ``from_ms`` are **pre-roll**: they build EMA/ATR/pivots and
  their events are kept as history but excluded from window metrics.
* Outcome model (docs/07 §3, docs/08 §3): full position exits at TP2 or SL, whichever is
  touched first on **ordered ticks** after the simulated fill. TP1 is informational. A
  stop gapping through fills at the worse actual price. A data gap while the position is
  open makes the result INDETERMINATE (path unknown). No fill at any candle close.
* Entry scenario: zero manual delay = the READY quote itself (E0). Other manual-delay
  scenarios are OPEN (docs/08 §3) and not implemented.
* Net R only with a declared cost model; currency only with a declared contract.
  Otherwise outcomes are GROSS research results, clearly labeled.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from grog import __version__
from grog.analysis.params import CALC_CONTEXT
from grog.domain.enums import (
    ExitOutcome,
    GapKind,
    S1EventKind,
    SignalEventKind,
    Timeframe,
)
from grog.domain.ids import canonical_json, sha256_hex
from grog.domain.models import GapRecord, NormalizedQuote, SignalEvent, SignalRecord
from grog.risk.quotes_and_plans import (
    CostModel,
    TradePlan,
    evaluate_exit_ticks,
    net_price_move,
)
from grog.signals.engine import SignalPolicy
from grog.signals.pipeline import S1ResearchPipeline
from grog.strategies.s1_pullback import record_to_dict

ENTRY_SCENARIO_ZERO = 0  # "zero-at-first-quote" (docs/08 §3)
REPORT_VERSION = "grog-research-report/1"


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    source_id: str
    policy: SignalPolicy = field(default_factory=SignalPolicy)
    from_ms: int | None = None  # visible decision window start (inclusive)
    to_ms: int | None = None  # window end (exclusive); later quotes are not processed
    entry_delay_ms: int = ENTRY_SCENARIO_ZERO  # manual-entry delay scenario (OPEN)
    cost_model: CostModel | None = None
    config_hash: str = "built-in"
    source_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.entry_delay_ms != ENTRY_SCENARIO_ZERO:
            # Manual-delay scenario values are OPEN (docs/08 §3); none is invented here.
            raise ValueError("only the zero-delay first-quote entry scenario is defined")
        if self.from_ms is not None and self.to_ms is not None and self.to_ms <= self.from_ms:
            raise ValueError("--to must be after --from")


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """Simulated outcome of one READY (or labeled counterfactual) plan. Not a real trade."""

    trigger_id: str
    signal_id: str | None
    side: str
    counterfactual: bool
    fillable: bool
    fill_time_ms: int | None
    fill_price: Decimal | None
    outcome: ExitOutcome | None  # None when not fillable
    exit_time_ms: int | None
    exit_price: Decimal | None
    tp1_touched: bool
    gross_r: Decimal | None
    net_r: Decimal | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    run_key: dict[str, Any]
    run_id: str
    summary: dict[str, Any]
    signals: tuple[SignalRecord, ...]
    signal_events: tuple[SignalEvent, ...]
    s1_events: tuple[Any, ...]
    outcomes: tuple[TradeOutcome, ...]
    processed_quotes: int
    pair_ids: dict[str, str]  # signal_id -> frozen pair identity
    final_states: dict[str, str]  # signal_id -> READY | EXPIRED | INVALIDATED


def data_hash(batch_sha256s: Sequence[str]) -> str:
    return sha256_hex(canonical_json(sorted(batch_sha256s)).encode())


# Packages whose source determines replay results (docs/08 §2; docs/14 F-09). UI, CLI and
# journal code are excluded: they cannot change a simulated outcome.
ENGINE_PACKAGES = ("domain", "market_data", "analysis", "strategies", "signals", "risk")
ENGINE_FILES = ("replay/runner.py",)


@cache
def engine_code_hash() -> str:
    """sha256 over the engine sources (sorted relative paths + LF-normalized bytes).

    Editing any engine file changes the run identity, even without a version bump, so a
    stored run can never be silently re-used for different code."""
    root = Path(__file__).resolve().parent.parent  # src/grog
    files = [f for pkg in ENGINE_PACKAGES for f in (root / pkg).rglob("*.py")]
    files += [root / rel for rel in ENGINE_FILES]
    h = hashlib.sha256()
    for f in sorted(set(files), key=lambda x: x.relative_to(root).as_posix()):
        h.update(f.relative_to(root).as_posix().encode() + b"\0")
        h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def code_version() -> str:
    return f"{__version__}+engine.{engine_code_hash()[:12]}"


def run_identity(cfg: ReplayConfig, data_sha: str, pipeline: S1ResearchPipeline) -> dict:
    return {
        "code_version": code_version(),
        "engine_code_hash": engine_code_hash(),
        "report_version": REPORT_VERSION,
        "source_id": cfg.source_id,
        "data_hash": data_sha,
        "config_hash": cfg.config_hash,
        "strategy_hash": pipeline.detector.parameter_set_hash,
        "signal_hash": pipeline.signals.parameter_set_hash,
        "from_ms": cfg.from_ms,
        "to_ms": cfg.to_ms,
        "entry_delay_ms": cfg.entry_delay_ms,
        "cost_model": record_to_dict(cfg.cost_model),
    }


def compute_run_id(cfg: ReplayConfig, data_sha: str) -> tuple[str, dict]:
    """Deterministic run identity: code + config + params + data + window + scenario."""
    key = run_identity(cfg, data_sha, S1ResearchPipeline(cfg.source_id, cfg.policy))
    return "RUN-" + sha256_hex(canonical_json(key).encode())[:24], key


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _sum(values: Sequence[Decimal]) -> Decimal:
    total = Decimal(0)
    for v in values:
        total = CALC_CONTEXT.add(total, v)
    return total


class _Outcomes:
    def __init__(self, quotes: Sequence[NormalizedQuote], gaps: Sequence[GapRecord]) -> None:
        self.quotes = quotes
        self.received = [q.received_time_ms for q in quotes]
        self.index = {q.source_event_key: i for i, q in enumerate(quotes)}
        self.data_gaps = sorted(
            (g for g in gaps if g.timeframe is Timeframe.M1 and g.kind is GapKind.DATA_GAP),
            key=lambda g: g.from_ms,
        )

    def _gap_between(self, start_ms: int, end_ms: int) -> bool:
        return any(start_ms <= g.from_ms < end_ms for g in self.data_gaps)

    def evaluate(
        self,
        plan: TradePlan,
        fill_index: int,
        cost: CostModel | None,
        *,
        trigger_id: str,
        signal_id: str | None,
        counterfactual: bool,
    ) -> TradeOutcome:
        fill = self.quotes[fill_index]
        fill_price = fill.ask if plan.side.value == "BUY" else fill.bid
        # Re-anchor R to the actual simulated fill would change the plan; the original
        # frozen plan is evaluated as issued (fill at E0 in the zero-delay scenario).
        res = evaluate_exit_ticks(plan, self.quotes[fill_index + 1 :])
        reasons: list[str] = []
        outcome = res.outcome
        if outcome in (ExitOutcome.TARGET, ExitOutcome.STOP) and self._gap_between(
            fill.provider_time_ms, res.exit_time_ms or 0
        ):
            outcome = ExitOutcome.INDETERMINATE
            reasons.append("DATA_GAP_DURING_HOLD")
        gross = res.gross_r if outcome in (ExitOutcome.TARGET, ExitOutcome.STOP) else None
        if fill_price != plan.e0 and gross is not None and res.exit_price is not None:
            move = (
                res.exit_price - fill_price
                if plan.side.value == "BUY"
                else (fill_price - res.exit_price)
            )
            gross = CALC_CONTEXT.divide(move, plan.risk)
        net = None
        if gross is not None and cost is not None and res.exit_price is not None:
            _g, net_move = net_price_move(plan.side, fill_price, res.exit_price, cost)
            net = CALC_CONTEXT.divide(net_move, plan.risk) if net_move is not None else None
        if outcome is ExitOutcome.OPEN:
            reasons.append("END_OF_DATA_UNRESOLVED")
        return TradeOutcome(
            trigger_id,
            signal_id,
            plan.side.value,
            counterfactual,
            True,
            fill.received_time_ms,
            fill_price,
            outcome,
            res.exit_time_ms if outcome is not ExitOutcome.OPEN else None,
            res.exit_price if outcome in (ExitOutcome.TARGET, ExitOutcome.STOP) else None,
            res.tp1_touched,
            gross,
            net,
            tuple(reasons),
        )


def run_replay(
    quotes: Sequence[NormalizedQuote],
    cfg: ReplayConfig,
    *,
    data_sha: str,
    on_checkpoint: Callable[[int, S1ResearchPipeline], None] | None = None,
    checkpoint_every: int = 5_000,
) -> ReplayResult:
    pipe = S1ResearchPipeline(cfg.source_id, cfg.policy)
    window_quotes: list[NormalizedQuote] = []
    processed: list[NormalizedQuote] = []
    for n, q in enumerate(quotes, start=1):
        if cfg.to_ms is not None and q.provider_time_ms >= cfg.to_ms:
            break
        pipe.on_quote(q)
        processed.append(q)
        if cfg.from_ms is None or q.provider_time_ms >= cfg.from_ms:
            window_quotes.append(q)
        if on_checkpoint is not None and n % checkpoint_every == 0:
            on_checkpoint(n, pipe)

    eng = pipe.signals
    oc = _Outcomes(processed, pipe.aggregator.gaps)
    in_window = (lambda t: True) if cfg.from_ms is None else (lambda t: t >= cfg.from_ms)
    outcomes: list[TradeOutcome] = []
    for sid, sig in eng.signals.items():
        plan = eng.plans[sid]
        # Zero-delay scenario: simulated fill at the READY quote itself (E0); never later
        # than READY, never at a candle close.
        idx = oc.index.get(sig.first_quote_event_key)
        if idx is None:  # pragma: no cover - READY always comes from a processed quote
            outcomes.append(
                TradeOutcome(
                    sig.trigger_id,
                    sid,
                    sig.side.value,
                    False,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    False,
                    None,
                    None,
                    ("NOT_FILLABLE_UNDER_ENTRY_SCENARIO",),
                )
            )
            continue
        outcomes.append(
            oc.evaluate(
                plan,
                idx,
                cfg.cost_model,
                trigger_id=sig.trigger_id,
                signal_id=sid,
                counterfactual=False,
            )
        )
    for trig_id, (plan, q) in eng.counterfactual.items():
        outcomes.append(
            oc.evaluate(
                plan,
                oc.index[q.source_event_key],
                cfg.cost_model,
                trigger_id=trig_id,
                signal_id=None,
                counterfactual=True,
            )
        )

    summary = _summarize(cfg, pipe, processed, window_quotes, outcomes, in_window)
    run_id, key = compute_run_id(cfg, data_sha)
    return ReplayResult(
        run_key=key,
        run_id=run_id,
        summary=summary,
        signals=tuple(eng.signals.values()),
        signal_events=tuple(eng.events),
        s1_events=tuple(pipe.detector.events),
        outcomes=tuple(outcomes),
        processed_quotes=len(processed),
        pair_ids={
            sid: pipe.detector.candidates[s.candidate_id].pair_id for sid, s in eng.signals.items()
        },
        final_states={sid: st.state.value for sid, st in eng.status.items()},
    )


def _r_stats(items: Sequence[TradeOutcome], attr: str) -> dict[str, Any]:
    values = [getattr(o, attr) for o in items if getattr(o, attr) is not None]
    if not values:
        return {"resolved": 0, "total_r": None, "mean_r": None}
    total = _sum(values)
    return {
        "resolved": len(values),
        "total_r": str(total),
        "mean_r": str(CALC_CONTEXT.divide(total, Decimal(len(values)))),
    }


def _outcome_block(items: Sequence[TradeOutcome], cost_known: bool) -> dict[str, Any]:
    counts = Counter(o.outcome.value if o.outcome else "NOT_FILLABLE" for o in items)
    block = {
        "count": len(items),
        "outcomes": dict(sorted(counts.items())),
        "tp1_touched_without_tp2": sum(
            1 for o in items if o.tp1_touched and o.outcome is not ExitOutcome.TARGET
        ),
        "gross": _r_stats(items, "gross_r"),
        "net": _r_stats(items, "net_r") if cost_known else "UNKNOWN (no declared cost model)",
    }
    return block


def _summarize(
    cfg: ReplayConfig,
    pipe: S1ResearchPipeline,
    processed: Sequence[NormalizedQuote],
    window_quotes: Sequence[NormalizedQuote],
    outcomes: Sequence[TradeOutcome],
    in_window: Callable[[int], bool],
) -> dict[str, Any]:
    eng, det, agg = pipe.signals, pipe.detector, pipe.aggregator
    trig_events = [e for e in det.events if e.kind is S1EventKind.TRIGGER_OBSERVED]
    win_triggers = [e for e in trig_events if in_window(e.decision_time_ms)]
    first_decisions = [
        e
        for e in eng.events
        if e.kind
        in (
            SignalEventKind.READY_ISSUED,
            SignalEventKind.MISSED_DATA_GAP,
            SignalEventKind.MISSED_PRICE_CHASE,
            SignalEventKind.NOT_ISSUED,
        )
    ]
    win_decisions = [e for e in first_decisions if in_window(e.decision_time_ms)]
    win_signal_ids = {s.signal_id for s in eng.signals.values() if in_window(s.first_ready_ms)}
    issued = [o for o in outcomes if not o.counterfactual and o.signal_id in win_signal_ids]
    trig_time = {e.trigger.trigger_id: e.decision_time_ms for e in trig_events if e.trigger}
    rejected = [
        o for o in outcomes if o.counterfactual and in_window(trig_time.get(o.trigger_id, 0))
    ]
    not_issued = [e for e in win_decisions if e.kind is not SignalEventKind.READY_ISSUED]
    cost_known = cfg.cost_model is not None

    days: dict[str, int] = {}
    for q in window_quotes:
        days.setdefault(_day(q.provider_time_ms), 0)
    for sid in win_signal_ids:
        d = _day(eng.signals[sid].first_ready_ms)
        days[d] = days.get(d, 0) + 1
    final_states = Counter(
        st.state.value for sid, st in eng.status.items() if sid in win_signal_ids
    )
    gaps = [g for g in agg.gaps if g.timeframe is Timeframe.M1]
    reasons = Counter(r.value for e in not_issued for r in e.reason_codes)
    preroll_ready = len(eng.signals) - len(win_signal_ids)
    p = cfg.policy
    return {
        "mode": "REPLAY",
        "execution_fidelity": "SIMULATED",
        "source_id": cfg.source_id,
        "source_origins": list(cfg.source_origins),
        "window": {
            "from_ms": cfg.from_ms,
            "to_ms": cfg.to_ms,
            "first_quote_ms": window_quotes[0].provider_time_ms if window_quotes else None,
            "last_quote_ms": window_quotes[-1].provider_time_ms if window_quotes else None,
        },
        "quotes": {
            "processed": len(processed),
            "pre_roll": len(processed) - len(window_quotes),
            "in_window": len(window_quotes),
        },
        "bars": {tf.value: len(agg.history.all(tf)) for tf in Timeframe},
        "data_gaps": {
            "m1_gap_records": len(gaps),
            "data_gap": sum(1 for g in gaps if g.kind is GapKind.DATA_GAP),
            "market_closed": sum(1 for g in gaps if g.kind is GapKind.MARKET_CLOSED),
            "missing_m1_buckets": sum(g.missing_bars for g in gaps),
        },
        "candidates": dict(
            sorted(
                Counter(e.kind.value for e in det.events if in_window(e.decision_time_ms)).items()
            )
        ),
        "funnel": {
            "trigger_observations": len(win_triggers),
            "first_quote_decisions": len(win_decisions),
            "ready_offered": len(win_signal_ids),
            "fillable": sum(1 for o in issued if o.fillable),
            "simulated_filled": sum(1 for o in issued if o.fillable),
            "missed_data_gap": sum(
                1 for e in win_decisions if e.kind is SignalEventKind.MISSED_DATA_GAP
            ),
            "missed_price_chase": sum(
                1 for e in win_decisions if e.kind is SignalEventKind.MISSED_PRICE_CHASE
            ),
            "not_issued": sum(1 for e in win_decisions if e.kind is SignalEventKind.NOT_ISSUED),
            "pre_roll_ready_history": preroll_ready,
        },
        "not_issued_reasons": dict(sorted(reasons.items())),
        "ready_final_states": dict(sorted(final_states.items())),
        "execution_blocks": sum(
            1
            for e in eng.events
            if e.kind is SignalEventKind.EXECUTION_BLOCKED and in_window(e.decision_time_ms)
        ),
        "simulated_outcomes": _outcome_block(issued, cost_known),
        "rejected_counterfactual": {
            **_outcome_block(rejected, cost_known),
            "not_evaluable": len(not_issued) - len(rejected),
            "label": "COUNTERFACTUAL — rejected setups under the same plan/fill/exit rules; "
            "not executed, not guaranteed",
        },
        "days": {
            "covered": len(days),
            "with_ready": sum(1 for n in days.values() if n),
            "zero_opportunity": sum(1 for n in days.values() if n == 0),
            "per_day_ready": dict(sorted(days.items())),
        },
        "assumptions": {
            "entry_scenario": (
                "ZERO_DELAY_AT_FIRST_QUOTE"
                if cfg.entry_delay_ms == 0
                else f"DECLARED_DELAY_{cfg.entry_delay_ms}MS"
            ),
            "exit_policy": "FULL_POSITION_AT_TP2_OR_SL (TP1 informational only)",
            "fill_prices": "long ASK entry / BID exit; short BID entry / ASK exit; "
            "never at a candle close",
            "stop_gaps": "stop fills at the worse actual price when gapped through",
            "unknown_order": "data gap while open => INDETERMINATE",
            "costs": "DECLARED" if cost_known else "UNKNOWN: gross research results only",
            "contract": "UNKNOWN: no currency P/L, no lot sizing",
            "max_quote_age_ms": p.health.max_quote_age_ms,
            "max_first_postclose_delay_ms": p.health.max_first_postclose_delay_ms,
            "price_step": None if p.price_step is None else str(p.price_step),
            "max_spread": None if p.max_spread is None else str(p.max_spread),
            "unset_thresholds_block_ready": True,
            "probability_or_win_rate": "NOT CLAIMED",
        },
    }
