# Decisions, Approval Status and Documentation Change Control

Updated 2026-10-30. **This is the authoritative record of agreed scope and unresolved decisions**, not proof of implementation or strategy profitability.

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

## 6. Blocking OPEN decisions (before S1 implementation, not necessarily before isolated replay utilities)

1. **Broker/provider and executable symbol contract:** XAUUSD source, BID/ASK tick data/history rights, quote precision, contract size, lot constraints, server times, actual stop order behavior and commission/slippage assumptions.
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
