# Signal eligibility, scoring and selection
## Hard gates (not scoring points)
No fresh bid/ask → NO NEW SIGNAL. Also reject invalid market hours, inadequate contract metadata, excessive spread/estimated costs, disallowed event window, broken strategy trigger, impossible stop, insufficient room to target, duplicate or inconsistent exposure.
## Candidate states
DETECTED / FORMING (not tradable) → READY with unique ID and TTL; READY can expire, invalidate or be manually entered/skipped. Monitor still rechecks ready signal; no frozen recommendations after major change.
## PROPOSED 100-point quality rubric (to calibrate)
- Market context and directional structure 25
- Strategy setup quality 25
- Entry confirmation 20
- Execution/spread/slippage environment 20
- Reward-to-risk/target feasibility 10
Each term must be computed from measurable evidence, with versioned thresholds. Hard gates override score. Initial WATCH/ELIGIBLE/PREFERRED bands remain **OPEN**, to be selected using validation, not invented.
**Crucial:** 84/100 is a rubric score, **not** an 84% win probability. A predictive win probability may only be displayed after suitable historical calibration by time and strategy, with sample-size uncertainty.
## Outputs
Instrument, timestamp, ID, side, strategy/version, timeframe, entry zone and expiry, SL, TP1/TP2, gross and estimated net R/R after costs, expected fill convention, validity status, scoring breakdown, explanation, blocked reasons, risk caveats.
## Anti-spam and independence
Deduplicate overlapping signals; apply cooldown only if justified; track total eligible and rejected candidates. Do not optimize away all signals. Respect simultaneously monitored positions and manual status.
## No-trade
A visible NO TRADE state explains its primary reasons and when reevaluation occurs; never manufacture trades to meet a frequency goal.