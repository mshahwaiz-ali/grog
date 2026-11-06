# Grog — Instructions for Grok and Other External Coding Assistants

**Project:** private `mshahwaiz-ali/grog` | **Branch:** `main` only | **Working language:** English  
**State:** R0 (M00–M08) implemented and acceptance-audited ([docs/14](docs/14-r0-acceptance-audit.md)); M09 offline adapter work only within the limits of [docs/10 §9](docs/10-roadmap.md) — installing/connecting MT5, Wine, broker accounts or data sources requires separate explicit owner permission. This file guides the external coding assistant; Grog itself is **NOT** an AI agent.

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
- Keep Textual and the current `gold` launcher until feature parity, user acceptance and full regression tests. No change to strategies, live MT5 permissions or broker execution.
- GUI reads existing replay snapshots and validates all manual records through the existing PositionJournal. Do not duplicate domain calculations, import Qt into the engine, or cross SQLite thread ownership.
- D00 is bounded to documentation, pure decimal-preserving display helpers and an **isolated Qt probe**. Do not claim a working trading GUI or fabricate a `uv.lock` update before package resolution.

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
- **M09** separate read-only MT5 demo adapter is **not included in the Start instruction**: user permission required to install/connect Wine/MT5/demo service.
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