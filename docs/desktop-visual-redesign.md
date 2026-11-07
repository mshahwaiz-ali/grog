# GROG — Desktop Visual & Interaction Redesign V2
**Status:** OWNER-APPROVED 2026-11-07 — charcoal Dark, warm-white Light and System appearance; ready for Grok's U0–U5 handoff (documentation only in this commit)  
**Scope:** Native PySide6 / Qt Widgets presentation, navigation, settings, information architecture, dialogs, source chooser, keyboard help, fault UX and readability.  
**Repository:** mshahwaiz-ali/grog, branch main  
**Remote baseline inspected:** c0ef834a58399fa112419142009d8253e7e0b491 (2026-11-07)  
**Document role:** One implementation-facing **visual and presentation companion** to the canonical desktop contracts. This is not a strategy specification, permission to trade, or evidence that a Qt release has been accepted.

> **Purpose:** Make every GROG desktop journey feel like one coherent, premium, human-readable trading *decision* workstation. This is a complete user-experience redesign, not a new dark stylesheet, not a web rewrite, and not a new trading engine. Dark and Light must both be first-class, user-selectable themes, with a System option. Default to a neutral charcoal/graphite dark aesthetic, **not blue/navy**, with a restrained neutral identity treatment.

## 0. Authority, approval and safety boundary

This document owns the **new visual system, human-readable presentation patterns and visual acceptance checklist only**. It deliberately does not supersede:
- **AGENTS.md** and **docs/00-index.md** for external assistant workflow and documentation precedence.
- **docs/11-decisions.md §16** for approved scope, permission boundaries and open decisions.
- **docs/02-workflows-and-ux.md §16** for what each page/action means, complete workflow behavior and keyboard rules.
- **docs/09-architecture.md §13** for the real, already implemented replay/journal ownership model, detached frames and concurrency.
- **docs/08-validation.md §20** for GUI-11..62, the existing GUI-01..10 and R0 parity.
- **docs/10-roadmap.md §12** for existing D00–D05 verification obligations.
- **docs/03–07** for all market timing, S1 strategy, eligibility, signal lifecycle, price-side/risk math and manual-record semantics.

If presentation guidance appears to conflict with an approved functional contract, **preserve the canonical behavior**, document the discrepancy and escalate. Never silently reinterpret domain data to fit a visual reference.

The two Overview visual concepts shared with the owner in the accompanying ChatGPT conversation are **illustrative mockups, not actual Qt screenshots or actual feed data**. They establish layout, density and color direction, NOT an invented BUY signal, filled position, broker quote, confirmation checklist or hardcoded market status. Bind every real UI state to existing source facts.

**Owner approval received 2026-11-07:** both Overview visual directions are accepted, and the owner directed this documentation to be finalized for **Grok** to implement the complete desktop redesign. This document update itself performs no runtime or UI code changes. Grok's work begins from the implementation handoff prompt in §13, starting at U0 and preserving every existing safety gate. Error reports the owner supplies later are a separate evidence-driven bug backlog, not permission for speculative changes.

Absolutely out of scope: strategy/threshold/eligibility changes; market-event ordering; SL/TP or position math; loss of exact Decimal/source timestamps; schema/transaction/idempotency changes for styling; live MT5, Wine or broker connection; auto trading; new markets, generic charting, dashboards, notification feeds, data imports, source synthesis, new journal correction/delete features; changes to the existing gold alias; production and unrelated repos.

## 1. U0 — As-built map and bounded change plan

**GitHub remote main, inspected at the baseline above:** the native desktop already has all five pages, dialogs, playback controls, source chooser and R0 parity tests. There is no justification to replace the replay engine, journal service or Qt architecture. The local Ubuntu working tree at ~/data_drive/grog was **not accessible to this documentation audit**; Grok must inspect local branch, HEAD, uncommitted files and runtime tests before editing.

| Existing file or group | Observed role | Proposed visual-only change | High-risk boundary |
| --- | --- | --- | --- |
| src/grog/desktop/theme.py | Static navy QSS, palette, labels, pills, Card and Metric | Tokenized Dark/Light/System palettes, typography, focus, surfaces and reusable primitives | Avoid per-widget style overrides that prevent runtime theme updates |
| src/grog/desktop/presentation.py | Lossless price_text, full UTC, forming-trigger sentence | Add **opt-in UI-only** human time, timestamp-role, secondary metric and reason-label adapters | Existing exact Decimal/UTC callers and tests must stay valid |
| src/grog/desktop/window.py | Shell, sidebar, status, Overview, replay toolbar, responsive layout and page routing | Recompose shell and Overview; add unnumbered Settings access, theme/time selection and contextual status | Keep pause ack, frame tags, all playback actions and keys 1–5 intact |
| src/grog/desktop/frames.py and overview_model.py | Detached typed frames and Qt-neutral Overview read-model | Preserve source/domain facts; adapt *display-only* labels at view boundary where feasible | Never modify causal snapshot computation, source identity or events to beautify text |
| src/grog/desktop/signals_model.py and signals_page.py | Keyed Developing/READY/History rows, search filters, stable selection and detailed signals | Clearer columns, state hierarchy, summary-first detail and progressive disclosure | Full IDs, frozen plan and READY/blocked/expiry rules unchanged |
| src/grog/desktop/records_model.py and records_pages.py | Positions/Journal rows, provenance, selection, reconciliation and actions | Human chronology, compact rows, persistent detail, provenance separation | Journal must remain append-only through existing PositionJournal service |
| src/grog/desktop/manual_forms.py and form_dialog.py | Spec/validation/preview and modal Save/Cancel/retry | Field grouping, labels, scroll, validation placement, exact-value preview and confirmation | No change to validation, immutable PlanRef, action IDs or save-time recheck |
| src/grog/desktop/diagnostics_model.py and diagnostics_page.py | Owner-sourced feed/integrity/reference/journal facts | Actionable health summary first, advanced evidence below | Do not hide source mismatch, stale frames or safety warnings |
| src/grog/desktop/chooser.py and help_dialog.py | Source chooser and keyboard guide | Premium responsive dialogs with readable grouped content and focused actions | Open/Remember remains read-only inspect until operator action |
| src/grog/desktop/source_select.py, launcher.py, replay_worker.py, journal_worker.py and manual_controller.py | Source selection, launch, thread ownership, journal commands | Prefer **no edits**; only a proven UI boundary change with tests | Do not alter data protection, alias, import/launch semantics or transaction model |

**Baseline verification to run on the real Ubuntu checkout before U1:** confirm actual main HEAD and local changes; capture all five page states, each modal, source chooser and help on the current build; run existing desktop presentation, Overview, Signals, D03/D04/D05 UI and relevant unit tests plus Ruff; record failing/skipped tests, display plugin, PySide6 version, exact commands and screenshots. Never claim the test counts in a commit message as newly run without running them.

## 2. Product-quality criteria and information hierarchy

The UI is successful only when a user can identify, without deciphering a log:

1. **Is there an actionable research proposal right now?** Distinguish NO TRADE, DEVELOPING (NOT TRADABLE), READY (SIMULATED/INDICATIVE), EXECUTION BLOCKED, INSUFFICIENT HISTORY, REPLAY ENDED, DATA UNAVAILABLE and SOURCE FAULT.
2. **Why this state, and what exact confirmation is still required?** Explain from engine facts, not invented checklist success.
3. **Which sourced BID/ASK and source mode are displayed?** Quotes and execution fidelity must remain visible and honest.
4. **What is the confirmed H1 / M15 / M5 context?** Provisional bars are explicitly marked and cannot masquerade as confirmed.
5. **What needs operator attention?** Local manual records, reconciliation, feed faults and unsaved actions outrank decorative market observations.
6. **Where is the complete audit evidence?** Full IDs, exact time, exact prices, hashes and raw codes must be accessible and copyable, but not dumped in ordinary page summaries.

Prefer a calm, information-dense productivity interface over both a terminal and a card-heavy analytics dashboard. One clear primary region per page; restrained panels only to group meaningfully different tasks. No fake candles/charts, glows, gradients, promotional illustrations, giant saturated buttons, noisy micro-badges, percentage confidence, win probability or fake account P&L.

## 3. Design system — stable visual tokens

### 3.1 Colors

Both themes use a **neutral** surface system. No dark-blue backgrounds, blue-gray panels or gold-tinted application chrome.

| Semantic token | Dark — default | Light |
| --- | --- | --- |
| App background | #111111 | #FAFAF9 |
| Sidebar / toolbar | #151515 | #F5F5F3 |
| Primary surface | #1B1B1B | #FFFFFF |
| Raised / hover surface | #242424 | #F5F5F3 |
| Active navigation | #2A2A29 | #EAEAE6 |
| Hairline divider | #323232 | #E6E6E3 |
| Primary text | #F4F4F1 | #232320 |
| Secondary text | #A7A7A3 | #64645E |
| Tertiary text (avoid for required facts) | #92928E | #77776F |
| Neutral focus / identity accent | #D5C3A4 | #71624C |
| Positive / BUY | #40B99A | #177D63 |
| Positive tint | #153229 | #E2F5EC |
| SELL / adverse movement | #E98C80 | #B64E47 |
| Warning / pending | #ECC37E | #8D5F21 |
| Warning tint | #392D1B | #FBF1E1 |
| Error / fault | #F08E83 | #B84541 |

BUY/SELL colors indicate **side**; warning/error color indicates **severity**. A READY proposal is NOT automatically green or recommended. A SELL proposal is not an error. A green source-health indicator must never imply a LIVE feed or safe broker fill.

Do not approximate theme colors by dynamic inversion; define semantic color roles in one palette object and use the same roles across QSS and any custom-painted delegates. Hover, selected, disabled, borders, scrollbars, combobox popups, tooltips and focus state must all have Dark/Light variants. All user-visible statuses need words or icons **in addition to** color.

### 3.2 Typography

- Use installed **Inter** when available; fallback to **Noto Sans**, then native Qt/system sans-serif. No bundled commercial fonts and no font installation.
- Regular body **15–16 logical px**, tabular rows **14–15**, control labels **14–15**, section headings **17–19**, page heading **28–30**, decision headline **27–30**, prominent sourced quotes **26–30**.
- Supporting copy **13–14**; avoid tiny 10–11px metadata. A 12px minimum is reserved for low-priority timestamps/eyebrows, **never for a required price, reason, warning or form instruction**.
- Use medium/semibold instead of frequent all-caps. Keep line length near 45–75 characters for explanatory text; wrap in meaningful sentences. Preserve usable line height around 1.35–1.55.
- Use tabular numerals where Qt/font supports them; otherwise align price/quantity columns right without changing the stored digits.
- Do not change global engine/CLI/TUI fonts, terminal output or existing public formatting utilities in place without auditing consumers.

### 3.3 Geometry and component behavior

Use spacing tokens **4 / 8 / 12 / 16 / 24 / 32** logical pixels; most panels have 10–12px corner radius and subtle 1px borders. Sidebar approximately 210–224px on wide screens; a **65–72px** slim top strip; fixed but **wrappable** replay controls at bottom only in REPLAY mode. Inputs and buttons typically at least **36–40px** high; clear hover/focus/disabled states.

Core reusable UI components (names conceptual, not mandatory new classes): PageHeading, DecisionSummary, StatusLabel, ReasonSummary, QuoteMetric, MarketContextRow, CompactTable, DetailPanel, KeyValueList, ProvenanceLine, AlertBanner, EmptyState, Timeline, FilterBar, DialogSection, ExactValueRow and ConfirmationFooter.

Create a component only when actually shared; do not invent a framework, QML migration, web frontend or a large widget inheritance system. Minimize ad-hoc setStyleSheet calls scattered across pages. A runtime theme change must repaint **all** existing widgets and future dialogs.

## 4. Settings — an additional utility view, NOT a sixth trading screen

Provide **Settings** via an unnumbered bottom-sidebar item (or accessible overflow menu in compact mode). Preserve **1–5** mappings for Overview, Signals, Positions, Journal and Diagnostics, including their existing focus and selection behavior.

**Appearance (approved and mandatory):** segmented/radio selector with exactly **Dark / Light / System**; default **Dark** on fresh installations, respecting an existing explicit preference. **Dark** and **Light** are persistent *manual overrides* unaffected by OS changes. **System** reads the current Ubuntu/Qt appearance at launch, reacts to OS appearance changes without restarting when the platform exposes them, and returns to automatic following when the user switches back from a manual override. Use Qt 6's `QGuiApplication.styleHints()` / `QStyleHints.colorScheme` / `colorSchemeChanged` or the verified equivalent for the pinned PySide6 runtime; account for palette-change ordering and ensure custom QSS is fully reapplied. See [Qt QStyleHints](https://doc.qt.io/qt-6/qstylehints.html). A platform may report `Unknown` or fail to deliver a change signal: **fail visibly to effective Dark**, still show the saved preference as **System** with a small explanatory “System appearance unavailable — using Dark” note, and re-detect at next launch. Never guess Light based on arbitrary gray pixels. A theme switch must repaint the **entire** existing UI (nav, tables, drawers, context menu, tooltips, dialogs including already-open dialogs, chooser, banners, scrollbars, popups, empty states and focus rings). **Theme preference is only a presentation setting**; it cannot change replay, source, trade state, journal or execution permissions.

**Time display:** **PKT (Asia/Karachi) / UTC**, default PKT for a fresh preference while retaining current exact UTC audit/detail exports. Every date/time in human-facing summaries has an explicit timezone indicator. Even if the UI is showing PKT, full exact source, provider, received, available-at, event and recorded UTC remain accessible.

**Transparency / safety:** a small read-only section may explain active mode, source fidelity and that manual records are **not broker-synced**. The screen must not offer a trading mode switch, risk-policy override, fake LIVE toggle, MT5 connection action, DB repair action or new import service. If source selection can be reached from Settings, it must invoke the **existing, safety-gated chooser** and preserve its source-switch and modal rules; otherwise keep source controls where they currently work.

Persist only UI preferences via a clearly scoped local Qt/QSettings or existing appropriate XDG application settings mechanism. Keep preference storage **separate** from the D05 saved source-selection TOML and from the journal/research SQLite databases. Test fresh, malformed, read-only and restart settings; a failed preference save must never alter the source selection or journal. No new global shell environment or alias changes.

## 5. Shared human-readable presentation layer (U1 priority)

A **pure Python, Qt-neutral adapter** should support the view layer. Start by extending src/grog/desktop/presentation.py in a backward-compatible manner; factor another small presentation module only when needed. Do not import PySide6 into the engine.

### 5.1 Time and chronology

- Storage and audit remain **integer epoch milliseconds / UTC**. Never rewrite them on a timezone preference change.
- Distinguish **provider/source event time**, **received time**, **bar available time**, **replay virtual time**, **operator fill/event time**, and **local recorded time**. Do not collapse multiple clocks into one misleading “Time”.
- Overview/table compact examples: **10:24 PM PKT**, **15 Jan · 10:24 PM PKT** and **Today · 10:24 PM PKT** only when the selected virtual/wall clock basis makes “Today” unambiguous. Prefer an absolute date in replay history and mixed-date lists.
- Complete detail/audit examples: **2026-01-15 17:24:05.123 UTC**, clearly labeled **Event UTC** or **Recorded UTC**, plus source ID. Do not hide the year, milliseconds or offset in exports.
- Use an explicit **zoneinfo** conversion from UTC for PKT; avoid mixing the machine’s unspecified local timezone or a wall clock with the virtual replay clock. Avoid float conversion through timestamp_ms / 1000 when a divmod-based integer path preserves exact millisecond intent.
- Replay TTL and “ago” labels must use the **replay virtual clock**, not wall time; frozen REPLAY ENDED values must state they are historical.
- Preserve stable ordering and identity for equal-provider-millisecond ticks; never sort, deduplicate or renumber underlying events in a formatter.

### 5.2 Decimal and units

- **Exact, unrounded** finite Decimal representation for BID, ASK, entry, E0, SL0, current SL, TP1, TP2, entry bands, actual fills, fee input, quantity, risk values in actionable previews and all audit/copy details. Preserve significant trailing source digits where the existing contract requires them.
- **Secondary, non-actionable** metrics (such as context overview ATR, quote-age duration or an ancillary distance) may have a *separate, clearly named view-only abbreviated display* where explicitly safe. Keep a full-precision detail/tooltip; never replace domain Decimal or use binary floats.
- Do not invent universal XAUUSD digits, contract size, lot conversion, USD profit, net R or account balance. UNKNOWN fees are not zero; missing values are not zero.
- Manual input must retain the exact typed decimal string until parsed by existing validators; formatting cannot silently insert commas, round or convert NaN/Infinity into a number.
- Provide explicit units and side: **ASK for BUY entry**, **BID for SELL entry**, existing closeable side for positions. Keep any source-specific unit metadata from the engine.

### 5.3 Missing/unknown and severity taxonomy

| Raw distinction | Human-facing representation | Non-negotiable behavior |
| --- | --- | --- |
| No value supplied | — / Not available | Never display zero |
| Unknown/unverified economic value | UNKNOWN | Never imply known zero |
| Feature or reference producer not configured | NOT CONFIGURED | Not equivalent to an error-free live feed |
| Source or local record not verified | UNVERIFIED | Never claim “Open at broker” |
| FORMING | Developing · **NOT TRADABLE** | No entry action |
| READY, eligible and unclaimed | READY · SIMULATED or INDICATIVE as sourced | No automatic ranking or fill |
| READY but failed current execution checks | EXECUTION BLOCKED | Explain source reason, disable on-plan action |
| Replay exhausted | REPLAY ENDED · historical | Do not show a fresh LIVE price |
| Adapter integrity fault / journal write failure | ERROR / NOT SAVED with code | Prominent, persistent and not downgraded |
| Local manual record | RECORDED LOCALLY · NOT BROKER-SYNCED | Saved only after actual journal commit |

Map **known technical reason codes** to concise human explanations at the view boundary. Preserve every raw code in a disclosure/Details panel and accessible Copy details; unknown codes display intact with a neutral “Technical reason” fallback. Do not infer health, eligibility, source origin or severity from text string heuristics when typed facts exist.

## 6. Global shell — interaction and visual anatomy

### 6.0 Owner-approved Overview composition reference

The **approved paired dark/light visual concepts** from the owner review define the *visual target*. They are design illustrations, not proof of a BUY/SELL signal or of a live data connection. Grok must reproduce their calm density, comfortable typography, aligned hierarchy and neutral palette, while correcting any illustrative words/values to match the real engine's states. The following schematic is the implementation-neutral composition and is usable even when separate image attachments are unavailable to Grok:

```text
┌───────────────┬──────────────────────────────────────────────────────────────────┐
│ GROG          │ XAUUSD · REPLAY / SIMULATED · SOURCE · HEALTH · TIME (PKT/UTC) │
│               ├──────────────────────────────────────────────────────────────────┤
│ Overview      │ [MATERIAL SAFETY WARNING / RECONCILIATION, only when true]      │
│ Signals       │                                                                  │
│ Positions     │ CURRENT DECISION              NEXT ENGINE-VERIFIED CONDITION     │
│ Journal       │ NO TRADE / DEVELOPING / READY / EXECUTION BLOCKED / UNKNOWN      │
│ Diagnostics   │ Human explanation; full reason evidence in Details              │
│               ├────────────────────┬────────────────────┬────────────────────────┤
│               │ BID (exact)        │ ASK (exact)        │ SPREAD (exact)         │
│               ├────────────────────┴────────────────────┴────────────────────────┤
│               │ H1 confirmed       M15 confirmed          M5 confirmed / pending│
│               ├──────────────────────────────────────────────────────────────────┤
│               │ DEVELOPING / READY (never automatically ranked)                 │
│               │ Short meaningful rows; stable selection; open exact details      │
│               ├──────────────────────────────────────────────────────────────────┤
│               │ LOCAL POSITIONS / RECONCILIATION  │ RECENT MEANINGFUL CHANGES   │
│               │ (NOT BROKER-SYNCED)               │ (never every tick)         │
│ Settings      ├──────────────────────────────────────────────────────────────────┤
│               │ REPLAY ONLY: Play/Pause · Step · Pace · Progress · Safety         │
└───────────────┴──────────────────────────────────────────────────────────────────┘
```

Dark and Light share **identical geometry, labels, information priority and interactions**; only semantic colors/shadows/borders adapt. Do not reproduce invented data, fake checkmarks, fake open positions, or a tradable BUY from an illustrative mockup. At 820×620, collapse sidebar and stack content while keeping safety, mode/fidelity, decision, details and replay controls accessible. At large sizes keep line lengths moderate, not stretched across the entire window.

### Sidebar

### Sidebar
- Brand: GROG / Gold, one subdued mark, five known views with readable active selection and small **meaningful** counts only.
- Settings at bottom, separate from numbered workspaces; readable collapsed state at 820px.
- No duplicate sentence about “manual only” on every panel. Keep one visible, reliable **No broker orders** caveat in the app shell and critical local-record areas.

### Header/status
- Always expose **XAUUSD**, **REPLAY/SYNTHETIC versus authorized REFERENCE/INDICATIVE**, actual source state and health, with typed labels.
- Show compact source label, selected PKT/UTC time and critical recovery state; full source ID, file hashes and all exact clocks live in disclosure/Diagnostics.
- Do not allow mode badges to conceal source faults. If a risk-integrity state demands action, a contextual alert must appear **above** the opportunity area.

### Content
- One readable title and one short purpose sentence per view. No giant empty title blocks or unnecessary duplicate overview cards.
- Dense information lives in **progressively disclosed details**, never permanently in the Overview hero.
- Use native scroll areas, not fixed-height text blocks that truncate on smaller windows. Table columns have measured minimums, good labels, right-aligned numerics and an explicit “more columns in details” affordance.

### Replay footer
- Play/Pause, Step one quote, Slower/Faster, truthful pace, processed/total and pre-roll; proper disabled states and reason at REPLAY ENDED.
- Keep the same event pacing and one-Step-one-quote semantics. No Step/Play/source switch while manual save/modal gate is active.
- At narrow widths split into two deliberate rows before truncation, or move lower-priority progress into an accessible secondary line. Keep Cancel/Confirm dialogs independent of footer shortcuts.

## 7. Screen redesign — required behavior and layout

### 7.1 Overview — decisive, not diagnostic

**Priority order:** (1) high-priority safety or reconciliation alert, (2) current decision and next *engine-grounded* confirmation, (3) BID/ASK/spread with mode/fidelity, (4) H1/M15/M5 context and confirmed/provisional distinction, (5) Developing/READY counts and opportunities, (6) local-position and reconciliation summary, (7) recent meaningful changes. Exact hashes, engine counters, ATR debug, schema versions and raw reason strings belong in Diagnostics/Details.

**At wide widths:** decision region near full width; contextual “next condition” may occupy an adjacent column **only if derived from actual facts**. Three quiet quotes below. Market structure and manual-position summary side by side. Bounded opportunity and recent-change lists below.

**State variations must be designed, not hacked:** NO TRADE; one/multiple READY; Developing (NOT TRADABLE); blocked READY; insufficient warm-up; loading/pre-roll; source fault; REPLAY ENDED; unverified journal; safe unknown price. For multiple READY, state the count and route to Signals; never silently select a winner. During faults, do not paint a stale last quote as fresh.

**A confirmed state is not implied by a pretty check icon.** If checklist evidence is unavailable, use facts such as “H1: Unknown”, “M15: Unavailable”, “M5: Awaiting confirmed close” rather than speculative tick marks.

### 7.2 Signals — browse, compare, understand, then act locally

- Clearly separate **Developing**, **READY & Execution Blocked**, **History** with accurate counts. Preserve all existing status transitions, keyed selections and current search/filter semantics.
- A compact top FilterBar: full-ID/price/reason search, BUY/SELL, state; filters may narrow the view but do not change the engine or the selected plan.
- At a glance show side, lifecycle, strategy, issued/event time in chosen zone, source mode, actionable/not actionable and essential exact plan levels. No unreadable wall of code strings as primary columns.
- Selected detail: short human explanation first; then **Current status and blocking reasons**; exact immutable plan and price-side details; H1/M15/M5 evidence; timeline; original source, strategy/config, full signal/candidate IDs, timestamps, raw reason codes and copyable audit section.
- **No rank** among multiple READY proposals. Current source-eligibility checks, expiry and first-operator-claim must still disable on-plan actions. An OFF_PLAN record is explicit and separate.
- Wide screen: table left, resizable/reasonable detail right. Medium/narrow: detail below table or deliberate detail overlay, preserving full ID access, horizontal scroll and selected row.
- When a selected row is promoted/moved/vanishes as replay advances, preserve the stable identity and show a plain-language moved/unavailable notice rather than silently selecting a different trade.

### 7.3 Positions — real manual record state, no pretend broker sync

- Summary first: **Open local records**, **Need reconciliation**, **Closed**, and “Not broker-synced”.
- Filter by Open/Needs reconciliation/Closed; show real position ID, linked signal versus OFF_PLAN, side, remaining and original quantity, actual entry, closeable mark with freshness, SL/TP, gross-R fields only when meaningful.
- Reconciliation-required records receive a prominent worklist and **Confirm still open** local flow only after user checked externally. Do not imply an open broker position based on SQLite.
- Selected position has a calm, structured details panel: current and initial levels, immutable original PlanRef where applicable, actual vs planned risk, observations versus fills, source mismatch and freshness, append-only event chronology with **Event** versus **Recorded** times.
- Partial / Close / Modify actions are contextual and safety-gated. Show what will be locally recorded; never show fake brokerage buttons or editable closed history. UNKNOWN net P&L stays UNKNOWN.

### 7.4 Journal — chronologically readable provenance

- Strong, persistent provenance distinction: **Operator records (saved locally)** versus **Replay/engine events (reconstructed)**; combined chronology is allowed with explicit source labels.
- Filter by producer, event type/state, side, source, full ID and time range; search must remain complete even when rendering a manageable visible subset.
- Default newest first with stable tie order. Ordinary row: readable event date/time + zone, event name, short explanation, side, producer and record/reference. Details reveal exact event/recorded UTC milliseconds, full IDs, full original payload and codes.
- Use timeline/grouped-day styling where it improves reading but preserve deterministic ordering and every event. Do not invent fill status, persist ephemeral engine events into the operator journal, or add correction/delete UI.

### 7.5 Diagnostics — prioritize operational health, retain the evidence

- Summary header: actual source/feed verdict, replay state, data completeness, local-journal status and most urgent safety issue **derived from DiagnosticsFacts**. A clear “All checks passed” must never appear if the journal is unreadable, a source mismatch exists, or the feed/integrity is degraded.
- Sections: Source & provenance; Feed health; Confirmed bars & warm-up; Replay integrity; Engine eligibility; Reference adapter (read-only); Local journal & errors.
- Put simple operator implications first (“Replay source integrity verified”, “No source connected”, “Journal read-only — records cannot be saved”), followed by date and optional safe next step.
- Complete raw hashes, paths as safely exposed, config values, 64-hex evidence, codes, versions and counters remain available in **Advanced details**. Never remove/lower severity of a material warning to make the page cleaner.
- M09-A/H reference status stays read-only and truthful. **NOT CONFIGURED** is not LIVE, and a fixture can never appear as broker connected.

### 7.6 Settings — see §4

### 7.7 Manual action dialogs — ALL journeys, one common anatomy

Cover selected READY Entry; Skip; standalone OFF_PLAN fill; Partial Close; Full Close; Modify stop/target; Confirm still open/reconciliation. Also review dirty-form discard, save-in-progress, uncertain outcome, stale signal, source mismatch, blocked eligibility, read-only DB, permission fault and successful commit states.

**Dialog visual order:**
1. Title + unmistakable local-only provenance + source/position/signal identity.
2. Immutable plan/position summary (no editable copied plan).
3. **Required fields first**, with clear side/units and exact input; advanced optional fields (fees, broker label, notes, contextual times) in a disclosed secondary group.
4. Inline validation immediately next to the relevant field (not only a bottom error wall).
5. Live, bounded and scrollable **Before you save** preview with exact price/qty/SL/TP/fees and warnings, sourced from existing service preview/validators.
6. Visible, consistently placed **Cancel** (default focus) and **Confirm local record** buttons, plus real Saving / SAVED LOCALLY / NOT SAVED outcome.

Preserve existing parse_amount, UTC parse, exact field semantics, plan immutability, action_id, idempotent retry, first-operator claim, journal write owner, replay pause/ack and save-time checks. Do not let Enter in a text field submit unexpectedly; Esc on dirty forms needs explicit discard; keep the footer reachable at 820×620 and 200% scaling. A screenshot that fits only after hiding errors is a failure.

### 7.8 Source chooser — safe launch, understandable inspection

Replace dense raw path/status presentation with a clear **Choose an existing local source** flow: state directory, read-only inspection result, available sources, SOURCE ORIGIN/FIDELITY, caution panel, Open, Remember, Cancel and existing import guidance. Explain “NO DATA LOADED” and invalid/missing state in ordinary language. Preserve real source paths/IDs accessible in details, their checks, Remember persistence and explicit Open semantics. Never auto-import, auto-create a data source or use a temporary UAT source as a durable default.

### 7.9 Keyboard help / recovery sheets

Group navigation, replay, selection, manual records and safe exit shortcuts in a readable searchable-or-scrollable reference as needed. Show keys with compact keycaps and descriptions, not a raw transcript. Reflect actual bound shortcuts and their availability. Existing **1–5 / Space / . / +/- / e / s / p / m / x / n / r / ? / q** behavior remains context-safe; typing in filters/forms must never trigger global shortcuts. Help and error dialogs respect selected theme.

## 8. Responsive and accessibility specification

**Target logical viewport matrix:** 820×620 (minimum), 1366×768, 1920×1080; 100% / 125% / 150% / 200% scale; both themes. The owner’s real Ubuntu GNOME launch must be visually inspected, not only offscreen Qt geometry asserted.

- **>=1440 wide:** stable sidebar, decision priority, two-column secondary content, Signals/Positions table plus full detail.
- **1100–1439 medium:** decision full width, context/lists split only when legible, shorter visible columns but all details accessible.
- **820–1099 compact:** an icon-rail or accessible compact navigation; one-column Overview; responsive filters; tables with either horizontal scroll + disclosure or list/detail composition; no clipped safety text; source and fidelity always discoverable.
- **Height <=768 / scaling >=150%:** content scrolls, safety and modal actions remain visible; footer wraps or reduces non-critical chrome; dialogs scroll inside, with fixed confirmation row where practicable.
- Test long translated-style strings (even if the app is English-only), long raw IDs, extremely long Decimal values, full hashes, empty views, 100+ journal entries, warnings and real Qt focus traversal. Tables may ellipsize *visually* but full values must always be available via details/copy.
- Target text contrast >=4.5:1 and non-text UI contrast >=3:1 where practical, visible keyboard focus, accessible labels/tooltips, semantic statuses independent of color and a logical Tab/Shift+Tab order. Audit both themes instead of assuming contrast from the palette.
- Settings must be reachable at the minimum window size without reassigning shortcut 5 from Diagnostics.

## 9. State-specific copy examples (illustrative only)

| State | Recommended human summary | Raw evidence |
| --- | --- | --- |
| No eligible setup | **No trade signal** · Conditions are not confirmed | Exact engine reasons under Details |
| FORMING candidate | **Developing BUY · Not tradable** · Wait for a completed M5 BID close above the actual sourced threshold | Full candidate ID, source, evidence, code |
| Blocked READY | **Execution blocked** · The proposal exists, but current execution checks failed | Immutable plan + current blocking codes |
| Reconciliation | **Verify 2 local positions** · Check the actual broker before confirming them open | Position IDs and recorded event times |
| Journal unavailable | **Local records unavailable** · Existing records cannot be verified or saved | Full error code and safe next action |
| No reference adapter | **Reference feed not configured** · Offline replay still available | Existing read-only adapter status |
| Replay end | **Replay ended** · Last quote is historical, not live | Exact final virtual UTC and source |

Only display counts, sides, levels and checkmarks if they come from the current validated model. The illustrative numbers/images are not a spec for fixed values.

## 10. Execution plan — small independently verified phases

**U0 — baseline / map / before evidence.** Check main and local git status; inspect exact code/consumer contracts and active docs. Capture all current screens, dialogs and launcher states in both normal and fault fixtures. Run targeted baseline tests and label skips/failures. Prepare a brief file/function change matrix and exact acceptance criteria **before writing code**.

**U1 — foundation first.** Add palette tokens and runtime theme application, UI-only appearance preferences, Qt-neutral time/number/status presentation adapters and pure tests. Verify old price_text/utc_ms_text/trigger tests unchanged, no engine/CLI/TUI import regression, no Decimal/UTC loss and persistence isolation. Do not redesign individual page layouts before this contract is stable. Commit tested U1 only.

**U2 — shell, Settings, Overview and Signals.** Apply the approved visual design, correct responsive layout and source/fidelity visibility. Implement progressive details and filters preserving every selection/action. Validate the complete U2 states and existing GUI-01..29 / R0 parity for affected paths. Save visible screenshots for Dark/Light at all three widths. Commit only after acceptance.

**U3 — Positions, Journal and manual forms.** Rework structure and human chronology without touching PositionJournal authority, journal schema, stop/TP calculations, event ordering, pause/recheck or idempotency. Verify full Entry/Skip/OFF_PLAN/Partial/Close/Modify/Reconcile journeys and all negative/fault/restart tests; produce screenshots of every form and invalid/saving/saved/not-saved state. Commit only after acceptance.

**U4 — Diagnostics, source chooser, help, compact layouts and fault UX.** Prioritize health and safe recovery; retain full advanced evidence. Test no-data, corrupt source, stale/switching source, unavailable/locked DB, adapter not configured, keyboard conflicts and modal close. Check every screen/dialog at both themes and three sizes. Commit only after acceptance.

**U5 — final regression and owner review.** Run complete Qt-enabled pytest and R0 parity, Ruff check/format, deterministic replay events/IDs, Decimal and time exactness, every journal transaction/idempotency path, theme persistence and source isolation. Run native GNOME visual QA at 100/125/150/200% scaling. Report exact pass/fail/skip counts, baseline-to-commit SHAs, screenshots, unchanged strategy invariants, remaining defects. No automatic approval of LIVE/MT5 or gold alias cutover.

If a phase fails a gate, stop at that phase, isolate the cause, repair only that bounded defect and rerun its relevant tests. Do not rewrite unrelated modules or perform a simultaneous “cleanup” refactor.

## 11. Acceptance checklist — owner-visible definition of done

- [ ] The **same product identity** appears in Dark and Light, with no navy/blue foundation or unreadable tiny labels.
- [ ] Settings offers functional Dark / Light / System and PKT / UTC; choices survive restart and never touch source/journal state.
- [ ] All five screens have been **substantively redesigned** (layout, hierarchy, copy, navigation and detail), not merely recolored.
- [ ] Every source state, missing-data state, fault, replay end and manual-action safety state is honest, legible and suitably prominent.
- [ ] Overview prioritizes decision and next known condition; technical logs/codes are available but not dominant.
- [ ] Signals preserve developing/ready/blocked/history, full exact plans, IDs, expiry, current revalidation and stable selection; never falsely rank/execute.
- [ ] Positions and Journal distinguish local/manual, reconstructed, reconciled/unverified and actually saved events; all transaction flows work.
- [ ] Every manual form, chooser, Settings and Help fits or scrolls at 820×620 and high DPI with visible inputs, validation and Cancel/Confirm.
- [ ] Dates display a named zone; source/event/recorded clocks remain distinguishable; audit UTC milliseconds and full exact numeric values still exist.
- [ ] UI preference changes do not mutate engine, replay, SQLite journal, source identity, event ordering, eligibility or immutable plans.
- [ ] All required existing Qt and R0 tests genuinely pass, not silently skip; a real Ubuntu visual matrix and keyboard/fault journeys are documented.
- [ ] No broker execution, MT5 installation/connection, auto-trading, production actions, new CI workflows or gold alias modification.

## 12. Documentation and handoff discipline

- Treat this as **one reference file for the visual redesign**. Do not create parallel “latest style guide” versions or duplicate the canonical strategy and R0 contracts.
- When the visual direction is owner-approved, record the design decision in existing owning documentation only if necessary; keep this page as the presentation checklist and update its actual implementation status after verified phases.
- The owner will supply additional **error reports later**. Capture the reproduction, stack trace, affected version, environment and minimal failing test; fix those as separately scoped bugs. Do not guess their causes or quietly mix them into U1.
- Do not use GitHub Actions (disabled for this repository). Follow the existing direct-main small-tested-commit workflow after verifying a clean/understood local tree.

## 13. Single Grok implementation prompt — owner-approved handoff

> Grok, implement the owner-approved GROG **complete desktop UI/UX V2** using **docs/desktop-visual-redesign.md** as the single visual/presentation checklist. First inspect current main, local git changes and **AGENTS.md**, then the canonical docs/11 §16, docs/02 §16, docs/09 §13, docs/08 §20 and docs/10 §12. Compare the actual existing five Qt pages, dialogs, source chooser, help and tests against the spec; do not assume baseline c0ef834 is still current. Execute **U0, U1, U2, U3, U4, U5 sequentially**, each as the smallest verified phase with one coherent commit and a test/screenshot/change report. Dark default must be graphite/charcoal, not navy; Light is equal quality; **System must follow the OS at startup and on supported appearance changes**, with a truthful Unknown/fallback indication; PKT/UTC is a display-only preference. Completely improve hierarchy, readability, human time/reasons, responsive tables, modals and fault states across **every** screen, while keeping exact Decimal/UTC audit values and every existing trading, replay, journal, source and keyboard contract. Do not change strategy, signal eligibility, SL/TP, event ordering, schema, idempotency, broker/live permissions, gold alias or unrelated code. No MT5 install, broker access, live feed, automatic trading, production changes or GitHub Actions. Run real Qt-enabled and R0 tests and visible GNOME QA; **never claim skipped tests passed**. If a phase fails, stop and repair that phase rather than continuing. Await separately supplied error reports before fixing unrelated faults. Report baseline SHA, phase SHA, files, exact test counts, visual evidence, residual risks and next gate after each phase.

**Design decision APPROVED (2026-11-07):** owner accepted both charcoal Dark and warm-white Light; **System theme following OS appearance is mandatory**. Grok is the designated implementation owner once given the §13 handoff. No UI code, broker connection, gold alias or production state changed by these documentation updates.
