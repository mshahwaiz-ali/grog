# Grog

**XAUUSD Gold scalping research and manual trading decision-support software.**

**State:** documentation/research only; no implemented trading software, live data feed, tests, proven accuracy or profitability.  
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

Proposed strategies/indicator periods have **not** been tested; an attractive quality score is **not** a win probability. Phase 18 now specifies evidence-first signal selection and negative tests in the **existing** signal/validation documents. Numerical ranking remains experimental.

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
- Real-time market quotes are still required for live software; the provider/terminal remains undecided. This does **not** imply any AI API or order-execution API.
- Test realistic bid/ask spreads, latency and out-of-sample/forward outcomes before promoting a strategy.
- Never commit broker secrets or private customer/account data. This is not financial advice and there are no guaranteed trading results.

No strategy code was authorized by this documentation maintenance.
