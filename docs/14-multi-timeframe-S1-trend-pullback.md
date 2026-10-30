# MTF-01 + S1: Multi-timeframe trend-pullback research specification

**Version:** research draft 0.1 (2026-10-30)  
**Status:** Multi-timeframe analysis = APPROVED direction. Exact formulas, thresholds, entries and exits below = **PROPOSED / EXPERIMENTAL**, NOT approved or proven profitable. **Documentation only; no implementation authorized by this document.**  
**Audience:** Grog planning reviewers and Grok implementation assistant.

> Objective: select and monitor better manual XAUUSD scalping trades, not build a general platform. Every rule must be definable, observable at signal time, testable, explainable, and justifiable by incremental out-of-sample improvement.

## 1. Key design rule: context is not unanimity

- **H1:** principal directional *bias* for the trend-continuation strategy.
- **M15:** context, prior structural levels, whether the smaller move is a correction or a dangerous contradiction.
- **M5:** detect the impulse, pullback and baseline actionable trigger.
- **M1:** optional, separately tested **early-entry variant**, not a mandatory extra confirmation.
- **Bid/ask ticks:** quote freshness, actual signal price/expiry, spread and fill-aware live monitoring.

A bullish H1 + bearish/corrective M15 + bullish M5 reversal **may be desirable**. Requiring all timeframes to show green candles would systematically exclude pullbacks. Distinguish a *healthy correction* from a *larger thesis invalidation* by a defined structural rule, not color alone.

**Default test hypothesis:** H1 establishes direction; M15 mainly changes quality assessment; M5 confirms. M1 is off in baseline. Compare alternatives in Section 11; do not assume adding timeframes raises accuracy.

## 2. Data and causal (no-lookahead) contract

1. Normalized quote event: `{provider_ts_utc, received_ts_utc, sequence, symbol, bid, ask, feed_quality}`. Reject nonsensical quotes, mark gaps/staleness.
2. Derive bid-side and ask-side OHLC for M1, M5, M15 and H1 from the **same** provider event stream, using UTC half-open intervals `[bar_start, bar_end)`. Bid bars are the default analysis reference; retain ask history for executable stop/exit modeling. Do not mix incompatible feeds without an explicit mapping.
3. A bar is **confirmed** only after the period ends and the stream has advanced past that end. Evaluate bar-close signals on the **first valid event after close**, not at a hypothetical earlier fill price. If no tick arrives or a gap is detected, do not invent a favorable fill.
4. At decision time `t`, use only fully finalized bars with `end <= t` whose actual `available_at <= t`. Do not use completed bars that arrived late before they were truly available. Unfinished H1/M15/M5 candles may be displayed as **provisional**, never as finalized evidence for a READY signal.
5. All derived pivots/levels have `pivot_time`, `confirmed_at` and version. No backdating availability to the pivot candle.
6. Capture a snapshot `{decision_ts, last_confirmed_H1, M15, M5, M1, indicator_versions, data_quality}` for every candidate/READY/rejection decision.
7. If timestamp order, history completeness or feed freshness is untrustworthy: mark WATCH/UNAVAILABLE, **suspend new actionable signals**, preserve open-position records and show monitoring limitations.

**Time alignment example:** At 10:07:20 UTC (assuming valid uninterrupted data), available last completed candles are H1 09:00–10:00, M15 09:45–10:00, M5 10:00–10:05 and M1 10:06–10:07. The H1 10:00–11:00 candle is **not** confirmed. At exactly 10:15 UTC, the 10:00–10:15 M15 candle only becomes usable after feed advancement/finalization.

This contract applies to live execution, historical replay and tests. The software is not Pine Script, but the same kind of higher-timeframe future leakage/repainting documented by TradingView must be prevented.

## 3. Initial indicator set (not a signal by itself)

- H1 **EMA20** and **EMA50** on *confirmed H1 bid closes*. EMA recurrence: `EMA_t = alpha*C_t + (1-alpha)*EMA_(t-1)`, `alpha=2/(N+1)`. Record the seed and warm-up policy so replay matches live.
- H1/M5 **ATR14**, using confirmed bid bars, Wilder recurrence after initial average: `TR_t=max(H_t-L_t, abs(H_t-C_(t-1)), abs(L_t-C_(t-1)))`; `ATR_t=(13*ATR_(t-1)+TR_t)/14`.
- M15 and M5 confirmed swing highs/lows plus distance to levels. A width-(2 left,2 right) pivot high at bar k requires `high[k] > high[k-2], high[k-1], high[k+1], high[k+2]` and similarly strict lower-than comparisons for lows. It becomes known only once `k+2` has closed; equal extrema are not pivots in this initial candidate. `left/right=2` is an experiment, not a market fact.
- Trend strength features: `ema_gap_atr=abs(EMA20-EMA50)/ATR14_H1` and `ema_slope_atr=(EMA20_t-EMA20_(t-3))/ATR14_H1`, when ATR positive. These are descriptive quality features; thresholding needs tests.
- For accurate EMA initialization, use a reproducible warm-up (e.g. enough H1 candles to stabilize EMA50). If insufficient bars, label bias UNKNOWN rather than silently using short-history EMAs.

**Do not add RSI, MACD, ADX, VWAP, volume-profile or institutional/SMC labels to S1 by default.** Research separately only if the simpler baseline is insufficient, with an ablation experiment.

## 4. H1 bias state (initial deterministic candidate)

Using the latest **confirmed** H1 bar t:

- `UP` if `EMA20_t > EMA50_t`, `EMA20_t > EMA20_(t-3)`, and `Close_t > EMA50_t`.
- `DOWN` if all three inequalities reverse.
- `NEUTRAL` if mixed and sufficient data exist.
- `UNKNOWN` if data or minimum history is insufficient.

The normalized EMA gap/slope quantify *strength* but do not impose an extra mandatory filter in baseline. S1 BUY READY requires `UP`; S1 SELL READY requires `DOWN`. `NEUTRAL` may still show a developing market observation but never force S1.

**Research warning:** This is a reproducible regime hypothesis, not an independently validated predictor. H1 can remain UP during an intrahour reversal; M15 structural risk and current spread/volatility must be assessed.

## 5. M15 structural context (not an all-green requirement)

Use only M15 pivots that have already been confirmed at decision time.

For a BUY candidate, describe M15 as:
- **SUPPORTIVE**: higher confirmed swing-low structure, or confirmed close above M15 EMA20, with no clear structural breakdown. This is positive context.
- **CORRECTIVE**: price is pulling back against H1 UP, but remains above the last relevant confirmed M15 structural low. This is a legitimate pullback, not an automatic rejection.
- **OPPOSING**: at least one confirmed M15 close breaks below the last relevant confirmed M15 swing low **and** M15 EMA20 is declining. Flag conflict and downgrade quality; how strictly to block is OPEN pending ablation.
- **UNKNOWN**: insufficient confirmed pivots/EMA or ambiguous state.

SELL is mirrored. Tie-breaking priority: OPPOSING > CORRECTIVE > SUPPORTIVE > UNKNOWN when candidate conditions overlap; the exact definition of the last *relevant* pivot (recency, distance, reuse) is **OPEN**, must be frozen before Grok implements scoring.

Always calculate distance to the closest confirmed opposing M15 structural level in the proposed trade direction; show target congestion. A nearby level is not automatically a veto until testing demonstrates the benefit.

## 6. S1 M5 setup: proposed fully observable baseline

### BUY example (SELL is mirrored)
1. H1 bias `UP`. Existing quotes, risk metadata and trading-hours checks are healthy.
2. On a completed M5 bar, select the most recent **confirmed** swing low `L` followed by a confirmed swing high `H` using Section 3. Keep the exact pivot/confirmation timestamps and selected-pair ID.
3. Define upward impulse distance `I = H.bid_high - L.bid_low`. Preliminary impulse criterion: `I >= 1.0 * ATR14_M5` measured at `H.confirmed_at` and `H` occurs at most 12 M5 bars after `L`. These numeric values are **experimental defaults**.
4. Starting after H's actual pivot bar, track the *completed* M5 pullback-bar minimum `P` (low). Require at least 2 closed M5 bars in the pullback, `L.bid_low < P < H.bid_high`, and preliminary retracement `d=(H.bid_high-P)/I` between `0.25` and `0.75`. H confirmation normally overlaps early pullback bars; **never** retroactively declare a READY signal during those bars.
5. Emit a **FORMING** candidate with fixed `L,H` pair, current pullback low P, age, and pending trigger. If P falls below 25%/above 75% as measured from H, update state and reason; after >75% or break of L invalidate the frozen candidate. A subsequent independent pivot-pair can create a new candidate but must not resurrect an expired signal.
6. **Baseline M5 trigger** on a *newly closed* bullish M5 candle: close above the greater of the preceding two completed M5 highs; candle close > open; candle's low has not breached the previously tracked P by more than a configured allowance (initial candidate allowance=0). Evaluate against **previous** bars before incorporating trigger-bar extremes in P, to prevent self-reference.
7. If M15 opposing, retain a warning/quality penalty for baseline research rather than silently blocking. If higher-timeframe structural invalidation, feed outage, disallowed macro event window, or cost hard-gate occurs, **NO READY SIGNAL**.
8. At the first valid quote after the trigger's bar close, quote **BUY entry at ASK** with an allowable entry band and expiry. Do not claim the completed bar's close was an executable fill. Preliminary no-chase bound: `ask_at_signal <= trigger_bid_close + 0.20*ATR14_M5`. This is a test parameter, not a promise.
9. Determine long stop using bid-side completed pullback structure: `SL = min_pullback_bid_low - 0.10*ATR14_M5` rounded **downward** to valid broker price increment. Validate `SL < current_bid`. Short uses ask-side pullback high plus buffer, rounded upward, because short stops are triggered on the **ASK**.
10. Risk in XAUUSD price units: `R_long = entry_ask - SL`; `R_short = SL - entry_bid`. Must be positive. Candidate benchmark TP1 and TP2: long exit on BID at `entry_ask+1R` and `entry_ask+2R`; short exit on ASK at `entry_bid-1R` and `entry_bid-2R`. Convert these to valid price ticks. Account separately for commissions, slippage and latency in reported **net** reward/risk. Structural levels between entry and target must be displayed and experimentally assessed as possible congestion.
11. Re-check eligibility and entry-band validity on every new quote until manual entry or expiry. Initial expiry hypothesis: first of material invalidation, excessive price chase, or end of the next completed M5 bar (not a guaranteed optimal TTL). Record missed/expired signals and do not turn them into hindsight wins.

### SELL mirror
H1 DOWN; confirmed M5 swing high then later low; pullback high P; bearish completed M5 close below min(previous two M5 lows); short entry at BID; stop above **ASK**-side pullback high; targets based on closeable ASK prices. Tests must enforce full long/short symmetry while preserving bid/ask asymmetry.

### Critical unresolved rules
Before implementation, freeze pivot pair replacement and competing candidates, exact market-level relevance, stop buffer/spread and commission conventions, eligibility thresholds and trigger-bar stop-reference handling. Grok should not invent these. These open items can be researched using an initial narrow candidate grid and then explicitly approved.

## 7. M1 faster entry is a **separate experiment**, not mandatory

M1 early entry must never justify itself with a future M5 candle close. Test an alternate path:
- H1 confirmed trend; M15 known context; M5 already FORMING based solely on previously confirmed M5 evidence.
- An M1 candle **closes** past the last completed M1 swing/2-bar extreme in the trend direction, with valid bid/ask spread and an unbroken frozen M5 setup.
- Issue provisional early READY only when that branch has its own specified entry/stop/expiry and measured quality. Do **not** label it the same as a M5-confirmed entry.
- Compare time-to-entry, slippage, opportunities, failure rate and net expectancy versus the baseline M5-close trigger. Do not promote M1 merely because entries look earlier.

Until that experiment is accepted, M1 data can support live visualization but not independently authorize entries.

## 8. Risk gates versus ranking

**Hard gates:** malformed/stale feed; invalid market hours/instrument specs; invalid direction/setup/stop; clearly expired or already entered signal; unacceptable actual spread/estimated trading cost; known high-risk event restrictions; pre-agreed exposure limits. Values for spread and event windows remain OPEN until broker data and research.

**Evidence / scoring (soft, except H1 direction in S1):** normalized H1 trend strength, M15 supportive/corrective/opposing, M5 impulse/retracement quality, target congestion, entry lateness, spread as percentage of R. Integrate these into the existing versioned quality rubric in `06-signals-and-scoring.md`. **A score of 85/100 is not an 85% probability of winning.**

Avoid redundant vetoes that shut down all signals. Report trades per day/session and missed profitable opportunities in every test.

## 9. Live-monitoring expectations

Upon user-confirmed fill, store actual execution-side price, timestamp, position size, initial SL and target(s). During monitoring:
- Show last **BID** mark for long close and **ASK** for short close, and actual open-trade R/P&L only when contract metadata are available.
- Warn when M5 continuation fails, M15 structure breaks against the held trade, H1 bias changes on a *new confirmed H1 bar*, volatility/spread spikes, known event risk approaches, or TP/SL touch occurs.
- Warning is **not** an automatic order and not necessarily an exit recommendation; exit/hold rules require separate independently backtestable specifications.
- A touched price is **not** a confirmed broker fill; user updates partial/closed state. Reconcile after offline intervals.

## 10. Observable examples for user acceptance

- **Healthy corrective long:** H1 UP; M15 CORRECTIVE (its latest candle is bearish but relevant structural low intact); M5 pullback + confirmed bullish trigger; costs acceptable → BUY may become READY with a lower M15-context score. **Do not require a bullish M15 candle**.
- **Against higher trend:** H1 DOWN; bullish M5 trigger → no S1 BUY READY; can remain an untraded observation for future strategy study.
- **Unconfirmed higher candle:** H1 current intrahour bar temporarily UP but last confirmed H1 is DOWN → no S1 BUY READY.
- **Same-bar pivot hindsight:** M5 pivot high needs two subsequent M5 bars; backtest cannot emit signal before the second bar closes.
- **Late manual entry:** quote/actual fill beyond recorded entry band → label late/off-plan and recompute R/R; never rewrite original signal.
- **Spread doubles:** fresh quote pushes costs beyond configured limit → READY invalidated or suspended; record reason; never count at old spread.
- **Partial history:** cannot initialize stable EMA/ATR or M15 pivot → UNKNOWN and cannot fake confidence.
- **Restart:** previously entered position reappears as needing reconciliation, not automatically CLOSED or still actively monitored.
- **Simultaneous TP/SL in OHLC candle:** do not claim a win without real-tick order of events; mark indeterminate/skip until tick evidence or conservative documented treatment.

## 11. Required experiments before approving parameters

| Experiment | Setup | What to compare |
| --- | --- | --- |
| B0 | M5 price-structure pullback trigger alone | Baseline frequency, expectancy, loss distribution |
| B1 | B0 + confirmed H1 directional bias | Incremental net expectancy, missed winning trades, drawdown |
| B2 | B1 + M15 level/context score | Improvement vs overfiltering; session/regime stability |
| B3 (optional) | B2 + separately specified M1 early-trigger variant | Earlier executable fills vs noise, costs and false signals |
| Robustness | Spread inflation, manual delay, major announcements, regime changes | Profit stability after actual costs and latency |

Test on chronological unseen broker-matched bid/ask ticks, including sessions and rare volatile days. Record parameter trials and avoid repeated tuning to the final holdout. Report net expectancy (R), profit factor, max drawdown, entry lateness, win rate, signal frequency and confidence intervals. A higher win rate with worse expectancy is **not an upgrade**.

**Acceptance condition:** Only promote MTF features that beat the simpler S1 baseline robustly out of sample *after costs*. If a timeframe/indicator hurts outcomes or loses too many favorable trades, remove or relax it.

## 12. Source notes and research limitations

- TradingView on confirmed HTF data and lookahead/repainting: https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/ . The causal lesson applies to Grog's own aggregator, even though Grog will not run Pine.
- MetaTrader 5 real vs generated ticks and variable bid/ask spread: https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation
- Batten et al. (2017), intraday periodicity in precious-metal returns, volatility and spreads (historical sample, **not** direct support for any strategy): https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0174232
- Bailey et al., probability of backtest overfitting: https://escholarship.org/uc/item/4w1110bb

**No cited material proves this S1 strategy is profitable.** Source-backed points concern timing, data realism and testing pitfalls; S1 formula and thresholds are deliberately proposed hypotheses.

## Important follow-up: S1 failure-mode audit

See [15 — S1 failure modes and robustness](15-S1-failure-modes-and-robustness.md) for specific false-breakout, regime reversal, execution/spread, late-entry, news and over-filtering scenarios, proposed adversarial fixtures T01–T20, comparative tests, and unresolved rule ambiguities from this document. **Draft 14 is a hypothesis, not a final implementation contract.** In particular, pivot pairing, target conventions, trigger-bar stop references, full entry band and suspended-state semantics remain OPEN. Implementing them without explicit decisions would contradict our planning-first policy.

## 13. Grok handoff rules

This file is a *research specification*, not an instruction to implement now. Before creating code, the implementation prompt must:
1. Name the agreed revision of this document and exactly which OPEN items were approved.
2. Limit work to one module (e.g. confirmed-bar MTF aggregator, then H1 bias, then M15 context, then M5 S1 detector).
3. Include input/output schemas, deterministic event-time semantics, pseudocode/tests and negative cases.
4. Refuse future data, retroactively redrawn trades, hardcoded profitability claims, broker order execution, AI APIs or unrelated product features.
5. Report back exact files, commits, test results and unresolved decisions without silently altering strategy criteria.
