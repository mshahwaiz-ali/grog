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

## Canonical documentation contracts (planning only)

Grok must **read the active topic owner before coding**:
- User-facing terminal interactions: [02](02-workflows-and-ux.md).
- Quotes/bar timing, feed health, market/event metadata: [03](03-market-data.md).
- Indicator mathematics, pivot confirmation, H1/M15/MTF features: [04](04-analysis-engine.md).
- S1 structural pairing/pullback/trigger and future S2/S3 hypotheses: [05](05-strategies.md).
- Signal readiness, immutable issuance, reversible block overlay, scoring: [06](06-signals-and-scoring.md).
- Execution-side SL/TP, actual manual fills, P/L, position monitoring: [07](07-risk-and-monitoring.md).
- Indicator variants, failure taxonomy, full testing/acceptance: [08](08-validation.md).
- Approval status, blocker decisions and change control: [11](11-decisions.md).

The historical [S1 draft archive](archive/2026-10-30/README.md) is **non-authoritative**. Do not import unresolved assumptions from drafts or build extra product features because competitors offer them.

## Architecture constraint

**Proposed**, not implemented: a deterministic timestamped event pipeline and separate manual-position ledger. Store first-issued signal values immutably, alongside mutable eligibility and user-acknowledged fills. Event-time and actual receive-time are distinct. Terminal redraw frequency must not determine signal expiry or trade-monitoring integrity. No broker write/execution interface, AI inference, agent orchestration or unnecessary external service.
