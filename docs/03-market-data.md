# Market data, events and sessions
## PROPOSED live feed contract
A pluggable read-only adapter from eventual broker/platform (provider OPEN). No LLM service or trading API is required; a local feed exported by a platform may be used. Do not assume the exact bid/ask, symbol, spread or hours of one broker match another.
Required tick: UTC exchange/provider timestamp if available, local receipt time, bid, ask, source, symbol, sequence/quality flags. Enforce bid > 0, ask >= bid, monotonic handling, deduplication, gap alerts and configurable staleness threshold. Calculate spread in price units and standardized units; never guess pip size.
## Bar construction
Build M1/M5/M15/H1 bars from consistently defined source price (bid or mid for analysis), track separate bid/ask for execution; document candle conventions. Use only completed bars for bar-close rules; intra-bar signals must explicitly declare this.
## Metadata
Symbol mapping, contract size, lot step/minimum, precision, session schedule, server timezone, commissions, swaps if relevant, trading halts/holidays. Spot/CFD liquidity is OTC: **broker tick volume is quote activity, not total market traded volume**. Exchange gold futures volume/order book is a different instrument and optional contextual proxy requiring validation.
## History
Prefer real bid/ask tick files for execution simulations; persist immutable raw source, import metadata, checksum, data gaps, daylight-saving conversions, time coverage and license constraints. Separate training, validation, out-of-sample and untouched final evaluation periods.
## Economic events
Scheduled Fed decisions, CPI, US jobs and other relevant releases: UTC time, event type, source, publication/last-refresh, uncertain/missing flag. Choose blackout windows only after studying costs and behavior. Never assume an absent calendar event means a safe market.
## Feed health
Fresh/lagging/offline; when quote quality fails suspend new actionable signals, keep existing trade records, display monitoring unavailable.
## Research references
See [12](12-references.md) for official sources and platform documentation.