# GROG — Trade-First Redesign
**Owner direction:** 2026-11-11 · **Status:** APPROVED product scope; SPECIFICATION ONLY — not implemented · **Goal:** make a simple, one-click XAUUSD trade finder with measurable signal quality.

> **One job:** Open Gold, automatically read trustworthy XAUUSD BID/ASK, analyse H1/M15/M5 using the existing engine and show selective **BUY / SELL / NO TRADE** with an executable-side *indicative* entry plan, SL, TP, expiry and reasons. Never force a signal.

## 1. Current decision — what this document replaces

The earlier one-click design in docs/10 §14 and docs/02 §17 included a Watch setup flow and optional position monitoring. **The owner withdrew that feature on 2026-11-11.** This document is the compact product/interface/engineering redesign for the next implementation. It **supersedes watch-specific tasks** in LWX-4, LWX-20..27 and earlier optional monitoring/UI requirements **for the new primary application**. The older implemented R0/Qt journal, trader action forms, data and replay logic remain intact as legacy/research tools, not daily UI features. No deletion or breaking migration.

This document is a single **product redesign and handoff companion**, not a new mathematical authority. Canonical calculations are in docs/03–07, empirical validation in docs/08, source/owner architecture in docs/09, decisions in docs/11. When values are OPEN there, this document does not invent replacements.

### Explicitly in scope
- Locally installed **native Qt desktop** (reuse the current application), XAUUSD only, dark/light/system from existing Settings.
- Automatic read-only MT5 demo/reference feed supervision *after one-time onboarding*. No daily MetaEditor, exporter attach, scripts or terminal commands.
- Existing causal H1 trend + M15 structure + M5 S1 setup engine; selective BUY, SELL or NO TRADE.
- Accurate sourced BID and ASK, expiry, exact entry band, SL, TP1, TP2, gross R/R, quality/fault explanations, visible source/date/freshness.
- A **research/evidence** view that actually measures strategy performance on independent real-data tests.
- Explicit status for unvalidated strategy, source faults, missing historical warm-up, market close, missing broker cost inputs and failed trade gates.

### Explicitly out of the new primary product
- Watch setup, selected-trade monitoring, price touch alerts, TP/SL alerts, tracking orders, position cards, daily trading journal, manual execution forms, paper position P/L, portfolio, account balances, Telegram/mobile notifications.
- Automated order placement/modification/cancellation, broker credential handling, LLM chatbot, multi-asset scanning, indicator zoo, arbitrary confidence score, win-probability marketing.
- Rewriting previously audited engine modules simply for UI styling, replacing local Qt with web, deleting historic files or the SQLite journal.
- Auto-selecting an aggressive risk/leverage level or recommending a lot size before execution-broker contract/cost facts are known.

**Important distinction:** The program still **observes incoming market ticks internally** to detect new setups and expire old ones. The user does **not** monitor a selected trade inside Grog. Grog does **not** know whether a real order was placed.

## 2. The daily workflow — one command, one decision

1. User opens Gold. The Qt Trade Finder window appears immediately with CONNECTING / DATA UNAVAILABLE; it never opens fake demo signals.
2. After a one-time permissioned setup, the app discovers or starts the existing local Wine/MT5 reference installation **in the background**. It validates account/server/symbol/source and reads existing exporter transport. No popup demanding an EA attachment every day.
3. Grog consumes **all** eligible ticks in event order, computes confirmed M1/M5/M15/H1 bars and the existing deterministic S1 pipeline, then evaluates data, strategy and execution gates. UI paint may be coalesced; engine ticks must not be dropped.
4. Grog presents ONE clear headline:
   - **NO TRADE — market checked, no qualifying setup** (healthy, evaluated);
   - **BUY / SELL — REFERENCE · INDICATIVE** (only when existing eligibility and measured source policy permit);
   - **FORMING — NOT READY** (a potential setup; no entry advice yet);
   - **DATA STALE, CLOSED, CATCHING UP, INTEGRITY FAULT, or POLICY UNVERIFIED — BLOCKED** (distinct from healthy NO TRADE).
5. If a valid plan exists, show its exact source quote, timestamp, direction, entry band, stop, TP1/TP2, expiry, gross R/R and (only if supported) estimated net R. The user decides independently whether to trade with an external platform. No Watch/Enter/Mark Filled controls.
6. As time advances, Grog automatically refreshes the **trade opportunity itself**, replacing expired/invalidated plans with their truthful statuses; this is not post-entry trade monitoring.
7. If the app, MT5 or feed fails, the last quote may remain as **HISTORICAL / STALE** only; it is never displayed as a live actionable level.

**One-time setup exception:** If MT5 is absent, not logged into the demo server, or the read-only exporter cannot be restored reliably, show a single guided setup action and honest status. Normal daily operation after onboarding must not require terminal commands.

## 3. Screen design — premium, compact, decision-first

The main window has exactly **one primary work surface**, not five equally prominent trading screens.

**Navigation:** Trade Finder (default) · Research (secondary, for evidence/replay) · Settings. Diagnostics accessible through a small status/detail link or Settings; the old Positions/Journal remain in legacy/replay code but are not navigable as daily trade-finder features. Preserve legacy application mode and tests independently rather than deleting their implementation.

### 3.1 Trade Finder layout

~~~text
 GOLD / XAUUSD                                     REFERENCE · INDICATIVE
 Source: MetaQuotes-Demo  |  Feed: [status]  |  Last tick: [UTC/PKT]

 [DECISION]
 NO TRADE — [clear reason]          or          BUY / SELL — [condition]
 [Data qualified?]  [Strategy version / validity]  [Expires UTC]

 BID [exact]          ASK [exact]          Spread [exact]
 Last received [time]  |  Confirmed source time [time]

 H1 trend [confirmed]  |  M15 structure [confirmed]  |  M5 trigger [state]

 [TRADE PLAN — only if correctly eligible]
 Direction [BUY/SELL]         Entry BID/ASK [exact]
 Entry zone [low - high]      Stop loss [exact]
 TP1 [exact]                 TP2 [exact]
 Gross reward:risk [exact]    Net after costs [value or UNKNOWN]
 Reasons [2-3 factual lines]  Valid until [timestamp]
 [See full causal evidence]   (no Watch, Enter or Monitor button)

 When no plan: explain what is missing. No decorative empty plan or fake levels.
~~~

**Visual rules:** current charcoal Dark (#111111 app, #1B1B1B surfaces) / warm-white Light (#FAFAF9, #FFFFFF), theme System option, restrained #D5C3A4 accent, Inter if installed, otherwise system sans; compact spacing, thin borders, minimal cards, no candlestick wall, neon, gradients, enormous charts or gimmicks. BUY and SELL convey *direction*, not a trading success label. Use readable 15–16px main type and tabular numerals; all risk prices must remain fully visible at target 820x620 / 1366x768 / 1920x1080. Support PKT/UTC display preference while preserving exact source UTC in details.

**Detail panel:** full signal ID/strategy hash, source/server/symbol, exact observed vs received time, original BID/ASK, price increment provenance, H1/M15/M5 confirmed bar IDs and available-at, frozen signal levels, quality/blocker codes, replay/real label, source-integrity and research-validation status. Expanded details do not invent a probability.

### 3.2 Research page (secondary, not the daily workflow)

- Overview of **genuine validation evidence**, not synthetic profit claims: dataset, dates, observed signal count, percentage of evaluable signals, win/loss/indeterminate count, mean/median net R (when costs known), gross R otherwise, drawdown, longest losing streak, return dispersion, regime and spread sensitivity, number of independent walk-forward folds.
- Test origin clearly labeled: SYNTHETIC (software correctness only), HISTORICAL/REPLAY (research), PAPER/FORWARD (observational), or UNVALIDATED.
- Reuse existing offline replay/report code. Research analysis should not write into the operator trading journal or automatically create simulated entries just to make a metric appear.
- Keep detailed legacy manual-journal tools available through an explicit legacy entrypoint for backward compatibility, not visible by default.

### 3.3 Settings and diagnostics

Settings show only effective appearance, PKT/UTC, source connection (read-only/demo), source profile and a diagnostic access link. Advanced options can inspect config and local export paths, health, timestamps, gaps, cursors, startup state and last fault. No trading enable toggle, fake LIVE toggle, broker login form, config magic "fix" button, or user-maintained daily MT5 script.

## 4. Accuracy first: what "good trades" must mean

**We cannot promise an accuracy percentage or profitable setup from an unfinished or unvalidated system.** Build an evidence-first trade selector rather than a confidence percentage generator. The top objective is *out-of-sample, risk-adjusted net expectancy under plausible execution*, **not maximum win rate**. A high win rate with rare catastrophic stops can be inferior to fewer trades with positive expected R.

### 4.1 Preserve the current S1 research baseline
- Existing S1 = confirmed H1 directional context, M15 structure and M5 impulse-pullback/closed-bar trigger; use the original code and versions in docs/04–06. Do not introduce five new strategies, ML or dozens of indicators before proving whether S1 adds value.
- Initial hypotheses (EMA/ATR/pivot/depth/no-chase/SL/TP) are **not validated**. Do not treat hand-picked research parameters as successful solely because fixture tests pass.
- Once the baseline is measured on a sound real dataset, compare **only pre-registered, causally implementable alternatives** to the baseline and document whether they improve unseen net results. Keep original results reproducible.
- A valid market condition can legitimately yield ZERO signals. Don't loosen rules simply because the user wants a trade every day.

### 4.2 Data/clock validation before looking at returns
- Source = specifically identified broker/demo server and symbol, not generic spot gold. Preserve actual BID and ASK with Decimal fidelity, flags, source timestamp, UTC mapping, receive time, crossed/invalid quote count, duplicates and gaps.
- The November 11 current MetaQuotes-Demo clock probe supports server-time tick_ms and observed +02:00 conversion **for that observation only**. Older Oct 19/27 exports may cross broker DST; old files with OFFSET_ASSUMED are not certified by applying the current offset retroactively. No silent timezone patch. See docs/03 §11.
- The earlier mt5full20261108 stream has an explicit G/4022 gap and is **not** a clean qualified source. Create an isolated, collision-free source for live data, retaining all prior data/metadata unchanged. Do not clear a latched fault, merge broken sessions to appear healthy, or recursively scan all 3.2 GiB on every UI repaint.
- A connected 1Hz heartbeat does not prove fresh ticks: require actual incoming T/L records, valid quote/received timing, completed warm-up and no unresolved integrity fault. During broker breaks and weekends show CLOSED/STALE, not READY.
- No preset broker-agnostic pips, price step, commission, slippage, stop/freeze level, quote-age or future-skew "magic numbers." Measure and verify the source; source-bound safety policy values require explicit approval before promotion.

### 4.3 Robust evaluation protocol (reuses docs/08 §18)
1. Freeze the exact reference data version/checksums, time-normalization assumptions, S1 version, signal eligibility, outcome/fill and stop/target rules, all parameters and source-specific costs. Document exclusions, not just survivors.
2. Use chronological **development → walk-forward validation → untouched final test** with non-overlap and a declared embargo spanning maximum eligible trade life. Predeclare dates and selection criteria **before** opening untouched outcomes; prevent look-ahead.
3. Simulate exact **BUY ASK entry, SELL BID entry** and the appropriate BID/ASK exit/stop/TP side, using ordered ticks, genuine first available quote after confirmed M5 trigger, true expiry and latency/delay scenarios. Count same-ms distinct ticks; if gap/intrabar ambiguity prevents deciding a fill/SL/TP order, mark INDETERMINATE, not WIN.
4. Report **all signal counts** (forming, eligible, rejected, expired, hypothetical fills, wins, losses, no-fill, unknown), net expectancy in R only if fee/slippage assumptions are grounded, maximum drawdown in R, consecutive losses, win fraction, actual reward:risk distribution, trade frequency and sample count. Show uncertainty/confidence intervals (accounting for time clustering) rather than a naked "accuracy" number.
5. Stress spread, commission, slippage and manual entry delay; break results down by trend/range, low/high volatility and time of day. Hold out market regimes and examine whether small assumption changes destroy profitability.
6. Pre-register acceptance criteria and minimum sample/coverage before assessing final results. If the record covers only ~3 weeks, **mark insufficient evidence**; no fabricated statistical promotion. Forward paper observation is the next independent test, not proof of real-money fills.
7. Prefer the simplest S1 version meeting reliable net return criteria. If the evidence fails, show **UNVALIDATED / NO TRADE** until improved on new development data, then re-test with untouched periods; never fit a strategy to the held-out test set.

**Metric policy:** Win rate is descriptive only. The decision to promote a strategy requires positive, stable *net* expectancy with acceptable drawdown, realistic fill/fee assumptions, enough independent outcomes and uncertainty. Numeric pass limits are OPEN in docs/08 and must be agreed before blind evaluation; do not silently invent "80% accuracy" or "90% confidence."

## 5. Minimal architecture: reuse, don't rebuild

Current verified GitHub baseline: existing Qt five-page REPLAY application with script launcher; ReferenceReader / ReferenceSession can parse real exported ticks (a bounded real-data UAT parsed 411,566 backfill, four duplicates and no parser faults); **Qt is not yet wired to live**. The installed Ubuntu/Wine demo exporter was observed but has not been qualified for continuous live T/L and has a prior contaminated source. No one-click LIVE program currently passes acceptance.

**Minimal ownership map:**

| Reuse / extension | Responsibility | Avoid |
| --- | --- | --- |
| scripts/gold-desktop.sh; desktop/launcher.py + main.py | Launcher, onboarding, mode selection; eventually one-word gold after sign-off | Changing existing alias early, global config edits, spawning duplicate MT5 |
| Existing Qt window, theme, overview/signals models | New **Trade Finder** read models and compact primary surface | Rebuilding GUI from scratch, reimplementing price/risk math in Qt |
| live/session.py and adapters/mt5_reference | Persistent read-only ReferenceSession, cursor, integrity and clock evidence | Parsing all history on every frame, silently accepting G/offset faults |
| Small local supervisor (new only if needed) | Discover/launch **approved** Wine/MT5, verify exporter already attached, bounded backoff, process ownership | Password handling, killing unrelated Wine, EA auto-install without consent |
| Pure signal pipeline and replay/reporting | Immutable and causal S1/entry/expiry, independent M10 performance evaluation | Extra strategies before evidence, changing synthetic source flags to live |
| Legacy journal/positions modules | Preserve in repository and optional old replay mode | Wiring entry/fill/monitor buttons into new Trade Finder |

**Trade Finder frame:** one source-scoped immutable snapshot with generation, sequence, link and feed health, source timestamps, exact quote sides, latest completed H1/M15/M5, active opportunities, full frozen plan + expiry, blocking reasons and a separate *strategy-validation state*. UI timer updates freshness/expiry even with no tick. Latest UI paint can be coalesced but every accepted tick reaches the pure pipeline.

**Local MT5 lifecycle:** one-time setup may still require an account login and permission. Later Gold opens quickly and starts the already-authorized read-only terminal only if absent. Reuse verified EA/profile auto-restore; do not reattach/compile repeatedly. No background daemon, cloud service, credentials, broker orders, auto-trading permission, or destructive cleanup. An already running MT5 owned by the user must not be killed by Gold.

## 6. Small practical implementation plan — we build it ourselves

One focused commit at a time; run a targeted regression before moving on. **No Grok dependency**. No production server, destructive commands, sweeping refactor or GitHub Actions.

| Phase | Build exactly this | Objective verification |
| --- | --- | --- |
| TF-0 — Baseline and decisions | Read current main and current desktop/API. Freeze this simplified scope. Record tests/known MT5 source faults. | Clean checkout, baseline reference + desktop + signal tests, no unapproved edits |
| TF-1 — Trustworthy, automatic reference feed | One-time local Wine/MT5 onboarding; dedicated clean source; correct current UTC mapping and honest historical offset uncertainty; no repeated EA setup; persistent bounded reader. | Fresh T/L ticks seen with exact bid/ask, pause/disconnect/market close and G/offset faults block READY, repeated app launch doesn't spawn duplicate MT5 |
| TF-2 — Trade Finder desktop | Reuse Qt: one default overview, simple proposal detail, no watch/journal/position daily UI; read-only LIVE worker and status/expiry from existing engine. | One launcher shows true NO TRADE/FORMING/BLOCKED or indicative plans; no fake prices, source/time fidelity, responsive 820x620; replay fallback still works |
| TF-3 — Performance and trade-quality evaluation | Verified real tick datasets, chronological walks, bid/ask realistic fills, fees/latency sensitivity, report for existing S1, compare only pre-registered variants if justified. | Reproducible hashes, no lookahead, honest sample counts/wins/losses/indeterminate, net expectancy/drawdown with confidence and explicit UNVALIDATED if evidence insufficient |
| TF-4 — Native acceptance and launcher | One-command user demo and a full fault/restart/mode regression; only then propose gold alias cutover. | Owner sees real reference source and correct selective opportunities without touching MT5, plus no order calls; explicit approval before changing alias |

**Stop conditions:** If TF-1 cannot deliver verifiably fresh source ticks or clocks remain unqualified, do not promote LIVE and do not bypass with fixture thresholds. If TF-3 fails to establish a reliable edge, the product remains an honest research-only/no-trade analyst; do not add fabricated win rates or mandatory trade frequency. If native execution isn't available to the developer, mark only that test BLOCKED and complete independent fixture tests honestly.

## 7. Focused acceptance contract (new primary Trade Finder)

- TF-A01: Normal daily launcher starts UI, discovers approved MT5 without requiring MetaEditor; already running terminal is not restarted or terminated.
- TF-A02: Absent/incorrect demo server, missing exporter, missing terminal, no network or permissions = SETUP REQUIRED/OFFLINE, no new actionable proposal.
- TF-A03: H connected and session OPEN but zero T/L for longer than measured freshness threshold = STALE/BLOCKED, never LIVE.
- TF-A04: Prior G/4022 source, OFFSET_CHANGED, uncertain DST backfill, malformed line, file rotation/partial record = latched diagnostics and no READY until separately verified recovery.
- TF-A05: Historical B and first-start backlog never issue actionable READY; reconnect only after fresh T/L and valid source/health/clock/policy.
- TF-A06: On genuine reference fixtures, engine signal plan matches existing S1 pipeline exactly (signal ID, BID/ASK side, entry band, SL, TP, expiry and reason), independent of UI.
- TF-A07: No setup yields honest NO TRADE; forming or blocked signals are never disguised as BUY/SELL entry advice. Multiple READY shown without fabricated rank.
- TF-A08: UI shows no Watch, Enter, Partial, Modify, Close, manual Positions/Journal or broker controls in the primary LIVE mode. Existing legacy functionality and its tests stay intact.
- TF-A09: A live-proposal expiry/invalidation updates from clock/engine even if the market has no new quote; old source levels are visibly STALE.
- TF-A10: Real-tick evaluation produces reproducible untouched sample, net/gross labels, drawdown/win rate/indeterminate, costs sensitivity and reasons why a strategy remains UNVALIDATED.
- TF-A11: No LLM, order calls, account credentials, auto-trading toggle, production changes, source-file deletions or unsupported data repair.
- TF-A12: Qt dark/light/system, PKT/UTC, exact Decimal, source label and full timestamps survive mode switch/replay fallback and 820x620 / 1366x768 / 1920x1080 layouts.
- TF-A13: Startup, shutdown, crash, replay transition, file/directory failures and GUI-close do not leak workers, corrupt cursors or stop unowned MT5.
- TF-A14: All focused reference/session/strategy/desktop tests and Ruff pass; exact native Wine tests documented separately; **gold alias unchanged** until explicit owner sign-off.

**Definition of done:** The owner opens a single Gold desktop command and sees only evidence-backed current XAUUSD **trade proposals or NO TRADE**, with no need to operate MT5 manually after setup. No unsupported trade-quality claims. No monitoring workflow.

## 8. Open evidence (cannot be hidden by design)

- Current MT5 full historical source contains a recorded G/4022 and unresolved pre/post-DST timestamp assumptions.
- Current exporter had connected heartbeats without observed T/L ticks after catch-up in the inspected session. Need diagnose on native Ubuntu; do not assume a healthy stream.
- Source-specific quote/heartbeat/future-skew, spread/cost limits, execution broker tick specifications and real-world fees/slippage are not yet calibrated and approved.
- Existing S1 has no demonstrated edge on untouched, sufficiently long XAUUSD data; the existing ~3-week FullUAT sample cannot justify a live win-rate claim by itself.
- Native one-click orchestration, LIVE Qt worker and final alias change do not exist in GitHub at this design stage.

**Next implementation action, only after this documentation phase:** TF-0 audit and one small independent TF-1 module. Do not start watcher work. Any later change to these scope decisions is recorded in docs/11 before coding.
