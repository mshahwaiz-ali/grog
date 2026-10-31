# R0 Acceptance Audit — Findings, Execution Plan and Evidence Record

**Topic owner:** the independent R0 (M00–M08) acceptance audit: baseline evidence, confirmed findings with source locations, the bounded fix plan and the final verification record. **It defines no trading, UX, data or architecture rule** — those remain owned by [02](02-workflows-and-ux.md)–[09](09-architecture.md) and approvals by [11](11-decisions.md). When a finding changes a contract, the owning document is edited and this record only links to it.

**Status:** IN PROGRESS (opened 2026-10-31). Implementation of M00–M08 exists; **R0 is not VALIDATED by this record** until every phase below has executed evidence. Nothing here is evidence of strategy profitability, live-data readiness or broker-verified fills.

## 1. Baseline (Phase A)

| Item | Value |
| --- | --- |
| Audited commit | `dca9ee3` (main, "feat(journal): wire manual-journal forms, position monitoring and restart reconciliation into the workstation") |
| Environment | Python 3.11 via `uv sync --locked` (16 packages resolved, lockfile unchanged), Textual 8.2.8, rich 15.0.0, SQLite migrations 0001–0003 |
| `uv run pytest -q` | **439 passed**, 0 failed, 112.68 s |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 97 files already formatted |
| Failures at baseline | none |
| Rendered UI evidence | earlier PNG/SVG captures (outside the repo) at 120×34 and 80×24; none at 70×18 |

Conservative decisions already in force and **kept** by this audit: OPEN thresholds stay unset (feed health `UNKNOWN`, default config issues no READY); SQ-17 grace recovery not implemented; H1 invalidation while READY follows the stricter [05 §8](05-strategies.md) wording (conflict with [06 §5](06-signals-and-scoring.md) still OPEN with the owner); replay has only the zero-delay entry scenario; operator skips are stored in `signal_decisions`; no journal correction event; `TP1 APPROACHING` not emitted (distance threshold OPEN).

## 2. Confirmed findings

Each finding was reproduced against `dca9ee3` (probe script or code reading noted) before any change. "Fix" lists the planned bounded change; §4 records the commit and regression test that closed it.

| ID | Area | Finding (source location at `dca9ee3`) | Planned fix |
| --- | --- | --- | --- |
| F-01 | B1 exposure | Live "ACTIONABLE PROPOSALS" lists a READY signal that is already ENTERED or USER_SKIPPED in the local journal as a fresh opportunity (`ui/panels.py` `proposals_panel`, called from `ui/app.py` `_render_all`). Reproduced: record an on-plan entry, the panel still shows `READY TTL 4m59s`. | Operator status overlay passed to the panel; acted-on signals move to a "Recorded" line, never the actionable list. Signal record untouched. |
| F-02 | B1/B5 labels | Signals table replaces the engine state with the journal status (`ui/panels.py` `ready_rows`: `operator.get(id, state_label(v))`), hiding EXPIRED / INVALIDATED / EXECUTION BLOCKED once a signal is entered or skipped. | Show both lanes: engine state and operator status, e.g. `ENTERED · EXPIRED`. |
| F-03 | B1 exposure | No overlap/exposure information anywhere: a new READY (or the Record Entry form) does not mention locally recorded open positions. | Factual warning (`n open local position(s), same/opposite side; overlap policy OPEN`) on Live, Signals detail and Record Entry. **No automatic limit** (docs/11 §6.3 stays OPEN). |
| F-04 | B2 monitoring | Marks look fresh unless feed status is exactly `STALE` (`ui/manual.py` `_stale`; `journal/positions.py` `mark_position`). With the default UNKNOWN feed, DEGRADED gaps, declared closures, NO_DATA or REPLAY ENDED the closeable mark and R are shown unqualified; the Live positions panel never passes staleness at all. | `Mark.freshness` (FRESH / UNVERIFIED / STALE / DEGRADED / MARKET_CLOSED / OFFLINE / REPLAY_ENDED / UNAVAILABLE) computed in the journal layer; every view shows it next to the mark. Touches stay observations only. |
| F-05 | B2 diagnostics | `DIAG_LABEL` maps feed `UNKNOWN` and `STALE` to `DEGRADED` (`ui/panels.py`), and Diagnostics replaces the feed status with `REPLAY_PAUSED` while paused, so an unverified feed reads as a degraded one or disappears. | Separate *feed* status (FRESH/UNKNOWN/STALE/DEGRADED/MARKET_CLOSED/OFFLINE) from *playback* status; add `NOT CONFIGURED` for unset thresholds ([02 §8](02-workflows-and-ux.md) updated first). |
| F-06 | B3 integrity | Check-before-transaction races in `journal/positions.py`: `record_entry` and `record_skip` check `signal_status` and the action-ID dedupe outside the write transaction; `_exit`, `record_modify`, `confirm_open` validate open state, remaining quantity and next sequence outside it; `restore_on_startup` likewise. Two writers can record ENTERED and USER_SKIPPED (or two entries) for one signal; a concurrent stale `CLOSE` can leave a position open; a concurrent identical resubmission reports `NOT_SAVED` although the action was saved. Schema 0003 has no cross-table uniqueness for the first operator action on a signal. | New append-only migration 0004 `signal_operator_actions` (PK source+signal, backfilled from existing rows, never deleting anything); every validation and the dedupe re-check run inside `BEGIN IMMEDIATE`; two-connection race tests and failure-recovery tests. |
| F-07 | B4 R | Different denominators under the same "R" label: `Mark.unrealized_r` is per-unit move / initial risk, `ManualPosition.realized_r` is realized price units / (initial risk × initial qty); the Positions table column is just `R`. No remaining-position unrealized R or total is available after a partial close. | One explicit breakdown (`r_breakdown`): gross move per unit, per-unit risk, original full-position risk, move R per unit, realized R and unrealized remaining-position R on the full-position basis, total gross R, net R / currency `UNKNOWN` without contract and fees. Labels state the denominator. |
| F-08 | B5 detail | Signal detail of a READY signal currently `EXECUTION BLOCKED` prints `Eligibility: PASS` and `Action: [e] Record … [s] Skip` (`ui/panels.py` `signal_detail`); terminal and already-acted signals also advertise `[e]/[s]`. Original issuance vs current state is not separated. | Two explicit lines: *Issued* READY (immutable, eligibility at issuance) and *Now* (READY / EXECUTION BLOCKED with reasons / terminal, never resurrected); action hints only when the action is actually allowed. |
| F-09 | B6 identity | Run identity uses only the package version as `code_version` (`replay/runner.py` `run_identity`). Changing engine code without a version bump reuses the persisted run ID, so the deterministic re-verification either rejects a legitimate rerun as "nondeterministic" or silently reuses an incompatible COMPLETE run. | Add `engine_code_hash` (SHA-256 over the engine package sources that decide signals/outcomes) to the run key and stored `code_version`. Old runs stay untouched; new code gets a new run ID. |
| F-10 | B6 window | Window membership uses quote provider time for quote counts but event decision (received) time for event/outcome membership (`replay/runner.py` `run_replay` / `_summarize`). Only matters for a quote straddling `--from`; documented and pinned by a test, no trading-rule change. | Document in [08](08-validation.md); boundary tests for `--from` / `--to`, exits after `--to` (no lookahead), gap → INDETERMINATE, counterfactual labeling. |
| F-11 | Docs | Status wording is stale: README ("M00–M07 implemented … manual journal arrives in M08", "application is not yet built"), [00](00-index.md) ("NOT implemented", "no code has been written"), [10](10-roadmap.md) ("documentation-only"), [09](09-architecture.md) header, [11 §12](11-decisions.md) ("SOFTWARE NOT BUILT"). | Phase E corrections; roadmap progress table that separates IMPLEMENTED from VALIDATED. |
| F-12 | UX | Long wrapped lines, weak hierarchy, identifier noise, cramped modals, wasted space; Journal mixes SIMULATED session events and operator records in one table with no lane filter; Diagnostics is an unstructured dump; no 70×18 evidence. | Phase C redesign (visual system in [02](02-workflows-and-ux.md) first). |

## 3. Execution plan

Strictly sequential A → B → C → D → E, small verified commits on `main`, local tests only (no GitHub Actions).

1. **A** — this record, roadmap progress table, index registration.
2. **B** — one commit per finding group, each with a focused regression test that fails on `dca9ee3` behavior: B3 (F-06) → B1 (F-01..03) → B5 (F-08) → B2 (F-04/05) → B4 (F-07) → B6 (F-09/10).
3. **C** — visual system in [02](02-workflows-and-ux.md); then views (Live, Signals, Positions, Journal, Diagnostics), modals, responsive 120×34 / 80×24 / 70×18 Pilot tests and rendered screenshots.
4. **D** — end-to-end Pilot + journal acceptance test over the deterministic synthetic fixture with test-only declared thresholds.
5. **E** — README/index/02/07/08/09/10/11 updates, M09 plan, M10 prerequisites, final evidence in §4–§6 below.

## 4. Fix and verification log

Filled as commits land (short SHA → test that proves it).

| Finding | Commit | Regression evidence |
| --- | --- | --- |
| — | — | — |

## 5. Final verification

Pending.

## 6. Remaining limitations

Pending.
