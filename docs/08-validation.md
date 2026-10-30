# Backtesting, paper trading and validation
## Goal
Find robust **positive net expectancy**, manageable drawdown and sufficient high-quality trade frequency. Do not target win rate alone or claim 90% accuracy before evidence.
## Data and causality
Use broker-matched bid/ask real ticks when available; no future-bar access, repainting pivots or retrospective entry. Event calendar must use information known by decision time. Every test stores code/settings/data version, source and time window.
## Execution model
Simulate executable bid/ask: long enters at ask/exits at bid; short enters at bid/exits at ask; apply realistic fees, latency, slippage, spreads, position sizing, stop gaps and partial TP handling. Test variations when precise historical costs missing. Never infer stop/TP order from 1-minute OHLC if ambiguous.
## Research process
1. Validate data; freeze baseline rules.
2. Use chronological training, validation and untouched final test; walk-forward rolling/expanding splits with gaps if features overlap.
3. Measure per-strategy and aggregated outcomes; no cherry-picking favorable days.
4. Ablation: disable EMA/ATR filters, sweep confirmation, risk gates one at a time; retain only statistically and economically useful components.
5. Sensitivity and stress: spread inflation, delayed manual fills, slippage, regime shifts, different sessions and volatility.
6. Shadow/live paper testing with full logging for a sufficient representative sample; do not claim readiness solely from backtest.
## Reported metrics
Sample count, trades/day by session, win rate, average win/loss, net expectancy in R after costs, profit factor, max drawdown, losing streak, payoff distribution, time-in-trade, missed-entry rate, MFE/MAE, fee sensitivity, regime stability, signal-to-fill degradation and confidence intervals.
## Example why accuracy alone fails
90% wins * 0.3R + 10% losses * -3R = -0.03R/trade; 40% wins * 2R + 60% losses * -1R = +0.20R/trade (before costs).
## Promotion gates
No live-capital readiness until data fidelity, deterministic replay, credible out-of-sample profitability, cost robustness, monitoring reliability and forward results satisfy **pre-registered thresholds** (OPEN). Do not change thresholds after inspecting final test outcomes. Losses remain possible.
## S1-specific failure and overfiltering experiments
Before implementing S1, review [15 — S1 failure-mode and robustness](15-S1-failure-modes-and-robustness.md), which specifies 16 failure classes, 20 adversarial synthetic fixtures, bid/ask-and-human-latency worked examples, and staged ablation experiments. Do not evaluate rejected trades only by their loss rate: include counterfactual performance of rejected winners, lost net R and reduced signal frequency. Mark all as proposed until broker-matched data and research windows are approved.

## Small indicator-selection research grid
See [17 — indicator combinations](17-indicator-combination-research.md) for the nine predeclared diagnostic/experimental variants I0–I8. To prevent overfitting, don't tune the final untouched holdout and don't add RSI/MACD/ADX merely to increase agreement. Use documented hypothetical execution rules from [16](16-S1-refined-test-contract.md), reporting fillability and opportunity cost under the same risk and costs.
