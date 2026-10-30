> **ARCHIVED ON 2026-10-30 — NON-AUTHORITATIVE HISTORICAL RESEARCH.** Do not use this draft as an implementation contract. See the canonical [Analysis](../../04-analysis-engine.md), [Strategies](../../05-strategies.md), [Signals](../../06-signals-and-scoring.md), [Risk](../../07-risk-and-monitoring.md), and [Validation](../../08-validation.md) documents. Original Git blob: `5b905fccf1f60eddea0d8d422e92532a7891b420`.

---

# S1 v0.2 — Deterministic Trend-Pullback Research Contract

**Date:** 2026-10-30  
**Status:** PROPOSED RESEARCH BASELINE. **No backtest has run; this is not an approved live trading strategy or an implementation authorization.**  
**Dependencies:** [14 — MTF original draft](14-multi-timeframe-S1-trend-pullback.md), [15 — adversarial analysis](15-S1-failure-modes-and-robustness.md), [17 — indicator selection](17-indicator-combination-research.md), [03 — market data](../../03-market-data.md), [08 — validation](../../08-validation.md).

## 0. Authority and purpose

This document turns previously ambiguous *research hypotheses* into a **deterministic candidate algorithm** that can be reviewed and, after approval, implemented in a simulator. **Where it contradicts draft 14 on the S1 research baseline, this version supersedes draft 14**. No confirmed profitable edge, broker choice, cost threshold, risk allocation or real-money readiness is implied.

Our only goal: help a person choose **better XAUUSD scalping trades**, with transparent entry, stop, take-profit and monitoring. No LLM, agent runtime, order execution, wallet, unrelated platform features, or extra indicators by default.

## 1. Required inputs and time causality

- Source: one broker-consistent, timestamped bid/ask tick feed. Analysis bars use **BID** OHLC; maintain parallel **ASK** extrema for executable-price checks. Provider timestamp, arrival timestamp, symbol, quote source/health and UTC conventions must be stored.
- Bars: UTC half-open windows for M1/M5/M15/H1. A completed bar is available **only on a valid subsequent quote after the bar closes**, if no disqualifying feed gap. Never calculate READY on a hypothetical exact candle-close fill.
- Confirmed-bar and pivot events must carry both `event_time` and `available_at`. Every decision uses the **information set actually available** at that decision time. Replaying ticks must give the same output.
- Bar gaps, no valid subsequent quote, missing broker precision/cost metadata, insufficient indicator warm-up or stale feed => insufficient information / no actionable signal.
- Research default warm-up: 250 finalized H1 bars for EMA50 stability (**>=450 H1 bars for the slower EMA90 research variant**), at least 50 M15 bars for recent level context, and >= 30 M5 bars for ATR and pivots. An absent M15 pivot after sufficient warm-up yields context UNKNOWN as a **soft** condition, not an invented level or forced veto. Exact sufficiency must later be verified against initialization convergence; these values are **candidate requirements**, not market facts.

## 2. Indicators and structures (minimal, complementary)

| Evidence axis | Initial candidate | Why used | What it DOES NOT prove |
| --- | --- | --- | --- |
| Direction | H1 EMA20/EMA50 on confirmed closes, EMA20 3-bar slope | Higher-timeframe trend summary | A trade will win |
| Context | Most recent confirmed M15 swing high/low and optional M15 EMA20 slope | Level proximity / healthy correction vs reversal warning | Real institutional order flow |
| Timing | M5 confirmed pivots, impulse/pullback ratio, two-bar breakout of prior M5 extremes | A reproducible entry event | Breakout will hold |
| Volatility | M5 Wilder ATR14, H1 Wilder ATR14 (descriptive) | Normalize movement, stop buffers, speed | Trade direction |
| Execution | Live bid/ask, spread, known news calendar | Price actually available and known risks | Guaranteed fill |

EMAs: seed with SMA of first N complete bars, then `alpha=2/(N+1)` recursion. ATR: initial SMA of N true ranges using a prior close, thereafter Wilder recursion `ATR_n=(ATR_(n-1)*(N-1)+TR_n)/N`. Missing/zero ATR => UNKNOWN/no READY. Preserve initialization and data versions in audit records.

Pivots use **strict** (left=2, right=2) bid highs/lows on **completed M5/M15 bars**. A pivot's bar time is NOT its confirmation time. Ties do not create a pivot. At bar k, pivot high requires H[k] > H[k-2], H[k-1], H[k+1], H[k+2], and is visible only after k+2 closes. Mirror for pivot low. Same-bar high/low pivots may both occur (outside bar); tie-break direction and time deterministically.

These are **one small candidate set**, not a universal best indicator formula. Study sensitivity in doc 17.

## 3. H1 trend state

On last confirmed H1 bar t:

- UP: EMA20[t] > EMA50[t] AND EMA20[t] > EMA20[t-3] AND bid close[t] > EMA50[t].
- DOWN: the three strict comparisons all reverse.
- NEUTRAL: sufficient data, neither UP nor DOWN.
- UNKNOWN: missing or stale input.

The proposed full S1 candidate long requires UP, short requires DOWN. **I0 in document 17 is a diagnostic exception** that deliberately disables the H1 bias gate to measure its incremental benefit; it is not an alternate production rule. Signal must reference exact H1 bar and EMA values. Do not use a running/unclosed H1 candle for an actionable signal. If H1 changes during FORMING, reassess; if it reverses after READY and before manual entry, invalidate. **No claim this specific EMA filter is optimal**.

## 4. M15 context — deterministic experimental classification

At each decision evaluate all **confirmed** M15 pivots *known by that time*. For a BUY choose the most recent confirmed **pivot low** with pivot_time before decision; for SELL, the most recent confirmed **pivot high**. Ignore levels older than 48 completed M15 bars in this provisional version (12 hours of bars in uninterrupted trading); older/missing references are UNKNOWN and never silently replaced by future swings. Do not infer real stop-order placement.

- BUY OPPOSING if latest confirmed M15 BID close < selected pivot-low BID price **and** EMA20_M15[t] < EMA20_M15[t-1].
- BUY CORRECTIVE if not OPPOSING and (close < EMA20_M15 OR EMA20_M15 falling).
- BUY SUPPORTIVE if not OPPOSING/CORRECTIVE and price/EMA data are available.
- BUY UNKNOWN if required input missing or no reference level.
- SELL mirrors: OPPOSING on confirmed close > reference pivot high and rising EMA20; CORRECTIVE on close > EMA20 or rising EMA20.

If a reference is present but market conditions do not satisfy any informative case, do not invent a direction. State classification and reference ID/timestamps in the explanation. Recalculate this context on confirmed M15 updates; record the M15 snapshot used at signal time.

**Baseline policy:** M15 OPPOSING contributes an adverse **warning/soft quality penalty**, not an automatic veto. An experimental hard-veto variant can be tested separately. M15 CORRECTIVE against H1 is often the shape of a pullback; *do not* require candle-by-candle alignment across H1, M15 and M5.

## 5. Deterministic structure pairing on M5

Use finalized BID bars and confirmed pivots, processed in event-time order.

### 5.1 Long impulse selection
1. When a **new M5 pivot high H becomes confirmed**, find the most recent **confirmed M5 pivot low L** whose pivot_bar_time is strictly before H's. Its confirmation must be available no later than decision time. If none, no pair.
2. Require `I = H.bid_high - L.bid_low > 0`, `I >= 1.0 * ATR14_M5` evaluated **when H is confirmed**, and H.pivot_bar_index − L.pivot_bar_index <= 12. `1.0` and `12` are **preliminary experimental parameters**.
3. Create `pair_key = (S1_VERSION, LONG, L.bar_id, H.bar_id)`. Record `L/H` prices, pivot/confirmation times, I and contemporaneous ATR. **Never rewrite them.**
4. Maintain at most one **FORMING** S1 candidate per direction. When a newer *valid confirmed H* yields a new pair, mark the older still-FORMING pair `SUPERSEDED` (reason and timestamp), then activate the new pair. **READY** or manually entered signals remain distinct immutable records, subject to usual expiry/invalidation. Do not regenerate a rejected pair with the same key. This deterministic choice is a design hypothesis, to compare against keeping multiple candidates.
5. Do not retroactively issue READY at an earlier pivot bar simply because the H confirmation arrived later.

### 5.2 Short impulse selection
When a new confirmed **pivot low L** appears, use most recent confirmed earlier pivot high H, require `I=H.bid_high-L.bid_low > 0` and corresponding ATR and age constraints, and form `(S1_VERSION, SHORT, H.bar_id, L.bar_id)`. The pair freezes the same way.

## 6. Pullback formation and invalidation

**Long**: After pivot-high **bar** H (not after its later confirmation), consider completed M5 bars with bar_index > H.bar_index. Initial pullback includes the right-hand bars used to *confirm H* **only after they have actually closed**. Define `P_bid = MIN(low_bid)` over this window, updated with each newly closed M5 bar. Require >= 2 completed post-H bars. Define `depth = (H.bid_high - P_bid)/I` with original I frozen. Preliminary watch zone `0.25 <= depth <= 0.75`.

- If depth < 0.25: DETECTED/FORMING with reason `PULLBACK_SHALLOW`, not READY.
- If depth > 0.75 or observed BID <= L.bid_low: invalidate pair and record the exact observed time. Equal-to structural break handling: `BID <= L.bid_low` counts as broken.
- If pullback duration > 12 completed M5 post-H bars: EXPIRED (candidate hypothesis; compare alternative durations).
- If no post-H bars/invalid ATR: WAIT/UNKNOWN, never fabricate data.

**Short**: After pivot-low bar L, define `P_bid = MAX(high_bid)` of subsequent complete M5 bars and `depth = (P_bid - L.bid_low)/I`. Need >=2 bars; invalidate on depth > 0.75 or BID >= H.bid_high. Stop for short will use parallel ask extremes, not bid-only P.

**Important correction to draft 14:** a trigger bar may create a new, slightly deeper pullback wick yet still close strongly. Do not automatically reject merely because its low/high extends earlier P. Instead include the **completed trigger bar** in P **before** checking depth/invalidation; if the final pullback breaches the frozen L/H thesis or 0.75 bound, reject. This is more inclusive than draft 14's zero-tolerance wick rule and must be A/B tested, not presented as proven superior.

## 7. Trigger evaluation (M5-close baseline)

For each just-finalized trigger candidate bar j, and only when the paired pivots are **confirmed by that decision**:

**Long:** `close_bid[j] > MAX(high_bid[j-1], high_bid[j-2])` AND `close_bid[j] > open_bid[j]`, with pair still active, post-H count >= 2 and final depth in [0.25, 0.75].  
**Short:** `close_bid[j] < MIN(low_bid[j-1], low_bid[j-2])` AND `close_bid[j] < open_bid[j]`, mirrored depth.

Use the **two completed prior bars**, never today's high/low in the breakout threshold. Trigger bar P update (Section 6) uses only its just-finalized values, before READY is evaluated. Store both threshold and trigger-bar identity.

This is **only the baseline trigger**. Wick/body quality, one-bar hold, retest or M1 entry are independent experiments, not an extra bundled set of filters.

## 8. First executable quote and READY signal

1. On the first **valid, causally subsequent** bid/ask quote after the triggering M5 bar is finalized, check H1 bias, pair validity, stopped/expired signal IDs, news/exposure policies, broker contract and bid/ask feed health.
2. If the quote is too delayed after bar close (threshold **OPEN until broker latency is known**), record `MISSED_DATA_GAP` rather than backdating a READY signal.
3. Reference prices at first quote: `E0_long = ASK0`, `E0_short = BID0`. Additional preliminary **no-chase** test: `E0_long <= trigger_bid_close + 0.20*ATR14_M5`, short `E0_short >= trigger_bid_close - 0.20*ATR14_M5`. If failed, mark `MISSED_PRICE_CHASE`, no READY; this specific tolerance must be backtested with spread.
4. Freeze the original `E0`, signal timestamp, triggering bar, reference pivot pair, original stop, benchmark target(s), indicator snapshot, evaluation result and rule version. Each new quote changes **current eligibility**, never the original issued plan.
5. Provisional **manual entry band** evaluated against current executable price while READY:
   - Long ASK in `[E0 − 0.10*ATR14_M5, E0 + 0.20*ATR14_M5]`.
   - Short BID in `[E0 − 0.20*ATR14_M5, E0 + 0.10*ATR14_M5]`.
   Freeze ATR and band boundaries at issuance. The 0.10/0.20 offsets are **experimental**. Require current price to remain on valid side of strategy's historical trigger within an additional `0.10*ATR` tolerance (long BID >= trigger_threshold - tolerance; short BID <= trigger_threshold + tolerance); study whether this adds value.
6. **Expiry:** candidate TTL = first instant of the next M5 bar close after signal issuance (typically up to 5 minutes), independently of UI refresh. This is a hypothesis to stress-test, not established optimal timing.
7. Quote temporarily outside band, temporarily high spread or price temporarily below a confirmation tolerance => display `EXECUTION_BLOCKED(reason)` as **reversible eligibility overlay on a READY record**, not a fresh signal and not an additional durable FSM state. A structural hard invalidation or TTL crossing => terminal EXPIRED/INVALIDATED. If eligibility recovers inside original frozen band and TTL, show READY again with the **same ID** and event history.
8. If BID touches or breaches frozen stop (long) or ASK touches or exceeds frozen stop (short) before entry, original READY is invalid, even if market rebounds. Do not regenerate same pair.
9. Recorded real operator entry after expiry/band breach is accepted only as a **deviation** in the journal, clearly `OFF_PLAN`, with new actual risk; do not rewrite historical signal or imply Grog executed it.

Two independent policies still OPEN before implementation: precise maximum post-close quote delay; actual broker-valid spread/commission/latency hard limits. Unsupported limits must never be guessed.

## 9. Structural stops, benchmarks and actual costs

Long:
- `P_bid_final = MIN(post-H completed BID lows through trigger)`
- `SL_long = FLOOR_TO_BROKER_TICK(P_bid_final − 0.10*ATR14_M5)`.
- Confirm `SL_long < BID0` and `SL_long < E0_long`.
- `R_price_long = E0_long − SL_long > 0`.
- **Benchmark** TP1 (BID close price) = E0_long + 1*R; TP2 (BID close price) = E0_long + 2*R.

Short:
- `P_ask_final = MAX(post-L completed ASK highs through trigger)`
- `SL_short = CEIL_TO_BROKER_TICK(P_ask_final + 0.10*ATR14_M5)`.
- Confirm `SL_short > ASK0` and `SL_short > E0_short`.
- `R_price_short = SL_short − E0_short > 0`.
- **Benchmark** TP1 (ASK close price) = E0_short − 1*R; TP2 (ASK close price) = E0_short − 2*R.

Round target prices **towards feasible broker ticks**, using frozen stated rounding policy (OPEN). TP/SL levels are proposals, never guaranteed fills. On BUY, exit valuation is current BID; on SELL it is current ASK. P&L and actual realized risk require contract size, commissions, lot step and execution slippage.

### Keep exit strategy unambiguous
- Baseline benchmark reports TP1 and TP2 levels for the operator, but its **single-position performance simulation exits all at TP2 or SL** (whichever is first by actual ticks; gaps/slippage modeled). TP1 crossing is an **informational milestone**, NOT an assumed partial fill in this baseline. This avoids pretending that two quoted TPs imply a fixed partial quantity.
- A **separate variant** may test e.g. 50% close at TP1, remaining 50% at TP2 or SL, explicitly specifying fees, sizes and what happens if SL is moved. No automated breakeven stop or discretionary TP enlargement without its own pre-registered test.
- Level congestion versus benchmark TP2 is a **recorded soft warning**; structural-target clipping is a separate research variant.
- Initial position risk may be proposed in percent of equity, but concrete account risk, lot sizing, maximum spread/cost-in-R and daily limits are **not frozen here**.

## 10. Continuation monitoring vs new signals

After manual entry, continue to monitor prices and exact recorded fills. Track original SL/TP, distance and P&L from **actual** entry, not from E0. Changes to M15 structure, H1 confirmed bias or live spread are **warnings**, unless a separately tested monitoring/early-exit rule explicitly says to recommend action. Do not treat a touched level as a broker-confirmed fill. Reconcile after restart.

Separately allow Grog to scan for developing opportunities while monitoring a position; the overlapping-risk acceptance policy is OPEN, so do not issue extra exposure by default.

## 11. Pseudocode-level event ordering (research reference)

```text
on_valid_tick(tick):
    validate_bid_ask_and_timestamps(tick)
    finalize_eligible_m1_m5_m15_h1_bars_and_confirm_pivots()
    update_last_confirmed_h1_bias()
    update_last_confirmed_m15_context()
    expire_and_invalidate_existing_candidates_by_timestamp_and_price()
    process_newly_confirmed_m5_pivot_pairs()
    update_m5_pullback_windows_from_newly_closed_bars()
    for each newly_closed_m5_bar:
        evaluate_s1_trigger_only_if_pivots_were_available_by_decision_time()
    for each newly_completed_trigger_not_yet_issued:
        evaluate_first_executable_quote_and_all_hard_gates()
        emit_AT_MOST_one_versioned_READY_or_record_rejection()
    recheck_existing_READY_current_quote_and_TTL_without_rewriting_issuance()
    update_manual_positions_using_current_closeable_bid_ask()
    persist_audit_events_idempotently()
    refresh_terminal_view_at_a_rate_lower_than_tick_processing()
```

Ordering must not accidentally let a pivot confirmed **after** the trigger's decision time authorize a historical trigger. A trigger and confirmation processed in one batch are allowed only if both were genuinely available at that batch's tick timestamp and the event is not backdated.

## 12. Required synthetic tests (specification, not executed)

| Test | Expected outcome |
| --- | --- |
| S1-01 H1 incomplete candle shows bullish while confirmed H1 DOWN | No READY long |
| S1-02 confirmed H1 UP, M15 corrective, valid M5 long | Eligible after gates; correction alone does not veto |
| S1-03 pivot H only one completed bar to its right | Not confirmed, no READY requiring it |
| S1-04 later confirmed H supersedes active FORMING | One active forming pair, deterministic SUPERSEDED event |
| S1-05 long trigger makes a new shallow P wick but remains inside 0.25–0.75 bounds | May READY; do not reject simply because P moved |
| S1-06 candidate P crosses 0.75*I or L structural low | INVALIDATED, not READY |
| S1-07 M5 wick exceeds previous 2 highs but close fails | FORMING/WAIT, never READY |
| S1-08 first executable quote arrives after configured max delay | MISSED_DATA_GAP, no fictional fill |
| S1-09 ASK first quote exceeds chase bound | MISSED_PRICE_CHASE |
| S1-10 READY price exits band then returns within TTL | Same signal ID with temporary EXECUTION_BLOCKED overlay, not duplicate |
| S1-11 READY stop touched prior to manual entry | Terminal INVALIDATED, no resurrection |
| S1-12 bid spread spike makes long mark appear to hit stop while mid does not | Respect BID and broker trigger conventions |
| S1-13 short stop based on ask high, not bid high | Correct short SL and ASK-side touch check |
| S1-14 TP1 touches; TP2 does not; later SL touches in baseline full-TP2 variant | Baseline LOSS, no fake TP1 partial win |
| S1-15 real manual fill is worse than E0 | Recompute actual R/R, retain immutable original |
| S1-16 ambiguous same M1 OHLC has SL and TP2 | UNKNOWN without real tick order, not optimistic win |
| S1-17 replay same timestamped tick stream twice | Identical pivot selection, signal IDs, states, P&L before rounding |
| S1-18 mixed/stale/zero ATR or missing broker tick precision | NO READY; explicit incomplete data reason |
| S1-19 M15 structural level older than 48 bars | M15 context UNKNOWN, not a future/reference fabricated level |
| S1-20 after expiry same pivot pair triggers again | No new duplicate; a new pair needed |

Every test includes both BUY and mirrored SELL paths, tick-boundary timestamps, a negative case, rule-version reference and expected exact status/reason.

## 13. Decision queue (must review before Grok coding S1)

**Already specified as a provisional, reproducible baseline, not approved optimal values:** EMA20/50, ATR14, pivot 2+2, impulse >=1 ATR, impulse age <=12 M5 bars, retracement 25–75%, candle 2-bar confirmation, 0.10 ATR stop buffer, 0.20 ATR no-chase bound, manual entry bands, 5-min typical TTL, 1R/2R quoted targets, full-exit-at-TP2 benchmark, 48-bar M15 reference validity.

**Still OPEN and blocking full S1 implementation:**
1. Broker/feed, quote cadence, XAUUSD instrument size/tick/commission and real historical bid/ask coverage.
2. Exact cutoffs for stale quote, maximum bar-close-to-first-quote delay, spread and estimated net-cost/risk limits.
3. H1/M5 sufficient warm-up, session hours/gaps, corporate time conventions, quote sequence rules.
4. Symbol-specific tick rounding for target and risk, stop trigger constraints, execution/slippage model.
5. Whether 12-bar impulse expiration and last-pair supersession are sensible; formal research approval.
6. Macro-event provider/blackout restrictions (may need manual calendar input, but NEVER assume unverified safe news).
7. Simultaneous open position and overlapping candidate policy, manual entry action syntax.
8. Acceptance thresholds and human-delay distribution, chosen **before** unseen-data testing.

Grok should start with *non-trading* data quality, causal bar/pivot utilities only **after that module is separately authorized**, then run unit/replay fixtures. It must not present this document's exploratory numbers as a production strategy.

## 14. Evidence and limitations

- TradingView official repainting and higher-timeframe documentation: https://www.tradingview.com/pine-script-docs/concepts/repainting/ and https://www.tradingview.com/pine-script-docs/faq/other-data-and-timeframes/
- MetaTrader real ticks, within-minute spreads, bid/ask execution: https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation
- Fidelity ATR guide, Wilder ATR as volatility tool (not direction): https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
- Batten et al. (2018), moving-average parameter effectiveness varies: https://research.monash.edu/en/publications/does-intraday-technical-trading-have-predictive-power-in-precious/
- Bailey et al. (2017), backtest overfitting and configuration search risk: https://scholarworks.wmich.edu/math_pubs/42/

**No backtest, forward trial, signal accuracy or profitability claim has been established for S1 v0.2.**
