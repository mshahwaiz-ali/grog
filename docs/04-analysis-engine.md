# Analysis inputs and calculations
**EXPERIMENTAL** indicators and parameters until validated. Prefer interpretable calculations over large indicator stacks.
## A. Market structure (primary)
- Confirmed pivot highs/lows using a fixed symmetric lookback on **closed bars only**; a pivot isn't known until subsequent bars close (prevents lookahead).
- HH/HL versus LH/LL with explicit break thresholds; swing structure break and reversal state defined relative to confirmed pivots.
- Horizontal support/resistance as clusters of confirmed prior extrema and session highs/lows; cluster tolerance scaled by volatility; don't draw levels using future bars.
- Session opening ranges and previous-day high/low (timezone/DST aware), distance to nearest opposing level and room available to TP.
- Sweep/reclaim: observable breach of a defined level by a minimum threshold, then close/hold back on the prior side within a limited window; **not evidence of deliberate manipulation**.
## B. Numerical and volatility inputs
- True Range TR=max(high-low,abs(high-priorClose),abs(low-priorClose)); ATR = Wilder-smoothed TR over N completed bars (N initially 14 as a candidate).
- Returns, trend slope and slope normalization by ATR, candle body/range ratio, wick fraction, distance from EMA in ATR units, retracement depth and break magnitude.
- Volatility regime via trailing realized volatility/ATR percentiles calculated on past information only; spread-to-ATR ratio and estimated cost-in-R.
- Trend EMA candidate 20/50 bars; EMA_t = alpha*close_t+(1-alpha)*EMA_(t-1), alpha=2/(N+1). Avoid treating EMA crosses as standalone entries.
- Optional ADX (trend strength) and RSI (momentum) only if an ablation study shows **incremental out-of-sample benefit**; initially exclude unnecessary indicator overlap.
## C. Market regime
Classify TREND_UP, TREND_DOWN, RANGE, TRANSITION/UNCERTAIN, DISRUPTED using combined structure, normalized trend and volatility. Define rules, conflict resolution and thresholds before coding; avoid retrospective labeling.
## D. Safety context (primary)
Tick freshness; spread/estimated slippage; broker hours; known event risk; nearby opposing structure; plan's stop distance; trader's risk budget.
## E. Explainability
Each input has value, time, timeframe, data provenance and threshold; signals explain major positive/negative conditions and hard vetoes. Avoid subjective labels such as 'smart money detected'.
## Multi-timeframe causality and trade-decision mapping
The detailed as-of timestamps, closed-bar synchronization, H1 directional bias, M15 correction/contradiction context, M5 setup, optional M1 test and expected decision snapshots are in [14 — MTF and S1 detailed research spec](14-multi-timeframe-S1-trend-pullback.md). The multi-timeframe concept is agreed; numeric settings and strategy thresholds remain experiments, not validated performance.

## S1 current research baseline and indicator selection
The currently specified deterministic S1 candidate is [16 — refined test contract](16-S1-refined-test-contract.md); [17 — indicator combinations](17-indicator-combination-research.md) defines a bounded comparison of EMA/ATR variants and whether M15 opposition should be a warning or experimental veto. Do not assume EMA/ATR alone create an actionable signal; research parameters are neither frozen for production nor profitable by claim.
