# Trading strategies — research hypotheses
**None proven.** Develop one candidate at a time with deterministic, non-lookahead definitions. Each implements discover(context), form(candidate), confirm(entry), invalidate(candidate), exit_context(position), and emits auditable evidence.
## S1: Trend pullback continuation — first research priority

**Detailed research draft:** [14 — Multi-timeframe and S1 trend-pullback specification](14-multi-timeframe-S1-trend-pullback.md). It contains causal multi-timeframe conditions, proposed observable price rules, trigger, stop/target calculations, negative tests and research benchmarks. None of the numeric thresholds is yet approved as a proven live trading rule. **Failure-mode research and required negative tests:** [15](15-S1-failure-modes-and-robustness.md).

- Eligible when higher-timeframe structure and normalized trend agree and execution costs/volatility acceptable.
- Detect meaningful impulse, pullback toward prior structure/value area, and price rejection/renewed movement on M5/M1.
- Trigger only after a declared closed-bar break/reclaim or explicitly defined tick event; calculate actual bid/ask executable entry.
- Stop beyond pullback invalidation with volatility/noise buffer. Targets near previous swing/opposing levels or tested R multiples.
- Reject late chase, trend exhaustion, insufficient space, contradictory structure, excessive spread, stale feed or event-risk veto.
- Failure cases: false continuation, deep pullback reverses, thin liquidity and changing trend regime.
## S2: Level sweep and reclaim — second research priority
- Predefine reference high/low on completed history (session/pivot). Price breaches by objective threshold then reclaims within limited bars; optional retest.
- Confirm with momentum reversal/market structure and available room to opposite level. No claiming detection of actual stop orders.
- Stop beyond observed sweep extreme plus buffer; profit at structural targets; reject weak reclaim, repeated level churn and high spread.
- Failure cases: strong breakout mistaken for sweep, multiple tests of level, whipsaws and news spikes.
## S3: Breakout and retest — research backlog, not part of initial two-strategy implementation
- Define range and compression before breakout; require closed-bar acceptance beyond range, meaningful displacement and valid retest if used.
- Reject late entries, crowded target, weak breakout or adverse costs.
- Failure cases: false breakouts, no retest, spread widening, breakout already exhausted.
## Experimental timeframe proposal
H1/M15 context, M5 setup, optional M1 entry; tick bid/ask for executable prices. Test alternatives; don't optimize dozens of combinations.
## Strategy research card (required per candidate)
Version, precise inputs, timeframe, setup/confirmation/invalidation equations, no-lookahead proof, entry timing, stop/TP rules, estimated costs, exit/recommendation rules, expected failure modes, ablation tests, validation evidence and approval status.
## Signals may conflict
Central allocator groups overlapping levels and opposing directions; select none or one preferred opportunity under a documented policy. Do not fabricate independent signals by duplicating the same setup across modules.