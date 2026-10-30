# IC-01 — Selecting a Robust, Minimal XAUUSD Indicator Combination

**Date:** 2026-10-30 · **Status:** RESEARCH PLAN / PROPOSED. No backtest, parameter selection or live profitability claim has been completed.

**Scope lock:** Grog's job is to find **better Gold trades**, not collect indicators, copy marketed signal tools, implement an AI agent, or create auto-trading functionality.

## 1. What "best combination that works almost everywhere" can realistically mean

No known indicator combination is proven to remain profitable across **all** XAUUSD regimes, brokers, spreads, news releases, or trading hours. A single trend-following algorithm such as S1 should **not** force signals when the market is ranging, transitioning or dislocated. Grog should instead:
- Observe market condition using a stable, small set of interpretable measurements.
- Activate a strategy **only when its tested conditions exist**.
- Show WAIT / NO TRADE outside those conditions, without becoming so restrictive that it trades almost never.
- Prove improvements across **unseen** market periods and regimes, with actual execution assumptions.
- Prefer a **stable parameter region** to a single optimized best backtest; reject improvements that only work at one exact threshold.

**Relevant research:** Batten et al., *Does intraday technical trading have predictive power in precious metal markets?* (2018), found previously popular moving-average settings lacked predictive ability in their sample; some other parameter configurations for gold showed predictability. This does **not** validate our chosen configuration or imply optimization gives robust live profits. Bailey et al. document the danger of selecting a winner from many backtests.

## 2. Distinct information roles: avoid redundant "votes"

| Role | Candidate input | Decision question | Mandatory? |
| --- | --- | --- | --- |
| **Context/trend** | H1 EMA20/EMA50 and EMA slope (or one slower alternative) | Is there an observable directional regime appropriate to S1? | Provisional S1 directional hypothesis |
| **Location/structure** | Confirmed M15 pivots, preceding swing highs/lows, nearby opposing levels | Is this a real pullback or a potential reversal / crowded target? | Compute as context; hard filter experimental |
| **Entry event** | M5 impulse + retracement + *confirmed* breakout of previous 2 M5 extremes | Is a decision-ready trigger available NOW? | Proposed S1 baseline |
| **Volatility scale** | M5 ATR14 (or ATR21 alternative) | Are stop buffers, impulse and risk meaningful at the prevailing volatility? | Proposed S1 math |
| **Execution costs/safety** | Live BID/ASK, spread in R, scheduled event knowledge, feed freshness | Is there a sensible executable trade at this moment? | Correctness and user safety, with tested numeric thresholds |

**Do not count the same price trend as three independent confirmations** just because EMA, MACD and RSI all happen to agree; all are derived from much of the same underlying price sequence. Multi-timeframe calculations likewise are correlated views of the same market. Distinct mathematical roles are a design choice, **not** statistical independence.

ATR measures volatility, **not direction** (Fidelity). EMA is a smoothed price statistic, **not a causal leading indicator**. Neither should become a BUY/SELL signal by itself.

## 3. Initial recommended combination for the S1 research baseline

- **H1 directional bias:** EMA20 > EMA50, EMA20 rising and last closed H1 price above EMA50 for longs; mirror for shorts.
- **M15 structural assessment:** confirmed pivots and price relative to recent levels; classify SUPPORTIVE, CORRECTIVE, OPPOSING or UNKNOWN. **CORRECTIVE is allowed**, as it is integral to many pullback setups.
- **M5 trigger:** confirmed L→H impulse, 25–75% pullback depth and M5 candle-close continuation beyond previous 2 bars' highs/lows. Values are candidate study settings, not accepted thresholds.
- **ATR14:** normalize impulse and stop/entry tolerance. No claim that exactly 14 is optimal.
- **Actual bid/ask and costs:** mandatory feed-validity checks; broker-specific cost and risk thresholds OPEN.

The exact deterministic candidate rules and intentional changes from draft 14 are in [16 — S1 refined test contract](16-S1-refined-test-contract.md). Do not implement a disjoint combination chosen from marketing websites.

## 4. Explicitly excluded from S1 baseline

- **MACD**: overlaps H1 trend momentum; no need until incremental value is demonstrated.
- **RSI14**: may help in some strategies but cannot be assumed to improve a trend-pullback trigger; defer to separately preregistered testing.
- **ADX14**: potentially useful to distinguish trend/range; compare against already-defined EMA/structure regime before including.
- **Bollinger Bands / Stochastic / CCI**: not included by default; additional overlapping signals raise the multiple-testing burden.
- **VWAP / volume profile / order flow**: require an appropriate traded-volume dataset to mean what users often assume. Broker tick-count alone is not centralized XAUUSD exchange volume. Avoid false "institutional activity" claims.
- **SMC labels, order blocks, fair value gaps, Fibonacci grids**: no automatic inclusion or special predictive status; study only if expressed in fully causal equations and compared against simpler structure rules.
- **M1 confirmation for S1**: optional, **separate early-entry strategy variant**. It must not be part of the M5 baseline or retroactively use a future M5 candle.

Any future proposed indicator must specify: observable added information, exact formula, parameter source, causal update time, baseline comparison, incremental **net** result, and its data/maintenance cost. Otherwise reject it.

## 5. Small, pre-registered research grid — not massive parameter mining

Before looking at final holdout performance, compare **one simple diagnostic benchmark + eight bounded combinations**:

| ID | H1 bias | ATR | M15 context policy | Why test it |
| --- | --- | --- | --- | --- |
| I0 | none (M5 baseline only) | 14 | displayed only | How much does H1 add? |
| I1 | EMA20/50 | 14 | soft, not a veto | Proposed default |
| I2 | EMA20/50 | 14 | veto OPPOSING | Does a stricter M15 rule help? |
| I3 | EMA20/50 | 21 | soft, not a veto | ATR sensitivity |
| I4 | EMA20/50 | 21 | veto OPPOSING | Filter sensitivity with longer ATR |
| I5 | EMA30/90 | 14 | soft, not a veto | Slower H1 bias alternative |
| I6 | EMA30/90 | 14 | veto OPPOSING | Slower H1 plus M15 hard filter |
| I7 | EMA30/90 | 21 | soft, not a veto | Slower EMA/ATR combination |
| I8 | EMA30/90 | 21 | veto OPPOSING | Full slow/filter candidate |

All other strategy rules, pivot method, entry assumptions and exit rules must remain identical **per paired comparison**, except a parameter that is necessarily transformed by ATR scaling. **Bigger ATR can change both impulse/stop and entry thresholds; record this instead of calling it an isolated indicator test.**

"Soft" means M15 context is reported and available for later ranking, **but does not change a stand-alone S1 entry decision**. Therefore I1 vs I0 measures H1; I1 vs I2 measures the M15 veto. **Do not claim that simply displaying a higher score increased strategy profit.** Scoring thresholds/allocator decisions are a separate later experiment.

EMA30/90 is a slower **candidate**, not a literature-backed proven optimal pair. Keep every individual candidate trial in the search ledger, even ones that perform badly. Do not expand to dozens of parameters merely to find a profitable historical curve.

### Optional second research wave (not automatic feature expansion)
Only if regime confusion or entry quality remains a measured problem: compare one **ADX strength filter** or one **M5 trigger-body strength filter**, **one at a time**, against I1 and the validated strongest baseline. Do not introduce RSI/MACD automatically; evaluate only a concrete identified failure mode. Every new wave requires a newly allocated **untouched** test period, not reuse of a repeatedly inspected final holdout.

## 6. Objective measurement and selection

### Predefine
- Data periods, broker/symbol specs, market time-zone/session convention, bid/ask quote quality, transaction costs, manual delay distributions and missing-event handling.
- Execution model, stop trigger rules, market/limit order assumptions, full-exit TP2 baseline and alternatives; never optimize the fills alongside the indicator.
- Size of training/validation/untouched test windows. A short good-looking period is insufficient; require diverse conditions and uncertainty intervals rather than arbitrary claims of significance.
- Performance measure: **net expectancy per realistically eligible/fillable trade in R** as the first comparison, along with net total R at the defined risk budget, drawdown and frequency. Keep loss tails visible.
- Practical minimum frequency constraints (OPEN, must be chosen by operator), so the highest-score variant cannot "win" by generating nearly no signals.

### Compare
1. Reproduce same timestamps, data quality and executable quote assumptions across I0–I8.
2. Replay each strategy from actual availability time, not the historical pivot candle.
3. Use training/development windows only for candidate creation; hold out chronology, include distinct quiet/trending/volatile/news periods.
4. Run walk-forward on unseen windows, calculate per-market-regime net expectancy, median/worst-period results and bootstrap uncertainty by **day or session**, rather than treating clustered tick-level observations as independent samples.
5. Examine **all declined signals** and counterfactual fillability: did a hard filter avoid more losses than winning opportunities, after costs?
6. Stress variable spreads, slippage, gaps and human entry latency. One indicator set that fails as soon as costs rise is not robust.
7. Inspect parameter **neighborhoods** (are EMA20/50, EMA30/90 and ATR14/21 both reasonable?) instead of picking a single razor-thin peak. Limited alternatives only; log every attempt.
8. Reserve an untouched final holdout that is evaluated **once** after the selection policy is frozen, then conduct forward paper testing. If it fails, label the strategy unproven and establish a **new** untouched test, not re-optimize the old final holdout.

### Must report
Eligible signals per day/session; actual fillable signals; winners/losses/breakevens; net expectancy (R), gross/net profit factor, drawdown, frequency, win rate, average winner/loser, spread and latency sensitivity, expected vs realized fill differences, and count of missed winning candidates. Report confidence intervals and sample sizes for each subgroup.

### Decision standard
Prefer the simplest strategy whose **out-of-sample**, risk-adjusted net expectancy and operational resilience remain comparatively strong **across multiple market conditions** at an acceptable opportunity frequency. Do not treat a higher percentage of wins as a superior trading system if losses become more costly or drawdown becomes unacceptable.

## 7. When one combination cannot handle the market

| Regime | Proposed Grog behavior |
| --- | --- |
| Stable higher-timeframe trend + orderly pullback | S1 watch/confirm with H1/M15/M5 as specified |
| Broad sideways market | S1 remains inactive if H1 NEUTRAL; later S2 may be researched independently |
| Fast directional move without pullback | Watch but do not chase; await a **new valid structural setup** |
| News/dislocation or unreliable feed | Explain NO TRADE / monitoring risk; do not infer a safe signal from a lagging indicator |
| Conflicting H1 and M15 | S1 uses confirmed H1 direction; M15 conflict is logged and tested, not three-timeframe unanimity |

**"Works across everything" is not an acceptance target for a single S1 algorithm.** The target is *reliable decisions when S1 applies, safe abstention when it does not, and measured stability across years/sessions*.

## 8. Grok implementation discipline (future)

This is a **research brief**, not authorization to implement. When a module is approved:
- Reproduce the exact indicator formulas, warm-up, bar-close availability, pivot times and versioned config before any signal logic.
- Implement only the approved experiments and hard-coded candidate grid; do not "improve" by adding new indicators or AI components.
- Include unit tests for EMA seed vs common libraries, ATR Wilder recurrence, no-lookahead H1/M15 update, soft vs veto context, and price-side execution.
- Supply variant comparison tables, negative cases and complete search ledger; report every inconclusive result.
- Request explicit decisions for thresholds / broker metadata / cost model / risk caps rather than silently inventing them.

## 9. References (study context, not verified edge)

- Batten, Lucey, McGroarty, Peat & Urquhart (2018), *Does intraday technical trading have predictive power in precious metal markets?*, Journal of International Financial Markets, Institutions & Money: https://research.monash.edu/en/publications/does-intraday-technical-trading-have-predictive-power-in-precious/
- Bailey, Borwein, López de Prado & Zhu (2017), *The Probability of Backtest Overfitting*: https://scholarworks.wmich.edu/math_pubs/42/
- Fidelity, *Average True Range*, clarifies ATR measures volatility, not direction: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
- TradingView official technical guidance, confirmed vs realtime higher timeframe and repainting: https://www.tradingview.com/pine-script-docs/concepts/repainting/
- MetaTrader 5, real tick/bid-ask spread effects in backtests: https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation

**Research integrity:** None of these sources independently verifies that the particular Grog S1 inputs, EMA lengths, ATR lengths or nine test variants are profitable.
