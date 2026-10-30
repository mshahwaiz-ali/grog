# Terminal workflows and UX
## APPROVED concept
Separate **Developing Opportunities** and **Actionable Signals** plus **Active Positions**; user executes externally.
## Session lifecycle
1. `grog start` (illustrative CLI; not implemented): load config, storage, history; verify feed and clock; display HEALTHY/DEGRADED/OFFLINE, market and economic-event state.
2. Scanner identifies regime, levels and strategy candidates without issuing entries prematurely.
3. Developing cards: strategy, direction, zone, invalidation, missing confirmation, timestamps and current state.
4. On full rules satisfied: actionable signal with unique ID, BUY/SELL, bid/ask-aware entry/acceptable range, stop, target(s), risk/reward after costs, score (not win probability), evidence, confidence limitations, TTL and safety flags.
5. Trader uses broker separately; chooses `enter <id> price=<actual> qty=<actual>`, `skip <id>`, or `miss <id>` (illustrative). Reject confirmations missing essential fill information; never silently assume strategy's quoted price is actual fill.
6. Active positions show real-time closeable bid/ask, R multiple, unrealized P&L only when contract specs/costs available, initial/current SL/TP, market regime, status, event warning and most recent update.
7. Trader reports `partial`, `modify`, `close`; journal every action with effective and recorded time. Monitor suggests, never submits.
8. Continue scanning while in trade; avoid duplicate/conflicting correlated exposures; policy for simultaneous positions OPEN.
9. On restart, restore saved positions as **unverified** until operator reconciles them; if feed stale show MONITORING UNAVAILABLE.
## State machine
DETECTED → FORMING → READY → {ENTERED, SKIPPED, MISSED, EXPIRED, INVALIDATED}; ENTERED → MONITORING → {CLOSED, RECONCILIATION_REQUIRED}. Candidate can invalidate before READY. Signal expiry is separate from trade closure.
## User feedback
Use calm terse status, meaningful state changes and throttled refresh rather than repetitive prints. Prominent feed health and timestamps. Exact controls/keybindings designed after selecting terminal library.
## Edge cases
Missed entry, partial position, same signal twice, restart, feed disconnect, wrong broker symbol, delayed user confirmation, target touched before entry, spread blowout, stale orders, time-zone mismatch, manual stop adjustment. Never treat a price touch on mid-price as guaranteed fill.