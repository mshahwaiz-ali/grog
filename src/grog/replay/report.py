"""Plain-text evidence report for a stored research run (docs/02 Section 13, docs/08 §13.2).

Every report carries REPLAY / SIMULATED labels, data fidelity, unset thresholds and
assumptions. It never states a probability, win rate or expected profit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from grog.journal.research import RunRow


def _utc(ms: int | None) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _r(block: dict[str, Any] | str) -> str:
    if isinstance(block, str):
        return block
    if not block["resolved"]:
        return "no resolved outcomes"
    return f"{block['total_r']} R total over {block['resolved']} (mean {block['mean_r']} R)"


def render_text(run: RunRow, comparable: list[RunRow]) -> str:
    res = run.result or {}
    s = res.get("summary", {})
    w, q, f, a = s["window"], s["quotes"], s["funnel"], s["assumptions"]
    so, rc, days = s["simulated_outcomes"], s["rejected_counterfactual"], s["days"]
    synthetic = s["source_origins"] == ["SYNTHETIC"]
    lines = [
        f"GROG / REPORT    MODE: REPLAY  FIDELITY: SIMULATED  RUN: {run.run_id}",
        f"Source: {s['source_id']}  Origin: {','.join(s['source_origins']) or '-'}  "
        f"Data sha256: {run.data_hash[:16]}  Config: {run.config_hash[:12]}  "
        f"Code: {run.code_version}",
        f"Window UTC: {_utc(w['from_ms'])} .. {_utc(w['to_ms'])}  "
        f"(quotes {_utc(w['first_quote_ms'])} .. {_utc(w['last_quote_ms'])})",
        "BANNER: REPLAY — SIMULATED research evidence, not live trading, not a real fill, "
        "not a broker result."
        + (" SYNTHETIC data: no market-performance claim." if synthetic else ""),
        f"Quotes: {q['processed']} processed | {q['pre_roll']} pre-roll (history only) | "
        f"{q['in_window']} in window",
        "Bars: " + "  ".join(f"{k} {v}" for k, v in s["bars"].items()),
        f"Data gaps (M1): {s['data_gaps']['data_gap']} DATA_GAP, "
        f"{s['data_gaps']['market_closed']} MARKET_CLOSED, "
        f"{s['data_gaps']['missing_m1_buckets']} missing M1 buckets",
        f"Funnel: triggers {f['trigger_observations']} -> first-quote decisions "
        f"{f['first_quote_decisions']} -> READY {f['ready_offered']} -> fillable "
        f"{f['fillable']} -> simulated filled {f['simulated_filled']}",
        f"Missed: data gap {f['missed_data_gap']}  price chase {f['missed_price_chase']}  "
        f"not issued {f['not_issued']}  (pre-roll READY history excluded: "
        f"{f['pre_roll_ready_history']})",
        "Not-issued reasons: "
        + (", ".join(f"{k} {v}" for k, v in s["not_issued_reasons"].items()) or "none"),
        f"Execution blocks: {s['execution_blocks']}  READY final states: "
        + (", ".join(f"{k} {v}" for k, v in s["ready_final_states"].items()) or "none"),
        "Simulated outcomes (READY): "
        + (", ".join(f"{k} {v}" for k, v in so["outcomes"].items()) or "none")
        + f"  TP1-only touches {so['tp1_touched_without_tp2']}",
        f"  Gross: {_r(so['gross'])}",
        f"  Net:   {_r(so['net'])}",
        "Rejected setups (COUNTERFACTUAL, not executed): "
        + (", ".join(f"{k} {v}" for k, v in rc["outcomes"].items()) or "none")
        + f"  not evaluable {rc['not_evaluable']}",
        f"  Gross: {_r(rc['gross'])}",
        f"Days: {days['covered']} covered | {days['with_ready']} with READY | "
        f"{days['zero_opportunity']} zero-opportunity",
        "Assumptions: "
        + "; ".join(
            [
                f"entry {a['entry_scenario']}",
                a["exit_policy"],
                a["fill_prices"],
                a["stop_gaps"],
                a["unknown_order"],
                f"costs {a['costs']}",
                f"contract {a['contract']}",
            ]
        ),
        "Thresholds: "
        + "  ".join(
            f"{k}={'UNSET' if a[k] is None else a[k]}"
            for k in (
                "max_quote_age_ms",
                "max_first_postclose_delay_ms",
                "price_step",
                "max_spread",
            )
        )
        + "  (unset hard thresholds block READY)",
        "Probability / win rate: NOT CLAIMED. Small samples are not evidence of an edge.",
    ]
    if comparable:
        lines.append(
            f"Dataset reuse: {len(comparable)} other completed run(s) on the same data and "
            "window with different config/params: "
            + ", ".join(f"{r.run_id} (config {r.config_hash[:12]})" for r in comparable)
            + " — repeated testing on one dataset inflates apparent results."
        )
    else:
        lines.append("Dataset reuse: none recorded for this data and window.")
    return "\n".join(lines) + "\n"
