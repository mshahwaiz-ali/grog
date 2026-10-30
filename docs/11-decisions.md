# Decisions and open questions
Updated 2026-10-30.
## APPROVED (conversation)
- Project/repository: **Grog**, private GitHub repository `mshahwaiz-ali/grog`, main.
- Gold (XAUUSD) as initial focus; scalp-oriented, manual execution.
- Local terminal session (GUI possible), continuously updated status.
- No GPT, Claude, chatbot or AI agent; use programmed analysis and strategy modules.
- Separate **developing opportunities** from **actionable signals**.
- After manual fill confirmation, monitor positions live; journal results.
- Documentation-first, planning can be revised during implementation for measured accuracy; don't force trades or overengineer.
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