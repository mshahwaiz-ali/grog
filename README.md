# Grog

**Gold (XAUUSD) trading research and decision-support software — documentation-first project.**

**Status:** Planning / specifications only. No implemented trading engine, live feed, signals, backtests, or verified profitable strategies.  
**Repository:** Private; main branch only.  
**Last planning update:** 2026-10-30.

## Goal

Build a local, terminal-first, rule-based application that continuously studies XAUUSD, detects developing opportunities, emits selective actionable BUY/SELL signals with entry, stop-loss and take-profit levels, and monitors positions after **manual confirmation** by the trader.

Grog is **not** an LLM/AI-agent/chatbot and **never** places, modifies or closes broker orders.

## How trade decisions will work (proposed)

1. Validate market data, bid/ask spread, market session and event restrictions.
2. Identify market regime and important price levels using price structure, volatility and simple supporting indicators.
3. Run eligible, independently specified scalping strategy modules.
4. Distinguish developing setups from fully confirmed actionable signals.
5. Enforce risk and execution checks, rank candidates and explain reasons.
6. Allow manual entry/skip/expiry; track entered positions with live market observations.
7. Record all signals and outcomes for independent backtesting and live paper-trading evaluation.

**Trading rules are research hypotheses until validated out of sample.** High win rate alone is not evidence of positive profitability; net expectancy after spread, slippage and other costs is central.

## Documentation index

- [00 — Guide and status](docs/00-index.md)
- [01 — Product vision and requirements](docs/01-product-vision.md)
- [02 — Terminal workflow and UX](docs/02-workflows-and-ux.md)
- [03 — Market data, events and sessions](docs/03-market-data.md)
- [04 — Analysis inputs and calculations](docs/04-analysis-engine.md)
- [05 — Trading strategy research specifications](docs/05-strategies.md)
- [06 — Signal scoring and selection](docs/06-signals-and-scoring.md)
- [07 — Risk and live position monitoring](docs/07-risk-and-monitoring.md)
- [08 — Backtesting and validation](docs/08-validation.md)
- [09 — Proposed software architecture](docs/09-architecture.md)
- [10 — Build phases and acceptance gates](docs/10-roadmap.md)
- [11 — Decisions, assumptions and open questions](docs/11-decisions.md)
- [12 — Research references](docs/12-references.md)
- [13 — Competitor research and trade-quality lessons](docs/13-competitor-research.md)
- [14 — Multi-timeframe design and S1 trend-pullback research specification](docs/14-multi-timeframe-S1-trend-pullback.md)
- [15 — S1 false signals, execution realism and adversarial validation](docs/15-S1-failure-modes-and-robustness.md)
- [16 — Refined S1 deterministic research contract](docs/16-S1-refined-test-contract.md)
- [17 — Indicator-combination research and selection](docs/17-indicator-combination-research.md)

## Boundaries

**Scope lock:** Any upgrade or competitor-inspired idea must directly improve XAUUSD trade selection, timing, validation, risk decisions or live monitoring, with measurable evidence. Reject unrelated product features. See [Decisions](docs/11-decisions.md).


- Instrument: **XAUUSD only** at first.
- Use: educational/research decision support and manual trading; not financial advice.
- No auto execution; no LLM inference, remote AI providers, or chatbot interface.
- Real-time market data **is still required** for live analysis; provider/broker undecided. Offline historical replay must work without connectivity.
- Default interface: local live terminal UI, optional UI enhancement later.
- Performance targets, indicator parameters, strategy settings and risk limits are **proposals until measured and approved**.

This private repository contains specifications; never commit broker credentials, personal account exports, or private trading records.