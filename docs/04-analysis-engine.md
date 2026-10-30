# Market Analysis and Indicator Mathematics

**Document owner:** Market analysis. **Specification status:** Multi-timeframe analysis is APPROVED in principle; all parameters and S1 classification rules below are PROPOSED RESEARCH SETTINGS, not measured edge. Updated 2026-10-30.

**Scope boundary:** This is the **only active specification for indicator formulas, feature definitions, H1/M15 context and pivot calculations**. Trading triggers/pivot-pair lifecycle belong to [05 — Strategies](05-strategies.md); signal states and score belong to [06 — Signals](06-signals-and-scoring.md); SL/TP/fill economics belong to [07 — Risk & Monitoring](07-risk-and-monitoring.md); tests/variants belong to [08 — Validation](08-validation.md). [Archived source drafts](archive/2026-10-30/README.md) are not requirements.

## 1. How Grog determines a trade

A **single indicator never creates a BUY or SELL**. The research sequence is:
1. Verify live BID/ASK and availability of completed historical bars ([03](03-market-data.md)).
2. Compute directional trend, objective swing structure, volatility, known event and session context.
3. Run eligible strategy-specific structure/trigger rules ([05](05-strategies.md)).
4. Validate executable prices and risk and calculate transparent scoring ([06](06-signals-and-scoring.md), [07](07-risk-and-monitoring.md)).
5. Issue READY only if objective strategy and safety conditions pass; otherwise show FORMING/WAIT/NO TRADE.
All decisions are made **as of their true observable time**; no future high/low or incomplete higher-timeframe close is allowed.

## 2. Multi-timeframe responsibilities

| Source | Role in S1 trend pullback | Policy |
| --- | --- | --- |
| H1 **closed** bars | Main BUY/SELL bias | For full proposed S1, UP allows long, DOWN allows short |
| M15 **closed** bars | Structural levels; supportive/corrective/opposing context | Corrections against H1 do **not** automatically veto a trade |
| M5 **closed** bars | Confirmed impulse/pullback and actionable trigger | Main baseline decision timeframe |
| M1 | Observational timing only | Optional independent early-entry experiment; never retroactively borrow a future M5 confirmation |
| Timestamped BID/ASK ticks | Freshness, spread, first executable quote, live monitoring | Required for realistic execution and timing |

**Do not demand all timeframes have the same candle direction.** H1 UP + M15 corrective + a valid M5 recovery can be precisely the desired setup.

## 3. Time causality and incomplete bars

The data-time contract is governed by [03 — Market Data](03-market-data.md). All feature values must carry `bar_id`, `event_time`, `available_at`, `timeframe`, `source` and calculation version. Use a feature only when `available_at <= decision_time`.

Use finalized BID OHLC for indicator/structure calculations. Maintain the parallel ASK stream for SELL stop/reference and actual trade economics. A candle ending at 10:05 is not evidence at 10:04:59, and is usable only after its actual finalization on a subsequent valid tick. Unclosed H1 and M15 values may be displayed as **provisional**, but cannot authorize a READY signal that requires a confirmed bar.

At 10:07:20 UTC, for an uninterrupted stream, the newest usable H1 is 09:00–10:00, M15 is 09:45–10:00, M5 is 10:00–10:05, M1 is 10:06–10:07. Late quotes or data gaps can make availability **later**.

## 4. EMA — descriptive trend statistic

**Proposed** H1 trend candidates: EMA20/EMA50 (baseline) or EMA30/EMA90 (alternative). M15 EMA20 is used for corrective/opposing context.

- `alpha = 2/(N+1)`
- `EMA[N-1] = SMA(first N finalized close prices)` for deterministic seeding, then `EMA[t] = alpha*C[t] + (1-alpha)*EMA[t-1]`.
- Record seed, warm-up, bar-close timestamp and decimal/rounding policy. Compute without future information.
- Proposed initial warm-up: >=250 finalized H1 bars for EMA50 baseline; >=450 H1 bars for EMA90 variant; >=50 M15 bars for level/context work. Final sufficiency requires reproducibility checks, not these counts alone.

The same bar history must be used for all compared variants; do not make a slower EMA look better/worse because it was started on an incompatible date.

## 5. ATR — volatility, not direction

For finalized bar t with previous close:
- `TR[t] = max(H[t]-L[t], abs(H[t]-C[t-1]), abs(L[t]-C[t-1]))`.
- Initialize `ATR_N` with arithmetic mean of first N **valid** TR values (requires prior-close convention).
- Wilder recurrence: `ATR[t] = ((N-1)*ATR[t-1] + TR[t])/N`.

Proposed periods are **ATR14** baseline and **ATR21** sensitivity research. H1 ATR is optional descriptive regime information; M5 ATR is currently proposed as the scale for impulse, pullback, stop and entry distances. Zero/invalid ATR means these calculations are unavailable, not a zero-risk trade.

ATR describes recent movement size. It cannot independently predict BUY/SELL direction.

## 6. Causal swing highs/lows

Use confirmed strict (left=2, right=2) pivots on finalized BID bars for both M5 and M15:

- Pivot high at bar k if `H[k] > H[k-2], H[k-1], H[k+1], H[k+2]`.
- Pivot low at bar k if `L[k] < L[k-2], L[k-1], L[k+1], L[k+2]`.
- A pivot at k becomes **confirmed only when k+2 closes and becomes available**. Incomplete right-hand bars cannot be used.
- Equal highs/lows are **not** pivots with this strict definition.
- Each pivot has ID `(source, timeframe, pivot_bar_id, side)`, price, `pivot_time`, `confirmed_at`, `available_at`. Store same-bar high/low pivots separately; they do not imply a tick order inside that bar.
- Recalculate candidate lists as-of decision time. Never plot/backtest signals at `pivot_time` when they only became knowable at `confirmed_at`.
- For S1 pair selection, the pairing algorithm is in [05](05-strategies.md); same-bar ambiguity cannot silently impose an invented intrabar sequence.

Experimental pivot width (2/2) must be sensitivity-tested if it causes excessive lag or spurious structure. No claims about observing institutional liquidity from pivots.

## 7. H1 S1 bias state (proposed)

Using the latest **finalized** H1 bar t:
- **UP:** `EMA20[t] > EMA50[t]` AND `EMA20[t] > EMA20[t-3]` AND `C_bid[t] > EMA50[t]`.
- **DOWN:** reverse all three strict inequalities.
- **NEUTRAL:** data available but comparisons mixed.
- **UNKNOWN:** insufficient/stale inputs.

For EMA30/90 research variants, replace EMA20 with EMA30 and EMA50 with EMA90 consistently; keep the 3-bar fast-EMA slope test.

Also log `abs(EMA_fast - EMA_slow) / ATR_H1` (if valid) and `(EMA_fast[t]-EMA_fast[t-3]) / ATR_H1` as descriptive strength features. **Do not introduce untested threshold vetoes.**

Full S1 uses this confirmed H1 direction. A diagnostic M5-only benchmark in [08](08-validation.md) explicitly removes H1 to measure incremental value; it is **not** a separate approved live strategy.

## 8. M15 S1 structural context (proposed)

For a BUY evaluate the **most recent confirmed M15 pivot low**; for SELL use the most recent confirmed M15 pivot high, selecting by pivot-bar time. Only reference pivots within the previous **48 completed M15 bars** for this *research setting*. If none, context is **UNKNOWN** (soft, not an automatic veto). Use the most recent confirmed M15 bid close and EMA20 values.

For a BUY:
1. **OPPOSING** if confirmed M15 close is **below** chosen pivot-low price AND M15 EMA20 has declined since the preceding finalized M15 bar.
2. Else **CORRECTIVE** if close < EMA20 OR EMA20 declining.
3. Else **SUPPORTIVE** when the required data are present.
4. Else **UNKNOWN**.

For SELL mirror: OPPOSING if M15 close > selected pivot high AND EMA20 rising; otherwise CORRECTIVE if close > EMA20 OR EMA20 rising; otherwise SUPPORTIVE if complete.

Tie order is OPPOSING → CORRECTIVE → SUPPORTIVE → UNKNOWN. Display reference ID and known time. M15 **CORRECTIVE** is permitted in the base S1; M15 **OPPOSING** is initially a warning/quality penalty, not an automatic veto. Comparing a stricter veto is a separate experiment in [08](08-validation.md).

The selected M15 reference can be an imperfect representation of a meaningful level. A more sophisticated level relevance algorithm may only replace it after reproducible evidence. Do not infer stop orders or deliberate manipulation.

## 9. Other observable features (optional research, not extra mandatory gates)

- `body_fraction = abs(close-open)/(high-low)` for nonzero range; `wick_fraction` similarly (define long/short adverse wick specifically when tested).
- `retracement_fraction = pullback_distance/impulse_distance`; denominators must be >0.
- `spread_in_R = (ask-bid)/(entry_to_stop_risk)` if positive denominator.
- `distance_to_opposing_level_in_R`: confirmed opposing level distance / original risk. Display and test whether it meaningfully predicts target congestion.
- Session/opening/previous-day levels, realized-ATR percentiles, rate of H1 bias changes, and known event proximity can be researched as **context**, never assumed profitable extra filters.
- ADX/RSI/MACD/BB/VWAP/volume-profile/order blocks/FVG are **not** included in initial S1. Before adding one, prove its independent net contribution (see [08](08-validation.md)). Broker tick-volume counts are not aggregate spot-gold traded volume.

## 10. Indicator selection principles

We want **few complementary measurements**, not five correlated votes derived from the same prices. Initial hypotheses: H1 EMA trend; M15 structure; M5 closed-candle trigger; M5 ATR scaling; actual BID/ASK costs. The alternative EMA/ATR periods and strict M15-veto variants I0–I8 are defined and evaluated **only** in [08 — Validation](08-validation.md). There is no known universal combination profitable in all regimes; S1 should abstain when its conditions are absent.

## 11. Offline implementation version boundary

Once the user explicitly tells Grok to start, the already-defined EMA, ATR, pivot and H1/M15 equations in this document can be implemented as **S1_RESEARCH_V0_2** for synthetic and imported historical replay. This freezes mathematical reproducibility for tests, **not optimality or live use**. The nine I0–I8 alternatives remain controlled tests in [08](08-validation.md); no unreviewed indicator may be added. A fully missing H1 warm-up returns UNKNOWN and blocks S1 simulation READY rather than silently changing EMA periods to fit a short demo fixture.

**Research sources:** [12 — References](12-references.md). Historical originals: [archive index](archive/2026-10-30/README.md).
