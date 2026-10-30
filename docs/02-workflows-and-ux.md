# Terminal Workflows and User Experience

**Topic owner:** User-visible interaction and session commands (proposed UI). Updated 2026-10-30. **Status:** Separation of developing opportunities, actionable signals and manually entered positions APPROVED. Exact CLI syntax/UI framework OPEN; no code exists.

## 1. What Grog looks like

A single local terminal session with continuously refreshing **market/feed health** and three separated surfaces:
1. **Developing Opportunities:** FORMING setups, direction, watched level, missing confirmation, H1/M15 context, candidate expiry and *why Grog is waiting*. No prompt to execute a trade.
2. **Actionable Signals:** READY/temporarily EXECUTION_BLOCKED signals with strategy, original and current executable BID/ASK, entry band, SL, TP1/TP2, gross and estimated net R/R, expiry, reason codes, quality evidence. **Do not show arbitrary 85%-win 'confidence' scores.** Show numerical rubric only after its formula is specified/approved; see [06](06-signals-and-scoring.md).
3. **Active Manual Positions:** Only operator-confirmed entries, actual fill, latest quote age, P/L when metadata sufficient, stop/targets, regime changes, advisory observations, partials and reconciliation warnings.

## 2. Session flow

1. Start local session (`grog start` is illustrative, not yet implemented).
2. Verify XAUUSD quote feed, exchange/broker hours, UTC synchronization, spread and news-event context; if unsafe/unavailable, show NO TRADE rather than manufacturing signals.
3. Scan H1/M15/M5 objectively under [04](04-analysis-engine.md) and [05](05-strategies.md); FORMING watchlist may be populated before confirmed M5 entry.
4. READY created only on a genuine post-trigger executable quote. A temporary spread/price-band problem displays `EXECUTION_BLOCKED` overlay on **same signal ID**; absolute expiry/structural invalidation is terminal.
5. You independently place a broker order (never via Grog), then explicitly `enter <signal-id> price=<actual-fill> qty=<actual-lots>` or `skip`/`miss` (example commands only; exact grammar OPEN). Do not imply Grog can see fills without a selected/approved read-only integration.
6. After confirmation, Grog monitors actual BID/ASK and position data. You report `partial`, `modify`, `close`; each update is recorded with timestamp and cost details.
7. Continue scanning while monitoring positions, but **avoid duplicate/conflicting additional exposure** pending approved overlap policy.
8. When program restarts after an outage, previously entered positions appear as **RECONCILIATION_REQUIRED** until user confirms whether they were changed/closed externally. Stale feed => MONITORING UNAVAILABLE.

## 3. Interaction and clarity

Display WATCH, READY, EXECUTION BLOCKED, ENTERED, PARTIAL, CLOSED, EXPIRED, INVALIDATED and OFF_PLAN with plain-language explanations and UTC/local timestamps. Rendering should be throttled independently of tick processing; never flood terminal with identical observations.

A TP/SL **price touch** is not a confirmed real execution. If source data or broker contract metadata is incomplete, label calculated P/L as unavailable/estimated rather than inventing numbers. Advisory observations are distinct from an executable instruction.

## 4. Critical UX test cases

- H1 up, M15 temporarily corrective, M5 BUY ready: show the correction as context, not automatic prohibition.
- M5 wick crosses threshold but close fails: remain FORMING/WAIT.
- First quote is too late/entry moved beyond band: never show old execution price as still READY.
- Operator enters late: show original signal **and** changed actual R/R, marked OFF_PLAN when necessary.
- Temporary spread block within TTL: keep same signal ID; terminal invalidation/expiry cannot revive it.
- Feed disconnect after manual entry: mark position unverified and P/L stale; reconcile on restart.
- Repeated quote or keypress: avoid duplicate trade/position records.

## 5. Boundaries

No wallet, auto-execution, chatbot, AI runtime, outside notifications or extra interface screens unless directly justified by better XAUUSD trade decisions. Implementation choices and shortcuts belong in [09](09-architecture.md), approved requirements/unknowns in [11](11-decisions.md).
