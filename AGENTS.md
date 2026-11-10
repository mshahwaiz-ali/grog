# Grog — Instructions for Grok and Other External Coding Assistants

**Project:** private `mshahwaiz-ali/grog` | **Branch:** `main` only | **Working language:** English  
**State (2026-11-11):** R0 implemented/conditionally audited; M09 reference adapter offline parts exist; the owner independently granted and performed local Wine/MT5 MetaQuotes-Demo read-only commissioning, but continuous live T/L feed, data/policy qualification and Qt connection are NOT accepted. D-018 authorizes one-click, local, read-only supervision of that existing demo after one-time onboarding. See [docs/10 §14](docs/10-roadmap.md#14-lwx-implementation--one-click-live-workstation). This file guides the external coding assistant; Grog itself is **NOT** an AI agent.

## Mission — unchangeable without explicit user approval

Build a lightweight, high-quality local Python workstation (existing terminal plus approved native desktop successor) that researches **XAUUSD Gold** and displays objective **forming** and **ready** trading opportunities and monitors only **manually recorded** positions. Improvement must mean **better and more testable Gold trade decisions**, not extra features.

**Never implement:**
- LLM, chatbot, autonomous reasoning/trading agent inside Grog.
- Broker order placement, modification/cancellation, trade copy, recovery grid/martingale, account/wallet manager.
- Crypto, stocks, unrelated assets, generic financial dashboards, notifications/social feeds, SaaS/cloud server, web dashboard, heavyweight charting or excessive indicators.
- GitHub Actions workflows. The user's account has them disabled. **Local tests and direct Git commits do not require GitHub Actions**.
- Any change to production hosts or other projects; particularly **never touch `erp.omchouse.com`**.

## Native desktop modernization — approved 2026-11-07

- The owner approved a **local PySide6/Qt Widgets desktop frontend**, not a web dashboard; see docs/11 D-014, docs/02 §15, docs/09 §12 and docs/10 §11.
- Keep Textual and the current `gold` launcher until feature parity, user acceptance and full regression tests. New *read-only local MT5 demo* permissions are specifically limited by D-018. Never change strategy rules, trading permission or broker execution.
- GUI reads existing replay snapshots and validates all manual records through the existing PositionJournal. Do not duplicate domain calculations, import Qt into the engine, or cross SQLite thread ownership.
- D00 is bounded to documentation, pure decimal-preserving display helpers and an **isolated Qt probe**. Do not claim a working trading GUI or fabricate a `uv.lock` update before package resolution. (Historical D00 boundary: D00–D04 are now committed; current status in docs/10 §11.)

## Before doing any work: read in this order

1. `README.md`
2. `docs/00-index.md` — document ownership and precedence.
3. `docs/11-decisions.md` — user-approved decisions, broker-neutral MT5 direction, open/experimental items.
4. `docs/09-architecture.md` — exact package architecture, domain types, persistence, CLI, data/time contracts.
5. `docs/10-roadmap.md` — milestone sequence, acceptance criteria and commits.
6. The **canonical topic documents** for the milestone:
   - `docs/01-product-vision.md` product scope
   - `docs/02-workflows-and-ux.md` full premium Textual TUI design and keyboard/modal contracts
   - `docs/03-market-data.md` quotes, timestamps, broker-independent BID/ASK
   - `docs/04-analysis-engine.md` confirmed MTF bars, indicators, swing calculations
   - `docs/05-strategies.md` precise research S1 trend-pullback logic
   - `docs/06-signals-and-scoring.md` states, signal TTL, eligibility
   - `docs/07-risk-and-monitoring.md` price-side stops/targets and manual positions
   - `docs/08-validation.md` existing acceptance cases and research results criteria
   - `docs/12-references.md` external source caveats
   - `docs/13-competitor-research.md` inspiration only; **not approved features**

**Critical:** Everything under `docs/archive/` is historical only, NOT an active instruction. Where two clauses conflict, first follow docs/11-decisions, then the **one document owning that topic** and report the conflict precisely; never pick whichever rule is more convenient for code.

## When the user says "Start Grog"

This explicitly authorizes the **non-trading, local, offline M00–M08 implementation** described in `docs/10-roadmap.md`, in sequence, subject to local repository permissions. No more per-step clarification is required when the document gives an implementable testable contract. Work one module/milestone at a time and **report after each**.

- **M00** setup Python/uv, CLI and config.
- **M01** strict quote model/importer and durable catalog.
- **M02** true timestamp/availability-driven M1/M5/M15/H1 aggregation.
- **M03** EMA/ATR/pivot and H1/M15 features from confirmed bars.
- **M04** S1 *research-only* pullback/trigger.
- **M05** simulated signal eligibility and bid/ask price-side plan (NO uncalibrated score).
- **M06** deterministic replay and research reports.
- **M07** Textual UI with five screens and source fidelity; no fake confidence/price or broker orders.
- **M08** local manual-position record (including explicitly OFF_PLAN user-recorded trades), partial/modify/close forms and restart reconciliation.
- **M09** was excluded from the original R0 Start instruction. A separate 2026-11-11 owner direction now authorizes integrating the **existing read-only MetaQuotes-Demo** under D-018, with no live-account orders, credential handling, unapproved policies, data deletion or production access.
- **M10** independent research validation requires real historical/forward data and cannot be claimed complete based on synthetic tests.

If external live feed is not connected, **continue offline safely**. Broker choice is NOT a blocker for M00–M08. Never use a broker account's credentials without explicit permission.

## Research profile versus live execution policy

The formulas and candidate values defined in docs/04/05/06/07 may be **implemented only for deterministic synthetic/offline S1 research** as `S1_RESEARCH_V0_2` after the Start instruction. They are not approved profitable settings. An actual broker-specific spread, lot/contract, stop trigger, commission, slippage, trade sizing, account risk threshold and data-latency cutoff must **never** be guessed.

All REPLAY-ready outputs are labeled `SIMULATED`; eventual MT5 demo quotes are `REFERENCE` / `INDICATIVE`. Never call simulated findings verified broker fills. All actual operator fills are recorded as local journal events, not broker actions.

Do not invent a quality-score formula or trade win probability from the provisional 100-point rubric; until independent calibration is approved, display raw evidence and exact reason codes.

## Working practice

1. Inspect repository and working tree; do not overwrite pre-existing uncommitted changes. Default to `main`; do not create branches/PRs unless user changes policy.
2. Read exact milestone + owner documents **before implementation**. Identify inputs/outputs and at least positive, negative, boundary and restart/idempotency tests.
3. Create the smallest coherent set of modular files. Avoid needless new dependencies, scaffolding, duplicate logic or copies of markdown specs.
4. Run tests locally; use `uv sync --locked` after `uv.lock` exists and commands `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`. For M00 resolve `uv.lock` before attempting `--locked`.
5. If a test fails, fix the same bounded module and rerun; don't claim passing checks you didn't execute.
6. Commit tested, intended files to `main` with a clear message; direct Git push if permitted. **No GitHub Actions**. No force-push, destructive reset/cleanup, production server actions, mass dependency upgrades or changing unrelated projects.
7. Update the **existing canonical document** only when a proven implementation detail warrants it. Maintain one source of truth per topic. Don't create a new sequential doc for each milestone.
8. Report at the end of each milestone exactly as specified in docs/10-roadmap.md (SHA, tests, files, safety, blocker, next milestone).

## Required safeguards

- Prefer standard-library `argparse`, `dataclasses`, `Decimal`, `sqlite3`, `datetime`, `hashlib`. Depend on Textual for TUI, pytest for tests, Ruff for static checks; record actual versions in `uv.lock`.
- NEVER future-leak H1/M15/M5 bars or prematurely confirmed pivots. Use true first eligible post-close BID/ASK quote in hypothetical fills.
- Preserve distinct market ticks with identical source millisecond stamps; do not make timestamp the dedup key.
- Never double-charge spread when BID/ASK fill prices already include it.
- No external orders, no automatic partial close; a price touch isn't a confirmed fill.
- Keep `source_id`, `source_origin`, `available_at`, rule version and execution-fidelity labels in all records and terminal views.
- SQLite updates/journal actions must be transactionally safe and idempotent; replay must be deterministic across restarts.
- Missing data/costs/contract metadata yield `UNKNOWN`/WAIT/NO BROKER-VERIFIED PLAN, never guessed precision.
- UI should remain premium but restrained: strong typography, correct H1/M15/M5 labels, distinct FORMING/READY/POSITIONS, keyboard accessible; no marketing-style dashboard.

## One-message launch instruction from the user

> **Start Grog implementation from the existing GitHub main repository. Follow AGENTS.md and all canonical docs, especially docs/10-roadmap.md. Implement M00–M08 sequentially with local tests and one clear commit/report per milestone. Work offline without waiting for a broker, do not use GitHub Actions, do not add trading automation or unrelated features, and stop only for actual outside permissions or contradictions.**

The instruction is **not** consent to connect external broker/demo accounts, install Wine/MT5, access personal funds or run anything on production infrastructure.

## Complete native desktop handoff — start only after new explicit owner instruction (2026-11-07)

The owner requested a **documentation-only** complete Qt workstation handoff. Current state: D00–D04 are committed on main (D04 at `3dd0299`) under the owner's phased authorization and D05 is implemented (docs/10 §11, baseline `c0ef834`); the `gold` alias cutover still needs the owner's separate explicit authorization. Superseding the older D00-only description above **for future desktop work only**, use this exact canonical reading order once the owner asks you to begin native GUI implementation:

1. [docs/11 §16](docs/11-decisions.md) — authorization limits/open decisions.
2. [docs/02 §16](docs/02-workflows-and-ux.md) — all five screens, every action/dialog, human wording, keyboard and responsive design.
3. [docs/09 §13](docs/09-architecture.md) — actual existing ports, detached frames, thread/SQLite ownership, pause handshake, optional Qt and launcher.
4. [docs/08 §20](docs/08-validation.md) — exact GUI-11..62 tests, alongside existing GUI-01..10 and all R0 tests.
5. [docs/10 §12](docs/10-roadmap.md) — **D00 verification first**, then D01–D05 in strict verified phases, one commit/report per gate.

Inspect the actual current branch, working tree and APIs before any implementation; do not assume the documented initial SHA remains current. Preserve existing validated trading formulas, causality, precision, source fidelity, first-operator-claim idempotency, restart reconciliation and durable journal data. Never call the broker or implement auto-trading. Qt may format and invoke existing domain service methods, but must not reimplement them or access SQLite from the GUI thread. The current `gold` alias remains Textual until D05 regression/visual acceptance and the owner's **separate explicit cutover authorization**; `grog ui` stays available as fallback. No real MT5/demo activation or change to M09-B access rights.

**Historical D00–D05 starting instruction (already fulfilled by `c0ef834`):** do not repeat the original D00–D05 build; the current authorized project is the **V2 presentation redesign** below.

## Current owner-approved work — full desktop UI/UX V2 (2026-11-07)

**D-015 approval:** owner accepted both charcoal Dark and warm-white Light Overview visual directions and explicitly requires **Dark / Light / System** under Settings, with System following the OS when available. This is a **complete five-page/dialog/source chooser/help UX redesign**, not a new engine, web app or trading strategy. Owner requested **Grok** to implement once handed the single launch prompt; no UI code changes are part of the documentation update.

**Primary design document:** [docs/desktop-visual-redesign.md](docs/desktop-visual-redesign.md), especially its owner-approved §§3–10 and single Grok prompt in §13. Functional behavior remains canonical in [docs/02 §16](docs/02-workflows-and-ux.md), architecture in [docs/09 §13](docs/09-architecture.md), acceptance in [docs/08 §§20–21](docs/08-validation.md), phase ordering in [docs/10 §13](docs/10-roadmap.md), authorization boundaries in [docs/11 D-015](docs/11-decisions.md).

**Implementation order:** U0 (baseline read-only audit) → U1 (themes/presentation/settings) → U2 (shell/Overview/Signals) → U3 (Positions/Journal/forms) → U4 (Diagnostics/chooser/help/responsiveness) → U5 (full Qt/R0/visual/keyboard/fault acceptance), with a narrow tested commit/report per phase. Confirm local HEAD and dirty files before touching anything. **Do not rewrite D00–D05, alter the `gold` alias, install MT5, connect a broker, add trading automation, change SQLite journal schemas, precision or strategy**, or fix unrelated errors before the owner supplies them. No GitHub Actions.

## New active owner priority — one-click LIVE workstation (2026-11-11)

**Before building more visual-only U2–U5 changes, implement the daily product flow in docs/10 §14, following D-016..019 in docs/11.** Read functional UX docs/02 §17, source/time docs/03 §11, risk watch docs/07 §13, architecture docs/09 §14 and tests docs/08 §22. Keep unchanged R0 engine and the journal. The one-click desktop auto-manages the previously onboarded read-only MT5 dependency; not the broker. The new Watch setup action MUST NOT create an actual trade or journal ENTRY. **Old documentation that says M09-B was never authorized describes the historical 2026-10-31 baseline, not today's approved read-only demo scope.** No executable LIVE signals until real T/L source, verified time basis, no latched faults, completed warm-up and source-specific approved safety policies. Do not force setups, assume a broker fill or report profit.

Follow LWX-0..LWX-5 in order. Run focused tests per phase, keep GitHub main, no GitHub Actions; owner should not be asked to routinely run MT5 scripts/probes. If native Wine cannot be exercised in your environment, implement and test independent components with simulated subprocess/reference fixtures and label the native test BLOCKED. Do not modify the existing gold alias without separate final sign-off. This newer directive supersedes only older *read-only MT5 demo access restrictions*; every no-trading and data-integrity safeguard remains active.

## Current product priority — trade-only, NO WATCH (owner correction 2026-11-11)

**This is the latest instruction and supersedes the preceding November 11 one-click watch specification.** Implement [docs/trade-first-redesign.md](docs/trade-first-redesign.md), the simplified [docs/10 §15](docs/10-roadmap.md#15-tf--trade-finder-only-implementation-supersedes-watch-workflow) and decision [docs/11 §19](docs/11-decisions.md#19-trade-first-scope-correction--owner-approved-2026-11-11). The actual owner and ChatGPT will code the project directly; Grok is not a required tool. For the new daily LIVE app: **no Watch setup, no selected-trade/position monitor, no journal/entry controls, no notifications about TP or SL.** Keep validated legacy replay/journal code but hide it from the simplified LIVE workflow. Show only selective, sourced BUY / SELL / NO TRADE with objective entry/SL/TP and evidence. Test accuracy empirically on real independent data; never claim high win rates without reproducible proof. No need for another broad visual redesign or imaginary strategy. Old D-017/LWX-4/watch-focused implementation language is not current authorization. All no-automatic-trading, fault-rejection and non-destructive limits remain active.
