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

**Status:** Direction approved; new GUI not implemented beyond D00 foundation. The terminal app remains fully supported. [Decisions](11-decisions.md), [Architecture §12](09-architecture.md), [Roadmap §11](10-roadmap.md).

- **Form factor:** local Qt Widgets application, not web. Left navigation for Overview, Signals, Positions, Journal and Diagnostics. Clean dark surfaces, restrained gold accent, accessible typography, whitespace and mouse/keyboard controls. No charting sprawl, SaaS, wallet, broker orders or new trading features.
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
