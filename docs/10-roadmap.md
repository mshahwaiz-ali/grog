# Roadmap and acceptance gates
**Phase 0: Agree scope and documentation.** Confirm workflows, decision logic, data requirements and unresolved choices; all docs versioned on main. No code until planning approved.
**Phase 1: Data/replay foundation.** Choose realistic broker-matched source; implement schema/validation, gap detection, time normalization, quote replay and deterministic fixtures. Gate: identical replay generates identical bars and costs.
**Phase 2: Market analysis.** Confirmed swing structure, levels, EMA/ATR math, regime and event guardrails. Gate: no future leakage, unit tests for all edge cases.
**Phase 3: Strategy S1.** Define equations before implementing. Produce forming/ready/rejected events and explainability; test against synthetic and historical data. Gate: correct triggers and nonlookahead assertions.
**Phase 4: Signal/risk engine.** Gates, scoring, expiry, deduplication, bid/ask execution, trade sizing. Gate: no signals from stale quotes, safe no-trade fallback.
**Phase 5: Operator UI and monitoring.** Start/pause/status, signal acceptance, actual fills, live position observations, alerts, restart reconciliation and journal. Gate: simulated reconnects/restarts/partial fills work.
**Phase 6: Validation.** Cost-aware OOS walk-forward, stress tests, paper-trade tracking, objective performance reviews. Gate: pre-registered thresholds met; otherwise iterate research, no promotion.
**Phase 7: S2 and improvements.** Only add S2 when independently justified; compare portfolio effects, not just individual trade quality.
**Phase 8: Optional production-style use.** Only after robust evidence, explicit trader approval, broker execution plan and realistic risk limits. No order placement by program.
At each phase update relevant docs, tests, changelog and decision log. Protect existing behavior and do not optimize on the untouched final test split.