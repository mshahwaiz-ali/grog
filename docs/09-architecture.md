# Proposed local software architecture
## Principles
Modular Python on Ubuntu; one local process or small set of supervised components rather than premature microservices. No LLM, cloud AI or trading order placement. Main branch only.
## Logical modules
- `feed/`: provider adapters, normalized bid/ask ticks, heartbeat, replay import and quality checks.
- `market/`: timeframe aggregation, structure levels, indicator math, regime classifier, time/event context.
- `strategies/`: strategy-specific detect/confirm/invalidate/monitor rules, versioned configs.
- `signals/`: eligibility gates, candidate FSM, rubric scoring, conflicts, expiry and explanations.
- `risk/`: contract-aware position risk, stops/targets, exposure restrictions and cost model.
- `positions/`: manual fill/partial/modify/close, position state, mark-to-market, monitoring suggestions.
- `research/`: replay, backtester, walk-forward runner, reports and scenario tests.
- `storage/`: SQLite schema/migrations, event logs and versioned metadata; optional compressed tick files.
- `ui/`: terminal interactive dashboard/commands (evaluate Textual/Rich); read-only UI plus confirmed local operator input.
- `tests/`: unit, property, integration, replay, resilience and deterministic fixtures.
**Do not create this tree yet**; it is a logical proposal and may be refined.
## Event processing
Normalized quote → validated bars → market context → strategy candidates → gates/scoring → view/events; operator trade action → position state → monitor on each new quote. Durable append-only audit/event log with transactional state snapshots.
## Interfaces
Typed Tick, Candle, ContextSnapshot, StrategyCandidate, Signal, ManualFill, Position, AdviceEvent. Time in UTC; display local timezone separately; every computed value includes data timestamp and rule version.
## Reliability
Explicit stale-feed state, restart recovery, DB transactions, duplicate event handling, bounded memory/history, deterministic simulation clock, graceful shutdown. No network-facing listening required for initial version.
## Config/security
Typed config, profiles, separate secrets outside Git; broker credentials not required for read-only local file export. No uploaded account statements or historical licensed datasets in repo. Private repo does not replace credential hygiene.
## Open architecture choices
Data-feed source, broker metadata adapter, tick store format, UI framework, CLI commands, economic-event provider, concurrency design, retention and resource budgets. Benchmark before selecting.