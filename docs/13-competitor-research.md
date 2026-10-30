# Competitor research: trade-quality lessons for Grog
Date: 2026-10-30 | Status: RESEARCH NOTES, not approved product features or validated trading edge

## Non-negotiable scope
Grog remains **XAUUSD-only manual scalping decision support**. Competitive research is allowed solely to improve *which trades we recommend, when to enter, when to avoid an entry, how to set/monitor SL/TP, or how we prove whether these decisions are reliable*. We do **not** adopt LLMs, automated execution, wallets, copy trading, unrelated accounts/portfolios, chatbots, social feeds, or complex dashboards because competitors offer them. Simpler is preferred when net trading quality does not materially improve.

## Primary-source competitor benchmark
These are **vendor descriptions** of capabilities; none demonstrates audited live profitability or proves a signal edge.

| Product | Verified relevant capability | Research lesson for Grog | What NOT to import |
| --- | --- | --- | --- |
| LuxAlgo Price Action Concepts | Defines swing and internal market structure, liquidity grabs, zones; explicitly warns some swing structures are identified retrospectively. | Make structure and reversal patterns deterministic and time-causal; record when a level became knowable; distinguish pending confirmation from ready. | Every SMC label, order-block/FVG collection, or marketing claim. |
| TrendSpider | Dynamic levels plus multi-factor / multi-timeframe alert conditions; strategy testing tools. | Align higher-timeframe context with lower-timeframe triggers, while measuring the incremental benefit of each filter. | AI assistant, automated bots, countless indicators or broad asset scanning. |
| Autochartist | Detects chart patterns/key levels; measures pattern-performance by instrument, data interval and time of day; volatility by hour/day and event alerts. | Research empirical **conditional** performance by Grog strategy, time of day, session and volatility regime; adapt the eligibility process only if stable out of sample. | Separate forecasting API services, extra notification channels, extra instruments. |
| Trading Central Technical Views | Preferred directional scenario with two targets, pivot/invalidation line and alternate scenario. | Every actionable recommendation must explain the *thesis*, objective invalidation and what conditions would change the recommendation. | Paid analyst team, duplicate market newsletters. |
| FX Blue Trading Simulator | Supports hands-on historical manual trade replay in MetaTrader. | Include manual-fill timing and entry-lateness tests in Grog evaluation. | Separate brokerage UI, account automation or a fully featured simulator UI by default. |
| MetaTrader 5 Strategy Tester | Real-tick vs simulated-tick testing distinguishes changing spreads and bid/ask execution. | Real broker-matched bid/ask history and simulated operator delay are necessary before any scalping edge can be believed. | Robot execution, copy-trading marketplace, VPS. |

## Market-specific findings
- Gold activity is distributed across OTC markets and listed futures. A single broker's spot feed or tick volume is not a view of all global order flow. CME gold futures order-flow tools may offer different information but **are not assumed essential** for spot-XAUUSD scalping.
- CME documentation finds larger movements around some macro releases (e.g., jobs data). Treat event windows as a *measurable risk dimension*; avoid asserting that a blanket news blackout always improves expectancy.
- TradingView technical documentation explicitly highlights repaint/future-leak risks when using unconfirmed bar and higher-timeframe information. A chart that looks perfect in hindsight may be impossible to trade in realtime.
- Academics describe serious backtest overfitting risk from searching many strategies/settings on the same history. More rules alone cannot manufacture a real edge.

## Proposed lessons, ordered by impact
1. **Timestamp-true signal replay:** Grog must produce the same setup at the time it was actually knowable; preserve first-detected, first-ready, invalidated and expired timestamps. Never let retrospective pivots rewrite past signals.
2. **Cost-and-latency-aware trade eligibility:** use available spread, slippage sensitivity and realistic delay from signal to *manual* entry. No signal if likely executable reward is eroded below validated limits.
3. **Scenario-aware monitoring:** each signal contains expected continuation, stop/invalidation, first/second targets and exact conditions that would weaken the thesis. Explanations must be objective, not decorative.
4. **Conditional performance diagnostics:** review actual strategy statistics by XAUUSD session/time/regime, with sample-size uncertainty; only promote differences that survive untouched historical and forward tests.
5. **Ablation over accumulation:** test whether any new confirmation (EMA, ATR, RSI, volume proxy, pattern) improves net expectancy and stability *after costs* compared with the simpler system.

These are **research priorities**, not authorization to change the trading engine or user workflows. Score weights and thresholds remain hypotheses; do not call rubric scores win probabilities.

## Avoid adopting on sight
- '90% win rate' vendor claims or screenshots without full verified trade ledger, costs, drawdown, sample coverage and forward statistics.
- Order blocks, fair value gaps, liquidity pool labels or 'institutional manipulation' as if they were proven order flow.
- Futures footprint/delta as a free substitute for spot market truth.
- Feature proliferation: news feed summaries, bots, portfolio tools, exchange wallets, sentiment dashboards, unlimited strategies, excessive confirmation rules.

## Research questions before upgrading strategy specifications
1. Which events/levels are genuinely observable at signal time? Exact mathematical rules, timestamps and no-lookahead tests.
2. Does conditional regime/session performance for S1/S2 show statistical persistence after fees and manual latency?
3. Which elements lower false positives **without** eliminating too many positive-expectancy opportunities?
4. What is the minimum historical tick fidelity required for entry and stop correctness under the chosen broker?
5. How should monitoring alter a held trade in objective, backtestable ways without excessive flip-flopping?

## Sources (accessed 2026-10-30)
- LuxAlgo official Price Action Concepts: https://www.luxalgo.com/library/indicator/luxalgo-price-action-concepts/
- LuxAlgo liquidity concepts and retrospective structures: https://docs.luxalgo.com/platform/algos/price-action-concepts/liquidity
- TrendSpider multi-factor dynamic alert types: https://help.trendspider.com/kb/alerts/types-of-alerts
- Autochartist official API capability and performance statistics: https://www.autochartist.com/developer-apis/
- Trading Central official Technical Views: https://investor.tradingcentral.com/technical-views
- FX Blue official manual historical simulator: https://www.fxblue.com/tools-for-download/fx-blue-trading-simulator
- MetaTrader official real vs generated tick documentation: https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation
- TradingView official repainting guidance: https://www.tradingview.com/pine-script-docs/concepts/repainting/
- CME gold and macro announcement risk: https://www.cmegroup.com/articles/2024/using-metals-weekly-options-to-hedge-event-risk.html
- World Gold Council primer on OTC and futures market structure: https://www.gold.org/goldhub/research/market-primer/gold-market-primer-market-size-and-structure
- Bailey et al., probability of backtest overfitting: https://escholarship.org/uc/item/4w1110bb

## Status and change rule
**No new feature or strategy rule has been approved from this research.** Evaluate and discuss one candidate improvement at a time. Only update approved specs after user agreement and measurable testing criteria.
