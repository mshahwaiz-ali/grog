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

## One-click daily workflow — approved 2026-11-11

The **primary user journey** is now: launch the Gold desktop with one command (ultimately 'gold') → Grog brings up its already-onboarded read-only MT5 reference source automatically → display truthful data/health and objective XAUUSD BUY/SELL/NO TRADE calculations (with complete entry, SL/TP, expiry, validation and reasons) → user may **select a signal to watch** → Grog continuously observes price, entry proximity, expiry, thesis invalidation and feed faults, with in-app alerts. No day-to-day MetaEditor/script/terminal operation. One-time permission/onboarding may be required for MT5 account login and initial setup; ordinary starts must not. No feed or unqualified source yields DATA UNAVAILABLE / NO TRADE, never a fabricated signal.

Watching a proposal is distinct from confirming that the user **actually filled an order**. The manual fill/position journal remains a separate optional workflow and all broker execution stays outside Grog. Auto-starting **read-only market-data infrastructure** does not authorize auto trading or bypass existing fail-closed data/policy checks. Continue to validate the empirical predictive edge rather than claiming a profitable signal engine. See [02 §17](02-workflows-and-ux.md#17-daily-one-click-live-workflow--2026-11-11) and [11 §18](11-decisions.md#18-one-click-live-reference-workstation--owner-direction-2026-11-11).

## Current simplified product direction — Trade Finder only (2026-11-11)

The **new primary Gold application has one job:** automatically provide selective, evidence-backed XAUUSD BUY / SELL / NO TRADE proposals, with real source identity, exact entry BID/ASK, entry zone, stop-loss, TP1/TP2, gross risk/reward, expiry, and objective H1/M15/M5 reasons. One command should open the desktop and supervise the already-configured read-only MT5 demo feed in the background after one-time setup.

**There is no user-selected setup monitoring, position/TP tracking, manual-entry flow or active trade journal in the new daily UI.** The older explicit monitoring/journal requirements above are retained as R0 historical/legacy functionality, **not current product requirements**; no deletion of existing data/code. Backend quote polling for opportunity creation and expiry still occurs.

Accurate signals are a **measured research outcome, not a UI feature or guarantee**. Strategy promotion requires timestamp/integrity-qualified source data, causal BID/ASK execution, sufficient independent samples and out-of-sample/forward-paper assessment of net expectancy, drawdown and robustness. Until then show UNVALIDATED / NO TRADE or clearly labelled indicative proposals and blockers. Zero trades is a correct result if evidence does not support any proposal.

**One implementation-facing companion:** [Trade-First Redesign](trade-first-redesign.md). Formal scope decision [11 §19](11-decisions.md#19-trade-first-scope-correction--owner-approved-2026-11-11); earlier watch-first paragraph in this file is superseded for the current product.
