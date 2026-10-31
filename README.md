# Grog

**XAUUSD Gold scalping research and manual trading decision-support software.**

**State:** M00–M06 implemented offline: `grog --help`, `grog version`, read-only `grog doctor`, validated config, and `grog import-ticks` (strict canonical BID/ASK CSV v1, checksummed immutable batches, SQLite source/batch catalog) plus causal M1/M5/M15/H1 BID/ASK bars, gap records and feed-health states, and pure no-lookahead analysis (EMA/Wilder ATR with documented SMA/mean-TR seeds, confirmed strict 2/2 M5/M15 pivots, H1 bias and M15 context under the offline research parameter set `S1_RESEARCH_V0_2`, UNKNOWN kept explicit), and the research-only S1 v0.2 detector (frozen M5 L/H pairs, one FORMING candidate per side, pullback depth/invalidation/expiry/supersession with reason codes, closed-bar trigger observations), and SIMULATED signal eligibility (first executable post-trigger BID/ASK quote, immutable E0/SL/TP1/TP2 and gross R, reversible EXECUTION_BLOCKED overlay, next-M5-close TTL, MISSED_DATA_GAP / MISSED_PRICE_CHASE). OPEN thresholds (quote age, first-quote delay, price step, spread, costs) default to unset/UNKNOWN, so no READY is issued until they are explicitly declared; no score, probability, lot sizing or orders, plus deterministic research replay (M06): `grog replay --source-id ID [--from ISO_UTC --to ISO_UTC] [--config PATH]` runs pre-roll + window on a virtual UTC clock, records a SIMULATED run (run/config/data/params hashes, append-only events, restart-idempotent checkpoints) and prints an evidence report; read-only `grog report --run-id ID [--format text|json]`; full-position TP2-or-SL outcomes on ordered BID/ASK ticks (INDETERMINATE on gaps, gross R only without declared costs, rejected setups as labeled counterfactuals, no win-rate claim); deterministic SYNTHETIC generator `python -m grog.replay.synthetic --out PATH`. Local checks: `uv sync --locked`, `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`. No terminal UI (M07), live data feed, proven accuracy or profitability yet.  
**Repository:** private; default branch `main`.  
**Last update:** 2026-10-31.

## Product mission

Help a person take **better Gold trades**, not more platform features. Grog will run locally (initially a terminal session), monitor XAUUSD market conditions, separate developing setups from confirmed actionable proposals, present BUY/SELL/WAIT/NO TRADE with explicit entry, SL/TP and conditions, and observe trades after the user manually confirms actual broker execution.

Grog is **rule-based software**, not GPT/Claude/LLM, an AI agent, an auto-trader, a broker wallet or copy-trading service. Grok is a **separate development assistant** that will implement only approved, testable specifications in small modules.

## How trade decisions are proposed to work

1. Validate live BID/ASK source, quotes, closed-bar timing and broker metadata.
2. Calculate H1 trend, M15 market structure and M5 setup/volatility using complementary measurements.
3. Run strategy-specific objective rules (S1 trend pullback first; S2 only if separately researched).
4. Show **DEVELOPING** opportunities until the trigger and eligibility pass.
5. On valid post-trigger executable quote, show **READY** proposal with time-limited entry band, stop/targets, cost/risk evidence and reason codes; never promise a fill.
6. Trader manually enters/skips through broker, then reports actual entry/quantity to Grog.
7. Monitor bid/ask, thesis changes, stop/TP proximity and position status; journal actions/results, with restart reconciliation and no automatic broker execution.
8. Replay realistic historical tick data and validate the smallest strategy/indicator combination that shows robust **net** performance, rather than chasing win-rate claims.

Proposed strategies/indicator periods have **not** been tested; an attractive quality score is **not** a win probability. Phase 18 specifies evidence-first signals and tests. **MT5 is now the preferred reference-price adapter**, regardless of the eventual execution broker. First build broker-neutral offline BID/ASK parsing, causal MTF analysis and replay; then connect an MT5 demo data source when separately approved. The actual broker/server and live feed are not selected or installed. Numerical ranking remains experimental.

## One-message Grok launch (only when you want implementation to begin)

**Grok's entrypoint:** [AGENTS.md](AGENTS.md), followed by [docs/00-index.md](docs/00-index.md), [docs/11-decisions.md](docs/11-decisions.md), [docs/09-architecture.md](docs/09-architecture.md) and [docs/10-roadmap.md](docs/10-roadmap.md). All specific rules, terminal wireframes, CLI/SQLite contracts, test cases and progress format are already documented. M00–M08 can be built **offline, without an execution broker or GitHub Actions**. MT5 demo connection and credible profitability testing are later separate milestones.

> Start Grog implementation from the existing GitHub main repository. Follow AGENTS.md and all canonical docs, especially docs/10-roadmap.md. Implement M00–M08 sequentially with local tests and one clear commit/report per milestone. Work offline without waiting for a broker, do not use GitHub Actions, do not add trading automation or unrelated features, and stop only for actual outside permissions or contradictions.

**The above is a future instruction for Grok. The application is not yet built, and no claims of strategy accuracy have been verified.**

## Active documentation — single source of truth

Start with [docs/00-index.md](docs/00-index.md) for the full canonical topic map.

- [Product goals](docs/01-product-vision.md)
- [Terminal workflow](docs/02-workflows-and-ux.md)
- [Market data and closed-bar contract](docs/03-market-data.md)
- [Indicators, MTF analysis and market structure](docs/04-analysis-engine.md)
- [S1 strategy and future strategy candidates](docs/05-strategies.md)
- [Signal states, entry-band and scoring](docs/06-signals-and-scoring.md)
- [SL/TP, manual fills, risk and position monitoring](docs/07-risk-and-monitoring.md)
- [Validation, indicator combinations and adversarial tests](docs/08-validation.md)
- [Proposed architecture](docs/09-architecture.md)
- [Build roadmap](docs/10-roadmap.md)
- [Approved decisions, open blockers and documentation standards](docs/11-decisions.md)
- [Research references](docs/12-references.md)
- [Competitor lessons (research only)](docs/13-competitor-research.md)

**Historical only:** [Archived S1 draft snapshots](docs/archive/2026-10-30/README.md). These are **not current instructions for Grok**. Exact original Git contents also remain in repository commit history.

## Project safeguards

- Any proposed "upgrade" must demonstrably improve Gold trade selection, realistic execution, risk/TP decisions, monitoring or testing accuracy. Reject unrelated product features.
- **Update existing canonical documents** instead of creating more numbered versions of the same idea.
- Do not guess broker/price data, fees, risk thresholds, scoring formulas or claimed performance.
- Live quotes will eventually come via the preferred read-only **MT5 reference adapter** (a demo broker server provides quotes; MT5 alone is not a universal source). **No execution broker choice is required to start offline engineering**. This does **not** imply an AI API or order-execution API.
- Test realistic bid/ask spreads, latency and out-of-sample/forward outcomes before promoting a strategy.
- Never commit broker secrets or private customer/account data. This is not financial advice and there are no guaranteed trading results.

No strategy code was authorized by this documentation maintenance.
