# Grok Build Roadmap — Exact Milestones, Tests and Handoffs

**Updated:** 2026-11-07  
**Status:** R0 (M00–M08) **IMPLEMENTED and acceptance-audited** (verdict CONDITIONAL, see [14](14-r0-acceptance-audit.md) §5); M09-B local read-only MetaQuotes-Demo permission is now granted (2026-11-11) but live stream/clock/policy/Qt commissioning is INCOMPLETE; M10 remains data/evidence-gated (plans in §9 and §10 below). **real broker connectivity, live trade-risk limits, performance thresholds and profitability cannot be finalized without actual data**. Implementation status is tracked factually in Section 8 below (implemented is not the same as validated).

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
| M09-H | IMPLEMENTED (offline) | `ddbd506`, `4df393f`, `14916ec`, `c56e18d`, `8a52beb`, `ccf99be`, `4f53840`, `7981928`, `1539514`, `2f4f7de`, `fe43454` | integrity hardening H1–H4 + UI-R1: REF-13..24 ([08 §15.6](08-validation.md)); exporter source v0.2 still never compiled/run; time basis, future-skew tolerance and fault recovery stay OPEN and block actionability; no MT5/broker/network used |
| M09-B | PARTIAL native evidence — not yet accepted | Owner-observed Ubuntu/Wine MT5 demo session + clock probe on 2026-11-11 | Demo terminal/exporter ran; a prior G/4022 gap persists; no verified T/L live ticks or qualified time/policy/Qt integration. LWX §14 owns remaining steps |
| M10 | NOT STARTED — data/evidence-gated | — | needs real permitted BID/ASK history and a forward-paper protocol |

## 9. M09 plan — read-only MT5 reference feed

**Purpose:** feed the unchanged engine from a *read-only* demo/reference BID/ASK stream, tagged `REFERENCE_LIVE` and `INDICATIVE`. It is not an execution broker and does not make any fill broker-verified. Implementation contract: [09 §5.1](09-architecture.md).

**M09-A — offline, authorized 2026-10-31 (no MT5/Wine/broker/network/credentials/market data):** transport parser/validator, normalizer (UTC offset, side carry-forward, dedup, ordering), durable reader with atomic cursor, backfill-vs-live separation, timer-driven link monitor with injectable clock, live `ReferenceSession` over the existing pipeline, `NOT_CONFIGURED` CLI/UI behavior, read-only `grog reference-status`, and the MQL5 exporter **source** (uncompiled, untested in MT5). Tests use recorded-format fixture files only (producer `FIXTURE`).

**M09-H — offline integrity hardening, approved 2026-10-31 (still no MT5/Wine/broker/network/credentials/market data).** Found by the read-only review of `667d8ef`; contract in [09 §5.1](09-architecture.md), tests REF-13..24 ([08 §15.6](08-validation.md)).

- **H1 transport/exporter reliability** — exporter source: binary UTF-8 LF bytes, input validation, unique file names, checked writes, non-overlapping windows, bounded retries + `G` gap record, atomic watermark, timer-driven catch-up with heartbeats, wrapping sessions. Source revised, **still uncompiled and unrun**.
- **H2 normalization/integrity** — per-file metadata, source-switch rejection, `E`-count check, cross-segment dedup, side consistency, latched integrity faults and the `INTEGRITY_FAULT` link state, fixture never actionable. **Timestamp conversion is a boundary marked UNVERIFIED** (offset change / offset-assumed history / future time / unset tolerance block READY).
- **H3 recovery/bounded ingestion** — streaming reader, throttled commits, cursor lock, `CURSOR_CORRUPT`, missing/truncated/replaced files, RECONSTRUCTED warm-up, startup fence.
- **H4 offline verification** — scratch repros ported as acceptance tests, producer-byte fixture, RSS ceiling, UI-R1 display fix.

**M09-B — authorized local read-only demo access, qualification still BLOCKED:** The owner installed Wine/MT5 and ran a read-only exporter/clock probe on Ubuntu (2026-11-08..11). This does not itself authorize READY, infer fills, or complete live desktop wiring; see §14.

**Original external permissions checklist (historical, updated 2026-11-11):** Items 1–4 were granted/observed locally using MetaQuotes-Demo; items 5–6 remain unresolved evidence/approval gates. Never collect MT5 credentials through Grog.

1. Install Wine and the MetaTrader 5 terminal on a named Ubuntu machine (not production servers, not the ERP host).
2. Open/use one named **demo** account on one named broker/server; credentials typed by the owner into the terminal locally, never committed, never given to Grok/Grog.
3. Copy `mql5/GrogReferenceExporter.mq5` into the terminal's `MQL5/Experts`, compile it in MetaEditor and attach it to one XAUUSD chart (AutoTrading/Algo-trading may stay **disabled** — the exporter needs no trade permission).
4. Allow that terminal's network egress to the demo server.
5. Approve the measured thresholds `live.max_quote_age_ms`, `live.max_first_postclose_delay_ms`, `reference.max_heartbeat_age_ms` and the future-skew tolerance (fixture/demo values are never reused).
6. Observe and record (M09-H left these UNVERIFIED): actual exporter bytes, the `time_msc` convention and its UTC relationship, the offset history across a DST change, what `COPY_TICKS_INFO` supplies for unchanged sides, `CopyTicksRange` failure/partial-return behavior and error codes, the broker's session table (midnight-wrapping sessions), the available tick-history depth versus the 250-H1-bar warm-up, and the recovery procedure after an integrity fault.

**Machine requirements:** Ubuntu 22.04/24.04 x86-64, ≥ 4 GB RAM free for terminal + Grog, Wine (stable) or the official MetaQuotes Linux installer, Xvfb if headless, NTP/chrony time sync, a local directory shared between the terminal's `MQL5/Files/grog` (Common Files) and Grog's `reference.exporter_dir`, ≥ 1 GB disk for rotated files.

**Ubuntu compatibility checks (before relying on data):** terminal starts and reconnects under Wine; exporter compiles with zero warnings about trade functions; files appear in the Linux path with complete lines; `TimeTradeServer() − TimeGMT()` offset matches the broker's published server time; behavior across weekend close, demo-server disconnect, terminal restart and DST change observed; CPU/RAM acceptable beside the TUI.

**M09-B acceptance:** `grog reference-status` shows `LIVE` with real heartbeats; killing the terminal → `OFFLINE` within the heartbeat threshold with no new tick; disconnect → `DISCONNECTED`; weekend → `MARKET_CLOSED`; restart Grog/terminal → no lost or duplicated tick (cursor/dedup counters); catch-up produces no actionable READY; header reads `REFERENCE · INDICATIVE`; R0 replay outputs unchanged; source scan clean. Otherwise status stays **BLOCKED: live reference readiness, time-basis, source integrity or policy qualification incomplete**.

## 10. M10 prerequisites — historical data and forward-paper evaluation (nothing claimed)

No evaluation result exists. **Research readiness:** the protocol structure is defined in [08 §17–§18](08-validation.md) — dataset quality checks, entry-delay scenarios D0/D1/D2/D-obs, fee/spread inputs, development/validation/untouched-test windows, the H1-STRICT vs H1-OPPOSITE comparison and the criteria table — with **every numeric value OPEN** for the owner. M10 may start only when all of the following exist:

1. **Data:** permitted genuine XAUUSD BID/ASK tick history (licence/permission recorded) passing [08 §18.1](08-validation.md), long enough for walk-forward folds plus an untouched test window.
2. **Execution inputs:** [08 §18.3](08-validation.md) declared for one named venue (until then net R and currency P/L stay UNKNOWN) and the delay parameters `d1`, `d2`.
3. **Pre-registration:** window boundaries, `ΔE`/`ΔDD` and the [08 §18.6](08-validation.md) values committed before the validation window is evaluated.
4. **Forward paper:** M09-B authorized and running; [08 §18.7](08-validation.md) period and stop rules fixed.
5. **Reporting rule:** SIMULATED/PAPER labels with sample sizes; no win-rate or profitability claim; missing data ⇒ **UNVALIDATED** with the missing item named. No new indicators/strategies; no fitting to synthetic data.

## 11. D00–D05 — native desktop migration (approved 2026-11-07)

Independent of MT5 M09-B and research M10; no broker connectivity/automation. Complete a bounded verified phase and commit before progressing.

| Phase | Task | Acceptance gate | Status |
| --- | --- | --- | --- |
| D00 | Optional Qt packaging, current code and probe verification | GUI-01..03, GUI-11..14; authentic lock and visible/offscreen Qt | DONE at `c4bd23c` (owner verified a regular Ubuntu GNOME terminal launch; VS Code-terminal GNOME settings issue remains a known limitation) |
| D01 | Harden replay-backed Overview with worker ownership | GUI-04/05, GUI-15..22; event and precision parity | DONE at `370f680` (replay owner thread, detached frames, redesigned Overview; owner approved). GUI-22 dialog/modal clauses are N/A until D03 forms exist (D01 has no dialogs or source switcher); its pause-acknowledgement and stale-intent parts are tested |
| D02 | Signals forming/READY/blocked/history, full details | GUI-23..29; immutable issuance and status parity | DONE at `43e1fd9` (keyed Developing / READY-execution-blocked / History tables with search and side/state filters, full-ID detail with the exact immutable plan, expiry, current eligibility, read-only operator overlay, reason codes and fidelity; multiple READY unranked; pre-roll and acted-on signals only in History; selection kept by full ID with moved/promoted/vanished/hidden notices; manual-record buttons disabled until D03; Refresh re-reads the journal overlay read-only and never moves the replay; responsive Signals layout: compact measured column widths with the core plan columns first, table beside the detail only when the core plan still fits, otherwise full-width table over the detail, an explicit more-columns hint, and wrapped exact detail values never cropped). Independent native QA passed 2026-11-07 on Debian XFCE after round-1 fixes (stale filter notice, column/detail layout); Ubuntu GNOME not re-run for D02. GUI-22 dialog clauses remain N/A until D03 |
| D03 | Positions, Journal, all confirmed manual forms/reconciliation | GUI-06/07, GUI-30..50; transactional recovery | DONE at `8662692` (independent native QA passed 2026-11-07 on Debian XFCE): journal owner thread (`journal_worker`) is the only SQLite writer and opens the writable store (existing migrations/backups, write-lock probe, `restore_on_startup`) after the first engine frame, else read-only UNVERIFIED (never creates a database); READY entry, skip, explicit OFF_PLAN fill, partial, full close, stop/target modify and confirm-still-open forms reuse `parse_amount`/`EntryPreview`/`exit_preview`/`r_breakdown`/`mark_position` and `PositionJournal`; replay paused with an acknowledged cursor before any form; signal eligibility and first operator claim re-checked at Save (a change refuses the on-plan record and offers a separate OFF_PLAN form); one stable action ID per dialog across retries; Cancel focused by default, dirty-cancel confirmation, scoped shortcuts; Positions (mode banner, reconciliation worklist, filters, exact detail with event vs recorded UTC) and read-only Journal (OPERATOR durable vs SIM ENGINE reconstructed, search/filters, no correction/delete). Audit fixes before commit: structured pre-save rules re-run at Save and on the journal owner (confirm-open can no longer be dated before the fill; the R0 `confirm_open` service itself still does not check time), a retry after OUTCOME UNKNOWN goes to the service idempotency first (identical payload = already saved, changed payload = DUPLICATE_ACTION_ID, never an OFF_PLAN duplicate), and every journal snapshot is one SQLite read transaction. Residual: when the writable open fails and the only readable path is an immutable open (unwritable folder, no pending WAL), the READ_ONLY view is a FROZEN snapshot that Refresh cannot update (stated in the banner; restart to re-read); a lock at startup keeps the session read-only until restart; other instances' writes appear on the next Refresh or local save. Native QA on Debian XFCE only |
| D04 | Diagnostics, fault handling, responsive/high-DPI QA | GUI-08/09, GUI-51..59; five-screen visual acceptance | DONE at `3dd0299` (independent native QA rounds 1–2 passed 2026-11-07 on Debian XFCE; not claimed natively: 125% repeated after the round-1 fixes, an induced long-preview internal scroll, the clean writable "no problems found" header — unit-tested only): Diagnostics page (key 5) built by the replay owner from the R0 diagnostics checks (same numbers; full 64-hex batch and config sha256) plus ENGINE, read-only REFERENCE ADAPTER = NOT CONFIGURED (M09-B/M10 pending) and LOCAL JOURNAL groups; the page header is an overall verdict over every group (journal included: read-only = NEEDS ATTENTION DEGRADED, unavailable = ERROR, not opened = UNKNOWN; reference NOT CONFIGURED named as expected in REPLAY) and the terminal R0 summary is shown only as the scoped "Replay source checks only" line; `?`/F1 modal help generated from the installed shortcut table (Close focused, Esc closes, never while typing); last good diagnostics labelled STALE after a mid-run source fault, UNAVAILABLE (not "waiting") when a load fails inside a running window; the real entrypoint keeps the D01 contract (GUI-01/GUI-14): missing state, unknown source or bad config is refused in the terminal before any window with exit code 3/5 and no writes, and the D05 chooser/import guidance owns that case; a source switch drops the old journal group at once; exit while a signal Save awaits its re-check reports NOT SAVED SHUTTING_DOWN, an already queued command finishes and reports first; long FAST replay with the journal owner keeps every engine event (parity with a direct replay) and a mid-load source switch paints nothing of the old generation; all five pages measured without horizontal overflow at 820x620, 1366x768, 1920x1080; all seven manual form types (entry, skip, off-plan, partial, modify, close, confirm-open) and the help dialog constrained to each of those boxes keep Cancel/Confirm fully visible, a usable scrolling field area that reaches the first and last field, a visible preview and Cancel focused; manual-form previews sit in a fixed-height region so ticking an acknowledgement or typing never resizes the field area (native 150% scroll jump, reproduced and fixed); help shows every line without scrolling (offscreen at QT_SCALE_FACTOR 1/1.25/1.5 — offscreen logical geometry is scale-independent, so real font/DPI rendering is accepted only by native QA). Mid-run fault injection is automated-only (no fake source in the app); source chooser stays D05. |
| D05 | Full parity, owner acceptance, then one-word launcher cutover | GUI-10, GUI-60..62; TUI fallback kept | CANDIDATE (launcher + chooser + parity; cutover NOT done): separate one-command launcher `scripts/gold-desktop.sh` → `python -m grog.desktop.launcher` (runs from any directory and through a symlink via `uv run --project`, relative `--state-dir`/`--config` stay relative to the caller; without uv it prints install guidance and exits 3; explicit arguments, else the operator's saved choice `$XDG_CONFIG_HOME/grog/desktop-source.toml` (0600, atomic, absolute paths, every control character escaped, written only on Open with Remember, never after an invalid From UTC/missing config, an unwritable config directory is reported and nothing opens) re-verified read-only, else the startup source chooser "NO DATA LOADED" with read-only state inspection (also beside a live writer in WAL mode), origin/temporary-location labels and the existing CLI import spelled out with a quoted path; nothing imported, created, copied or connected; Return/Enter press only the focused button, Return in the state field re-inspects, never Open/Quit from typing). GUI-05/17/62 replay parity (Textual app vs desktop worker, same imported state to REPLAY ENDED: quotes, feed, S1 and signal events by exact repr, signal IDs, final statuses, touches) and GUI-62 journal parity (entry, partial, modify, close, skip, unlinked OFF_PLAN, same-action-ID retry, restart RESTORED_UNVERIFIED once, confirm-open; allowed differences: action/position IDs, record times, the desktop's extra OFF_PLAN acknowledgement). Native D05 showcase (2026-11-07, isolated XDG/state): chooser states, inspection, Remember/relaunch/--choose/unchecked/malformed/explicit args and 820/1366 layouts observed; not yet observed natively at that time: Textual fallback, 125%, full Tab order (automated only). The existing `gold` alias is NOT changed: cutover only after observed desktop acceptance and explicit owner sign-off |

**D00 evidence correction:** Owner reports PySide6-Essentials 6.11.3 launched successfully from a regular Ubuntu 26 GNOME terminal using ephemeral `uv run --with`; VS Code terminal hits GNOME settings-schema failure. This has not yet been reproduced in a new locked project environment. Resolve optional Qt dependencies and regenerate `uv.lock` using real uv only after verifying compatibility; diagnose inherited environment without system GNOME/schema mutations. A preview opening does not demonstrate full GUI parity.

Canonical contracts: [02 §15](02-workflows-and-ux.md), [08 §19](08-validation.md), [09 §12](09-architecture.md), [11 D-014](11-decisions.md).

## 12. Desktop implementation order, verification gates and Grok handoff — 2026-11-07

**Historical D00–D05 acceptance plan:** These build phases were completed on main by `c0ef834` (see §11). The owner-approved **post-build V2 visual redesign** is a separate U0–U5 sequence in §13; do not repeat D00–D05 merely to change styling. Follow [02 §16](02-workflows-and-ux.md) for exact screens/forms, [09 §13](09-architecture.md) for runtime data flow and concurrency, [08 §20](08-validation.md) for GUI-11..62 plus existing GUI-01..10 cases, and [11 §16](11-decisions.md) for approvals and unresolved risks. D00–D05 are independent of M09-B/MT5 real demo integration and M10 market validation. **One small verified commit/report per phase**, on main, no GitHub Actions.

### 12.1 Universal preflight and stop rules

Before each implementation phase, inspect repository HEAD, branch, working-tree changes and the up-to-date canonical docs, implementation, tests and current behavior. Report the baseline exact SHA. Respect local uncommitted work. Run targeted pytest, Ruff check and Ruff format check on current code and record the real results (never inherit a previous "pass" claim). Confirm no changes to trading calculations, signal ID/state, exact Decimal, timestamp ordering, source hashes, journal schema, permissions or live MT5 gates except a separately approved, independently tested necessity. Develop/test in disposable state directories, not the user's live journal. Production erp.omchouse.com and other repos are out of scope; never run destructive commands. Actual Qt screenshots must be evaluated on Ubuntu: headless Qt tests alone are insufficient.

If any acceptance gate fails, stop further phases, isolate the smallest root cause and report it before changes. Do not hide skipped Qt tests, invent resolved lock hashes, add broker access or claim strategy success/profitability. All current S1 calculations and uncertainty defaults remain unchanged.

### 12.2 D00 — finish runtime/packaging foundation

**Precondition:** already-committed D00 helper and probe, D01 preview; no rewriting baseline merely because an alternative UI is planned. **Tasks:** (1) verify seven D01 test functions and existing pure formatter/probe tests from source, run them with accurate skip counts; (2) reproduce Qt probe and D01 in a regular Ubuntu terminal; inspect VS Code-inherited environment GNOME settings-schema failure, use only a proven app-scoped reversible solution; (3) add an *optional* desktop extra for PySide6-Essentials 6.11.3 if authentically resolvable, generate uv.lock with uv, verify default TUI installation and extra installation separately; (4) keep current gold alias and grog CLI unchanged. **Gate:** GUI-01..03 and GUI-11..14, test suite/Ruff, real offscreen + visible Ubuntu smoke and lock integrity. **Commit:** D00 dependency/compatibility corrections only; report SHA, exact package versions, passes/skips, environmental limitations.

### 12.3 D01 — finish Overview and responsive replay owner

**Tasks:** retain and surgically improve existing D01 Overview rather than replacing architecture; move source load/pre-roll and ordered replay work from GUI thread into a replay-owned worker; produce fully detached immutable frames tagged with source/generation/sequence; run existing every-quote TouchTracker and signal pipeline without skipped events; coalesce only paint updates at <=4 fps. Implement worker pause acknowledgement, startup/loading/unknown/replay-ended presentation, bid/ask/virtual UTC/simulation fidelity and H1/M15/M5 cause. Preserve 50/500/FAST event pacing and single-quote Step. Replay does not write to journal, and any position counts from read-only preview remain clearly unreconciled. **Gate:** GUI-04/05 and GUI-15..22 plus R0 replay/indicator/signal tests, source parity for exact Decimal and UTC, no UI freeze during FAST/pre-roll, observed 1366x768 screenshot. **Commit:** one bounded D01 commit and report.

### 12.4 D02 — complete Signals without journal writes

**Tasks:** add keyed model-backed forming/READY-blocked/history sections, search/filter, complete candidate/signal detail with immutable plan, expiry, current eligibility/status, operator overlay and exact reasons. Inherit engine source fidelity; show multiple READY without fake ranking, pre-roll only as historical; preserve selection and show terminal/moved state. Action controls remain read-only/disabled explanations until D03. **Gate:** GUI-23..29, prior S1 and signal regression, desktop source/price-side parity and observed wide/narrow details. **Commit:** one bounded D02 commit and report.

### 12.5 D03 — Positions, Journal, every manual record

**Tasks:** create journal worker with its own SQLite connection, opening writable Store and applying existing migrations/backups/restore_on_startup only on that thread; surface read-only UNVERIFIED if unavailable. Build position/mark/touch read models and full manual action workflows: READY entry, skip, explicit OFF_PLAN fill, partial, full close, stop/target modify, restart verify-open reconciliation. Use existing PositionJournal methods and parse_amount, EntryPreview, exit_preview, r_breakdown, mark_position, observations. Pause replay with acknowledged cursor before edit. Re-read engine signal/current claim before save; preserve original PlanRef and per-dialog stable action ID; error/retry must be transaction safe. Journal clearly separates durable operator records from replay-derived events, filters and stable detail access; do not introduce direct Qt SQL or unsupported correction/delete. **Gate:** GUI-06/07, GUI-30..50, R0 manual/positions/journal concurrency/fault/restart tests and visual dialogs with Cancel default. **Commit:** one bounded D03 commit and report.

### 12.6 D04 — Diagnostics, fault resilience, full GUI quality

**Tasks:** complete source/feed/warmup/confirmed bar/indicators/replay/config/integrity/journal diagnostics using existing read models; show read-only M09-A/H ReferenceStatus but never instantiate live MT5 or start exporter. Verify no source mismatch or stale-frame leak, graceful worker shutdown, no lost pending journal commit, missing source/no history/migration/locked DB errors, full keyboard/mouse access, consistent typography, high-DPI/820x620/1366x768/1920x1080 layouts and exact value details. Review screenshots for **each of all five screens and all action dialogs**, checking that they are not terminal-looking. **Gate:** GUI-08/09, GUI-51..59, scenario/visual approval, stable long FAST replay. **Commit:** one bounded D04 commit and report.

### 12.7 D05 — parity, owner-controlled gold cutover

**Tasks:** run complete offline pytest (including Qt-enabled tests), Ruff, all R0 operator journeys and concurrency/replay checks, compare complete signal IDs/events, journal projections, time/Decimal precision, disabled broker pathways and source-fidelity labels. Inspect user's actual shell alias and durable data configuration; provide a simple one-word `gold` launch into desktop with a truthful local source chooser/import guidance, **not** hard-coded `/tmp/grog-demo`. Keep explicit `grog ui --mode replay ...` Textual fallback; optional `gold-tui` convenience can be documented but is not required. Do not change the user's alias or global shell until observed desktop acceptance and **explicit owner signoff**. **Gate:** GUI-10, GUI-60..62 plus all earlier GUI and R0 tests, visible Ubuntu acceptance, verified TUI fallback and source-safe launcher. **Commit:** final D05 change after approval and report; without approval, leave gold pointing to TUI.

### 12.8 Required Grok report after each phase

Report **baseline SHA → phase commit SHA**, changed files and purpose, test commands with exact counts (pass/fail/skip), screenshot evidence and display environment, architecture/data-safety checks, any discrepancy or failed criterion, residual risks and next gate. Verify a clean final working tree and committed branch; no PR/CI workflow or unrelated refactor. A GUI screenshot does not verify journal writes; a test pass does not validate profitability or live source readiness.

**One-sentence starting instruction, only after owner approval:** Follow AGENTS.md and docs/11 §16, docs/02 §16, docs/09 §13, docs/08 §20 and docs/10 §12. Start at D00 verification and proceed sequentially with tested commits/reports, never modify trading logic or switch gold before D05 owner acceptance.

## 13. U0–U5 — complete desktop visual/interaction redesign V2 (approved 2026-11-07)

**Scope and source:** owner-approved [desktop-visual-redesign.md](desktop-visual-redesign.md) is the consolidated design companion, not a source of trading rules; [11 D-015](11-decisions.md) records approval. D00–D05 are **already implemented**; retain all GUI-01..62 and R0 contracts. This phase redesigns all five screens, Settings, dialogs, chooser, help, human-readable UTC/PKT presentation and Dark/Light/System; it is **not** a renderer/engine/journal rewrite.

| Phase | Bounded deliverable | Exit gate |
| --- | --- | --- |
| **U0** | Inspect remote/local main, uncommitted work and all Qt screens/dialogs/test consumers. Record baseline at actual HEAD; map UI-only touchpoints and capture before screenshots | Reviewable change map; existing targeted Qt/R0/Ruff results with real pass/fail/skip; no edits to trading code |
| **U1** | Central semantic themes and Dark/Light/System + PKT/UTC view preference; pure human readable time/status/secondary metrics formatters; exact audit and numeric details retained | UXV2-01..08 + existing desktop formatter and relevant Qt tests; theme persistence/OS change/fallback, exact Decimal and no unrelated global side effects |
| **U2** | App shell, Overview, Signals and Settings navigation; real model-backed human explanations and details; responsive tables, no false READY or source claim | UXV2-09..11 + GUI-01..29/R0 affected tests; both themes and widths/screenshots; true source/replay and stable selection |
| **U3** | Positions, Journal, local-record chronology and all manual forms; trustworthy saving, validation and reconciliation hierarchy | UXV2-12..14 + GUI-06/07, GUI-30..50, restart/idempotency and local transaction tests; no journal schema or service math changes |
| **U4** | Diagnostics, chooser, keyboard help, full fault and high-DPI/compact behavior | UXV2-15..17 + GUI-51..59; real Ubuntu visible QA in Dark/Light/System at 820×620, 1366×768, 1920×1080 and 100/125/150/200% scaling |
| **U5** | Full parity, final screenshots, source/Decimal/UTC and journal invariants, owner review package | UXV2-18 + all Qt-enabled GUI-01..62, R0 acceptance/integration, Ruff check/format, exact pass/fail/skip and clean tree report. No gold alias cutover. |

**Reporting:** One narrowly scoped tested commit/report per phase on the existing `main`, only after checking uncommitted local edits. Include baseline and result SHAs, changed paths, reproduced issues and tests, real GNOME screenshots, precise outcomes/skips, unchanged risk/journal/source/trading invariants, known gaps and next gate. Stop when any phase gate fails. Do not run GitHub Actions, install MT5/Wine, connect brokers or change the `gold` alias. Errors the owner supplies later require separate reproduction and authorization; do not guess them during U1.

## 14. LWX implementation — one-click LIVE workstation

**Owner direction 2026-11-11:** Resume Grog around the daily user product: single-command XAUUSD LIVE analyst with a local, supervised **read-only** MT5 feed, truthful BUY/SELL/NO TRADE plans and an optional **Watch setup** action. Do not rebuild engine R0, auto-trade, create another GUI, silently correct historical DST, or conflate watch with operator journal. The prior M09-A/H implementation is a foundation; the user already installed Wine/MT5 and manually tested exported data and the clock. M09-B reference-connected workstation work is authorized **within** decision D-018's read-only scope, but no live/real-money trade execution, policy guesses or gold alias cutover are authorized.

**Current as-built preflight (check again before coding):** GitHub main had f8d71b8 (GrogClockProbe added) when this handoff was written; normal desktop launcher opens REPLAY only; ReferenceSession is not wired into the Qt pages; Settings._validate_mode_policy rejects REFERENCE_LIVE; reference-status is read-only CLI; the FullUAT old source has recorded G/4022 and current server+02 observation, but zero verified continuous T/L. U1 Settings exists; U2–U5 visual tasks remain separate and must not block the functioning daily path. Do not rely on this SHA or acceptance figures without current checkout and native test reproduction.

### LWX-0 — Audit and baseline (no functional changes)

- Read AGENTS, 00-index, 01/02/03/06/07/08/09/10/11, relevant M09 parser/session, desktop launcher/main/worker/frame models and existing tests. Verify real current git main, clean local working tree, existing alias, executable discovery and installed Wine/MT5. Do not overwrite user changes.
- Reproduce focused existing reference, desktop, replay and journal tests plus Ruff; preserve exact baseline. Record observed current-clock probe evidence, old G/4022 source fault, current time-basis unknown and unknown thresholds. Identify complete source/Watch IDs and reuse validated risk plan and Qt owner-thread patterns.
- **Gate:** an implementation checklist maps each LWX requirement to a concrete module and test, with no missing ownership or guessed broker/market policies.

### LWX-1 — Local process supervisor and first-run setup (no trade engine modifications)

- Add validated, nonsecret XDG LIVE profile and concise first-run UI (approved Wine prefix/MT5 terminal, source, account/server XAUUSD evidence). Reuse existing PySide6 launcher without changing current REPLAY output or gold alias.
- Add smallest testable supervisor: exact process identity, optional controlled launch of known read-only demo terminal, detect already-running instance without modifying it, bounded recovery, UI status and clean shutdown. Reuse persisted EA/profile restoration first; automatically reattach/recompile neither in everyday use. Setup may require **one** manual MT5 login/consent only when genuinely missing.
- **Verify:** LWX-01..08, especially no modifying unowned EAs, no shell, no secrets, no double MT5 instance. Native Wine start/stop only against user-approved demo.

### LWX-2 — Qualified source and continuous reference reader (no READY promotion yet)

- Use a dedicated collision-free source ID for live startup, **not** contaminated mt5full20261108. Preserve all existing historical files and bookmarks. Do not assume 2-day warm-up; measure S1 H1/M15/M5 required pre-roll. Keep exporter read-only; compare its installed source/version to GitHub before any one-time install.
- Repair verified ingestion defects only: bounded tail polling with persistent session, complete M/T/H/B/E/G/Z audit, correct restart/fencing, source-specific time provenance, present-UTC server-time mapping, honest DST/offset uncertainty, current trade-session status; no silent repairs or deleting G.
- Log first genuine live T/L and compute observed ages/lag/spread/heartbeat distributions, then propose source-specific safe limits. Until approvals/verification, retain TIME_BASIS_UNVERIFIED, FUTURE_SKEW_TOLERANCE_UNSET and other existing blockers; show **OBSERVING / BLOCKED**, not tradable.
- **Verify:** LWX-09..19; real demo session with a tick, a gap/error, disconnect, terminal restart and stale quote; fixture shows no actionable READY on B/backlog.

### LWX-3 — LIVE Qt analysis / decision view

- Add dedicated LiveWorker on QThread over a persistent ReferenceSession and Qt-neutral detached frame models. Wire startup, source/feed health and actual engine H1/M15/M5/Developing/blocked/READY decisions to the existing Overview/Signals/Diagnostics. Preserve exact Decimal BID/ASK, original signal plan and UTC provenance; REPLAY remains optional. Do not invent signals if S1 outputs none.
- Keep the window responsive during initial catch-up and "no quote" intervals. Expose one clear headline: NO TRADE, DEVELOPING, READY · REFERENCE INDICATIVE, or why DATA UNAVAILABLE / BLOCKED. Never stamp "LIVE" on heartbeat-only updates.
- **Verify:** source/mode generation guards, causal engine parity, no omitted events under coalescing, LWX-13..19/28..30 and previous GUI regression.

### LWX-4 — One selected proposal watcher (separate from journal)

- Qt-neutral one-watch reducer with immutable plan/source IDs, frozen levels, versioned atomic XDG persistence, idempotent state transitions and on-screen alerts. Selection ≠ execution. Uses actual quote sides from 07 §13; statuses for touching, invalidation, expiration, unavailable. No guessed near-band threshold. Restore UNVERIFIED pending fresh confirmed source.
- Preserve all operator PositionJournal APIs/SQLite threads, manual entry save-time checks and reconciliation. Never turn watched/TP-touched signal into an open position, a fill, or R profit.
- **Verify:** LWX-20..27, corrupted watch file safe failure, crash/relaunch, repeated ticks, source switch, stale feed, broker-unknown case.

### LWX-5 — Native commissioning and optional command cutover

- Execute complete 08 §22 acceptance suite on owner's Ubuntu/Wine demo, then R0 replay/journal/UI parity and targeted U2–U5 legibility QA. Include positive and negative screenshots/logs (no credentials), audit the exact exporter and app for prohibited trade execution, CPU/RAM, and a usable market-closed/offline state. Report PASS/FAIL/BLOCKED for every gate, rather than hiding unresolved policies behind a nice UI.
- User should have to perform **only final one-click acceptance**, not daily MetaEditor/script checks. First-run MT5 login may still need one human action. A user-facing single command is the only operational interface after success.
- **Owner-controlled cutover:** Leave existing gold alias/launcher untouched during LWX-0..5. After independent PASS and explicit sign-off, change the alias once with simple rollback and keep an explicit REPLAY command; never delete the working fallback.

### Grok implementation directive (use without inventing more scope)

Start at LWX-0 and complete LWX-1, LWX-2, LWX-3, LWX-4, LWX-5 **in this order**. After each bounded verified phase, commit on main, run relevant tests/ruff, report exact commit SHA, changes, evidence and unresolved blockers. If an external/native MT5 step cannot be performed in your execution environment, test a fake/demo fixture locally, state precisely what native check remains, and continue independent modules—do not claim fully working LIVE or demand repeated manual terminal traces from the owner. Preserve no trading, manual-journal isolation and all existing fail-closed policy gates. Do not change production or unrelated repositories. Do not ask the owner to pick numeric broker-dependent thresholds; derive measurement reports and present explicit decisions for approval. The one-click experience is an integration goal, not license to fabricate readiness or performance.
