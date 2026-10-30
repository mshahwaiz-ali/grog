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

## Provider-agnostic market-feed boundary — research addition 2026-10-31

**Proposed logical interfaces, not yet implemented**. Do not turn the price adapter into a new application or auto-trading bot.

- `QuoteSource` (single read-only adapter interface): declare `source_id`, broker/dataset, symbol aliases, metadata coverage, `subscribe_quotes()` and optional `fetch_history(from,to,cursor)`. `subscribe_quotes` is a market-data subscription, **not** an order or execution call.
- `QuoteNormalizer`: validate original BID/ASK, timestamps, source flags and precision; preserve original values and produce a typed normalized quote. Same-ms distinct updates must survive; duplicate replays must be idempotent by genuine event identity/cursor, **not by timestamp alone**.
- `DurableQuoteSink`: append immutable raw quote batches, checkpoint an acknowledged source cursor and restart from overlap; historical backfill is a distinct data-origin event and cannot become a retroactive live READY signal.
- `FeedHealth`: clock offset/last quote age, known market closure vs disconnection, gap/latency statistics, mixed broker metadata errors and explicit DEGRADED/OFFLINE state.
- `BarAggregator`: form BID OHLC and parallel ASK extrema using finalized UTC windows; bars/pivots have `available_at`. Its inputs come exclusively from the normalized source, with no synthetic 'universal XAUUSD' mix.
- `SymbolContract`: read-only, versioned broker tick/lot/value/currency/trading-hours/stop-level metadata; expose only verified known values to risk calculations. No wallet, connected account ledger or trade-writing interface.

**Candidate adapter A (MT5 only if execution broker uses it):** Linux Wine terminal plus a *minimal MQL5 quote exporter* with `CopyTicksRange` catch-up; no MQL5 `OrderSend`/`CTrade`/broker write calls. MT5 `OnTick` event callbacks may be coalesced; never claim exporter is lossless before controlled continuity tests. Native Python MetaTrader5 package access on Ubuntu must not be assumed; evaluate bridge practicality separately.

**Candidate adapter B (cTrader only if user broker supports it):** Python Open API client, limited to documented market-data and tick-history calls; authorization/secret handling separated from repository. Historical requests bounded by one week and partial-response `hasMore` must be handled.

**Candidate importer C (offline research):** Dukascopy historical BID/ASK where licensing and exact coverage allow. Tag source PROXY and HISTORICAL; this is **not** a ready-to-trade broker feed.

Keep the first working version one-process, one-symbol, low-overhead and crash-recoverable on local Ubuntu. No web server, cloud broker bridge, microservice architecture, wallet, AI model or high-frequency signal engine. The finalized source adapter choice is **OPEN** in [11](11-decisions.md), acceptance evidence is specified only in [08](08-validation.md), and canonical source timestamp semantics are specified only in [03](03-market-data.md).
