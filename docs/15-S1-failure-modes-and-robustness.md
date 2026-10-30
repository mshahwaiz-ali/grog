# S1-F — Failure modes, false signals, execution realism, and anti-overfiltering

**Version:** research draft 0.1 · 2026-10-30  
**Status:** RESEARCH / PROPOSED. No strategy parameter, filter, threshold or performance claim is approved. This is **not** a completed backtest and **not** authorization to implement.  
**Depends on:** [14 — MTF + S1 specification](14-multi-timeframe-S1-trend-pullback.md), [03 — market data](03-market-data.md), [06 — signal engine](06-signals-and-scoring.md), [08 — validation](08-validation.md).  
**Product scope:** Better **manual XAUUSD scalping decisions**; no AI agents, wallets, signal-copying, auto-execution, unnecessary indicators or platform features.

## 1. Purpose and falsifiable objective

Find the smallest set of causal conditions that improves S1's **net expectancy after realistically simulated bid/ask costs and manual latency**, while preserving useful trade opportunity frequency.

**Non-negotiable:** A strategy that generates few but excellent-looking historical signals is not automatically better. Evaluate skipped winners and skipped losers, *and* the effect on average R, total net R, drawdown, and opportunity frequency. No invented 90% probability or guaranteed profitable trading.

Source-backed concerns:
- TradingView explicitly documents unconfirmed-bars, higher-timeframe information, and retroactively shifted pivots as possible causes of historical/realtime discrepancies [R1].
- MetaTrader documents that real broker ticks capture spread changes within a minute, whereas generated ticks can use a fixed minute spread [R2].
- World Gold Council reports 2026 increases in gold volatility and episodic spread widening, especially around thinner hours [R3].
- CME reports wider daily movement distributions on macro-release days for its historical GC futures sample; futures results are context, not identical broker XAUUSD fill statistics [R4].
- Research into backtest selection bias warns that adding many tried rules/configurations can inflate apparent historical profitability [R5].

## 2. Adversarial threat model: how a legitimate-looking setup loses

| ID | Failure | Why it happens | Observable pre-entry evidence | Proposed response / test | Type |
| --- | --- | --- | --- | --- | --- |
| F01 | Repainting/HTF hindsight | Uses unfinished H1 or a pivot not confirmed until later | `available_at > decision_ts` | Block READY; record data provenance | correctness hard gate |
| F02 | Stale trend | H1 EMA UP but M15 is structurally turning down | Break of confirmed M15 low, declining M15 structure | Display OPPOSING; compare score penalty vs strict blocking | soft experiment |
| F03 | False M5 breakout | One M5 close above two-bar high immediately fails | Weak body, very long adverse wick, nearby prior level | Compare baseline trigger vs optional strength/retest confirmation | experimental |
| F04 | Trend exhaustion | Pullback entry occurs after prolonged/extended impulse | ATR-normalized distance to opposing H1/M15 level; repeated failed pushes | Test congestion/distance-to-target penalty, not automatic veto | soft experiment |
| F05 | Pullback actually reverses | Retracement becomes structural break rather than correction | Confirmed key level breached, original candidate low/high invalidated | Hard strategy invalidation when frozen reference level breaks | strategy rule |
| F06 | Stop too tight/noise | Stop near ordinary Gold fluctuation and spread | Stop distance relative to ATR, spread and observed MAE | Compare buffer choices; preserve position risk | experimental |
| F07 | Poor bid/ask economics | Signal at candle close ignores spread and execution side | Spread-to-risk and estimated roundtrip cost in R | Block only after **empirically justified** cost limits | proposed gate |
| F08 | Manual entry too late | By the time operator enters, price has run away | New actual bid/ask and elapsed time after first READY | Expire/chase warning; recompute original plan using actual fill | proposed gate |
| F09 | Target blocked | Target lies beyond close opposing structure | Distance to nearest historical opposing pivot/level | Display congestion; test TP proximity; reject only proven bad ranges | soft experiment |
| F10 | Event-driven whipsaw | Important macro surprise creates rapid reversals and spread jumps | Known event time, realized jumps and quote quality | Test news/no-news window comparisons; no magical prediction | experimental |
| F11 | Transition/chop | Trend signals alternate in direction around unclear regime | H1 bias change rate, repeated opposite structure breaks | Test stability/chop penalty; don't demand every timeframe agrees | soft experiment |
| F12 | Data gap / out-of-order ticks | Market moves unseen or wrong bar formed | Receive/provider time lag; missing bars; sequence anomaly | Block READY; show MONITORING UNAVAILABLE on unreliable feed | correctness hard gate |
| F13 | Spread-only stop/target touch | Bid and ask differ from chart's displayed mid-price | Bid/ask extremes at actual trigger time | Use broker-side trigger rules; never claim mid-price fill | correctness hard gate |
| F14 | Same-minute stop AND TP | OHLC doesn't reveal hit order | Both thresholds inside same OHLC | Tick reconstruction or indeterminate, never presume a win | correctness hard gate |
| F15 | Simultaneous overlapping signals | Different pivot pairs create duplicate long or contradictory short | Same symbol/time/direction/overlapping risk zones | Single active candidate per structural pair; record supersession | execution policy OPEN |
| F16 | Over-filtering | Many confirmations suppress legitimate profitable trades | Missing-trade counterfactuals by gate | Measure filter ablation and net opportunity cost | design principle |

These are hypotheses and observable failure classes, **not evidence that a particular filter improves profitability**. Classifying an event as a 'false breakout' *after* the fact must not give Grog future knowledge before entry.

## 3. Safeguards: hard gates are few, soft evidence is measured

### 3.1 Correctness hard gates (must pass to issue READY)
- Quote source valid, feed fresh, bid/ask internally consistent, timestamps causally available.
- H1 bias agrees with S1 direction, when that rule is part of the tested S1 configuration.
- Strategy's frozen price structure and entry trigger remain intact **as of decision time**.
- Symbol metadata sufficient to calculate valid entry, stop, roundtrip cost, price precision and reward/risk. Otherwise watch but do not propose sizing.
- No duplicate/expired/previously-entered signal; entry not already invalidated.
- Actual known spread/execution/approved risk constraints pass **only once precise, tested thresholds are frozen**.

### 3.2 Soft evidence (do not create default veto)
- M15 SUPPORTIVE / CORRECTIVE / OPPOSING; corrective against H1 is expected for pullbacks.
- Strong vs weak trigger candle: body-to-range, close location, immediate historical level congestion.
- H1 trend strength and M15 opposition; age of impulse; retracement depth.
- Spread/R, volatility regime, session, distance to opposing structure.
- Number of recent failed continuation attempts; **do not claim to observe institutional intent**.

### 3.3 Experimental confirmations
Research these separately, not all at once:
- **E1: Trigger quality:** require bullish close above prior two M5 highs as baseline; compare with minimum body/range and/or close position within candle (both numbers OPEN).
- **E2: One-bar sustain:** evaluate whether waiting for a subsequent completed M5 candle improves net returns after lost entry price and fewer opportunities. A *retest* is an alternative entry branch, not a condition to tack onto every signal.
- **E3: Structural buffer:** stop beyond frozen pullback extreme with ATR-scaled buffer; compare narrow/medium/wide stop within same risk budget.
- **E4: Congestion warning:** opposing M15 levels close to TP1/TP2; test alternate attainable targets or ranking.
- **E5: Session/event context:** analyze by session and event proximity; reject only if time windows show robust degradation.

Do not automatically promote additional EMA, RSI, ADX, order blocks, FVG or volume-based sentiment. Each must show incremental evidence against this stripped-down baseline first.

## 4. Signal-state behavior during adverse conditions

`DETECTED -> FORMING -> READY -> {ENTERED, SKIPPED, EXPIRED, INVALIDATED}`.
- FORMING can remain a watched opportunity as pullback evolves. It may become INVALIDATED without ever issuing READY.
- READY has **immutable first-issued values** (time, quote, price bounds, stop/targets, evidence, rule version) plus **mutable current eligibility** (health, price distance, spread, remaining TTL). Do not rewrite the historical original signal as if it was better.
- If an execution hard gate fails before user confirms entry: `SUSPENDED` or `INVALIDATED` **as a reason/status overlay**, depending on reversibility. Whether SUSPENDED is a separate persisted state remains OPEN; do not invent transitions when implementing.
- Revalidation after recovery may only restore the **same** READY signal if its original deadline, original entry band and underlying setup are still valid; otherwise it expires and a **new structural setup** is required.
- An entered position remains in the journal even if the strategy's new signal eligibility changes; monitoring ≠ broker execution and ≠ guaranteed fill detection.
- Operator may enter *off-plan*. Record actual fill, label the deviation, recompute real R and warn rather than pretending the original recommendation was filled.

## 5. Non-chasing and trade economics — worked hypothetical

**Illustrative only; not a live XAUUSD quote.**

Proposed long signal:
- Quote at READY: BID = 4000.00, ASK = 4000.20 (spread = 0.20).
- Suggested executable entry `E=4000.20`, stop based on BID `S=3998.00`, target BID `T=4004.60`.
- Gross initial risk `R0=4000.20-3998.00=2.20`; gross target reward `4004.60-4000.20=4.40=2.0R`, **before fees and slippage**.
- Trader manually buys later at `E_actual=4001.10`, while the original target and stop remain fixed: actual risk `R_actual=4001.10-3998.00=3.10`; gross target reward `4004.60-4001.10=3.50`; gross reward/risk `3.50/3.10 ≈ 1.13R`.
- Thus a visually '2R signal' may become only **~1.13R before fees** after manual delay. **Never silently increase the TP merely to recover a 2R label.**

**Executable side:** long BUY uses ASK entry and BID stop/target exit; short SELL uses BID entry and ASK stop/target close, subject to broker-specific product and trigger conventions. Keep stop crossing separate from actual broker execution; stops may slip, and an unconfirmed target touch is not an executed fill.

**Proposed re-evaluation:** before confirming `ENTERED`, display current executable quote, distance to original suggested entry, remaining plan validity, spread, updated risk and expected net reward. If the operator enters anyway, store it as an off-plan fill; do **not** retroactively alter the signal's original quality score or candidate count.

## 6. More precise S1 failure definitions (needed before implementation)

- **Impulse structure:** confirm the L→H pair *before* forming READY; record pivot identity, confirmation timestamp, whether H remained the most recent structural high, and all bars considered.
- **Pullback end:** define when the low P is frozen. The M5 trigger bar's new low must not alter the frozen stop/reference after the trigger was declared. This avoids a self-referential condition.
- **Countertrend correction vs reversal:** `M15 CORRECTIVE` is not `M15 OPPOSING`. For research, use last confirmed structural-low break plus declining M15 EMA for opposition. Exact swing recency/window/tie-breaking are OPEN.
- **False continuation outcome:** define objectively *after entry* as first confirmed broker-side exit being the protective stop before the planned tested target horizon; classify break-even/time-stop/indeterminate separately. This outcome classification must never be used as information at signal time.
- **Trigger weakness:** a historical candle whose close is above preceding highs is still eligible under BASELINE. Additional wick/body/sustain checks are optional experiments.
- **Candidate invalidation:** a confirmed contradiction of the frozen structural thesis must cancel readiness even if H1 EMA has not updated. Define exact real-time invalidation observable without future pivots before coding.
- **Profit targets:** distinguish experimental fixed 1R/2R benchmark from structural M15 resistance/support. If a nearer barrier exists, test a documented structural target variant; do not cherry-pick after the outcome.
- **Stop buffer:** calculate direction-specific bid/ask trigger prices and include broker price precision plus fees/slippage; stop distance and quality score are separate from position size.
- **TTL:** define absolute timestamp (UTC) at READY. Review as price changes, not by waiting for a next signal refresh. A late operator entry must be reported as off-plan, never erased.

## 7. Adversarial scenario matrix — expectations for Grok's future tests

All values below are synthetic fixtures. **Expected results are specification assertions**, not real backtest returns.

| Case | Fixture | Expected outcome |
| --- | --- | --- |
| T01 | H1 UP confirmed, M15 corrective, M5 trigger closed | Eligible after normal gates: **do not reject solely because M15 bearish** |
| T02 | H1 previously UP but current unfinished H1 turns DOWN | Continue using previous confirmed H1; no future leak |
| T03 | Pending pivot H with only one right-side M5 bar | May display tentative structure; cannot mark H confirmed or issue READY dependent on it |
| T04 | M5 wick crosses trigger but candle closes below threshold | Not READY in closed-bar baseline |
| T05 | M5 trigger closes above high; immediately following bid crosses frozen invalidation | Cancel original READY; do not keep outdated BUY label |
| T06 | Price gaps higher between trigger close and first quote | First observed ASK used, no fictional fill at trigger close |
| T07 | READY long BID 4000.00/ASK 4000.20, actual BUY 4001.10 | Preserve original plan, compute **~1.13R** to fixed 4004.60 target |
| T08 | Spread expands above frozen accepted ceiling while READY | Suspend/expire according to reviewed state policy; no new in-band entry shown |
| T09 | M15 opposition without complete hard thesis failure | Warning/score change, not mandatory hard veto in baseline |
| T10 | Target 2R lies beyond much nearer M15 resistance | Show congestion, compare target variants; no unsupported 'guaranteed TP' |
| T11 | News release occurs, no historical calendar record known as-of the signal | Do not introduce future event knowledge or retrospectively remove that trade |
| T12 | Known high-risk event soon, accepted blackout rule active | No new READY if official event schedule known in advance |
| T13 | M1 flickers bullish while M5 not confirmed | No M5 READY; separate M1 variant only if approved |
| T14 | Feed stale or gap, even though chart visually attractive | No new READY; active monitoring marked degraded |
| T15 | Both stop and target within same minute OHLC bar | Outcome indeterminate without tick order; do not award profit |
| T16 | Long target hit on mid but BID never reaches target | No verified TP touch, no assumed fill |
| T17 | A strategy filter removes 70% of losing trades but 90% of profitable trades | Report rejected winners as well as losers; judge **net economic result**, not filter precision alone |
| T18 | Identical tick replay twice with same frozen config | Identical candidate timestamps, signals, expiry reasons and outcome classifications |
| T19 | Restart with manually confirmed open position | Display reconciliation required; never assume its status since last quote |
| T20 | Changing threshold after inspecting holdout | Prohibit promotion; treat changed model as a new version needing a fresh untouched test |

## 8. Experiments to distinguish actual improvements from decoration

**Freeze** benchmark versions and economic outcome conventions *before* running tests:
- **A0:** Basic causal M5 pullback-and-confirmation with correct bid/ask costs (no H1 gate, no M15 ranking). It is a diagnostic baseline only.
- **A1:** A0 + confirmed H1 bias.
- **A2:** A1 + M15 context as a **soft rank** (do not drop all corrections).
- **A3:** A2 + proposed candle-strength quality *alone*.
- **A4:** A2 + proposed level congestion logic *alone*.
- **A5:** A2 + proposed realistic entry/chase policy *alone*. Where appropriate, apply cost/correctness constraints to **all** benchmarks so comparisons are fair.
- **A6:** A2 + each separately validated addition. Do not treat a filter as valuable only because its training-set loss rate fell.
- **A7 (optional):** M1 early entry is a completely separate hypothesis and cannot 'borrow' the M5-close outcome.

Research steps:
1. Collect broker-matched tick samples from **multiple** market regimes/sessions and known high-impact event windows. Validate timestamps, spread, gaps and broker contract metadata.
2. Pre-register historical windows (development, rolling walk-forward, untouched final holdout) and trial budget. Do not keep testing dozens of variants on the same holdout.
3. Simulate one immutable original signal record per decision, plus later manual-fill latency scenarios (e.g., immediate, moderate, delayed)—**delay values OPEN** until user-workflow observation.
4. Use consistent stop/TP execution, slippage and fee model, chosen prospectively; report sensitivity to poorer spreads, delayed fills and cost stress.
5. Report both **signals offered** and **trades assumed filled**; entry-band policy can make offered signals unfilled. Avoid comparing an "all filled" variant to an "only good fills" variant without correcting selection bias.
6. Stratify by session, volatility and trend versus transition; disclose counts and uncertainty, avoid announcing an edge from a tiny subgroup.
7. Compute net expectancy in R; gross/net profit factor; max drawdown; trade frequency and *zero-signal days*; max loss; average winner/loser; MAE/MFE; score calibration if probability estimates are attempted; fill delay sensitivity; rejection opportunity cost.
8. Apply a realistic forward paper test. **No claim of high accuracy or profitability** until this happens.

### How to measure an added filter without fooling ourselves

For each evaluated filter store:
- `n_eligible_before`, `n_eligible_after`, accepted and rejected trades (and reason codes).
- Counterfactual results of **both** rejected and accepted signals under the same fill/cost assumptions.
- Change in net expectancy, total net R (at the chosen risk schedule), max drawdown, per-session performance and signal frequency, plus uncertainty estimates.
- Optional *attribution* analysis of how often the filter's rejected cases overlap with other filter reasons; avoid counting the same eliminated trade several times.

The promotion criterion is **better stable out-of-sample net risk-adjusted performance at an acceptable opportunity rate**; a mathematically higher score or smaller sample loss rate is not sufficient. Exact numerical thresholds remain OPEN until data availability and research are agreed.

## 9. Known unresolved specification issues in draft 14

Grok MUST NOT silently invent answers. This is a **review checklist** for our next decision cycle:

1. **Pivot pairing:** if multiple L→H candidate pairs overlap, which is frozen, replaced or suppressed? At what timestamps?
2. **M15 'relevant' level:** exact last-level selection, strict equality/tick rounding, stale pivot lifetime and duplicate clusters.
3. **P tracking:** whether M5 bars between H pivot and H *confirmation* count as pullback; ensure no retroactive READY.
4. **Trigger-bar stop reference:** if trigger bar temporarily makes a new low/high, can original stop be recalculated? Proposed: no retroactive rewrite; freeze at signal time with explicitly available bars.
5. **Quote availability:** how long after M5 close may first bid/ask arrive before considering the signal stale?
6. **Price chase:** draft 14 uses a preliminary upper bound for long entries; determine consistent lower/upper valid entry range and symmetric short policy; include both spread and structural invalidation.
7. **Risk target:** experimental 1R/2R benchmark vs nearest opposing structure; select pre-signal, not post hoc.
8. **Active signal behavior:** temporary spread spike could suspend readiness; define whether reactivation is allowed and immutable state transitions.
9. **Event context:** decide event source, real as-of times and validated event window tests; don't assume an unavailable news source is safe.
10. **Trading product:** spot XAUUSD/CFD broker mapping, lot/contract definitions, bid/ask stop-trigger semantics and actual execution costs.
11. **Execution model:** define signal-to-human delay distributions, market/limit order assumptions, missed fills and uncertainty in fills.
12. **Stop/TP priority:** ensure broker-tick order used; fallback for ambiguous historical bars must remain conservative/indeterminate, not biased.
13. **Timeframes and thresholds:** experimental values are not approved simply because this document is detailed.

Until these decisions are resolved, no S1 strategy logic should be generated as 'production ready'. Initial deterministic data/replay foundation can be planned independently.

## 10. No-feature-creep rule

Propose a future change only if it (a) changes a measurable trade decision or realistic outcome, (b) has a simple observable calculation, (c) can be isolated in an A/B or ablation test, and (d) justifies operating/data cost. Reject vendor imitations, opaque certainty scores, more indicators 'for confirmation', high-frequency designs, LLM/AI, wallets, auto brokers and cosmetic 'smart money' classifications.

## 11. Credible reference sources

- **[R1]** TradingView, Repainting, explains why live unfinished candles / pivot markers can differ from historical plots: https://www.tradingview.com/pine-script-docs/concepts/repainting/
- **[R2]** MetaTrader 5, Real and Generated Ticks, broker bid/ask execution and within-bar variable spreads: https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation
- **[R3]** World Gold Council (2026), *Has gold's performance structurally changed?*, volatility and spread trends in 2026: https://www.gold.org/goldhub/gold-focus/2026/04/you-asked-we-answered-has-golds-performance-structurally-changed
- **[R4]** CME Group (2024), *Using Metals Weekly Options to Hedge Event Risk*, historical GC movement on release days: https://www.cmegroup.com/articles/2024/using-metals-weekly-options-to-hedge-event-risk.html
- **[R5]** Bailey et al. (2015), *The Probability of Backtest Overfitting*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- **[R6]** FINRA, order types/execution price/slippage (equities context; general execution principle, not a XAUUSD broker guarantee): https://syndication.finra.org/content/understanding-order-types-can-save-time-and-money

**No external source establishes a profitable S1 edge.** Source-backed concerns motivate tests; proposed filters and parameter choices are not literature-derived guarantees.

## 12. Handoff boundary to Grok

This document gives an **adversarial test specification**, not a coding instruction. An eventual Grok prompt must explicitly freeze rule versions/OPEN decisions, demand time-causal deterministic fixtures for T01–T20, compare variants against benchmarks, and report failures without rewriting the trading definition to make backtests attractive. No agent runtime, automated trading or changes outside approved scope.
