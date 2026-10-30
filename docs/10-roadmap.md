# Roadmap and acceptance gates
**Phase 0: Agree scope and documentation.** Confirm workflows, decision logic, data requirements and unresolved choices; all docs versioned on main. No code until planning approved.
**Phase 1: Broker-neutral data/replay foundation.** Use synthetic ticks and, when permitted, offline historical BID/ASK to implement schema/validation, gaps, UTC timing, deterministic quote replay and fixtures **without waiting for a broker**. Gate: identical data replay generates identical normalized quotes and bars; monetary execution costs remain unavailable until symbol metadata is known.
**Phase 2: Market analysis.** Confirmed swing structure, levels, EMA/ATR math, regime and event guardrails. Gate: no future leakage, unit tests for all edge cases.
**Phase 3: Strategy S1.** Define equations before implementing. Produce forming/ready/rejected events and explainability; test against synthetic and historical data. Gate: correct triggers and nonlookahead assertions.
**Phase 4: Signal/risk engine.** Gates, scoring, expiry, deduplication, bid/ask execution, trade sizing. Gate: no signals from stale quotes, safe no-trade fallback.
**Phase 5: Operator UI and monitoring.** Start/pause/status, signal acceptance, actual fills, live position observations, alerts, restart reconciliation and journal. Gate: simulated reconnects/restarts/partial fills work.
**Phase 6: Validation.** Cost-aware OOS walk-forward, stress tests, paper-trade tracking, objective performance reviews. Gate: pre-registered thresholds met; otherwise iterate research, no promotion.
**Phase 7: S2 and improvements.** Only add S2 when independently justified; compare portfolio effects, not just individual trade quality.
**Phase 8: Optional production-style use.** Only after robust evidence, explicit trader approval, broker execution plan and realistic risk limits. No order placement by program.
At each phase update relevant docs, tests, changelog and decision log. Protect existing behavior and do not optimize on the untouched final test split.

## Documentation-consolidation gate (2026-10-30)

The active research specifications are consolidated by **topic**, not by sequential experimental draft number: market/indicators [04](04-analysis-engine.md); S1 strategy [05](05-strategies.md); signal lifecycle [06](06-signals-and-scoring.md); execution/monitoring [07](07-risk-and-monitoring.md); experiments/tests [08](08-validation.md). Superseded S1 research snapshots are [archived](archive/2026-10-30/README.md). This hygiene step **does not** mean strategy rules are approved, profitable, or implementation-ready.

**Before Grok writes the S1 engine**: freeze exact numeric assumptions, broker-matched BID/ASK and costs, missing data behavior, source/event policies, signal TTL/entry-band settings, executable stop/target details and a non-overfitting trial plan in [11 — Decisions](11-decisions.md). Start with independently approved **non-trading data/replay modules** before strategy/risk/position logic. Preserve each module's tests and acceptance results.

Every requested change must first answer: *What exact error in Gold trading does it reduce? How will we measure net improvement on unseen data?* If not demonstrable, don't add the feature.

## Source readiness gate before strategy implementation — 2026-10-31

**Documentation stage complete for market-data research, not for live market connectivity.**

1. **Decision 2026-10-31:** No manual execution broker/platform decision is required to build the initial offline analysis engine. MT5 is the preferred future reference quote adapter; a broker demo server/source still needs selection and verification.
2. Start with deterministic synthetic/offline BID/ASK import/replay. Later assess the MT5 **demo reference** quote server's permissions, coverage, timeliness, metadata and market hours as defined in [03](03-market-data.md). No trade-write functionality or order privileges in Grog.
3. Independently authorize **one** non-trading data module at a time: quote schema/normalization → offline importer → causal MTF bar aggregation → replay. Use [08](08-validation.md) MD-01..MD-22 tests, then integrate a read-only local MT5 bridge when approved; no need to build another broker adapter now.
4. Study S1 signals using explicitly labeled **reference prices and proxy execution assumptions**. When an eventual execution broker is chosen, agree its actual execution/cost conventions, manual-entry delays, and source-specific restrictions in [07](07-risk-and-monitoring.md). Until then, do not claim broker-matched sized actionable fills or real-account readiness.
5. Only after repeatable quote processing, allow Grok to implement already-approved indicator/strategy modules with as-of-time tests; verify S1 with broker-matched real tick history and forward paper trading.

GitHub **Contents API** commits to `main` do not require **GitHub Actions**. No CI workflow run or external implementation task is authorized by this plan. Avoid new top-level numbered planning files; update canonical topic owners only.
