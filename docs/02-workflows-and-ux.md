# Workstation UX — Canonical Terminal and Desktop Contracts

**Updated:** 2026-11-07  
**Status:** Product intent APPROVED; interface specification is the **implementation baseline when Grok is asked to start**. The visual designs below are synthetic examples, not live prices, real signals or evidence of profitability.

**Owner:** workstation layouts, wording, keyboard/navigation, input forms and empty/error states. Existing terminal sections remain the R0 fallback; §15 is the native desktop direction. Algorithm math is **not** defined here: indicators [04](04-analysis-engine.md), strategies [05](05-strategies.md), signal state/expiry [06](06-signals-and-scoring.md), actual fills/monitoring [07](07-risk-and-monitoring.md), validation [08](08-validation.md).

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

### 2.1 R0 premium terminal visual system (normative for the R0 build)

The tokens above are unchanged; this section fixes how they are composed so every view and modal reads the same way.

- **Shell, top to bottom:** (1) **header** — `GROG / GOLD WORKSTATION`, `XAUUSD`, a filled **mode badge** (`REPLAY • <ORIGIN>`), `SIMULATED`, playback state, virtual UTC clock; second line `Source: <id> [<source status>]`, BID / ASK / spread, pace and PRE-ROLL count. (2) **view tabs** — `1 LIVE  2 SIGNALS  3 POSITIONS  4 JOURNAL  5 DIAGNOSTICS`, active tab filled gold, counts of READY signals and open/unverified positions on their tabs. (3) **critical banner** (only when a safety state applies, docs/02 §11 precedence). (4) the view. (5) **context key bar** — only the keys valid in the current view, always ending with `[No orders]`; below 110 columns the labels become short whole words (`Enter open`, `e fill`, `p part`, `m mod`, `n ext`), never cut mid-word.
- **Panels:** every panel is a bordered box (`round`, border token) whose **border title** is the panel name in gold caps; content never repeats the title visually. Inner padding 1 column. A panel shows at most one idea per line; numbers that belong together (side, price, SL, TP) stay on one line with BID/ASK labels.
- **Status chips:** `[FRESH]` ok colour; `[UNKNOWN]`, `[STALE]`, `[DEGRADED]` caution; `[OFFLINE]`, `[MARKET_CLOSED]` error; text always carries the meaning. A safety blocker is never drawn in gold/green.
- **Tables:** gold header on raised background; selected row bold on raised background; secondary columns hidden below 120 columns; states always use full words (e.g. `RECONCILIATION REQUIRED`); cell padding is 1 column so the full Positions table fits 120 columns.
- **Breakpoints:** `>=120x34` full layout (side-by-side Live panels); `80-119` columns stacked panels with compact columns; `<80` columns or `<24` rows (tested at **70x18**) single column, panel borders reduced to a top rule that still carries the title, the resize notice shown, header/tabs/banner/key bar always visible, and every value still reachable by scrolling or `Enter` details.
- **Modal anatomy (all journal modals: Record Entry, Skip, Unlinked, Partial, Modify, Close; and Position Details / Reconciliation):** one bordered dialog with sections in this fixed order — **(1) identity** (border title = action, then signal/position ID, side, mode label), **(2) plan / position** (immutable original plan or current recorded position), **(3) fields** (your actual values; required fields marked `*`), **(4) risk preview & warnings** (live preview, exposure/OFF_PLAN/stop-further-away warnings, `NOT SAVED — reason` errors), **(5) actions** — `Confirm …` and `Cancel`, with **Cancel focused by default**. A hint line states that typing never triggers hotkeys, Esc cancels (twice when edited) and nothing is sent to a broker. Details overlays use the same box with a gold border title and `[Esc] Back`.

Authoritative Textual API references: https://github.com/Textualize/textual/blob/main/docs/guide/app.md and https://github.com/Textualize/textual/blob/main/docs/widgets/data_table.md

### 2.2 Live decision-first presentation (2026-11-06)

The Live view prioritizes the **current decision** above market evidence: (1) current actionable/simulated decision, (2) H1/M15/M5 context and forming watchlist, (3) manually recorded positions, (4) a short recent-state-transition feed. Keep the full Journal, Signals, Positions and Diagnostics views.

- The `NO TRADE` state remains explicit, with the next actual M5 condition displayed when the selected developing candidate is waiting for a trigger.
- The Live watchlist shows direction, state and next condition, while preserving the full immutable candidate ID in the row key and `Enter` details.
- Limit the Live event feed to four recent state transitions; do not discard engine or journal events.
- Retain immutable signal issuance/current status, source fidelity, correct BID/ASK prices, manual-record-only actions, keyboard controls and responsive detail access.
- These are presentation-only changes. No strategy rules, eligibility, prices, thresholds, P/L, executions or journal records are recalculated by the UI.

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
| `n` | Open **Record Unlinked Manual Entry** from Journal or Positions only | Explicitly OFF_PLAN/unverified; local journal only, **never** a broker order |
| `r` | Request UI panel refresh using latest already-ingested state | Must not cause duplicate market events |
| `Space` | **REPLAY only:** pause/resume historical playback | Does not alter actual market timestamps or emit LIVE signals |
| `.` | **REPLAY paused only:** step one normalized market event | Event-time/available_at advance exactly once |
| `+` / `-` | **REPLAY only:** switch playback pacing 50 events/s, 500 events/s or FAST (unthrottled) | Engine events are never skipped; only UI redraw throttled |
| `?` | Compact help overlay with keys and meanings | View only |
| `q` | Quit local program with informative warning if positions recorded as open | No broker action; persisted positions remain |
| `Ctrl+P` | OPTIONAL Textual command palette once stable | No new functionalities; shortcuts can expose above actions |

**Important:** Key bindings are global only when not typing into an input. Modal fields have priority; `e`, `s`, `x` typed into a price/notes input must **never** trigger the parent action. No global hotkey may place a broker order.

## 4. Screen 1 — LIVE / OVERVIEW (>=120 columns)

**Synthetic REPLAY screen** (values intentionally fictional; do not interpret as a trade):

```text
 GROG / GOLD WORKSTATION               XAUUSD   REPLAY • SYNTHETIC            2026-10-31 09:37:15 UTC
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
 H1: UP [08:00-09:00 UTC closed]     M15: CORRECTIVE     M5: Closed trigger confirmed
 First entry ASK: 4000.20    Current ASK: 4000.25    Valid band: [3999.99 - 4000.62]
 SL BID: 3998.00   TP1 BID: 4002.40   TP2 BID: 4004.60   Gross target: 2.0R
 Net risk/return: UNKNOWN (execution broker fees not confirmed)
 Issued: READY at 09:37:15 UTC (immutable plan)   Now: READY
 Eligibility at issuance: PASS (reference-only)   Warning: M15 corrective; monitor structural low
 Action: [e] Record external manual fill    [s] Skip    [Esc] Back
 No automatic broker order is created.
```

**Example values are illustrative;** the displayed price band must be computed by [06](06-signals-and-scoring.md) using actual frozen ATR and quote; timestamps must be consistent with actual snapshots. In the example, H1 was last confirmed at 09:00 UTC. A later unclosed H1 bar may be displayed as provisional but cannot be used for READY. Never fabricate available M15 pivots.

**Issued vs now (R0, docs/14 F-08):** the detail always separates the immutable issuance (`Issued: READY at …`) from the current state (`Now: READY | EXECUTION BLOCKED | EXPIRED | INVALIDATED`) and any local journal action (`ENTERED`, `USER_SKIPPED`). `[e]`/`[s]` appear only while the signal is still READY with no local action; when EXECUTION BLOCKED the hint reads `Record external fill (OFF_PLAN)`; otherwise the detail states why there is no on-plan action. A signal already ENTERED or USER_SKIPPED is never listed as a fresh opportunity on Live; same-side/opposite-side open positions are shown as `EXPOSURE:` warnings that never block and apply no limit (overlap policy OPEN).

A numeric quality percentage is **NOT** part of MVP: [06](06-signals-and-scoring.md) explicitly forbids uncalibrated '85% probability' labels. Show **why** the setup is ready and what would invalidate it.

**Priority behavior:** On simultaneous multiple candidates, show duplicates suppressed, exposure conflicts as explicit warning (not as hidden ranking), no forced one-signal selection until policy and evidence are ready.

## 6. Screen 3 — ACTIVE MANUAL POSITIONS

Table columns: `position ID`, `signal ID`, `side`, `qty`, `actual entry`, `current closeable quote`, `initial/current SL`, `TP status`, `gross/net estimated P&L`, `R`, `STATE`; `last updated` and the full event list are in `Enter` details so the table fits 120 columns (R0). 80-119 columns: position, side, qty, entry, R, state; <80 columns: position, side, qty, R, state.

- **Mark freshness is explicit** (docs/14 F-04): every mark carries `FRESH`, `UNVERIFIED` (thresholds not configured), `STALE`, `DEGRADED`, `MARKET_CLOSED`, `OFFLINE`, `REPLAY_ENDED` or `UNAVAILABLE`. Any non-`FRESH` mark is tagged in the table, the Live strip and the detail, with its reason; it never looks fresh.
- **R column** is gross total R = (realized + unrealized remaining) / original full-position risk (docs/07 §6.1). Details show per-unit move R, realized R, unrealized remaining R, total, the denominator, and `Net R: UNKNOWN`.
- **Long closeable mark is BID**; short closeable mark is ASK. Unknown lot specs/fees => `P&L UNKNOWN` with a clear explanatory reason; never treat reference-feed unrealized P&L as true account balance.
- Immediately show `RECONCILIATION REQUIRED` for positions restored after restart until user verifies them.
- Advisory event strip: `TP1 APPROACHING`, `STOP TOUCHED (NOT VERIFIED FILL)`, `H1 BIAS CHANGED`, `FEED STALE`, `MANUAL BROKER VERIFICATION NEEDED`.
- `Hold / reduce / exit` **advice** is absent until a separately tested rule is approved; show factual conditions without recommending unseen actions.
- If operator records a close/partial manually, append the action and update remaining lots and actual fill fees. Never submit any order.

## 7. Screen 4 — JOURNAL

Compact searchable/sortable local table: `UTC`, `recorded by` (the fill/record source: `OPERATOR` for operator-confirmed local journal records, `SIM ENGINE` for session SIMULATED signal events — never mixed or merged), `action`, `signal/position`, `side`, `state`, `realized R`, `reason`, `strategy ver`, `source fidelity` (secondary columns last; <120 columns shows UTC, by, action, ref, state). The filter also matches full IDs, reasons and mode behind abbreviated cells. `Enter` on a row opens the full record (every column, full IDs). Simulated replay outcomes from `grog replay` are research reports, never journal rows.

Filter via text input by `signal ID`, `date range`, `status` and `mode`; these are **local journal filters**, not a new analytics dashboard. Journal retains SKIPPED/MISSED/EXPIRED/RESEARCH_READY with correct state names and actual entered trades. When no file/history exists show `No journal events yet`, not sample gains.

Recording error correction is an **append-only correction event**, never silent deletion of original actions. Full-text search is optional after basic table filters work.

## 8. Screen 5 — DATA DIAGNOSTICS

Show `mode`, `source_id`, broker/server/dataset, original symbol and `canonical=XAUUSD`, UTC provider/receive latest timestamps, quote age, BID/ASK, spread, last finalized M1/M5/M15/H1 bars, missing ticks/bars, replay/import checksum and gaps, adapter status, history warm-up sufficiency, schema/config version, current data fidelity.

Source status labels are `FRESH`, `STALE`, `DEGRADED`, `UNKNOWN`, `OFFLINE`, `MARKET_CLOSED` as **diagnostic presentation**, distinct from the signal's domain FSM. `UNKNOWN` means freshness thresholds are not configured (docs/11 keeps them OPEN) and is shown with `Freshness thresholds: NOT CONFIGURED`; it is never relabeled `DEGRADED` or `FRESH`. Playback (`PLAYING`, `REPLAY_PAUSED`, `REPLAY_ENDED`) is shown **next to** the source status and never replaces it. Show reason and latest reliable quote time prominently.

No account balance, wallet, 'connect bank', API wallet, transaction dashboard or account order panel.

## 9. Modal contracts — manual actions, not trading commands

### Record Entry (`e` on READY)

Mandatory: selected `signal_id`, `side` (read-only), `actual fill price` (decimal, required), `actual filled quantity/lots` (positive decimal), `actual fill UTC time` (explicit; default **form-opening time**, user can correct), `trade label: SIMULATED / MANUAL` (derived from current mode). Optional: `commission`, `operator note`, `broker name`, actual stop/targets if different from recommended. The signal's original E0/SL/TP remain immutable.

Validation: no negative/NaN, finite amounts, quantity >0, broker tick size when known, event time not ahead of known clock without warning, duplicate action IDs rejected, and enough info to distinguish off-plan. Display **before saving** the original entry vs actual price, changed gross risk/target R and whether it is OFF_PLAN, if calculable. Buttons `Confirm local record` and `Cancel` (default selection Cancel). Do not send trades to a broker.

### Skip (`s` on READY) and Missed
Show signal identity, direction, reason (optional), original expiry and `Mark skipped` confirmation. Distinguish `USER_SKIPPED` from system EXPIRED/MISSED. Only status/journal changes.

### Unlinked / off-plan entry (`n`, Journal or Positions only)

The trader may have manually entered a real external XAUUSD position **without a READY recommendation**, or after the recommended band/TTL expired. Allow an explicitly labeled **OFF_PLAN** local position record with side, actual price, qty, UTC fill time and optional broker/notes; optional link to the historical signal ID is informational and **never changes** an EXPIRED/INVALIDATED/FORMING signal into READY. Confirmation dialog states **\"This records your external trade; Grog did not recommend or execute it.\"** The mode and source-fidelity labels still apply; real account monetary P/L remains UNKNOWN without validated contract details.

### Partial close (`p`)
Mandatory actual exit-side fill price, positive quantity <= remaining quantity, UTC time, known/unknown fees. Show remaining quantity and estimated realized P/L prior to confirmation. Never auto-reduce the live broker trade.

### Modify (`m`)
Record actual externally edited stop/target, UTC effective time, note and current risk change; explicitly warn if stop is being moved **further away**. Saving only records locally and cannot change broker positions.

### Close (`x`)
Mandatory actual exit price, full remaining quantity (default prefilled and validated), UTC time, fees known/unknown, optional notes. Only after user confirms local state moves to CLOSED.

## 9A. REPLAY playback and warm-up behavior

- CLI `grog replay` processes the source as quickly as it can while respecting stable event order and deterministic virtual UTC time. **Never** delay the analysis engine based on UI refresh.
- Interactive `grog ui --mode replay` first loads the saved source and pre-rolls enough historical events to satisfy valid MTF warm-up **if available**; the resulting market-state snapshot is marked historical, and the UI starts **PAUSED** at the first post-warm-up quote for inspection. If history is too short, show `INSUFFICIENT HISTORY` and permit user to view diagnostics rather than forging an EMA.
- UI controls: **Space** play/pause, **.** process one quote event when paused, **+/-** cycle through 50 events/s, 500 events/s, FAST. Pacing is **events per second**, not misleading "1x market speed"; UI redraw remains capped independently.
- An optional `--from ISO_UTC` selects the **visible decision window**; the replay engine must still process preceding valid lookback events as research pre-roll to form historical EMA/ATR/pivots. The source event time and availability must never be rewritten to the current wall clock.
- At replay end, keep the last snapshot with `REPLAY ENDED`, allow navigation/review/journal but no new quote or fresh signal. A PRE-ROLL/SYNTHETIC label must remain visible; pre-roll generated signals are history, not new live alerts.
- These controls are **view/test ergonomics only**; no new trading strategy, probability, broker access or automatic execution.

## 10. Empty, stale, invalid and reconnect states

| Condition | Correct visible behavior |
| --- | --- |
| App first start, no feed/history | `DATA NOT LOADED — import/replay data`, directions not invented |
| No forming setups | `No developing opportunities`; not an error |
| No READY signals | `NO TRADE — conditions not met` with highest-priority reason |
| REPLAY paused or reached end | Display last event time + `REPLAY ENDED/PAUSED`; do not show live timestamp |
| MT5 demo disconnected | Red `FEED OFFLINE` with time-of-last-quote and no new READY |
| Reference feed vs external broker | `INDICATIVE QUOTE — verify execution venue`; no false 'broker verified' |
| Reference feed not configured / unavailable (M09) | `REFERENCE NOT_CONFIGURED` (no `[reference]` config) or link state `NO_DATA / CATCHING_UP / OFFLINE / DISCONNECTED / MARKET_CLOSED / UNKNOWN` ([09 §5.1](09-architecture.md)); no mock or replayed quotes shown as live; fixture-producer files always read `FIXTURE · SIMULATED` |
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
## 13. Terminal command output contract — noninteractive CLI

**CLI output should be compact and unambiguous**, suitable for copy/paste into the Grok milestone report. No colored dashboard or interactive spinner required for commands that are not the Textual UI; use plain text summary and stable labeled status. Structured `--format json` may be implemented for deterministic test/report consumers **after** text mode is correct; never introduce a remote API to deliver it.

**Illustrative diagnostic output (fields are placeholders, not a real import):**

```text
GROG / DOCTOR                                 MODE: REPLAY  VERSION: <package-version>
Python: <version>        Source configured: NONE
Local state: <state-dir>  Database: AVAILABLE / NOT INITIALIZED
Market feed: NOT CONFIGURED [offline mode — expected]
Live broker: NOT REQUIRED FOR REPLAY
Trading/orders: DISABLED
Next: import a synthetic BID/ASK fixture or use an existing source ID.
```

**Illustrative replay result summary (no fabricated trade claims):**

```text
GROG / REPLAY REPORT                          FIDELITY: SYNTHETIC
Source: <source-id>    Range UTC: <start> .. <end>
Strategy: S1_RESEARCH_V0_2   Config: <sha256-prefix>
Data: <N> ticks | <N> completed M5 bars | <N> rejected/unknown
Decisions: <N> DETECTED | <N> FORMING | <N> READY | <N> INVALIDATED | <N> EXPIRED
Proposed entries: <N> | Fillable simulated: <N> | Actual broker fills: NOT AVAILABLE
Execution: first observable BID/ASK; contract/fees: UNKNOWN
Gross hypothetical R: <value or NOT EVALUATED>
Net broker P/L: NOT AVAILABLE — no verified execution contract
Warnings: <known gaps/cost assumptions/outcome ambiguity>
Verdict: OFFLINE FUNCTIONAL TEST ONLY; STRATEGY EDGE NOT VALIDATED
```

**Error example:**
`IMPORT_REJECTED line=17 field=ask reason=ASK_BELOW_BID; batch NOT committed; prior data unchanged.`

Report must never display a positive balance, live profitability or numeric confidence when the data cannot justify it. Metrics are produced by the **engine** and formatted by the interface, not recalculated independently in UI components.

## 14. Final UI definition of done

All five screens, two responsive layouts, keyboard controls including off-plan manual recording, lossless (within tested source limits) state visualization, explicit source fidelity, missing data displays and manual entry/partial/close/restart behavior must be validated against [08 — Tests](08-validation.md). Visual acceptance additionally requires: consistent 1-character separators, no overlapping borders in 80-column view, predictable focus and contrast, clipped columns whose full values are available in details, and no repeated tick-notification flood. No extra UI features may be added solely for aesthetics.

## 15. Native desktop GUI design (approved 2026-11-07)

**Status:** Historical D00–D05 design contract. All five native pages, manual journal UI, source chooser and desktop parity were implemented on main by `c0ef834` (2026-11-07); a complete **owner-approved V2 visual/interaction redesign** now follows [desktop-visual-redesign.md](desktop-visual-redesign.md). The Textual app remains fully supported. [Decisions](11-decisions.md), [Architecture §12](09-architecture.md), [Roadmap §11](10-roadmap.md).

- **Form factor:** local Qt Widgets application, not web. Left navigation for Overview, Signals, Positions, Journal and Diagnostics, plus a separate unnumbered Settings utility. Premium graphite Dark and warm-white Light themes, **System** following OS appearance, accessible typography, whitespace and mouse/keyboard controls. No charting sprawl, SaaS, wallet, broker orders or new trading features.
- **Overview:** prominent *No trade / Developing / Simulated READY / Execution blocked* state, the grounded next condition, readable BID/ASK/spread, feed fidelity and virtual UTC. Explain H1 trend, M15 structure, M5 trigger before showing low-level event codes.
- **Signals:** forming, ready/blocked and history are visually separate; full IDs and reason codes live in details. Preserve original vs current signal state, immutable entry/band/SL/TP1/TP2, TTL, price sides and operator action.
- **Positions and Journal:** explicit manual-only records, mark freshness, confirmation dialogs, append-only state, source identity, fee/risk unknowns and restart reconciliation. No trade is inferred from a quoted touch.
- **Diagnostics:** exact data age, gaps, completed bars, source hashes, pre-roll, link status and unknown inputs. Never silently relabel REPLAY as live.
- **Numbers:** format original Decimal values with grouping; never convert to float, assume two decimals, round an executable price, assume tick size, invent precision or turn unknown into zero. Source-specific precision requires verified metadata.
- **Actions:** dialog confirmation defaults to Cancel and revalidates state at save time. Blocked, expired or already-acted signals must not silently produce new on-plan entries. All journal writes use existing validated service methods.
- **Time/threads:** replay event order and source timestamps stay causal; only display redraw may be throttled. Qt widgets on GUI thread; replay worker/SQLite ownership explicit. No worker modifies Qt controls.
- **Sizes:** verify 1366×768, 1920×1080, high DPI, enlarged text, keyboard-only flow, empty/error states and readable signal details.
- **Cutover:** `gold` continues to launch Textual until desktop feature parity, observed visual QA, full suite and owner approval; `grog ui` remains fallback.

Acceptance matrix: [08 §19](08-validation.md). This specification sets no strategy or risk thresholds.

## 16. Complete native workstation interaction specification — D00–D05 handoff (2026-11-07)

**Status:** This section preserves the functional/interaction contract used for the now-implemented D00–D05 baseline. The owner-approved **V2 presentation redesign** is specified in [desktop-visual-redesign.md](desktop-visual-redesign.md), with U0–U5 in [10 §13](10-roadmap.md). Where desktop presentation differs from terminal geometry, §16 governs desktop behavior; exact new palette and typography live only in the visual companion. Underlying rules and validations remain in [03–07](00-index.md); concrete ports, thread boundaries and persistence are [09 §13](09-architecture.md); reproducible cases [08 §20](08-validation.md); ordered gates [10 §12](10-roadmap.md). No market claims, broker execution or automatic trade actions.

### 16.1 Mental model, navigation and visual language

The application is **GOLD — XAUUSD Decision Workstation**, a five-screen desktop, not a Bloomberg clone, broker terminal, web dashboard, social feed or AI assistant. The same data appears consistently in three non-interchangeable lanes: **Developing (not tradable)**, **READY proposal (research-simulated or indicative)** and **Manually recorded position (not broker-synced)**. Engine history and operator actions are two different sources of truth. A signal is never a position.

**Shell anatomy (all screens):** (1) fixed narrow sidebar with GOLD/GROG identity, Overview / Signals / Positions / Journal / Diagnostics and counts, plus unnumbered **Settings** separate from numbered page shortcuts; (2) fixed slim top status strip containing XAUUSD, mode, immutable source ID/origin, source health, latest provider/receive UTC and virtual replay UTC (compact human time may follow chosen PKT/UTC, with exact UTC retained in detail); (3) contextual safety banner *above* page content when feed/reconciliation/blocked risk matters; (4) scrollable page body with a persistent title and one-line purpose; (5) fixed lower replay toolbar for REPLAY mode only, showing Play/Pause, Step one quote, pace (50 events/s, 500 events/s, FAST), processed/total and pre-roll count, plus **No broker orders**. A page transition must not restart/rewind replay or mutate the journal. Main shell stays responsive during data loads and rendering.

**Owner-approved V2 visual tokens:** The old blue/navy palette is **superseded for presentation**. Implement a neutral charcoal Dark theme (app #111111, surface #1B1B1B, text #F4F4F1) and a matching warm-white Light theme (app #FAFAF9, surface #FFFFFF, text #232320), using the **complete shared semantic palette, typography, spacing and state/accessibility rules** in [desktop-visual-redesign.md §3](desktop-visual-redesign.md#3-design-system--stable-visual-tokens). BUY and SELL are semantic sides, not positive/negative trade advice; errors/warnings have independent severity styles. No fake charts/neon/badges; user-selectable Dark / Light / System and PKT / UTC are defined below. All existing functional contracts and lossless exact/audit detail remain in force.

**Appearance and time Settings (owner-approved 2026-11-07):** Provide a dedicated unnumbered Settings utility reachable by keyboard in wide and compact layouts. **Dark** (fresh-install default) and **Light** are persistent overrides; **System** reads and follows the supported OS light/dark scheme, including in-session changes. If OS scheme is unavailable, keep the selection as System but label effective **Dark fallback**; never imply successful OS detection. Explicit user selections persist independently of source selection and SQLite. Provide **PKT (Asia/Karachi) / UTC** as compact display preferences; exact UTC milliseconds and all event/provider/received/recorded roles remain visible in details and audit. Switching preference must not alter signals, engine events, replay cursor, journal, action IDs, source identity or existing shortcuts **1–5**. See [desktop-visual-redesign.md §§4–5](desktop-visual-redesign.md#4-settings--an-additional-utility-view-not-a-sixth-trading-screen) and [08 §21](08-validation.md#21-desktop-uiux-v2-additional-acceptance--owner-approved-2026-11-07).

**Desktop width contract (logical pixels, not physical screen pixels):**

| Window content width | Required composition | Never lost |
| --- | --- | --- |
| >=1440 | Sidebar 204–224px; main two-column Overview; three small quote metrics; full list columns | Source/fidelity, decision, safety state, exact selected plan |
| 1100–1439 | Sidebar ~200px; decision full width; context/watchlist side by side where they fit; secondary columns in detail only | Quote labels, playback and record access |
| 820–1099 | Compact/collapsible sidebar or top five-tab switcher; one-column scrollable cards; compact tables with expandable detail | All five pages, keyboard focus, forms, risk warnings |
| Height <=768 or enlarged text | Keep top source/safety and bottom controls visible; page content scrolls, dialogs internally scroll | Confirm/Cancel, input validation, exact full IDs |

The supported minimum app window is **820×620 logical px** unless measured Qt constraints require a slightly larger *documented* minimum; do not clip a trading safety message to force the minimum. Verify 1366×768 and 1920×1080 desktops, 100%/125%/150%/200% scaling, keyboard-only operation, dark-theme contrast, screen-reader labels/tooltips and non-color status distinctions. Avoid absolute positioning and overlapping fixed-height panels. Show full precision in details whenever a table ellipsizes.

### 16.2 Overview — current decision first

At first glance, answer **Can the operator act? Why/why not? At what sourced price?** Show these in priority order:

1. **Decision banner (full-width, first):** single truthful headline: NO TRADE, Developing BUY/SELL — NOT READY, SIMULATED READY BUY/SELL (possibly multiple, **never secretly rank**), Execution blocked, Insufficient history, Replay ended or Data unavailable. Include the primary reason and grounded next condition, with exact engine reason code available in details. Do **not** call a FORMING trigger a trade. A blocked/reconciliation/unsafe-data banner takes visual precedence over green/gold.
2. **BID / ASK / spread:** separate price cards, original Decimal scale, units **XAUUSD price units**, source/quote received UTC, quote freshness and REPLAY virtual time. Ask is the theoretical BUY entry side; bid the SELL entry side. Source origin and SIMULATED/REFERENCE labels never leave the screen.
3. **Context strip:** last finalized H1 trend, M15 buy/sell structure, M5 setup/trigger state, ATR only if the engine supplies a valid value; show last confirmed close/availability timestamps in expanded details. If unfinished bars appear, visibly tag **PROVISIONAL** and do not use them to imply readiness.
4. **Developing watchlist:** a bounded, keyed list with side, candidate ID (truncated only visually), current status, human-readable *next confirmed M5 BID close condition*, time and reason. Click/Enter expands frozen pair, thresholds, evidence and codes. Do not turn missing thresholds into 0. Count/watchlist must match engine snapshot.
5. **Manual position strip:** counts of open, reconciliation-required, off-plan; show closeable BID/ASK marks with freshness, not a portfolio/account balance. Clicking opens Positions selected by stable position ID.
6. **Recent changes:** last four meaningful engine or feed state transitions, including PRE-ROLL label and exact virtual UTC; provide link to complete current-session history in Journal. Never fabricate an event or append every quote as an alert.

At REPLAY end, retain last quote and history but label **REPLAY ENDED — historical mark**, never fresh live data. If multiple READY, show count and route to Signals, with no default recommendation or auto-selection. UI output must match the same source snapshot shown by Textual.

### 16.3 Signals — three distinct areas and an audit-grade detail view

Provide tabs/sections **Developing**, **READY / execution-blocked**, **History** with counts; state and search filters do not change the engine. Developing rows: candidate ID, BUY/SELL, S1, H1/M15 context, last eligible M5 close, trigger requirement, age, reasons; detail clearly says **NOT TRADABLE**. READY rows: immutable signal ID, side, strategy version, issuance UTC, current state, source fidelity, E0 price side, band, SL/TP1/TP2, expiry UTC/time remaining, operator overlay; blocked signals stay visible and clearly labeled **EXECUTION BLOCKED — no on-plan entry**. History includes terminal EXPIRED/INVALIDATED, pre-roll, entered/skipped and missed/non-issued *events* with their actual domain event types; never invent a persisted SignalRecord for a gate failure.

The detail drawer is the **single complete signal explanation**: (a) full IDs, side and origin, first READY UTC, immutable issued state vs **current** READY/BLOCKED/EXPIRED/INVALIDATED and operator ENTERED/USER_SKIPPED; (b) confirmed H1/M15/M5 evidence and source availability; (c) E0 = ASK (BUY) / BID (SELL), original BID and ASK, exact entry-low/high, SL0, TP1, TP2 and corresponding closeable price side, frozen ATR, original gross risk; (d) current applicable BID/ASK, spread, quote age/freshness, TTL/expired-at, blocking codes and revalidation rationale; (e) original strategy/config/rule version, source ID/origin/fidelity; (f) operator action/exposure warnings and **local-only** actions. Status is never synthesized from color or the user action alone. If now expired/invalidated or already acted, disable on-plan entry/skip; a real externally filled trade can only be recorded by an explicitly separate OFF_PLAN workflow. An execution-blocked signal may expose **Record external fill — OFF_PLAN** with an explicit acknowledgement; never offer it as on-plan Record Entry.

Selections use stable full candidate/signal IDs; sorted tables preserve selection/focus while replay advances and if a row moves to History, show a non-destructive moved-state notice. The selected details may update when the corresponding engine revision arrives, but frozen plan fields never change. Time remaining uses the **virtual** replay clock in REPLAY, not wall time.

### 16.4 Positions — manual record, honest monitoring, reconciliation

Default to **Open**, with **Needs reconciliation** and **Closed history** filters. Row shows position ID, linked signal or OFF_PLAN, side, remaining/initial qty, actual entry and time, current *closeable* BID (BUY) or ASK (SELL), mark freshness and timestamp, original/current stop, TP1/current target, realized/unrealized/total **gross R** when determinable, state and action-menu. Currency P&L/net R stay **UNKNOWN** without contract/cost metadata; don't invent USD, balance, profit or lot conversion. Keep actual operator broker label optional and its data separate from source venue.

Selected detail: complete immutable entry, PlanRef (if any), actual vs planned risk, fees known plus UNKNOWN count, off-plan reasons, observed stop/TP touches **not fills**, H1 bias change as observation, current freshness, full append-only PositionEvents with event UTC versus recorded UTC, and actions. Present factual observations, **no Hold/Reduce/Exit recommendation**. Expose Record partial, Record close, Record modify only for open records. A closed record is permanently read-only except an explicitly approved correction service in a future separate scope.

On each **writable** desktop session start, the existing validated **restore_on_startup** flow marks every persisted MONITORING record RECONCILIATION_REQUIRED; no double event for already unverified records, including multi-process startup. Present the reconciliation worklist *before* any "currently held" assertion. **Confirm open** is available only on RECONCILIATION_REQUIRED with a positive operator acknowledgement that they checked their actual broker; record through **confirm_open**. If the broker reports a partial/close/modify, use the corresponding manual form first, not an invented automatic sync. Do not manufacture an "assume closed" option. If the DB is read-only/unavailable, show saved positions read-only as **UNVERIFIED**; never call restore and never call them confirmed open.

After a partial, refresh remaining quantity, gross R with original full-risk denominator and event history. A price touch changes the observation only; it **never** closes or reduces quantity, and TP1 is not an automatic 50% exit. When the loaded source/time is before a fill or differs from the position source, mark **UNAVAILABLE** rather than price-marking a different venue.

### 16.5 Journal — two provenance-distinct streams, complete discoverability

Make explicit sections/filters for **Operator records (SQLite persisted)** and **Research/replay signal events (engine-derived)**, plus combined chronological view with provenance labels. Operator records comprise PositionJournal.events and decisions: ENTRY, PARTIAL_CLOSE, MODIFY, CLOSE, RESTORED_UNVERIFIED, CONFIRMED_OPEN, USER_SKIPPED and OFF_PLAN. Signal/S1 events come from the active session pipeline; replay research-run records live under their separate existing ResearchStore/reports, **not** in the manual journal. On restart, signal events from an imported source are **reconstructible by replay**, but an interactive view must **not** claim their full event stream was committed as operator records or offer an invented persistence guarantee. Never duplicate, drop or reclassify events when changing filters or tabs.

Columns and filters: event UTC, recorded UTC if applicable, producer (**OPERATOR** / **SIM ENGINE**), event type, full stable ref (display may abbreviate), BUY/SELL, engine state, operator state, strategy/source/fidelity, reason; filters: free-text/full ID, UTC start/end (start inclusive, end exclusive), producer, type/state, side and source/mode. Default newest first; deterministic tie order and stable row keys. Offer efficient incremental/virtualized loading or pagination for long histories, while search and detail remain complete; a 50-row *visible* buffer is not a 50-row storage limit. Enter/click reveals raw codes, exact event time/recorded time, immutable payload, original source/strategy and full IDs. No "equity curve" or fabricated paper profit.

Correcting mistaken operator records is **not implemented in the existing journal API** despite §7's longer-term append-only correction principle. Do not add arbitrary edit/delete UI, direct SQL or rewrite events. Record this gap as separately approval-gated service design; at desktop parity, existing allowed actions and truthful immutable history are required.

### 16.6 Diagnostics — actionable technical evidence, not settings guesses

Group into **Source & provenance**, **Feed health**, **Confirmed bars & warm-up**, **Replay integrity**, **Engine / eligibility**, **Reference-adapter status (read-only)** and **Local journal / errors**. Show provider UTC versus received UTC, quote age (virtual clock for replay; separately labeled wall time only in authorized reference mode), spread, raw/canonical symbol, source ID/origin, import batch SHA256 and paths safely redacted where appropriate, config hash/version, DB schema version, bar counts and last confirmed/available M1/M5/M15/H1 times, gaps/missing bars, H1/M15/M5 warm-up and indicator status, first-quote eligibility reasons, strategy version, replay cursor/total/pre-roll/window/pacing, integrity/error counters. Source status (FRESH/UNKNOWN/STALE/DEGRADED/CLOSED/NO_DATA) must be separate from PAUSED/PLAYING/ENDED and from position mark freshness.

For M09-A/H, show only **read-only status** through the existing ReferenceStatus / reference-status port when explicitly configured: NOT_CONFIGURED, NO_DATA, INTEGRITY_FAULT, CATCHING_UP, UNKNOWN, OFFLINE, DISCONNECTED, MARKET_CLOSED, LIVE, producer FIXTURE label, heartbeat age, time-basis and future-skew blockers, reconstructed history and counters. **Do not wire an MT5 live UI or start the exporter** during D00–D05; M09-B permissions/verification still gate it. Do not fake LIVE by showing demo fixture ticks. An integrity fault remains latched according to the adapter.

Each warning shows exact code, understandable explanation, data timestamp and a safe next step. "UNKNOWN" is not a defect to hide, and thresholds missing from config must say **NOT CONFIGURED**; Diagnostics may explain how to use existing CLI, not silently change policy.

### 16.7 Dialog and action matrix — every action is local only

| Action / context | Required input and preview | Confirm-time rule |
| --- | --- | --- |
| Record Entry / selected READY | Read-only full plan and source; actual fill price, positive quantity/lots, explicit UTC fill time; optional actual SL/TP, nonnegative fee or UNKNOWN, broker, note. Preview EntryPreview, actual vs E0/SL/TP and plan status. | Re-fetch same source/signal ID, current status, pre-roll, operator claim, quote/fidelity and broker-less policy; if blocked/expired/already claimed, **never silently ON_PLAN**. Reevaluate on authoritative state; if no longer eligible, stop and offer separate explicitly acknowledged OFF_PLAN, not automatic conversion. |
| Skip / selected unused READY | Signal ID, original expiry, optional reason; USER_SKIPPED distinct from engine expiry. | Revalidate current READY and unclaimed; PositionJournal.record_skip is authoritative transactional write. |
| Unlinked external fill / Positions or Journal | BUY/SELL, actual positive fill price and qty, UTC time; optional stop/target/fees/broker/note and **informational** historical signal ID. Prominent OFF_PLAN statement. | Use EntryRequest with plan=None; no READY/score mutation, and explicit extra acknowledgement that no recommendation/order was made. |
| Partial / selected open position | Actual exit-side fill price, positive qty < current remaining, UTC time, fees unknown/known, note; gross realized and remaining preview. | Reload position inside write transaction; reject closed, over-remaining, equal-to-all or exit before entry. |
| Close / selected open position | Actual exit-side fill, qty initially current remaining, UTC time, fee/note; show closure preview. | Qty **must equal current remaining** at commit and event time cannot precede entry. |
| Modify stop/target / open | New stop and/or target positive Decimal, UTC effective time, note; show before/after **current** risk and warning for moving stop farther away. Blank = unchanged, not delete. | At least one new level; reject closed and time before entry; preserve frozen initial risk/plan. |
| Reconcile confirmed open / unverified | Full position details, external broker verification checkbox/affirmation, UTC time/note and clear local-only promise. | Only RECONCILIATION_REQUIRED; transactional confirm_open; no automatic broker read. |
| Replay Play/Pause/Step/Pace/Refresh | No form. Toolbar and keyboard access. | Step only when PAUSED, exactly one normalized quote; pacing 50/500/FAST; refresh reads current snapshot only; never duplicate engine events. |
| Source change / app exit | Active source/path and unsubmitted-input warning; exit shows count of local positions needing external oversight. | Never silently discard dirty forms, assume broker position closure, reset state, migrate ephemeral /tmp data, or create a feed. |

**Input mechanics:** decimal fields accept an optional leading plus, plain decimal string and no binary float; reject NaN, Infinity, negative values and invalid quantities using the existing parse_amount. Currency/fees blank means **UNKNOWN**, entered zero is a deliberate known zero. Input display should not insert thousands separators while editing; use exact user-entered scale. UTC input uses the existing parse_utc_timestamp_ms and must not assume local timezone. No default synthetic broker tick precision on a real source. Actual fill time defaults to source virtual UTC when a replay exists, explicitly marked **editable suggested replay time**, not an actual broker confirmation. Future-of-known-clock entries trigger explicit warning, not invented failure where existing policy only warns. All save attempts show an accurate **SAVED LOCALLY** or **NOT SAVED** outcome; do not show success before commit.

**Modal anatomy:** identity / immutable plan or position / labeled form fields / computed preview and safety warnings / **Cancel** and **Confirm local record**. Cancel is initially focused and never saves; Enter in an input should not bypass the preview or an explicit confirmation; Esc cancels clean forms and requires a second Esc or explicit discard for edited forms. Disable duplicate submit while saving, retain the **same action_id** for retry after uncertain SQLite errors, and refresh the journal projection after transaction. Error messages include error code and next action; do not clear inputs on failed validation. Never permit shortcuts to fire through active fields/modal screens.

**Replay/modal consistency policy:** pause interactive REPLAY before opening a manual-edit dialog, preserve the exact replay cursor and show **Paused while recording**. Disable Step, Play and source switching while the form is open. Just before submit revalidate the latest engine snapshot plus journal overlay and compare source/identity; never rely on stale captured booleans. On close, playback **stays paused** until the operator deliberately resumes. Concurrent external writers are guarded by PositionJournal's own BEGIN IMMEDIATE checks and action-ID dedup. A real/reference feed cannot be paused; its later separate UI needs asynchronous revalidation and remains M09-B-gated.

### 16.8 Keyboard, focus and accessibility

Preserve R0 affordances with Qt-managed shortcuts **only outside text entry and modal focus**: 1–5 views, Space play/pause, period Step, +/- pace, e Record Entry, s Skip, p Partial, m Modify, x Close, n OFF_PLAN entry (only Journal/Positions), r Refresh, ? Help, q Quit. Tab/Shift+Tab traverse focusable controls; Up/Down navigate lists; Enter opens full detail or activates focused button. Esc closes detail or cancels a form safely; Ctrl+F focuses Journal filter only while Journal is visible (optional convenience). Replay keys are inactive in modal, disabled in non-REPLAY mode or on ENDED; when focus is in any editable control, typing **1-5 e s p m x n r q space +/-** must remain literal input, not a global action. If a shortcut cannot be made context safe in Qt, omit it in favor of a clearly labeled button until fixed.

Every interactive element has visible focus, keyboard-accessible name/tool tip, logical tab order, text-based status, and concise error description; do not steal focus or auto-scroll away from the selected record on quote refresh. Raw field/code disclosure via Details or Copy detail should preserve exact values and provenance; no broker credentials in clipboard exports. Add an in-app keyboard help overlay with all active bindings, source/fidelity caveat and **No broker orders**.

### 16.9 State, loading, safety and recovery presentation

| Condition | Primary presentation | Controls and recovery |
| --- | --- | --- |
| No state dir / imported source | **NO DATA LOADED — select/import an existing source**; never open fictitious prices | Startup source chooser and documented existing CLI import; no automatic network/import |
| Loading / causal pre-roll in worker | **Loading source / preparing confirmed history**, actual processed counts if known | Disable trading-record action until source + overlay ready; Cancel load if safe; no fake 0 values |
| Insufficient MTF/ATR history | **INSUFFICIENT HISTORY — cannot evaluate entry** | Allow all read-only screens/diagnostics and replay; never fabricate indicators |
| No FORMING / no READY | Explicit **No developing setups** / **NO TRADE** plus highest-priority evidence | View detail/diagnostics, no record-entry enabled |
| Source health UNKNOWN / stale / gap / closed | Visible reason/timestamp above opportunity lane; **reference quote not execution venue** | Fail closed for READY according to existing engine, no UI-made thresholds |
| READY → blocked / expired / invalidated while details active | Keep immutable issuance visible and show new current status | Stop on-plan action; OFF_PLAN is a separate explicit path |
| Operator position restored | **RECONCILIATION REQUIRED — verify externally** | Full verified-open workflow or record broker-reported changes |
| Source mismatch / replay before entry / REPLAY ENDED | **MARK UNAVAILABLE** or **REPLAY ENDED: historical mark** | No false live P&L or auto-closing |
| DB busy / permission / IO failure | **NOT SAVED** with unchanged record and retry/cancel | Keep action ID and fields; journal read-only fallback if safe; no silent empty overlay |
| Qt missing / incompatible display plugin | Clear missing-dependency or GNOME environment error, exit safely | No writes; existing TUI launch unaffected; do not patch system GNOME schemas |
| Reference not configured / integrity fault | **NOT CONFIGURED** / **INTEGRITY FAULT** read-only diagnostics | No synthetic replacement under live label; follow M09 separate permissions |
| Unexpected worker failure | Explicit last known frame time, STALE/UNAVAILABLE overlay, actionable buttons disabled | Safe restart/reload; do not continue processing from an unproved cursor |

### 16.10 Parity requirement and non-goals

Desktop must preserve all R0 Textual capabilities described in §§3–11 and their domain results, including off-plan manual recording, skip, reconciliation, partial/modify/close, selected full details, position touch observations, source/fidelity, pre-roll, pacing, journal history and diagnostics. The GUI must **not** rewrite trading math; introduce a risk score, confidence percentage, automatic fills, venue balance, charting suite, unapproved TP1 proximity alert or speculative cost threshold; import an MT5 module merely because Diagnostics displays its read-only status; or change journal schema for styling.

Operational access is **single local user**. There is no invented role-based permission system or broker authentication; permissions are limited to whether the local DB can be safely opened for the already-valid journal service commands. Lack of write access gives read-only mode and conspicuous warnings, never an override. Source identity and schema/config versions are displayed and validated, not silently migrated by the renderer.

**Pass/fail criterion:** An operator can complete all five pages and every available manual journal journey using only the desktop, with identical engine events and durable operator records as the existing R0 implementation and no loss of precision, fidelity or safety. See [08 §20](08-validation.md) for individually testable gates.

## 17. Daily one-click LIVE workflow — 2026-11-11

**Owner-approved product correction:** The daily application is an XAUUSD analyst, **not** an exporter diagnostics console. Keep the five existing desktop pages and Dark/Light/System + PKT/UTC presentation rules. The REPLAY controls and imported-source chooser belong to an explicit **Research / Replay** journey; they must not be the default experience after live onboarding. This section governs daily UX and defers domain calculations to 03–07, state ownership to 09 §14 and acceptance to 08 §22.

### 17.1 One-time setup (not an everyday task)

On first launch, show an integrated, short setup flow to discover the **existing** Ubuntu Wine binary/prefix, MT5 executable, demo-server connection and read-only exporter, and allow the operator to choose a dedicated Grog source and acknowledge that local MT5 may start. Show detected facts and an explicit permission control before modifying any MT5-owned files/profile. If MT5 login is missing, open it for user login and display a clear **one-time setup required** state; never request/store passwords in Grog. Do not run MetaEditor or attach scripts every day. A previously saved, verified setup bypasses onboarding on later launches. A first-run failure offers a single human-readable repair step, never a traceback or raw command as the primary screen. Advanced Diagnostics may expose paths, raw errors and a supported manual fallback.

### 17.2 Daily launch and mode

- Intended launch is a single desktop action/command, ultimately **gold** after an independent cutover sign-off. The current alias and replay launcher remain unchanged until all LW acceptance gates pass. Start/show the window promptly while background startup, catch-up and warm-up progress asynchronously. No invisible modal startup freeze.
- Default **LIVE (REFERENCE · INDICATIVE)** for an onboarded demo reference. Display real quote BID/ASK, timestamp/freshness, spread, H1/M15/M5 confirmed context and a single decision headline. **REPLAY (SIMULATED)** is an explicit secondary mode; never mix its cursor, virtual clock, journal marks or data provenance into LIVE.
- The supervisor may start MT5/Wine only when not already running under the specifically approved prefix. If the user already runs it, attach as a read-only observer and **do not** replace EAs, scripts or account settings. Closing Gold cannot kill another application's terminal or leave an unknown daemon behind. Terminal availability alone is not evidence of market-data freshness.
- Primary decision headlines: **CONNECTING**, **SETUP REQUIRED**, **CATCHING UP (NOT TRADABLE)**, **MARKET CLOSED**, **DATA STALE / OFFLINE**, **INTEGRITY FAULT — BLOCKED**, **NO TRADE (verified and evaluated)**, **DEVELOPING (NOT READY)**, **READY · REFERENCE INDICATIVE** and **POLICY UNVERIFIED — BLOCKED**. No false confident green LIVE state. Every non-ready status shows *why* and the next safe step; diagnostics only on demand. Distinguish no opportunity on a healthy feed from insufficient data or a failed feed.
- A READY proposal must originate from a **fresh, eligible post-trigger source quote** and the unchanged causal strategy/risk engine, with exact side-specific entry, entry band, stop, targets, expiry, original quote/received time, spread, units and explicit blocking codes. Multiple valid proposals are shown separately; no invented ranking, probability, "AI confidence", fees or fills. On a missing threshold, unknown market time basis, incomplete historical warm-up, gap, broker metadata or unvalidated risk gate: label research/developing information, **not actionable**.

### 17.3 Select a setup to WATCH (not enter a trade)

A separate button on an eligible proposal reads **Watch setup**. It does not call Record Entry, send a trade, assume a manual fill, or imply that the user is holding a position. In v1 allow **one watched proposal at a time** to keep state simple; replacement requires an explicit UI choice. The watch records the immutable proposal identity, source ID, strategy/version, frozen entry/SL/TP/expiry, creation/selection time, operator choice and current *observation* state; the plan never silently re-prices itself. Persist it as a watch preference/event separate from the manual PositionJournal.

Watch states use engine evidence and fresh reference ticks: **WATCHING / WAITING FOR ENTRY**, **PRICE NEAR ENTRY** (distance shown exactly; near-threshold policy must be explicitly defined before emitting the label), **ENTRY BAND TOUCHED (NOT FILLED)**, **PLAN INVALIDATED**, **PLAN EXPIRED**, **DATA UNAVAILABLE / STALE**, **WATCH ENDED**. Stop/target proximity may be shown **as observations only**, with the correct BID/ASK side and no claim that SL/TP executed. In-app attention messages are issued on **meaningful state changes**, deduplicated by watch ID + transition and never once per raw tick. Display source time and received time, plus reason. In a stale/offline/faulted feed the watch cannot reassure the user that an entry/stop is safe; keep the frozen plan visible but mark monitoring unavailable.

Explicit **Stop watching** is local, never a broker cancellation. If the app restarts, load the saved watch as **UNVERIFIED / RECONNECTING**, compare its source/version/expiry and restart/live status before resuming: never replay an old ENTRY BAND TOUCHED as a new alert. Auto-expire according to the original plan, not after an arbitrary UI timer. Operator-confirmed fills still require the existing manual journal entry action; that makes a **separate** position record and goes through existing save-time eligibility/RECONCILIATION logic. A watch can remain viewable as historical context without masquerading as a held trade.

### 17.4 Simplification and visibility

Overview shows Decision → Quote/health → H1/M15/M5 rationale → relevant proposals → Selected watch. Signals lists Developing / READY (or blocked) / History. Positions and Journal are secondary, for genuinely reported manual fills. Diagnostics shows MT5 health, source path, heartbeat/quote ages, offsets, gap/fault records, config and safe next action. UI must never ask the operator to manually inspect .grogref files, run MQL scripts or repeatedly open MT5 for ordinary operation. Preserve advanced audit evidence for developers and reproduce all previous GUI parity/formatting/accessibility requirements.

First-run account authentication, absent Wine/MT5 and permissions may require user interaction. **One-click** means repeatable day-to-day use after successful onboarding—not a promise to bypass external platform login or to operate while the laptop/app is off.

## 18. New primary Trade Finder UX — supersedes watch and journal-first navigation (2026-11-11)

**Owner scope change:** The daily product is now one compact native Qt **Trade Finder**, with only Trade Finder (default), Research (secondary), Settings and advanced Diagnostics. **No Watch setup action, selected setup monitor, active position screen, journal shortcut, manual entry modal or price-touch alert in the primary LIVE interface.** Preserve already implemented R0 replay/manual journal code and its tests in a separate legacy/research mode rather than removing them. Sections 1–17 document earlier R0, desktop/V2 and the previously approved watch-first design; §17's Watch setup requirements are **withdrawn** for the new product. See [11 §19](11-decisions.md#19-trade-first-scope-correction--owner-approved-2026-11-11).

Single source of detailed layout and daily journey: [Trade-First Redesign](trade-first-redesign.md#3-screen-design--premium-compact-decision-first). The functional state remains **NO TRADE / FORMING NOT READY / INDICATIVE READY BUY or SELL / DATA UNAVAILABLE or BLOCKED** and always shows truthful reason, source BID/ASK and clock. In LIVE, the view must **never present an actionable entry** when source quality, quote age, warm-up, source time basis, costs or strategy gate is missing; keep historical levels as explicitly STALE. No invented confidence or forced trade count.

**UX acceptance:** App opens directly to a compact decision surface; no daily MT5/MetaEditor/user-script interaction once onboarded. H1/M15/M5 confirmed evidence, exact entry/stop/targets/expiry and source/receive time remain accessible. Research performance evidence is a secondary screen. The new UI does not create PositionJournal events. UI choices never change actual strategy math; old REPLAY parity remains independently tested. The active implementation plan is [10 §15](10-roadmap.md#15-tf-trade-finder-only-implementation--supersedes-watch-workflow).
