# Terminal Workstation — Canonical UX, Layouts and Interaction Contract

**Updated:** 2026-10-31  
**Status:** Product intent APPROVED; interface specification is the **implementation baseline when Grok is asked to start**. The visual designs below are synthetic examples, not live prices, real signals or evidence of profitability.

**Owner:** terminal layouts, wording, keyboard/navigation, input forms and empty/error states. Algorithm math is **not** defined here: indicators [04](04-analysis-engine.md), strategies [05](05-strategies.md), signal state/expiry [06](06-signals-and-scoring.md), actual fills/monitoring [07](07-risk-and-monitoring.md), validation [08](08-validation.md).

## 1. Product UI principle

**One clean, fast terminal workstation for better XAUUSD decisions.** Do not clone broker terminals, trading websites, wallets, charts with 50 overlays, financial news sites, account portfolios or AI chat. The interface has three immutable conceptual lanes: **forming opportunities** (not actionable), **ready proposals** (can be acted on manually), and **confirmed manually held positions** (actually entered).

### Modes and source fidelity — always visible

| Mode | Where quotes come from | What a 'ready' signal means | What must never be implied |
| --- | --- | --- | --- |
| `REPLAY` | Synthetic or historical file; virtual clock | Simulated READY under versioned research rules | Live executable price, real gain/loss |
| `REFERENCE_LIVE` | Read-only MT5 demo/reference feed (future) | Indicative READY at **reference** BID/ASK | Exact prices available at unknown execution broker |
| `EXECUTION_VERIFIED` | Future reference plus explicit broker-specific costs/actual operator fills | Broker-aware **manual** trading decision support | That the app placed trades, or guaranteed filling/SL/TP |

**The eventual broker is optional for building/running offline mode.** Use a source-fidelity tag (SYNTHETIC/PROXY/REFERENCE/BROKER_VERIFIED) on results. The underlying state `READY` is unchanged; do **not** invent separate `RESEARCH_READY` and `LIVE_READY` domain lifecycles.

## 2. Terminal framework and presentation

- **Choice:** Python **Textual** TUI with Rich for rendering (Textual uses Rich); custom visual styles in one `src/grog/ui/grog.tcss` (see [09](09-architecture.md)). The engine must not import Textual or Rich.
- **Default:** dark, premium, low-density and readable; no large empty decoration. Prefer compact panels, 1-2 lines per idea, consistent columns and obvious priority.
- **Color tokens** (design constants, not trading signals): background `#0B111A`; panel `#121D2A`; raised `#192838`; muted text `#93A5B9`; primary text `#E7EDF5`; Gold/accent `#E6BA63`; BUY accent `#33C6A1`; SELL accent `#FF7D7D`; caution `#F2BE60`; error `#FF6666`; border `#2B3C50`. Green/red are **not** the sole way to communicate meaning: always show BUY, SELL, WAIT, BLOCKED and the actual status text.
- **Typography:** terminal monospace supplied by user's emulator; don't ship fonts. Prices right-aligned with broker-valid precision; quantities and R in tabular columns; do not output scientifically formatted prices.
- **Refresh:** process quotes immediately in domain/event pipeline, but visually redraw the live quote/status widgets at a **proposed max 4 FPS**; append an event-log line **only on a meaningful state change**, not each tick. Design setting `ui.max_refresh_hz=4`, does not change expiry/strategy event handling. Unit-test independence from UI refresh.
- **Size:** optimized for >=120 columns and >=34 rows; at 80-119 columns hide secondary columns and stack context panels; at <80 columns use a single-scrollable list and horizontal truncation with explicit view-details action; at extremely small heights show a helpful resizing notice while feed/position engine stays active.
- **Theme:** dark only in initial build; light mode not needed. Avoid flashing/blinking, loud sounds, automatic scrolling away from user selection or resetting table focus when quotes update. Do not require mouse; optional mouse use can follow Textual defaults.
- **App title:** `GROG / GOLD WORKSTATION`, environment tag (`REPLAY`, `REFERENCE`) and data freshness continuously visible. Source and last update time must be shown.

Authoritative Textual API references: https://github.com/Textualize/textual/blob/main/docs/guide/app.md and https://github.com/Textualize/textual/blob/main/docs/widgets/data_table.md

## 3. Navigation and keyboard bindings — exact MVP contract

| Key | Action | Safety |
| --- | --- | --- |
| `1` | Live / Overview screen | View only |
| `2` | Opportunities & Signals screen | View only |
| `3` | Manually held Positions screen | View only |
| `4` | Journal screen | View only |
| `5` | Source Diagnostics screen | View only |
| `Tab`, `Shift+Tab`, arrows | Focus/switch between controls, navigate tables | Use standard Textual focus rules |
| `Enter` | Details for selected candidate, signal or position | View only |
| `Esc` | Close details/modal; don't lose unsubmitted input without confirmation | No hidden side effects |
| `e` | Open **Record Entry** modal on selected READY signal | Saves local journal **only after confirmation**; never broker execution |
| `s` | Mark selected signal SKIPPED; require confirmation | Persist reason (optional) and timestamp |
| `p` | Open **Record Partial Close** modal on selected held position | Local journal update only |
| `m` | Open **Record Modification** modal on selected position | Local stop/TP record only |
| `x` | Open **Record Closure** modal on selected position | Local journal update only |
| `r` | Request UI panel refresh using latest already-ingested state | Must not cause duplicate market events |
| `?` | Compact help overlay with keys and meanings | View only |
| `q` | Quit local program with informative warning if positions recorded as open | No broker action; persisted positions remain |
| `Ctrl+P` | OPTIONAL Textual command palette once stable | No new functionalities; shortcuts can expose above actions |

**Important:** Key bindings are global only when not typing into an input. Modal fields have priority; `e`, `s`, `x` typed into a price/notes input must **never** trigger the parent action. No global hotkey may place a broker order.

## 4. Screen 1 — LIVE / OVERVIEW (>=120 columns)

**Synthetic REPLAY screen** (values intentionally fictional; do not interpret as a trade):

```text
 GROG / GOLD WORKSTATION               XAUUSD   REPLAY • PROXY            2026-10-31 09:37:15 UTC
 Source: SAMPLE_TICKS [OK]             BID 4000.00  ASK 4000.20          Spread 0.20  Updated 0.2s
 ───────────────────────────────────────────────────────────────────────────────────────────────────
 MARKET CONTEXT                           OPPORTUNITIES FORMING
 H1  UP       EMA20>EMA50   [closed]      ID      SIDE  STRATEGY   STATUS    NEEDS
 M15 CORRECTIVE  Low 3996.80 [closed]     S1-014  BUY   Pullback   FORMING   M5 close > 4001.10
 M5  Recovery watch       [closed]       S1-015  SELL  Pullback   WAIT      H1 direction invalid
 Volatility ATR14 2.10                    2 observed | 0 ready | 0 entered
 ───────────────────────────────────────────────────────────────────────────────────────────────────
 ACTIONABLE PROPOSALS                     ACTIVE MANUAL POSITIONS
 No valid READY signal.                   No manually confirmed positions.
 Reason: M5 trigger not confirmed.        Nothing is assumed executed by Grog.
 ───────────────────────────────────────────────────────────────────────────────────────────────────
 EVENT FEED (latest state transitions)
 09:36:02  S1-014  FORMING  Pullback inside observed impulse; waiting confirmation
 09:30:00  FEED     HEALTHY Historical playback verified
 ───────────────────────────────────────────────────────────────────────────────────────────────────
 1 Live   2 Signals   3 Positions   4 Journal   5 Diagnostics    ? Help    q Quit     [No orders]
```

**Panel rules:** Quote header and source health are always shown. Context row shows last **confirmed** bar timestamps on details. If current H1/M15 bar values are displayed, show `[provisional]`, never use them to imply actionable confirmation. Active positions should remain visible **even while scanning**. Critical feed-degraded banner takes precedence over price changes. Avoid fake 0% scores/empty charts.

## 5. Screen 2 — OPPORTUNITIES & SIGNALS

Two vertically separated tables by **state**, not one mixed table:

1. **Developing / Watchlist** shows candidate id, side, strategy, H1/M15 context, price/level, exact pending condition, age, and reason code. Must display `NOT TRADABLE YET` in detail.
2. **Actionable / Ready** shows signal ID, side, earliest READY time, ASK-entry for BUY or BID-entry for SELL, valid price band, SL, TP2, estimated R after costs if known, TTL and `READY / EXECUTION BLOCKED`. A small `TP1` note or expanded detail may show TP1. In `REPLAY`, add `SIMULATED`. In `REFERENCE_LIVE`, add `INDICATIVE - CHECK YOUR BROKER`.

**Detail drawer (selected signal):**

```text
 SIGNAL S1-014 / BUY   READY (INDICATIVE)   Source: MT5_DEMO [REFERENCE]
 Created 09:37:15 UTC / Expires 09:40:00 UTC / Valid entry quote age 0.2s
 H1: UP [09:00-10:00? see confirmed bar id]    M15: CORRECTIVE     M5: Closed trigger confirmed
 First entry ASK: 4000.20    Current ASK: 4000.25    Valid band: [3999.99 - 4000.62]
 SL BID: 3998.00   TP1 BID: 4002.40   TP2 BID: 4004.60   Gross target: 2.0R
 Net risk/return: UNKNOWN (execution broker fees not confirmed)
 Eligibility: PASS (reference-only)     Warning: M15 corrective; monitor structural low
 Action: [e] Record external manual fill    [s] Skip    [Esc] Back
 No automatic broker order is created.
```

**Example values are illustrative;** the displayed price band must be computed by [06](06-signals-and-scoring.md) using actual frozen ATR and quote; timestamps must be consistent with actual snapshots. The example's `H1 [09:00-10:00?]` is a **placeholder for a correctly finalized confirmed bar**, and must be replaced in the implementation with its actual finalized UTC time (not the uncertain literal label). Never fabricate available M15 pivots.

A numeric quality percentage is **NOT** part of MVP: [06](06-signals-and-scoring.md) explicitly forbids uncalibrated '85% probability' labels. Show **why** the setup is ready and what would invalidate it.

**Priority behavior:** On simultaneous multiple candidates, show duplicates suppressed, exposure conflicts as explicit warning (not as hidden ranking), no forced one-signal selection until policy and evidence are ready.

## 6. Screen 3 — ACTIVE MANUAL POSITIONS

Table columns: `position ID`, `signal ID`, `side`, `qty`, `actual entry`, `current closeable quote`, `initial/current SL`, `TP status`, `gross/net estimated P&L`, `R`, `last updated`, `STATE`.

- **Long closeable mark is BID**; short closeable mark is ASK. Unknown lot specs/fees => `P&L UNKNOWN` with a clear explanatory reason; never treat reference-feed unrealized P&L as true account balance.
- Immediately show `RECONCILIATION REQUIRED` for positions restored after restart until user verifies them.
- Advisory event strip: `TP1 APPROACHING`, `STOP TOUCHED (NOT VERIFIED FILL)`, `H1 BIAS CHANGED`, `FEED STALE`, `MANUAL BROKER VERIFICATION NEEDED`.
- `Hold / reduce / exit` **advice** is absent until a separately tested rule is approved; show factual conditions without recommending unseen actions.
- If operator records a close/partial manually, append the action and update remaining lots and actual fill fees. Never submit any order.

## 7. Screen 4 — JOURNAL

Compact searchable/sortable local table: `UTC`, `signal/position`, `strategy ver`, `side`, `action`, `state`, `fill source`, `realized R`, `source fidelity`, `reason`.

Filter via text input by `signal ID`, `date range`, `status` and `mode`; these are **local journal filters**, not a new analytics dashboard. Journal retains SKIPPED/MISSED/EXPIRED/RESEARCH_READY with correct state names and actual entered trades. When no file/history exists show `No journal events yet`, not sample gains.

Recording error correction is an **append-only correction event**, never silent deletion of original actions. Full-text search is optional after basic table filters work.

## 8. Screen 5 — DATA DIAGNOSTICS

Show `mode`, `source_id`, broker/server/dataset, original symbol and `canonical=XAUUSD`, UTC provider/receive latest timestamps, quote age, BID/ASK, spread, last finalized M1/M5/M15/H1 bars, missing ticks/bars, replay/import checksum and gaps, adapter status, history warm-up sufficiency, schema/config version, current data fidelity.

Source status labels are `FRESH`, `DEGRADED`, `OFFLINE`, `MARKET_CLOSED`, `REPLAY_PAUSED` as **diagnostic presentation**, distinct from the signal's domain FSM. Show reason and latest reliable quote time prominently.

No account balance, wallet, 'connect bank', API wallet, transaction dashboard or account order panel.

## 9. Modal contracts — manual actions, not trading commands

### Record Entry (`e` on READY)

Mandatory: selected `signal_id`, `side` (read-only), `actual fill price` (decimal, required), `actual filled quantity/lots` (positive decimal), `actual fill UTC time` (explicit; default **form-opening time**, user can correct), `trade label: SIMULATED / MANUAL` (derived from current mode). Optional: `commission`, `operator note`, `broker name`, actual stop/targets if different from recommended. The signal's original E0/SL/TP remain immutable.

Validation: no negative/NaN, finite amounts, quantity >0, broker tick size when known, event time not ahead of known clock without warning, duplicate action IDs rejected, and enough info to distinguish off-plan. Display **before saving** the original entry vs actual price, changed gross risk/target R and whether it is OFF_PLAN, if calculable. Buttons `Confirm local record` and `Cancel` (default selection Cancel). Do not send trades to a broker.

### Skip (`s` on READY) and Missed
Show signal identity, direction, reason (optional), original expiry and `Mark skipped` confirmation. Distinguish `USER_SKIPPED` from system EXPIRED/MISSED. Only status/journal changes.

### Partial close (`p`)
Mandatory actual exit-side fill price, positive quantity <= remaining quantity, UTC time, known/unknown fees. Show remaining quantity and estimated realized P/L prior to confirmation. Never auto-reduce the live broker trade.

### Modify (`m`)
Record actual externally edited stop/target, UTC effective time, note and current risk change; explicitly warn if stop is being moved **further away**. Saving only records locally and cannot change broker positions.

### Close (`x`)
Mandatory actual exit price, full remaining quantity (default prefilled and validated), UTC time, fees known/unknown, optional notes. Only after user confirms local state moves to CLOSED.

## 10. Empty, stale, invalid and reconnect states

| Condition | Correct visible behavior |
| --- | --- |
| App first start, no feed/history | `DATA NOT LOADED — import/replay data`, directions not invented |
| No forming setups | `No developing opportunities`; not an error |
| No READY signals | `NO TRADE — conditions not met` with highest-priority reason |
| REPLAY paused or reached end | Display last event time + `REPLAY ENDED/PAUSED`; do not show live timestamp |
| MT5 demo disconnected | Red `FEED OFFLINE` with time-of-last-quote and no new READY |
| Reference feed vs external broker | `INDICATIVE QUOTE — verify execution venue`; no false 'broker verified' |
| Order/position price touched only in chart | `TOUCHED — execution unconfirmed`; never auto-close |
| Source gaps / missing ATR | Explicit `DATA UNKNOWN`; no fake zero-risk values |
| 80-column terminal | Stack panels, hide nonessential columns; selected signal still has exact SL/TP in details |
| User quits with recorded open positions | `Positions remain open at broker; Grog will not close them. Reconcile on restart.` |

Use textual labels in addition to color. Error messages must include a practical next step (import another file, reconnect demo server, check contract metadata) **without performing external actions**.

## 11. Numbers, timestamps and formatting

- UTC date/time in headers as `YYYY-MM-DD HH:mm:ss UTC`; optional local clock is secondary and labeled `PKT` or configured IANA zone. Replay timestamps are **virtual** event times, not local now.
- Price precision equals actual source price format; when known, broker tick size controls valid SL/TP rounding, not UI decimal count. Unknown values show `—` / `UNKNOWN`, never 0.
- Long BUY uses ASK entry and BID close/SL/TP; SELL uses BID entry and ASK close. The UI labels these sides everywhere.
- R multiples: sign and at most 2 decimal digits in tables, extended precision in details/reports. Net P/L is labeled ESTIMATE or ACTUAL; fees UNKNOWN must show separate warning.
- Spread appears in Gold quote units and `spread / initial risk` only where denominators known. Never double-subtract spread from BID/ASK-based P/L.
- Status precedence in headers: FEED/QUOTE UNSAFE > STRUCTURE INVALIDATED/TTL > RISK POLICY BLOCK > WAIT FOR TRIGGER > SOFT WARNING. Do not mask a safety blocker with a gold/green visual accent.
- Keep a maximum 50 visible journal/event rows in the scrolling UI buffer; data storage retains all events under selected retention policy. Don't repeatedly render identical price alerts.

## 12. UI acceptance checklist — for Grok

**Use Textual's widget/Pilot testing approach where practical**, plus saved text-only screen state snapshots (not pixel-perfect fonts). On each implementation milestone verify:
1. Correct data-fidelity badge for REPLAY/REFERENCE/EXECUTION_VERIFIED and honest data time.
2. Forming, READY, blocked and held-position lanes remain distinct across all five views.
3. Exactly one immutable signal per pair across ticks/restart.
4. Missing inputs and errors never become zero values, fake win probabilities or chart fills.
5. Key bindings work and have **no effect when editing a form field**; confirmation required for local journal mutations.
6. Table focus/selection persists as quotes update; accessible labels work in monochrome mode.
7. 120×34 and 80×24 layouts have no overlapping critical information; 70×18 fallback is usable.
8. No broker orders can be created by any UI interaction.
9. Restart restores local positions as unverified; source-disconnected screen prominently warns.
10. Offline smoke demo uses deterministic fixture values and explicit `SIMULATED` everywhere.
11. Screenshot/terminal recordings, if produced, are **demo-only** and contain no private credentials or broker account identifiers.

**No implementation code is created by this document.**