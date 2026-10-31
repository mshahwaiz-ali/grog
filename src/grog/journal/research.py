"""Persistence of research replay runs (docs/09 Section 7; docs/08 Section 10).

* One ``research_runs`` row per deterministic run identity. ``RUNNING`` rows carry a
  processed-quote watermark updated at chunked checkpoints; ``COMPLETE`` rows are immutable.
* ``signal_events`` is append-only with a unique ``dedupe_key``: a restarted (or repeated)
  run recomputes deterministically and every event it re-derives must match the stored row
  byte for byte; otherwise the run is rejected as nondeterministic. Nothing is double
  counted.
* Everything here is ``SIMULATED`` research evidence, never a real trade.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grog.domain.ids import canonical_json
from grog.journal.store import Store
from grog.strategies.s1_pullback import record_to_dict


class ResearchStoreError(Exception):
    """A stored run disagrees with a deterministic recomputation."""


@dataclass(frozen=True, slots=True)
class RunRow:
    run_id: str
    source_id: str
    code_version: str
    config_hash: str
    data_hash: str
    params_hash: str
    window_from_ms: int | None
    window_to_ms: int | None
    status: str
    processed_quotes: int
    result: dict[str, Any] | None


def _row(r: sqlite3.Row) -> RunRow:
    return RunRow(
        r["run_id"],
        r["source_id"],
        r["code_version"],
        r["config_hash"],
        r["data_hash"],
        r["params_hash"],
        r["window_from_ms"],
        r["window_to_ms"],
        r["status"],
        r["processed_quotes"],
        None if r["result_json"] is None else json.loads(r["result_json"]),
    )


def _params_hash(key: dict[str, Any]) -> str:
    return f"{key['strategy_hash']}/{key['signal_hash']}"


def get_run(conn: sqlite3.Connection, run_id: str) -> RunRow | None:
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM research_runs WHERE run_id = ?", (run_id,)).fetchone()
    return None if r is None else _row(r)


def comparable_runs(conn: sqlite3.Connection, run: RunRow) -> list[RunRow]:
    """Other completed runs on the same data and window (ADV-08 reuse disclosure)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM research_runs WHERE data_hash = ? AND window_from_ms IS ? "
        "AND window_to_ms IS ? AND run_id != ? AND status = 'COMPLETE' ORDER BY run_id",
        (run.data_hash, run.window_from_ms, run.window_to_ms, run.run_id),
    )
    return [_row(r) for r in rows]


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Read-only connection for reports; never creates or migrates a database."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _event_rows(run_id: str, s1_events: Iterable[Any], signal_events: Iterable[Any]):
    for prefix, events in (("S1", s1_events), ("SIG", signal_events)):
        for e in events:
            payload = canonical_json(record_to_dict(e))
            yield (
                f"{run_id}:{prefix}:{e.sequence}",
                run_id,
                getattr(e, "signal_id", None),
                f"{prefix}:{e.kind.value}",
                e.decision_time_ms,
                e.decision_time_ms,  # virtual replay clock, never wall time
                canonical_json([r.value for r in e.reason_codes]),
                payload,
                f"{run_id}:{prefix}:{e.event_id}",
            )


class ResearchStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def begin(self, run_id: str, key: dict[str, Any]) -> RunRow | None:
        """Create the RUNNING row if absent; return the existing row (for resume/verify)."""
        with self.store.transaction() as conn:
            existing = get_run(conn, run_id)
            if existing is not None:
                return existing
            conn.execute(
                "INSERT INTO research_runs (run_id, source_id, code_version, config_hash,"
                " data_hash, params_hash, run_key_json, window_from_ms, window_to_ms,"
                " source_fidelity, status, processed_quotes, created_at_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,'SIMULATED','RUNNING',0,?)",
                (
                    run_id,
                    key["source_id"],
                    key["code_version"],
                    key["config_hash"],
                    key["data_hash"],
                    _params_hash(key),
                    canonical_json(key),
                    key["from_ms"],
                    key["to_ms"],
                    self.store.now_ms(),
                ),
            )
        return None

    def _append(self, conn: sqlite3.Connection, rows: Sequence[tuple]) -> int:
        added = 0
        for row in rows:
            cur = conn.execute(
                "INSERT INTO signal_events (event_id, run_id, signal_id, event_type,"
                " effective_at_ms, recorded_at_ms, reason_codes_json, payload_json, dedupe_key)"
                " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (dedupe_key) DO NOTHING",
                row,
            )
            if cur.rowcount:
                added += 1
                continue
            stored = conn.execute(
                "SELECT event_id, payload_json FROM signal_events WHERE dedupe_key = ?",
                (row[8],),
            ).fetchone()
            if stored is None or tuple(stored) != (row[0], row[7]):
                raise ResearchStoreError(
                    f"replay is not deterministic: stored event {row[8]} differs"
                )
        return added

    def checkpoint(self, run_id: str, processed: int, s1_events, signal_events) -> int:
        """Commit newly derived events and advance the watermark (one transaction).

        Re-derived events must equal stored rows; on a COMPLETE run nothing new may appear.
        """
        with self.store.transaction() as conn:
            run = get_run(conn, run_id)
            if run is None:
                raise ResearchStoreError(f"run {run_id} was not begun")
            added = self._append(conn, list(_event_rows(run_id, s1_events, signal_events)))
            if run.status == "COMPLETE":
                if added:
                    raise ResearchStoreError(
                        f"replay is not deterministic: {run_id} derived unrecorded events"
                    )
                return 0
            conn.execute(
                "UPDATE research_runs SET processed_quotes = MAX(processed_quotes, ?)"
                " WHERE run_id = ?",
                (processed, run_id),
            )
        return added

    def complete(self, result) -> RunRow:  # result: grog.replay.runner.ReplayResult
        """Persist the final signals, remaining events and summary; idempotent."""
        result_json = canonical_json(result_to_dict(result))
        with self.store.transaction() as conn:
            run = get_run(conn, result.run_id)
            if run is None:
                raise ResearchStoreError(f"run {result.run_id} was not begun")
            if run.status == "COMPLETE":
                stored = conn.execute(
                    "SELECT result_json FROM research_runs WHERE run_id = ?", (result.run_id,)
                ).fetchone()[0]
                if stored != result_json:
                    raise ResearchStoreError(
                        f"replay is not deterministic: stored result for {result.run_id} differs"
                    )
            self._append(
                conn, list(_event_rows(result.run_id, result.s1_events, result.signal_events))
            )
            for sig in result.signals:
                plan = canonical_json(record_to_dict(sig))
                state = result.final_states[sig.signal_id]
                existing = conn.execute(
                    "SELECT immutable_plan_json, current_state FROM signal_records"
                    " WHERE run_id = ? AND signal_id = ?",
                    (result.run_id, sig.signal_id),
                ).fetchone()
                if existing is not None:
                    if tuple(existing) != (plan, state):
                        raise ResearchStoreError(f"signal {sig.signal_id} differs from stored")
                    continue
                conn.execute(
                    "INSERT INTO signal_records (run_id, signal_id, pair_key, version, side,"
                    " first_ready_ms, immutable_plan_json, current_state, expires_ms)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        result.run_id,
                        sig.signal_id,
                        result.pair_ids[sig.signal_id],
                        sig.strategy_version,
                        sig.side.value,
                        sig.first_ready_ms,
                        plan,
                        state,
                        sig.expiry_ms,
                    ),
                )
            if run.status != "COMPLETE":
                conn.execute(
                    "UPDATE research_runs SET status = 'COMPLETE', processed_quotes = ?,"
                    " result_json = ?, completed_at_ms = ? WHERE run_id = ?",
                    (result.processed_quotes, result_json, self.store.now_ms(), result.run_id),
                )
            return get_run(conn, result.run_id)


def result_to_dict(result) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "run_key": result.run_key,
        "summary": result.summary,
        "outcomes": [record_to_dict(o) for o in result.outcomes],
    }
