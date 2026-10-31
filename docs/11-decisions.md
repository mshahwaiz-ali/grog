# Decisions, Approval Status and Documentation Change Control

Updated 2026-10-31. **This is the authoritative record of agreed scope and unresolved decisions**, not proof of implementation or strategy profitability.

## 1. Status vocabulary

- **APPROVED** — User explicitly accepted the **product direction**; sufficient to document, **not** blanket permission to write code.
- **PROPOSED** — Detailed candidate design; can be researched/reviewed, **not silently implemented**.
- **EXPERIMENTAL** — Measurable strategy formula, indicator parameter, filter or scoring policy whose usefulness remains untested.
- **OPEN** — Essential choice undecided; Grok must request instruction rather than fill it with invented specifics.
- **ARCHIVED** — Historical snapshot preserved for traceability; **never an implementation source of truth**.
- **VALIDATED** — Requires reproducible recorded test evidence; **no S1 trading edge is presently VALIDATED**.

## 2. Approved product directions

| ID | Status | Decision |
| --- | --- | --- |
| D-001 | APPROVED | Project **Grog**, private repo `mshahwaiz-ali/grog`, `main` branch, documentation first |
| D-002 | APPROVED | XAUUSD (Gold) scalping-focused **manual trading decision support**, not automated execution |
| D-003 | APPROVED | Local terminal session and commands with continuously updated monitoring; later UI alternative is possible, not required |
| D-004 | APPROVED | **Developing Opportunities** and **Actionable Signals** must be separate |
| D-005 | APPROVED | After **manual confirmation of actual entry**, show live position monitoring, trade journal and outcome status |
| D-006 | APPROVED | No GPT, Claude, LLM chatbot, agent runtime, brokerage write/execute interface or automatic broker orders |
| D-007 | APPROVED | Use **multi-timeframe analysis** without mandatory same-color/all-timeframes directional agreement; a corrective M15 can be desirable within H1 trend |
| D-008 | APPROVED | **Only core goal:** choose/monitor **better Gold trades**; avoid over-filtering, low-value indicators and forced signals |
| D-009 | APPROVED | **Grok is the external coding assistant**, not a Grog software component. Grok implements bounded, explicitly approved requirements and tests, never guesses omitted trading logic |
| D-010 | APPROVED | Maintain **one active authoritative document per topic**; improve those files instead of adding a new numbered document for each planning iteration. Preserve earlier conflicting drafts under `docs/archive/` |
| D-011 | APPROVED 2026-10-31 | **Use MT5 as Grog's preferred reference-price adapter for the first implementation**, with a broker-neutral normalized BID/ASK core. An MT5 demo server can provide development quotes; no final execution broker is chosen or required for offline engine implementation. MT5 itself is NOT an independent source of universally identical Gold quotes. |
| D-012 | APPROVED 2026-10-31 | **Do not block Grog's data, replay, MTF, indicators or offline S1 research on the user's broker choice.** Later broker selection changes executable spreads, cost, symbol specs and price-side SL/TP validation; mark reference-feed signals as indicative until validated against actual execution venue. Manual execution only; no brokerage write APIs. |
| D-013 | APPROVED DIRECTION 2026-10-31 | **Documentation-first handoff:** when the user expressly tells Grok to start implementation, follow [AGENTS.md](../AGENTS.md) and [10 — Roadmap](10-roadmap.md) through **M00–M08**, one bounded locally tested module at a time, main branch only. No repeated questions for already-specified offline behavior; live MT5 install/demo credentials and real-money broker settings still need separate permission. No GitHub Actions. |

## 3. Scope lock — what upgrades may and may not mean

An upgrade must materially aim to improve **entry quality/timing, detection of false setups, realistic BID/ASK execution and costs, stop/TP selection, risk decisions, trade monitoring or evaluation reliability**.

Do **not** add wallets, linked account portfolios, crypto/exchange features, auto bots, copy trading, chats/LLM, social feeds, extra notifications, marketing dashboards, strategy shopping malls or new instruments merely because competing platforms have them.

**Required proposal test:** (a) Which exact Gold trading mistake does it address? (b) What simple measurable new input/behavior? (c) What cost/maintenance burden? (d) How will it be compared to the simpler system on unseen data? Reject additions without answers.

## 4. Current active specification owners

| Topic | Canonical document |
| --- | --- |
| Product scope and quality goal | [01 — Vision](01-product-vision.md) |
| Terminal / operator workflows | [02 — Workflow](02-workflows-and-ux.md) |
| Quotes, completed bars, timing, calendar | [03 — Market Data](03-market-data.md) |
| MTF context, pivot/EMA/ATR mathematics and indicator choices | [04 — Analysis](04-analysis-engine.md) |
| S1 v0.2 pivot pairing, pullback and trigger; future S2/S3 | [05 — Strategies](05-strategies.md) |
| READY/expiry/entry band, eligibility overlays, scoring | [06 — Signals](06-signals-and-scoring.md) |
| BID/ASK stops/targets, fees, actual fills and trade monitoring | [07 — Risk & Monitoring](07-risk-and-monitoring.md) |
| I0–I8 indicator experiments, failures F01–F16, tests S1-01–S1-20/ADV | [08 — Validation](08-validation.md) |
| Implementation modules/dependencies | [09 — Architecture](09-architecture.md) |
| Modular build milestones | [10 — Roadmap](10-roadmap.md) |
| Sources and competitor lessons | [12 — References](12-references.md), [13 — Competitors](13-competitor-research.md) |

The former top-level research drafts **14–17 were consolidated into their topic owners and preserved at [archive/2026-10-30](archive/2026-10-30/README.md)**. A prior file number **never overrides** a current topic owner.

## 5. Research hypotheses (NOT approved trading parameters)

- Initial S1 idea: H1 EMA20/EMA50 directional bias, M15 confirmed swing reference and corrective/opposing context, M5 confirmed swing impulse/pullback trigger; ATR14 for volatility scaling.
- Alternative indicators **for controlled trials only**: EMA30/90, ATR21, M15 OPPOSING soft-vs-hard veto, nine pre-registered variants **I0–I8** in [08](08-validation.md).
- Proposed S1 experimental values: pivots left2/right2; impulse >=1 ATR and <=12 M5 bars; pullback depth 25–75%, >=2 bars; trigger beyond prior two M5 bar extremes; initial 0.10 ATR stop buffer; preliminary no-chase 0.20 ATR, quote-valid entry-band and next-M5-close expiry (exact rules in [05](05-strategies.md), [06](06-signals-and-scoring.md), [07](07-risk-and-monitoring.md)).
- Candidate benchmark TP1=1R informational; TP2=2R and full position exit at TP2/SL in **baseline simulation**. Partial TP policy is a distinct trial; no automatic changes to live broker orders.
- Proposed **0.25–0.5% equity risk** as an illustrative research range, not an approved position-size limit or universal safe threshold.
- Candidate 100-point quality rubric with five broad axes in [06](06-signals-and-scoring.md) is **not implementable yet**: normalization, exact subpoint formulas, cutoffs and probability calibration remain OPEN. Do **not** display invented 85%-type accuracy claims.
- Python modular local implementation, SQLite journal, possible Textual/Rich terminal UI and a read-only feed adapter are PROPOSED, not selected dependencies.

## 6. OPEN decisions — blockers for broker-verified live execution, NOT for offline R0 M00–M08

1. **Later live execution validation (NOT a blocker for broker-neutral development):** eventual XAUUSD execution broker, actual BID/ASK tick data/history rights, precision, contract size/lot limits, stop execution, server times and fees/slippage. A temporary MT5 demo reference server and offline data source still require concrete availability/terms checks; their details are not assumed.
2. **Data-health thresholds:** stale quote duration, first-post-M5-close maximum quote delay, acceptable gap/reorder, market-hours/downtime policy.
3. **Net execution/risk gates:** maximum spread/cost in R, minimum net reward, position sizing, daily caps and maximum simultaneous correlated exposure. No guessed defaults.
4. **Event policy:** calendar source with as-of data, refresh/certainty status, high-risk event blackout timing and response to unavailable calendar.
5. **Unfrozen S1 hypothesis parameters:** confirm or revise documented pivot, impulse, depth, M15 context age, candidate replacement/TTL, stop/TP, entry-band settings after research and source constraints.
6. **Market data initialization & test integrity:** strict EMA/ATR warm-up, bar finalization and price precision/tick rounding convention; simulator fill model including manual delay and partial exits.
7. **Performance promotion thresholds:** acceptable trade frequency, required sample/time/regimes, walk-forward/final untouched evaluation results, max drawdown and live paper-testing period.
8. **UI/interaction choices:** exact terminal commands, manual data-entry errors and corrections, program restart/position reconciliation, whether read-only broker fill import is desired.
9. **Later modules:** S2/S3 strategy equations and conflicts, M1 early entry variant, exact rubric calibration. These are **not** prerequisites for documenting S1 and should not be built by default.

**Open != permission to assume**. If a blocked decision is missing, Grok should explicitly list the blocker and implement only a separately authorized lower-risk module.

## 7. Documentation standard and change process

1. Research a topic, compare conflicting evidence, and propose **the smallest measurable improvement**.
2. Get user approval before treating a candidate rule as final. Record its status/date/why in this log.
3. Update **the existing canonical topic file**. Put formulas **only** in the owning document and reference them elsewhere; no competing copy/paste instruction blocks.
4. Keep test fixtures and performance-comparison contracts in **08**, risk/monitoring in **07**, signal behavior in **06**, strategy behavior in **05**, indicators in **04**.
5. For major superseded revisions, preserve historical version in `docs/archive/YYYY-MM-DD/` **only if needed for traceability**, then remove conflicting active duplicates once archive and references are verified. Git commit history also preserves exact changes.
6. Check README, [00 — Index](00-index.md), all internal Markdown links, version/status words, acceptance criteria and any cross-doc conflicts before handing work to Grok.
7. Grok task prompts: one bounded module, explicit version, source files, required positive/negative tests, forbidden features and expected evidence (commits, outcomes, unresolved questions). No undocumented behavior and no broad implementation based on research sketches.

## 8. Historical milestone record

- 2026-10-30: Project plan, terminal/manual workflow and initial numbered documents established.
- 2026-10-30: Competitor research limited to improvements in Gold trade quality; no unrelated features adopted.
- 2026-10-30: S1 MTF draft, adversarial analysis, refinement and indicator research existed as files 14–17.
- 2026-10-30: **Documentation consolidation**: core material organized into canonical 04–08 (plus aligned 02/03), drafts archived for traceability and links cleaned. This is a **documentation-quality milestone only**, **not live strategy validation**.

No code has been implemented; no trade win rate or profitability verified by these planning activities.

## 9. Phase 18 research milestone — 2026-10-31

**Status: PROPOSED SPECIFICATION / TEST PLAN, NOT VALIDATED AND NOT AUTHORIZATION TO IMPLEMENT.** The current **single source of truth** remains [06 — Signals & Scoring](06-signals-and-scoring.md), with all Phase 18 evaluation fixtures in [08 — Validation](08-validation.md). No new top-level numbered document was created.

- **Recommended decision order:** data integrity → existing S1 objective setup and confirmed trigger → actual BID/ASK-based entry/SL/TP plan → approved safety gates → transparent supporting evidence → READY/WAIT/NO TRADE → conflict handling. A quality-score display cannot override a failing data, strategy, execution or risk gate.
- **Default quality UI:** show explicit H1/M15/M5 evidence, known costs, market levels and reason codes **without** a numeric probability or invented 100-point subscores. The previously proposed 25/25/20/20/10 rubric remains an **unimplemented experimental outline**.
- **No new automatic filter:** M15 CORRECTIVE continues to be a normal possible pullback; M15 OPPOSING and nearby resistance remain documented soft warnings unless a strictly controlled experiment justifies a veto.
- **No extra exposures based on fake rank:** duplicate structural pairs deduplicated; contradictory/overlapping opportunities require an explicit operator-risk policy. Grog executes no broker trades.
- **Phase 18 research plan:** use a frozen S1/indicator baseline first, test proposed score/ranking and one additional filter **separately**, record rejected profitable as well as losing trades, and evaluate realistic after-cost net expectancy, frequency and drawdown on independent data.
- **18 synthetic tests SQ-01..SQ-18** are added to [08](08-validation.md). All are test specifications; none has been executed.
- **First-quote transient-spread recovery is OPEN:** existing baseline rejects an initially ineligible quote; a bounded pending-trigger variant can only be tried as a separately approved, fully timestamped experiment. No invented grace period, automatic reissue, retrospective fill or hidden state added.
- **Still OPEN:** broker/feed and contract metadata, quote age/latency and spread/cost limits, event restrictions, precise usable quality score, score cutoffs, multi-position handling, real-world frequency/return acceptance thresholds, and forward-paper evaluation criteria.
- **No GitHub Actions needed:** direct GitHub Contents API file commits suffice for documentation edits. GitHub Actions runner minutes are not required.

**Phase 18 historical note, now superseded by D-013 and Section 12:** S1 live-broker claims and risk gates require actual market-data/broker evidence. Offline **research S1 code** is explicitly permitted under user START after the causal data/indicator milestones pass, with SIMULATED labeling and no guessed live policy. The earliest next code module is M00, not broker selection.

## 10. Market-data and execution research — 2026-10-31

**Status: RESEARCH DOCUMENTED, NOT IMPLEMENTED OR FEED-VALIDATED.** The user's eventual execution broker remains undecided; MT5 is now the **approved preferred reference adapter direction**, not a connected live quote provider. No broker software, account credentials, Python package, Wine runtime, tick data or quote exporter has been installed or accessed.

**Original conditional comparison (refined by D-011/D-012):** For the MT5 reference feed, first research an Ubuntu/Wine-hosted MT5 **read-only quote exporter** and demo-server tick history. Its MQL5 side must not contain order execution or mutation functions; callback coalescence requires historical tick catch-up and gap evidence. If user's platform is **cTrader**, evaluate read-only Open API live/historical access instead, including authentication and 1-week historical-request batching. Dukascopy BID/ASK may be useful for **offline research only**, not a certified broker-matched fill model. Do not introduce a "universal" XAUUSD feed composed of several brokers.

**Core new correctness rules:**
- [03 — Market Data](03-market-data.md): canonical quote field contract, provider-vs-local time, BID/ASK updates, source identity, duplicate same-ms quote handling, replay/backfill origin separation, feed health, Linux source trial and due-diligence scorecard.
- [07 — Risk & Monitoring](07-risk-and-monitoring.md): symbol tick increment vs display digits, contract/lot/profit currency, stop/freeze properties, manual fill timing, BID/ASK P/L and **no spread double-counting** when execution sides already include it.
- [08 — Validation](08-validation.md): 22 deterministic MD test fixtures and a PASS/CONDITIONAL/FAIL source audit. Passing data-integrity tests is not a claim that the S1 strategy is profitable.
- [09 — Architecture](09-architecture.md) and [10 — Roadmap](10-roadmap.md): minimal read-only adapter boundary and sequence for quote normalization/replay before S1 strategy implementation.

**OPEN decisions requiring future evidence, NOT blocking offline engineering:** actual demo-server access, MT5 XAUUSD availability and market-data terms, dataset coverage, latency budget, exact reference symbol contract, historical source and local transport, data sampling tolerance. **Actual execution broker/platform** and its separate contract/cost assumptions are only mandatory before claiming accurate live execution economics, broker-matched signal fills or real-capital readiness.

**Scope/operations:** Updates to GitHub are via the connected **direct GitHub Contents API**, not GitHub Actions; Actions remains unnecessary/disabled. No GitHub Actions workflows were triggered for this documentation research. No trading/broker automation or new active documentation files were created.

**Next actionable phase:** Plan a bounded **broker-neutral offline BID/ASK importer → normalizer → causal MTF bars/replay** implementation for Grok, without installing a terminal or needing an execution broker. Next validate an **MT5 demo reference feed** using a minimal read-only quote adapter; never require that the user's eventual manual trading platform also be MT5. Live broker-specific spread/stop/cost differences remain a validation layer, not a rewrite of the analysis engine.

## 11. Broker-optional MT5 reference-data decision — 2026-10-31

**User decision:** MT5 is the preferred source integration for Grog's initial Gold **reference** data; choosing an eventual real-money broker is **deferred and must not delay development**. This supersedes earlier suggestions that the user's manual execution platform must first be specified. Broker/platform independence applies to analysis and research; **it does not mean executable BID/ASK prices or spreads are identical across brokers**.

**Why:** World Gold Council explains OTC gold trading is bilateral, and official MetaTrader documentation explains OTC Bid/Ask quotes are formed/provided by counterparties and brokers. MT5 is a client terminal connected to a selected **broker/server**; an MT5 demo account can provide market observation with no real-money commitment but still needs some demo-server access. References: https://www.gold.org/about-us/what-we-do/market-infrastructure/gold-trading-wholesale-market and https://www.metatrader5.com/en/terminal/help/trading_advanced/price_data and https://www.metatrader5.com/en/terminal/help/startworking/acc_open.

**Development order without a broker decision:**
1. Design and independently approve a **normalized BID/ASK quote and timestamp schema**, synthetic fixtures and historical importer (no broker, live account, wallet or secrets required).
2. Build confirmed M1/M5/M15/H1 bars, causal indicators and reproducible replay. Use marked-offline / PROXY data for research, **not** broker-verified simulated fills.
3. Investigate a **read-only MT5 demo feed exporter** on Ubuntu/Wine only when the relevant module is approved. Store `source_id`, `reference_venue`, `symbol`, price sides, timestamp and health. MT5/OnTick must use catch-up and gap checks.
4. Add accurate execution costs, stop conventions, and manual fill reconciliation once the user selects an actual broker. If broker differs from reference feed, Grog shows **indicative quotes** and checks the operator's real executable entry when supplied; do not pretend that the reference feed and actual stop fills are identical.

**Implementation scope:** One reference feed adapter first; no need to implement cTrader, multiple brokers or dynamic source aggregation. The adapter boundary stays modular so this can change without rewriting S1. GitHub Actions are disabled/not needed; documentation commits use direct GitHub Contents API. **No code or live feed configured by this decision alone.**

## 12. Implementation-readiness audit and research-only authorization — 2026-10-31

**Status (historical, as of the handoff): ENGINEERING SPECIFICATIONS READY FOR EXPLICIT HANDOFF.** R0 has since been built and audited — see §13. The user requested complete documentation, premium terminal UX, precise technical contracts, tests, and a single Grok starting instruction. We consolidated by canonical topic, with only the **root AGENTS.md** added as the external coding-agent entry, not another S1 research revision.

**Approved architecture and UI direction for implementation once told to START:** Python 3.11, uv lock, pure deterministic quote/MTF/strategy engine, SQLite operational journal, Textual TUI with five minimal screens and an XAUUSD-only scope. No AI/agent runtime, broker-order execution, wallet, generic dashboards, extra instruments or CI Actions workflows.

**Offline-safe research permissions on START:** M00–M08 may implement the precise existing `S1_RESEARCH_V0_2` formulas/parameter values in [04](04-analysis-engine.md), [05](05-strategies.md), [06](06-signals-and-scoring.md), [07](07-risk-and-monitoring.md) **for synthetic and historical REPLAY testing only**. The exact same formulas remain **EXPERIMENTAL and unproven** as profitable live trading rules. Use synthetic fixture tick size 0.01 exclusively within test data; third-party and live broker tick size/fees are UNKNOWN unless supplied and verified.

**External blockers do NOT block R0:** actual trading broker, authenticated MT5 demo server, license-restricted histories, live feed installation, true contract tick value, fee/slippage calibration, real trading risk policy, numerical quality-score calibration and independent forward results. These are not included in the initial start authorization. M09 live reference feed requires separate permission and source audit; M10 live performance qualification requires real data and evidence.

**Documents directly enabling a no-guess offline build:** [02 UX](02-workflows-and-ux.md) gives screens/bindings/input states; [09 Architecture](09-architecture.md) gives Python layout, type contracts, CSV, SQLite and CLI; [10 Roadmap](10-roadmap.md) lists M00–M10 with exact deliverables/tests/commits; [08 Validation](08-validation.md) includes CLI, UI, persistence, MD, S1 and signal cases. [00 Index](00-index.md) resolves precedence. [AGENTS.md](../AGENTS.md) tells Grok exactly how to begin without code or trading automation.

**Completion criterion:** Repo documentation prepared for the user to hand to Grok. No invented win-rate, untested profitability or claim of a working app. Grok must report real tests and commits once it starts.

## 13. R0 acceptance-audit decisions — 2026-10-31

Recorded by the R0 audit ([14](14-r0-acceptance-audit.md)); each is a bounded engineering decision, none sets a trading threshold.

| Decision | Status | Owner doc |
| --- | --- | --- |
| Operator actions are a separate overlay lane; signal records stay immutable; at most one first operator action per signal (migration 0004 `signal_operator_actions`, append-only, backfilled). | APPROVED (engineering) | [09 §7](09-architecture.md), [07](07-risk-and-monitoring.md) |
| Overlap/exposure is shown as factual warnings only; **no automatic exposure limit** (§6 stays OPEN). | APPROVED (engineering) | [02](02-workflows-and-ux.md), [07](07-risk-and-monitoring.md) |
| Mark freshness (FRESH / UNVERIFIED / STALE / DEGRADED / MARKET_CLOSED / OFFLINE / REPLAY_ENDED / UNAVAILABLE) is always shown with a mark; source status is separated from playback. | APPROVED (engineering) | [02 §6, §8](02-workflows-and-ux.md) |
| Gross R presentation: per-unit move R, realized R and unrealized remaining-position R share the original full-position risk denominator; net R and currency stay UNKNOWN without contract and fees. | APPROVED (engineering) | [07 §6.1](07-risk-and-monitoring.md) |
| Replay run identity includes `engine_code_hash`; window membership by provider time, `--to` exclusive. | APPROVED (engineering) | [08 §10](08-validation.md), [09 §2.1](09-architecture.md) |
| `config/synthetic-demo.fixture-only.toml` may declare freshness thresholds **for synthetic demo/tests only**; defaults stay unset and these values must never be reused for a real feed. | APPROVED (engineering) | [10 §9](10-roadmap.md) |
| R0 terminal visual system and modal anatomy (Cancel default, typing never triggers hotkeys, 120×34 / 80×24 / 70×18). | APPROVED (UX) | [02 §2.1](02-workflows-and-ux.md) |
| H1 invalidation while READY: the stricter rule (H1-STRICT — any newly confirmed H1 bias other than the required one invalidates) is the **PROVISIONAL S1 research baseline**; [05 §8](05-strategies.md) and [06 §5](06-signals-and-scoring.md) now say the same. The looser opposite-only rule is pre-registered research question RQ-H1 ([08 §17](08-validation.md)), not a runtime option. | PROVISIONAL (owner, 2026-10-31) — EXPERIMENTAL, not approved or validated for live use | [05](05-strategies.md), [06](06-signals-and-scoring.md) |

## 14. M09-A offline reference-adapter decisions — 2026-10-31

| Decision | Status | Owner doc |
| --- | --- | --- |
| Transport = append-only rotated text files `GROG-MT5-REF/1` written by a read-only MQL5 exporter; no socket/server/DB bridge. | APPROVED (engineering, owner M09-A brief) | [09 §5.1](09-architecture.md) |
| Dedup key = content + per-ms occurrence index within a delivery segment; timestamp alone is never a key. | APPROVED (engineering) | [09 §5.1](09-architecture.md), [03 §8](03-market-data.md) |
| Durable cursor as an atomically replaced JSON file in the state dir; no new SQLite table for M09-A. | APPROVED (engineering) | [09 §5.1](09-architecture.md) |
| LIVE eligibility requires mode `L`, outside catch-up, and quote age ≤ `live.max_quote_age_ms`; everything else is BACKFILL and can never yield an actionable READY. | APPROVED (engineering) | [09 §5.1](09-architecture.md), [06](06-signals-and-scoring.md) |
| `reference.max_heartbeat_age_ms` is a new OPEN threshold (unset ⇒ link UNKNOWN, never LIVE). | OPEN — measure on the authorized demo feed | [10 §9](10-roadmap.md) |
| Installing/running MT5, Wine or any broker software, any broker/data connection, credentials or market-data download. | **NOT AUTHORIZED** — separate explicit owner permission | [10 §9](10-roadmap.md) |

