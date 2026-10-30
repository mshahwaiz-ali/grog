# Market Data, Time Availability, Economic Events and Sessions

**Topic owner:** Canonical feed and time-data contract. Updated 2026-10-30. **Status:** A live price source is essential to Grog's approved workflow; provider, latency limits, fees and calendar source remain OPEN.

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

**No broker/feed has been selected and no live data/backtests have been executed by this specification.**
