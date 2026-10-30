# Decisions and open questions
Updated 2026-10-30.

## APPROVED (conversation)
- Project/repository: **Grog**, private GitHub repository `mshahwaiz-ali/grog`, main.
- Gold (XAUUSD) as initial focus; scalp-oriented, manual execution.
- Local terminal session (GUI possible), continuously updated status.
- No GPT, Claude, chatbot or AI agent **inside the application**; use programmed analysis and strategy modules.
- **Grok is the implementation assistant**, not part of the Grog trading runtime. Grok must follow approved documentation; when strategy rules are ambiguous, request a decision rather than inventing them.
- Separate **developing opportunities** from **actionable signals**.
- Multi-timeframe confirmation belongs in the trade-quality research/design. Do **not** automatically require all timeframes to align: a corrective lower-timeframe move can be part of the setup. Exact timeframes, equations and thresholds are still research proposals documented in [14](14-multi-timeframe-S1-trend-pullback.md).
- After manual fill confirmation, monitor positions live; journal results.
- Documentation-first; improve the design during building when supported by testing; don't force trades or overengineer.

## APPROVED scope lock — 2026-10-30
**Grog's singular product objective is to select and monitor better XAUUSD trades.**
- When user says "upgrade", interpret as improving trade-selection accuracy, falsity rejection, timing, stop/TP design, execution-risk estimates, evidence, backtesting fidelity or monitoring **only**.
- Competitor research is for **transferable trade-quality lessons**, not copying unrelated features.
- Do **not** add wallet, balance/product accounts, broker transaction features, copy trading, automated order placement, generic assistant/chatbot/AI agent, social channels, feature-heavy dashboards or unnecessary complexity merely because another platform has them.
- A proposed addition must state: (1) what precise trading error it reduces or positive result it improves, (2) how impact will be measured on unseen and forward data, (3) its operational/data cost, (4) why a simpler method is insufficient. If unsupported, keep it out.
- Practical enablers (market feed, audit trail, replay) are legitimate only in service of this product objective.
- Competitor findings belong in [13-competitor-research.md](13-competitor-research.md); **research notes never silently become approved requirements**.

## PROPOSED, not yet formally approved
- Python modular application, SQLite, Textual/Rich, read-only platform feed adapter.
- Strategy candidates: S1 pullback, S2 sweep/reclaim, later S3 breakout/retest.
- H1/M15 context, M5 setup, optional M1 trigger; EMA/ATR supporting calculations.
- Risk percent example 0.25%-0.5%, optional partial TP and controlled exposure.
- Five-factor 100-point **quality rubric**, not a calibrated probability.
- Implementation and validation roadmap in 10.

## OPEN
- Actual broker/platform and XAUUSD feed, historical bid/ask tick availability, licensing, and symbol specs.
- How to ingest macro-event times without unreliable availability, preferred timezone.
- Exact indicator periods, structure rules, signal thresholds, risk/stop/TP policy and allowed trade concurrency.
- User manual command syntax, duration of paper test, minimum sample and net-performance promotion thresholds.
- Whether and how to import manual execution confirmations from broker history.

## Research discipline
Mark changes to decision status explicitly, rationale, date and measured evidence. Never silently promote hypothesis into verified performance. Keep all records without misrepresenting past trades.
