# Market Data, Time Availability, Economic Events and Sessions

**Topic owner:** Canonical feed and time-data contract. Updated 2026-10-31. **Status:** A live price source is essential to Grog's approved workflow; provider, latency limits, fees and calendar source remain OPEN.

## 1. Feed boundary

Grog is not an AI agent and never sends orders. Real-time XAUUSD analysis still requires **a price feed**: later choose a read-only broker/platform adapter (possibly a local exporter). A future provider must deliver timestamps, BID, ASK, symbol, venue/source, and an integrity/heartbeat mechanism. Do **not** assume a public chart or different broker trades at identical prices/spreads.

Normalized quote fields: `provider_ts_utc` (if supplied), `received_ts_utc`, `sequence_or_event_id` if supplied, `symbol`, `bid`, `ask`, `source`, `quality_flags`. Validate positive bid, ask >= bid, timestamp sanity, duplicate/reordered events, provider-to-local lag and missing intervals; mark uncertain times rather than silently interpolate an accurate-looking trade.

**Do not guess pip size, lot value, contract size, price increment, market hours or commission**. Store exact broker product metadata and timezone conventions, including weekend/holiday session gaps.

## 2. Candle construction — one canonical convention

For the initial S1 research contract **derive indicator/structure candles from BID ticks**, not unspecified mid-price candles. Retain corresponding ASK history for short stops, executable exits and spread. Use UTC half-open windows `[start_utc,end_utc)` for M1/M5/M15/H1. Label every finalized candle with `end_utc` and `available_at_utc`.

A candle is confirmed **after its interval has ended and a valid subsequent tick advances the stream beyond the end**, with a documented policy for missing ticks. A candle ending at 10:05 cannot be used for READY at 10:04:59; if first subsequent quote arrives at 10:05:11, the first executable quote is from the actual subsequent event (not the theoretical bar close).

Every MTF computation must use only information with `available_at_utc <= decision_time_utc` **and** actually received by that time. Bar extremes, pivots and completed EMA/ATR are not backdated to when a candle started. Incomplete H1/M15 bars may be shown as provisional UI observations, never confirmed evidence. References to exact calculations in [04](04-analysis-engine.md).

## 3. Feed health

Status: FRESH, DEGRADED, OFFLINE / GAP, each with last good provider/receive time, current spread, observed age, reason and latest finalized bars. A malformed/stale feed means **no new actionable signals** and active-trade monitoring displays **UNAVAILABLE / STALE**, never a false all-clear.

Maximum quote age, maximum delay between M5 close and first usable quote, and gap-tolerance thresholds are **OPEN and must be calibrated against the actual source**. Do not silently choose constants.

## 4. Historical data

Prefer raw broker-matched historical **BID and ASK ticks** for realistic scalping simulations. Persist original source, checksums, quote schema, UTC/DST conversions, data gaps and available historical costs. Distinguish training/validation/untouched final periods. Compression/storage format and retention are OPEN. Replay must be deterministic and support exact event-time and arrival-time controls; see [08](08-validation.md).

A 1-minute OHLC bar cannot always reveal whether a stop or TP was reached first; do not award a winner under ambiguous intrabar order.

## 5. Sessions, macro events and volume limits

Store tradeable market hours, actual broker timezones, UTC and daylight-saving transitions. Sources such as BLS CPI/jobs release calendars and Federal Reserve meetings can provide **scheduled event time**, but each event needs its own `known_at`, `event_time`, `source`, `last_fetched`, and `unknown` state. An event added later cannot be assumed known during a historical trade.

Experimentally assess event windows (and their opportunity cost) before hard-blocking. Missing event information is **UNKNOWN**, not proof no significant news is due.

Spot gold/CFD is substantially OTC. **Broker tick volume is not aggregate global traded gold volume**; gold futures footprint or centralized futures volumes would be a distinct, optional dataset requiring independent validation. No volume indicator is required for S1.

## 6. Decision dependency

Actual spread/cost gates, price bands and signal TTL live in [06 — Signals](06-signals-and-scoring.md); contract-based SL/TP, position P/L and partials live in [07 — Risk & Monitoring](07-risk-and-monitoring.md). Data provider and risk-event policies are tracked in [11 — Decisions](11-decisions.md).

**Decision 2026-10-31:** MT5 is the preferred **reference-feed adapter**, but **no actual demo server or live feed is connected**. The eventual manual execution broker is not required for offline data/indicator development. No backtest has been executed.

## 7. Provider research and first-choice decision — 2026-10-31

**Status: MT5 reference-feed integration DIRECTION APPROVED (2026-10-31); a concrete broker demo server/source is not yet connected; no software or feed installed.** Grog remains a local, manual-only XAUUSD decision program. An external price source is necessary; this does **not** authorize an AI/LLM API, placing orders, or adding broker-account management.

| Candidate | Actual documented access | Advantages | Risks and decision |
| --- | --- | --- | --- |
| **MT5 reference feed on Ubuntu** | MT5 terminal runs under Wine; MQL5 `CopyTicksRange` yields timestamped `MqlTick` history and `SymbolInfo*` exposes symbol contract/tick properties | **Preferred first implementation adapter regardless of eventual execution broker**; its chosen demo server provides a consistent reference BID/ASK stream | MT5/Linux Wine runtime, broker history depth and missing ticks need proof. A **tiny read-only MQL5 exporter** may be required; it must NOT call trade/order APIs. No implicit assumption that native Python MetaTrader5 API works directly on Linux |
| **cTrader Open API** | Official live quote and historic tick access; official Python SDK; OAuth account authorization; historical request maximum one week per window and paginated/limited results | Strong alternative **if the execution broker uses cTrader** | Account/app registration/auth, scope and API request limits add complexity. Use **least-privileged access**, no write/order calls. Respect server response `hasMore`, retry/backoff and actual broker XAUUSD availability |
| **Dukascopy historical bid/ask** | Dukascopy's official historical export offers BID/ASK data | Useful for **offline development/replay and broad scenario coverage** if available for XAUUSD and permitted by terms | **Not** execution-broker data; spreads, trading hours, stop rules and execution can differ. Do NOT infer live-profitability from Dukascopy-only tests; verify date coverage, price precision, completeness and licensing before import |

**Approved development path:** Build offline historical/synthetic BID/ASK schema and deterministic replay **now, without a broker decision**. MT5 is our preferred subsequent **read-only demo reference quote bridge**. cTrader is merely a possible later alternative, not a parallel integration task. Once a manual execution broker is known, treat its prices/spreads/SL/TP semantics as an execution-validation layer. MT5 is not a universal source of identical XAUUSD quotes.

The **MT5 reference adapter approach is selected**, but a specific MT5 demo server, its permission/availability and the eventual real-money trading broker are not chosen. Access still must be verified **without initiating trades**. No application installation is part of this documentation task.

### References for this choice

- MT5 Linux under Wine: https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux
- MQL5 history `CopyTicksRange`: https://www.mql5.com/en/docs/series/copyticksrange
- MQL5 `OnTick` event queue semantics: https://www.mql5.com/en/docs/event_handlers/ontick
- MQL5 symbol metadata: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
- cTrader official quote/tick methods: https://help.ctrader.com/open-api/symbol-data/
- cTrader auth: https://help.ctrader.com/open-api/account-authentication/
- Dukascopy official export: https://www.dukascopy.com/api/data/get/historical-data-export

## 8. Feed adapter acceptance contract — what the future Grok module must prove

These are **required properties for a correct non-trading data adapter**, not trading edge or selected implementation technology.

**Normalized event** (type/schema finalization belongs to [09](09-architecture.md)):

```text
source_id, broker_id_or_dataset_id, broker_symbol, canonical_symbol="XAUUSD"
provider_time_utc_ms, local_received_wall_utc_ms, local_received_monotonic_ns
source_event_id_or_cursor_if_available, batch_ingest_index, raw_bid, raw_ask
price_precision, update_flags_if_available, data_origin=LIVE|HISTORICAL|BACKFILL|SYNTHETIC
source_timezone_definition, data_quality_flags, adapter_version
```

`local_received_wall_utc_ms` is the earliest Grog ingestion observation; the monotonic clock is for elapsed-time/latency diagnostics, **not** interchangeable with UTC. Provider timestamps may be missing, rounded or skewed: distinguish **quote age**, local clock drift and network/bridge transit latency. Do not claim sub-millisecond precision absent the source's support.

- Preserve the provider's original raw prices/timestamps **unaltered** plus normalized numeric prices. Use Decimal/integer tick counts or another documented non-floating rounding policy for broker-valid prices. Do not assume one XAUUSD pip/tick/lot convention.
- One **coherent source** must supply both BID and ASK for comparable decision/exit modeling; an update flag may identify only one changed side, with the last known other side carried forward explicitly and tracked as such. Invalid/crossed quotes are quarantined.
- **Identical timestamps are valid:** several distinct ticks can share `provider_time_ms`; do not deduplicate on timestamp alone. If there is no stable provider event ID, retain stable **ingestion order** and use an auditable overlap/cursor algorithm; distinguish true retransmits from different same-ms quotes.
- Separate LIVE stream from HISTORICAL/BACKFILL. **Never emit a historical READY as if it were live** after a reconnect. Backfill can repair analysis history and archived research but must not rewrite a missed live decision.
- Track: dropped or delayed quote callbacks, source heartbeat/last quote, out-of-order timestamps, duplicate rate, time jumps, reconnects, missing bars and missing ASK updates. If a gap cannot be resolved, mark affected signal/monitor intervals DEGRADED/UNKNOWN, never silently fill favorable ticks.
- **MT5 exporter caution:** `OnTick` events can be coalesced when a prior callback is running. A read-only exporter must use bounded history catch-up (`CopyTicksRange` or equivalent), overlapping inclusive boundaries with safe deduplication, checkpoint/replay after restart and a nonblocking local transfer; don't promise one received callback per market tick. A scripted MQL5 EA used *only* for quotation export is a **data adapter, not a trading bot**, and must have **zero** order-related calls. Installing/authorizing such a helper remains a later explicit decision.
- **cTrader caution:** historical tick requests cover at most one week per request, may return partial results, and must honor `hasMore` plus actual documented rate limits. Account-specific authorization must not silently grant order rights in Grog's application.
- **Dukascopy caution:** vendor-supplied historical bid/ask may support offline fixtures, but final S1 assessment needs matched broker feeds/costs and representative forward testing.

**M09 contract:** the concrete transport (`GROG-MT5-REF/1`), dedup key, cursor, backfill-vs-live and timer-driven link states are specified once in [09 §5.1](09-architecture.md); MT5 tick times are trade-server times converted to UTC only with the exporter-reported offset (never a guessed broker timezone/DST).

**Local transport:** prefer simple append-only, crash-recoverable batches (or another explicitly verified read-only bridge); record checksums, batch IDs, start/end timestamps and committed cursor. **No high-frequency server/database/web dashboard is needed.** File timestamps alone and writing one CSV row per `OnTick` without testing throughput/recovery are not accepted as proven lossless.

## 9. Market-data audit and broker trial — before any live signal

Evaluate a representative broker **demo/read-only** XAUUSD connection during ordinary active hours and spread-sensitive/quiet windows, plus at least one documented known event window *if safe and available*.

| Check | Required audit evidence |
| --- | --- |
| Price source | Broker/platform name and XAUUSD symbol alias; product type and terms; no hidden alternative provider |
| Quote completeness | UTC/ms/arrival timestamps, BID/ASK values, duplicates/gap report, out-of-order handling, broker reconnect proof |
| Freshness | Distribution of receipt vs provider timestamps; display last-update age and clock skew; no hardcoded "fresh" without measurements |
| Spread | Historical distribution by UTC time/session: median, upper percentiles, spikes, invalid/crossed quotes, spread-to-stop-risk ratio |
| Tick continuity | Confirm each exported batch can be caught up/replayed with identical sample counts and no irreversible callbacks loss, given source limitations |
| Trading contract | Digit precision **versus actual tick size**, contract size, volume min/max/step, tick-value/currency, stop/freeze levels, market hours and commission |
| Candle consistency | Compare self-aggregated M1/M5/M15/H1 BID candles to source BID conventions; explain differences, don't force undocumented history fills |
| Market restrictions | Weekend/rollover closures and time-zone/DST mappings; unknown news availability must be explicit |
| Platform restarts | Suspend new signals during outage; backfill as BACKFILL; reconcile all real/manual positions; never issue retroactive READY |
| Historical rights | Exact broker history range, coverage/gaps, access terms, reproducible checksum, whether dynamic spread and ASK are really available |
| Resource stability | Measure CPU/memory/disk throughput on local Ubuntu machine, prevent unbounded buffering, CPU-heavy polling and loss of quote visibility |

**Audit decision:** PASS / CONDITIONAL / FAIL for the specific **data source**, with failure reasons, remediation and evidence. The user must approve a provider and its material limitations before it is elevated from candidate to selected live feed. **Source PASS is not evidence S1 profits.**

## 10. Time and bid/ask edge cases to test

1. Several different quotes share the same provider millisecond; preserve order and don't discard them as duplicates.
2. One side changes while the other stays fixed; avoid fabricating a zero spread.
3. Received event order differs from provider time; quarantine/resequence safely or mark unavailable, not redraw earlier signals.
4. Last M5 candle closes during feed outage; on reconnect, backfill bars without generating a supposed on-time READY.
5. UTC broker session crosses midnight or US daylight-saving change; use IANA session calendars, not permanent fixed offsets.
6. BID rises above target but ASK does not: for a long, only BID exit side matters; for a short, only ASK matters.
7. Historical gap straddles both SL and TP: outcome unknown without valid tick order, not an automatic win.
8. Broker changes XAUUSD symbol suffix, price digits or contract metadata: pin source metadata version and suspend unsafe calculations.
9. Long inactive period with *no ticks* versus dead connection: use separate heartbeat/market-session state, not price age alone.
10. Source historical tick window is partially returned: paginate/retry/check coverage, never treat truncated data as complete.

**Implementation-ready offline input:** The single normalized BID/ASK **CSV v1 header, timestamp units, Decimal string and file identity/strict-rejection format** are defined in [09 — Architecture, Section 6](09-architecture.md); source validity/availability belongs here. The user does **not** need to choose a broker to build/test this importer. SYNTHETIC fixtures may declare their own price increment for examples; never infer real broker stop/tick or trade economics from it.

**Handoff:** [07](07-risk-and-monitoring.md) owns the trade-economics calculation contract; [08](08-validation.md) owns exact data-feed test fixtures. No broker order-write operation is authorized by this research.
