# Grok Build Roadmap — Exact Milestones, Tests and Handoffs

**Updated:** 2026-10-31  
**Status:** R0 (M00–M08) **IMPLEMENTED and acceptance-audited** (verdict CONDITIONAL, see [14](14-r0-acceptance-audit.md) §5); M09 is BLOCKED on external permission and M10 is data/evidence-gated (plans in §9 and §10 below). **real broker connectivity, live trade-risk limits, performance thresholds and profitability cannot be finalized without actual data**. Implementation status is tracked factually in Section 8 below (implemented is not the same as validated).

**One rule:** Grok is the **external implementation bot**. Grog's running software contains **NO agent/LLM/autonomous broker execution**. Use `main` only, direct Git commits, local tests, no GitHub Actions. Work solely in Grog repo and test directories; no production systems.

**Canonical source of truth:** [00 — Index](00-index.md) → [11 — Decisions](11-decisions.md) → [09 — Architecture](09-architecture.md) → this milestone sequence → owning topic specs [02–08](00-index.md). Historical archive is **not** executable instruction.

## 1. What "start the project" authorizes

When the user tells Grok: **"Start Grog. Follow AGENTS.md and docs/00-index.md, then work through docs/10-roadmap.md."**, Grok may implement **M00 through M08 sequentially** in this private Grog repository, including safe local tests and direct commits to `main`, without repeating planning questions already answered in the documents.

- **Proceed without asking** for each small implementation step *when the step is specified, non-destructive, local-only and testable*.
- **Stop and report** only on genuine missing external authorization (e.g. live MT5 demo account, installing Wine, credential access), conflict between canonical docs, inability to validate a safety-critical assumption, repository write permissions or potentially destructive actions. Do not invent values to get around blockers.
- If a later **MT5 live source** milestone is blocked by access/installation, **finish all independent offline milestones**, retain a clean read-only adapter boundary, label the live milestone BLOCKED and provide the exact missing external prerequisite. Do not silently skip test failures or pretend live quotes are connected.
- No auto-trading module, live-account broker write API, wallet, server infrastructure, cloud AI, web dashboard or GitHub Actions workflow.
- Preserve existing docs, branch and research status. Commit tests and source together after each milestone; no force push, no delete/reset commands on user data or production.

## 2. Release definitions

- **R0 — Offline research workstation (M00–M08):** one deterministic synthetic/offline quote source, MTF analysis, research-only S1, honest BID/ASK and simulated-entry outputs, local journal and Textual terminal. No claims of profitable live signals.
- **R1 — MT5 reference-connected workstation (M09 when independently authorized):** validated read-only demo/reference data, fresh quote monitoring and **indicative** setups. Actual execution broker may remain undecided; no guaranteed fill or account P/L.
- **R2 — Evidence-gated decision-support (M10, later):** data fidelity and out-of-sample walk-forward/forward-paper validation, broker-specific execution assumptions and *separately approved* empirical improvements. Not an auto-trader.
- **S2/S3 strategies:** later research separate from R0; do not automatically implement to make release look bigger.

**R0 can be built now without a broker or MT5 installation.**

## 3. Exact implementation order — one milestone at a time

### M00 — Repository skeleton and reproducible local environment

**Read:** [01](01-product-vision.md), [09](09-architecture.md), [11](11-decisions.md).  
**Create:** `pyproject.toml`, `.python-version` (3.11), `uv.lock`, `.gitignore`, `src/grog/__init__.py`, `src/grog/__main__.py`, `src/grog/cli.py`, `src/grog/settings.py`, `config/research.example.toml`, `tests/` setup only. Use specified Python 3.11, `uv`, `pytest`, `ruff`, Textual as eventual UI dependency. Choose a supported Textual version by actual dependency resolution, then lock it. No imported real broker account.

**Implement:** `grog --help`, `grog version`, a read-only `grog doctor`, config validation, runtime state-dir injection. Unknown/unimplemented commands must not masquerade as working. Sample configs have NO secrets, no trade execution. .gitignore local state, .venv, logs, raw quote history, keys, user config and `.scratch`.

**Tests:** package import, entry point, settings rejects unknown mode/invalid timestamps/unset live security policies, `doctor` doesn't connect to broker or write user home by default. Check `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`.  
**Done:** clean install from locked deps and CLI help/doctor. **Commit:** `build: bootstrap Grog offline Python project`.

### M01 — Quote models, strict importer and durable source catalog

**Read:** [03](03-market-data.md) Sections 1–10, [09](09-architecture.md) Sections 3,6,7, [08](08-validation.md) MD fixtures.  
**Implement:** `NormalizedQuote`, strict canonical CSV v1, exact Decimal parsing, UTC ms, stable source+row identity, source origin, validation error codes, checksum and atomic batch import; SQLite catalog/migration 0001 for sources/batches and minimal reusable storage API. Output counts, accepted/rejected, gaps/data fidelity. No strategy signals.

**Tests:** MD-01/02/03/04/05/13/14/19/22 where applicable; negative CSV rows, mixed same-ms quotes, duplicate idempotent import, re-open after interrupted import, SQLite transaction rollback. Use `tmp_path`, no real credentials or real-world data assumptions.  
**Done:** one synthetic CSV can be imported twice with **exactly one** durable batch; corrected/invalid files do not corrupt catalog. **Commit:** `feat(data): add causal quote schema and offline importer`.

### M02 — Causal M1/M5/M15/H1 candle aggregation and feed health

**Read:** [03](03-market-data.md), [04](04-analysis-engine.md) Sections 2–3, [08](08-validation.md).  
**Implement:** UTC half-open timeframe buckets from source-specific ordered BID/ASK ticks, close/available_at records, last closed bar selection, no synthetic empty bars, gap flags, healthy/stale/closed differentiation, virtual REPLAY clock. No pivot/strategy code yet.

**Tests:** MD-03/04/05/06/07/08/09/10/13/17/20/21/22; exact 10:05 candle boundary; reconnect backfill can't produce on-time READY; no future H1/M15 from current H1.  
**Done:** same bytes produce identical 4-timeframe bars, timestamps and gaps on two replays. **Commit:** `feat(data): build causal multi-timeframe bars and health states`.

### M03 — Pure market analysis: EMA, ATR, confirmed pivots, H1/M15 context

**Read:** [04](04-analysis-engine.md) and [08](08-validation.md) I0–I8 research definitions.  
**Implement:** pure EMA/ATR recurrence (frozen seed/warm-up), confirmed M5/M15 2-left/2-right pivots, H1 UP/DOWN/NEUTRAL/UNKNOWN, M15 SUPPORTIVE/CORRECTIVE/OPPOSING/UNKNOWN. Version research parameter set `S1_RESEARCH_V0_2`, use documented **proposed** parameters **for offline experiments only**. UNKNOWN remains explicit.

**Tests:** pivot appears after k+2 finalized, equality/ties, ATR zero, EMA insufficient history, H1 unclosed reversal, M15 corrective allowed, BID/ASK source provenance, replay equivalence and deterministic stress fixtures.  
**Done:** all indicators compare to independent reference calculations using **the same initialization convention**, documented. **Commit:** `feat(analysis): add no-lookahead MTF context and indicators`.

### M04 — S1 research-only impulse, pullback and trigger detector

**Read:** [05](05-strategies.md), [04](04-analysis-engine.md), [08](08-validation.md) S1 tests.  
**Implement:** frozen L/H pair identity, at most one FORMING per side, M5 impulse/pullback, P update (including completed trigger bar), H1 direction, M15 observation, closed-bar trigger, supersession/invalidation and reason codes. No guessed RSI/ADX/score. **Research profile:** exact v0.2 values in canonical docs are allowed for **synthetic and offline** simulated comparisons, not evidence of live edge.

**Tests:** S1-01/02/03/04/05/06/07/17/18/19/20; BUY/SELL symmetry, same-ms and DST/gap cases, no future lookahead, at most one candidate per pair.  
**Done:** deterministic output includes forming/invalidated/trigger observations with explicit UTC availability. **Commit:** `feat(strategy): implement deterministic research S1 detector`.

### M05 — Signal eligibility + price-side risk-plan mathematics

**Read:** [06](06-signals-and-scoring.md), [07](07-risk-and-monitoring.md), [03](03-market-data.md), [08](08-validation.md) SQ/ADV/MD cases.  
**Implement:** first actual post-trigger quote, original E0/SL/TP1/TP2 and gross R, immutable SignalRecord, READY/current BLOCKED overlay, fixed TTL, no-chase research bounds, stop pre-touch, duplicate prevention. All missing **execution-broker** costs/contract sizing are `UNKNOWN` and **do not get invented**. For offline profile, label `SIMULATED`; if an actual live policy gate isn't configured, never label price as broker verified. Do **NOT** implement the uncalibrated 100-point score or win probability.

**Tests:** S1-08..18, SQ-01..18, ADV-03/05/09/10/11, MD-15..18/21. Same signal ID on reactivation, no past-close imaginary fills, spread counted exactly once in ASK/BID economics, no optimistic stop-first ambiguity.  
**Done:** fixture replay emits understandable, bounded simulated READY/WAIT states and correct original trade levels, no monetary lot sizing without contract. **Commit:** `feat(signals): add replay-safe eligibility and reference trade plans`.

### M06 — Deterministic replay, source-quality and performance reports

**Read:** [08](08-validation.md) Section 1–14, [07](07-risk-and-monitoring.md), [09](09-architecture.md) SQLite/run records.  
**Implement:** `grog replay`, `grog report`, synthetic generator for **long enough** complete EMA/ATR warm-up (no real market claim), frozen run/config/data hashes, offered vs fillable vs simulated-filled counts, simple full-position-at-TP2-or-SL outcome model using ordered ticks. If unknown fill/SL/TP order, classify INDETERMINATE. Report net-R **only when costs/contract are known**; otherwise report gross-research outcomes clearly labeled. No optimized score/threshold selection yet.

**Tests:** identical replay twice, interrupted replay/restart event idempotency, no double-counted signals/fees, outcome order on real ordered synthetic BID/ASK ticks, false paper execution at candle-close prohibited, sample-days with zero opportunities and rejected-winner accounting.  
**Done:** one command emits a research report with source/mode/assumption banners and no fabricated win-rate claim. **Commit:** `feat(replay): add deterministic replay and evidence reports`.

### M07 — Premium Textual terminal workstation (view-only first)

**Read:** [02](02-workflows-and-ux.md) all twelve sections; [06](06-signals-and-scoring.md); [09](09-architecture.md).  
**Implement:** terminal shell and five views (Live, Signals, Positions, Journal, Diagnostics), responsive dark palette, source/time badge, H1/M15/M5 panel, FORMING vs READY separation, event strip, exact keyboard actions for navigation/details, compact terminal fallback and status/empty/error states. Use **real engine snapshots from synthetic replay**; never hardcode a winning 'demo signal' as output or display '85% confidence'.

**Tests:** Textual Pilot/navigation, stale/empty/replay-ended, **REPLAY starts paused and pre-rolls real historical lookback without lookahead**, Space/. play/step and +/- event-rate controls, 120×34 and 80×24 layouts, focused input prevents global hotkeys, no UI refresh changes expiry, no broker orders.  
**Done:** `grog ui --mode replay --source-id ID` provides working interactive workstation; command performs no broker writes. **Commit:** `feat(ui): ship responsive offline research workstation`.

### M08 — Local manual-fill journal, position monitoring and restart recovery

**Read:** [02](02-workflows-and-ux.md) modal contracts, [07](07-risk-and-monitoring.md), [09](09-architecture.md) SQLite schema.  
**Implement:** local record-entry (READY and explicitly OFF_PLAN unlinked manual trades), skip, partial, modify, close modals + transactional append-only `position_events`, reopen/reconcile on restart, closeable BID/ASK P/L where metadata complete, correct UNKNOWN states where not, no assumed broker fill on quote touch. UI actions only call validated journal domain services.

**Tests:** duplicate keypress/action idempotency, missing/negative amount, quantity > remaining, late/off-plan/unlinked manual fill changes actual R but not original signal, partial/close correct remaining, no fee fabricated, restart shows RECONCILIATION_REQUIRED, DB lock rollbacks. Include [08](08-validation.md) UI-21.  
**Done:** user can manually record simulated/external positions, see clearly labeled metrics and safely reopen program without losing events. **Commit:** `feat(journal): add verified manual-position records and reconciliation`.

### M09 — Read-only MT5 reference adapter (external access needed later)

**NOT a blocker for R0.** Read [03](03-market-data.md), [09](09-architecture.md) MT5 adapter contract, [08](08-validation.md) MD-11/12/19/22. Only after specific user approval to install/connect external runtime and demo server.

**Implement when authorized:** small read-only MQL5 bridge/exporter via Wine MT5, timestamped broker/demo XAUUSD tick history, bounded `CopyTicksRange` catch-up rather than assuming every `OnTick` is delivered, source health, dedup/cursors and reconnection. No order submission calls in any source. Feed adapter output obeys exactly the NormalizedQuote interface; core engine/strategies do not change.

**Tests:** live reference quote validation, transient disconnection/reconnect, no retroactive live READY on backfill, prove no trade/order API call, source metadata exact.  
**Done:** same TUI works with `REFERENCE_LIVE` source tag and warns `INDICATIVE`; if demo platform is not available, mark **BLOCKED: demo access/install authorization missing**, keep R0 usable. **Commit:** `feat(feed): integrate read-only MT5 demo reference data`.

### M10 — Validation and empirical strategy refinement (data/evidence-gated)

**Cannot be completed from synthetic fixtures alone.** Use genuine permitted broker/reference tick history and recorded execution assumptions. Run [08](08-validation.md) I0–I8 indicator comparisons, walk-forward OOS, realistic spread/delay, rejected winners, net R/drawdown/frequency and paper forward trial.

Only promote a variant if it materially improves actual out-of-sample net trading decisions under pre-registered criteria. **Do not optimize on final holdout; never claim 90% win rate or guarantee.** Without suitable data, report **UNVALIDATED** with what is missing; don't fake metrics.

## 4. QA gates shared by every milestone

- No code imports from a future implementation into an earlier layer; pure engine **never** depends on Textual, sqlite3 or MT5.
- No AI/LLM/cloud API, wallet, trade placement, order modification, copy trading or additional assets.
- Every emitted decision includes a source, source fidelity, timestamp, rule version and **why**.
- Never use unconfirmed bars/pivots, imaginary 5m close fills, guessed spreads/lots, future event calendars or fabricated outcomes.
- At least one **positive**, one **negative**, one **boundary** and one **restart/idempotency** test for any new stateful behavior.
- Running locally: `uv sync --locked`, `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`. Pin actual versions only by lockfile. Document known warnings/failures, do not claim passed tests that were not run.
- GitHub Actions: **DO NOT create, enable or trigger** workflows. Tests run locally or in authorized ephemeral test environment only, with no production access.
- After milestone: stage only intended files, review diff, commit on `main`, push if authorized; read result back. Do not force push, reset/delete, or rewrite history. If working tree was already dirty, isolate changes without overwriting.
- **Documentation hygiene:** update the correct canonical topic only when implementation exposes an issue. No `18-...` `19-...` file proliferation or conflicting copied formulas. Add docs archive snapshots only when a revision is truly superseded and history alone is insufficient.

## 5. Grok required progress report after each milestone

Use this **compact format**:

```text
GROG | Milestone M0X | PASS / BLOCKED / FAILED
Commit: <SHA> (main)
Files: <created/changed>
Contracts implemented: <docs and section numbers>
Checks: pytest <N pass/N fail>; ruff <pass/fail>; manual demo <result>
Safety: no orders, no AI, no GitHub Actions, no production changes
Evidence: <fixture names, source fidelity, artifacts if any>
Known OPEN items: <brief; don't invent solutions>
Next eligible milestone: M0Y
```

If test failure: explain exact defect, fix it in a **bounded correction** with tests before moving on; don't hide errors. If a later module is blocked by external dependencies, do independent offline work if valid, and report the blocker once rather than repeatedly asking the user.

## 6. End-of-R0 acceptance demo (must be repeatable)

From a **fresh local checkout and empty isolated state directory**, with only synthetic legal fixtures:
1. Lock/install dependencies and run `grog doctor`; report Python and config source.
2. `grog import-ticks` loads synthetic BID/ASK fixture and clearly reports source `SYNTHETIC`.
3. Duplicate import is idempotent; corrupt CSV fails without changing prior batch state.
4. `grog replay` produces fixed UTC MTF bars, H1/M15 context, S1 FORMING/READY/INVALIDATED events from genuinely confirmed data, realistic first-quote gross R and a reproducible report. It includes at least one zero-signal scenario and one valid synthetic trigger scenario; **no win-rate marketing**.
5. `grog ui --mode replay` shows all five views, dark compact layout, correct signal state/fidelity and exact SL/TP sides. Show WAIT and ERROR as carefully as READY.
6. Operator opens a manually confirmed simulated entry, partial close or closure; restart preserves local journal, restores open positions as needing reconciliation.
7. Quote gap/feed invalidity blocks new READY and displays current age/health; replays do not retroactively issue live proposals.
8. Full relevant test suite and static checks pass locally; direct Git commit references and test counts recorded. No external broker or network/CI automation required.

**Passing R0 means an offline research tool works. It does NOT establish that S1 makes money or that live source/broker fills are accurate.**

## 7. Blocker policy and escalation to user

Do not stop basic engineering for lack of a future execution broker, sample dataset beyond synthetic fixtures, live market session or unknown score threshold. Use the specified **offline-only research profile** and explicitly label unverified assumptions. If a necessary value for *even offline deterministic behavior* is missing, check canonical docs in order and the test case; if truly conflicting, stop just the affected module and report the two exact incompatible clauses.

External operations (Wine/MT5 installation, demo credentials, downloading proprietary market history, accessing personal accounts, real-money capital) need user permission. Don't assume consent from "start coding". Never run commands against `erp.omchouse.com` or any other production system.

**Next user instruction after this documentation phase can be a single sentence:** "Grok, start Grog from AGENTS.md and docs/10-roadmap.md, follow all canonical specifications, finish M00–M08 sequentially and report progress per milestone. No GitHub Actions."
## 8. Implementation progress — factual record

**IMPLEMENTED** = code and its milestone tests exist on `main`. **ACCEPTED** = the R0 acceptance audit ([14](14-r0-acceptance-audit.md)) has executed evidence for it. **VALIDATED** in the [11](11-decisions.md) sense (reproducible evidence of a trading edge) applies to **no** milestone: synthetic tests cannot validate S1.

| Milestone | Status | Commit(s) | Notes |
| --- | --- | --- | --- |
| M00 | IMPLEMENTED | `92b1484` | locked uv env, CLI, doctor, config validation |
| M01 | IMPLEMENTED | `279966e`, `f3f06f9`, `66a01c3` | strict CSV v1, catalog migration 0001 |
| M02 | IMPLEMENTED | `5e10a0e`, `67c2280` | causal bars, gaps, feed health (thresholds OPEN ⇒ UNKNOWN) |
| M03 | IMPLEMENTED | `d2b979d`, `9b00d65`, `bd3590d` | EMA/ATR, confirmed pivots, H1/M15 context |
| M04 | IMPLEMENTED | `4e94073`, `12e7156` | research-only S1 detector |
| M05 | IMPLEMENTED | `357ece7`, `67315b2`, `2133b02` | SIMULATED eligibility, BID/ASK plans |
| M06 | IMPLEMENTED | `78cf7df`, `230a582` | deterministic replay, reports (zero-delay entry only) |
| M07 | IMPLEMENTED | `246e990`, `f3e3c2a`, `261d486` | Textual workstation |
| M08 | IMPLEMENTED | `d0ff0fd`, `dca9ee3` | manual journal, reconciliation |
| R0 acceptance | ACCEPTED — CONDITIONAL | `50ea97d`…`8c97dec` (see [14](14-r0-acceptance-audit.md) §4) | audit opened at `dca9ee3` (439 tests, 12 findings F-01..F-12); all 12 fixed; 510 tests, ruff clean; operator journey + error-path acceptance tests; conditions in [14](14-r0-acceptance-audit.md) §5 |
| M09-A | IMPLEMENTED (offline) | `a88fd3f`, `d2709fe`, `f945500`, `be3479c`, `c712b18` | adapter, session, CLI, uncompiled exporter source; REF-01..12 ([08 §15.5](08-validation.md)); no MT5/broker/network used |
| M09-B | BLOCKED — external permission | — | read-only MT5 demo install/connection needs explicit owner approval |
| M10 | NOT STARTED — data/evidence-gated | — | needs real permitted BID/ASK history and a forward-paper protocol |

## 9. M09 plan — read-only MT5 reference feed

**Purpose:** feed the unchanged engine from a *read-only* demo/reference BID/ASK stream, tagged `REFERENCE_LIVE` and `INDICATIVE`. It is not an execution broker and does not make any fill broker-verified. Implementation contract: [09 §5.1](09-architecture.md).

**M09-A — offline, authorized 2026-10-31 (no MT5/Wine/broker/network/credentials/market data):** transport parser/validator, normalizer (UTC offset, side carry-forward, dedup, ordering), durable reader with atomic cursor, backfill-vs-live separation, timer-driven link monitor with injectable clock, live `ReferenceSession` over the existing pipeline, `NOT_CONFIGURED` CLI/UI behavior, read-only `grog reference-status`, and the MQL5 exporter **source** (uncompiled, untested in MT5). Tests use recorded-format fixture files only (producer `FIXTURE`).

**M09-B — BLOCKED until the owner grants every permission below:** compile/run the exporter, measure thresholds, wire the reference session into the workstation views, run the acceptance list.

**Explicit external permissions required from the owner (none granted yet):**

1. Install Wine and the MetaTrader 5 terminal on a named Ubuntu machine (not production servers, not the ERP host).
2. Open/use one named **demo** account on one named broker/server; credentials typed by the owner into the terminal locally, never committed, never given to Grok/Grog.
3. Copy `mql5/GrogReferenceExporter.mq5` into the terminal's `MQL5/Experts`, compile it in MetaEditor and attach it to one XAUUSD chart (AutoTrading/Algo-trading may stay **disabled** — the exporter needs no trade permission).
4. Allow that terminal's network egress to the demo server.
5. Approve the measured thresholds `live.max_quote_age_ms`, `live.max_first_postclose_delay_ms`, `reference.max_heartbeat_age_ms` (fixture/demo values are never reused).

**Machine requirements:** Ubuntu 22.04/24.04 x86-64, ≥ 4 GB RAM free for terminal + Grog, Wine (stable) or the official MetaQuotes Linux installer, Xvfb if headless, NTP/chrony time sync, a local directory shared between the terminal's `MQL5/Files/grog` (Common Files) and Grog's `reference.exporter_dir`, ≥ 1 GB disk for rotated files.

**Ubuntu compatibility checks (before relying on data):** terminal starts and reconnects under Wine; exporter compiles with zero warnings about trade functions; files appear in the Linux path with complete lines; `TimeTradeServer() − TimeGMT()` offset matches the broker's published server time; behavior across weekend close, demo-server disconnect, terminal restart and DST change observed; CPU/RAM acceptable beside the TUI.

**M09-B acceptance:** `grog reference-status` shows `LIVE` with real heartbeats; killing the terminal → `OFFLINE` within the heartbeat threshold with no new tick; disconnect → `DISCONNECTED`; weekend → `MARKET_CLOSED`; restart Grog/terminal → no lost or duplicated tick (cursor/dedup counters); catch-up produces no actionable READY; header reads `REFERENCE · INDICATIVE`; R0 replay outputs unchanged; source scan clean. Otherwise status stays **BLOCKED: demo access/install authorization missing**.

## 10. M10 prerequisites — historical data and forward-paper evaluation (nothing claimed)

No evaluation result exists. **Research readiness:** the protocol structure is defined in [08 §17–§18](08-validation.md) — dataset quality checks, entry-delay scenarios D0/D1/D2/D-obs, fee/spread inputs, development/validation/untouched-test windows, the H1-STRICT vs H1-OPPOSITE comparison and the criteria table — with **every numeric value OPEN** for the owner. M10 may start only when all of the following exist:

1. **Data:** permitted genuine XAUUSD BID/ASK tick history (licence/permission recorded) passing [08 §18.1](08-validation.md), long enough for walk-forward folds plus an untouched test window.
2. **Execution inputs:** [08 §18.3](08-validation.md) declared for one named venue (until then net R and currency P/L stay UNKNOWN) and the delay parameters `d1`, `d2`.
3. **Pre-registration:** window boundaries, `ΔE`/`ΔDD` and the [08 §18.6](08-validation.md) values committed before the validation window is evaluated.
4. **Forward paper:** M09-B authorized and running; [08 §18.7](08-validation.md) period and stop rules fixed.
5. **Reporting rule:** SIMULATED/PAPER labels with sample sizes; no win-rate or profitability claim; missing data ⇒ **UNVALIDATED** with the missing item named. No new indicators/strategies; no fitting to synthetic data.
