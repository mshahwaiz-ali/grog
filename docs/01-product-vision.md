# Product vision and requirements
## APPROVED direction
- XAUUSD-only, scalping-oriented, locally run program; no GPT/Claude/LLMs or chatbot; never automated broker order placement.
- Initially terminal based, with commands and continually updating sections. Optional local graphical interface later.
- Separate developing opportunities from actionable signals; manually confirm taken/missed/skipped positions; continuously monitor confirmed positions.
- Prioritize strong net results while avoiding forced entries and excessively restrictive filters. No assertion of 90% accuracy.
## Required capabilities
- Show feed health, bid/ask, spread, context/trend, session, event risk, strategy state.
- Candidate formation, precise signal state, entry/expiry/SL/TP and reasons for acceptance/rejection.
- Position monitor with user-reported fill, sizing, partial exits, modified stops and closure; journal signals including skipped trades.
- Replay/backtests using realistic tick execution and historical event timestamps; performance reports.
## Non-goals
- AI chat, automated brokerage trading, profit guarantees, high-frequency execution, copy trading, mobile push notifications (initially), expansion to other assets.
## Success definitions
- Correctness first: no stale-data signals; deterministic replay; accurate bookkeeping and timestamp handling.
- Statistical: positive net expectancy on unseen periods and paper trade, risk-adjusted stability, adequate setup frequency, controlled drawdown.
- Operational: visible reasons for WAIT/NO TRADE, recoverable restart, zero unacknowledged active-trade confusion.
## Trade-offs
More filtering may lower trade count; fewer filters may increase false signals. Evaluate empirically rather than promising a fixed trade frequency or win rate.