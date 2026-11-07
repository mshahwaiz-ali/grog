# Research Validation, Backtesting, Indicator Comparison and Adversarial Tests

**Topic owner:** All S1 research experiments, quality/performance acceptance criteria, adversarial fixtures, win/loss attribution and overfitting controls. Updated 2026-10-31.  
**Status:** RESEARCH SPECIFICATION ONLY. **No S1 strategy has been backtested, verified profitable, or approved for live trading.** Reference formulas [04](04-analysis-engine.md), signals [06](06-signals-and-scoring.md), S1 setup [05](05-strategies.md), SL/TP economics [07](07-risk-and-monitoring.md). Historical research drafts are [archived](archive/2026-10-30/README.md).

## 1. Research objectives and what constitutes a useful upgrade

Primary metric: **net expectancy per realistically filled trade in initial-risk units R**, after bid/ask spread, modeled manual latency, commission, slippage and broker constraints. Also protect net total R under agreed position-risk budget, maximum drawdown, tail loss, and a usable number of opportunities.

**High win rate is not sufficient.** Hypothetical example before costs: 90% × +0.3R + 10% × −3R = **−0.03R per trade**; 40% × +2R + 60% × −1R = **+0.20R per trade**. Both require additional real-world risk assessment; neither implies profitable execution after costs.

No target such as "90% accuracy" is guaranteed. A signal-quality score from [06](06-signals-and-scoring.md) is **not** a calibrated win probability.

Every indicator, strategy filter and added complexity must prove marginal value **on unseen, realistic data** and preserve reasonable signal frequency. Track how many profitable as well as losing signals each new filter would remove.

## 2. Dataset and event-time requirements

- Prefer broker-matched **real bid/ask ticks**, UTC source/receipt timestamps, historical spreads and documented transaction metadata. Generate M1/M5/M15/H1 from the same normalized feed.
- No unseen future bar, retrospective pivot, current H1 candle treated as finalized, or future news-calendar content. A scheduled event is usable only if its time/release was actually known when the signal occurred.
- Record source, raw-data checksum, coverage window, weekend/holiday and DST handling, missing tick gaps, spread distribution, contract specs and data licenses.
- Define chronological **development**, independent **validation**, **walk-forward**, and **untouched final evaluation** windows before selecting parameters. Include differing market regimes, sessions and news days; do not cherry-pick favorable months.
- Every test records immutable versions: strategy, indicator math, pivot algorithm, feed snapshot, rules/parameters, signal lifecycle, fee model, slippage assumptions, execution latency, risk policy, seed and results.
- Time-causal replay: given the same events/config, outcome and all intermediate candidate/READY timestamps must be identical. Do not rewrite historical READY if later conditions change.
- Inspect and quarantine untrustworthy quote periods; report excluded coverage and economic implications. Missing data is **not** a zero-loss trade.

## 3. Realistic hypothetical execution

- A **long** proposed market entry uses ASK; exits/long protective stops are assessed on BID subject to broker's actual conventions. A **short** entry uses BID; exits/short stops assessed on ASK.
- First eligible entry quote occurs **after** M5 trigger bar is finalized and available. Never fill at the earlier theoretical M5 close.
- Simulate explicit, observed **manual-entry delay scenarios** (zero-at-first-quote, moderate, late), using subsequent quotes rather than favorable retrospective fills. Delay values are OPEN until the workflow and real latency are measured.
- Where spreads vary, price path and costs must use actual side-by-side bid/ask history. Stress wider spread, additional slippage, gaps, commissions and partial fills.
- Baseline S1 exit policy from [07](07-risk-and-monitoring.md): show TP1 at 1R, TP2 at 2R, but **100% of simulated position exits at TP2 or SL** (whichever actually executes first), with fees and slip. TP1 does not create a fictional partial win. Test 50%-TP1 policy separately.
- A SL/TP crossed by an OHLC bar without known **tick sequence** has unknown order. Mark INDETERMINATE or use a clearly declared conservative assumption; never award the favorable outcome. If historical bid/ask lacks sufficient fidelity, report limitations prominently.
- Account for manual execution that does not fill, entries outside original band, broker price precision, trade size/lot increments and instrument-specific trigger semantics.

## 4. Initial pre-registered indicator/MTF experiment matrix

**Goal:** a minimal robust combination, not every indicator in existence. All entries below are **candidate tests**, none guaranteed best.

| ID | H1 bias | M5 volatility scale | M15 OPPOSING behavior | Question |
| --- | --- | --- | --- | --- |
| I0 | None (diagnostic M5 benchmark) | ATR14 | Observe only | What happens without H1 bias? |
| I1 | EMA20/50 | ATR14 | Soft warning/context | Proposed default |
| I2 | EMA20/50 | ATR14 | Hard veto | Does a stricter M15 filter improve net results? |
| I3 | EMA20/50 | ATR21 | Soft | Sensitivity to ATR length |
| I4 | EMA20/50 | ATR21 | Hard veto | Combined ATR length + strict M15 |
| I5 | EMA30/90 | ATR14 | Soft | Slower H1 trend alternative |
| I6 | EMA30/90 | ATR14 | Hard veto | Slower trend + strict M15 |
| I7 | EMA30/90 | ATR21 | Soft | Both slower lengths |
| I8 | EMA30/90 | ATR21 | Hard veto | Slow trend, different ATR and strict M15 |

**Important test interpretation:**
- I0 deliberately disables H1's direction gate, **only for research**, so its incremental effect can be evaluated. It is not an authorized production variant.
- EMA30/90 substitutes for fast/slow EMA **including fast EMA 3-bar slope** and requires enough H1 history (proposed >=450 bars) to warm up fairly. Do not let varying warm-up start dates bias results.
- **Soft M15** means context is displayed but **does not alter entry selection** in these baseline comparisons. Therefore a changed *displayed score* without changed trades is not a profit improvement.
- Compare variants with otherwise identical strategy/pivot/trigger/SL/TP/cost/latency rules. Changing ATR length can **also** change impulse/stop and entry thresholds because ATR scales those; report that linked effect, don't misstate it as an isolated cosmetic indicator.
- Never blindly stack EMA+MACD+RSI+ADX as independent votes; much of their information is correlated.
- If trend/range misclassification remains a **measured** failure, a later **single** ADX or candle-body filter experiment may be proposed **one at a time** with a new untouched evaluation window. RSI/MACD/order blocks/fair-value gaps are not automatically approved.

## 5. Additional targeted S1 variant experiments

Use the same held-out time boundaries and execution model wherever possible:
- **B0**: causal M5 price-structure baseline, no H1 directional gate.
- **B1**: B0 + H1 directional eligibility.
- **B2**: B1 + M15 context observed/soft, with later separate strict-veto test.
- **B3**: optional, separately versioned **M1 early-entry** trigger requiring preexisting M5 FORMING, *not* a future M5-close trigger.
- **E1**: one optional M5 trigger-body/close-location strength rule, after baseline.
- **E2**: one-bar persistence versus earlier READY, accounting for worse late prices and fewer filled trades.
- **E3**: wider/narrower ATR stop buffers under an identical percent-equity risk budget.
- **E4**: structural target congestion warning versus separately specified structural TP policy.
- **E5**: session/time-of-day/news-proximity soft-vs-hard eligibility after empirically measuring risk and lost opportunities.
- **E6**: signal expiry/entry-band, post-close delay and manual latency sensitivity.
- **E7**: one active FORMING pivot pair vs bounded multiple-pair candidate policy, deduplicated rigorously.

**Avoid a combinatorial explosion.** Freeze a small initial selection and an explicit experiment budget. Each variant must be linked to one defined error class and have a zero-change/simple comparator. Do not bundle all filters and then attribute improvements to a single one.

## 6. Objective S1 failure taxonomy

| ID | Failure mode | Correctness gate or experimental response |
| --- | --- | --- |
| F01 | Higher-timeframe repaint / future-pivot leak | Hard no-future-data rule |
| F02 | H1 trend lags M15 structural reversal | M15 soft warning; compare veto |
| F03 | M5 continuation candle breaks out then collapses | Study body/retest strength as isolated variant |
| F04 | Move exhausted / target structurally crowded | Level-distance observation and ablation |
| F05 | Pullback becomes genuine structural break | Hard invalidation against frozen pair |
| F06 | Stop is ordinary volatility noise | Buffer-vs-MAE/ATR experiments |
| F07 | Spread and commission consume apparent reward | Real bid/ask and cost-sensitive gates |
| F08 | Manual signal-to-entry delay ruins R/R | Live revalidation; late-entry experiments |
| F09 | Opposing level blocks TP | Structural-congestion vs target policy experiment |
| F10 | News/event spike and volatility | As-of event data, session/event experiments |
| F11 | Trend/range transition and chop | Regime audit, soft filter experiments |
| F12 | Feed gaps, out-of-order quotes | Hard data-integrity gate |
| F13 | Bid/ask-only stop/TP touch | Broker price-side simulation, not mid-price |
| F14 | Stop and target both in same OHLC bar | Tick ordering or indeterminate status |
| F15 | Duplicate or conflicting candidate pairs | Deterministic ID / overlap policy |
| F16 | Excess confirmations eliminate winners | Record rejected-winner counterfactuals |

These are **failure mechanisms worth testing**, not claims that proposed filters will solve them. A historical loss outcome cannot be used as a live prediction at entry.

## 7. Canonical synthetic acceptance fixtures (S1-01..S1-20)

All cases are **synthetic specifications**, not historical market evidence. Every test needs a BUY and mirrored SELL (where meaningful), a decision UTC, exact source side, source/arrival timestamps, rule version, expected state and reason, and negative counterexample.

| Test | Constructed condition | Expected observable behavior |
| --- | --- | --- |
| S1-01 | Unfinished H1 turns UP; last completed H1 DOWN | No S1 BUY READY; no future leak |
| S1-02 | H1 UP, M15 CORRECTIVE, M5 legitimate BUY | M15 correction alone does not veto |
| S1-03 | H pivot has only 1 of 2 right-hand closed M5 bars | H not confirmed; no READY dependent on it |
| S1-04 | Later confirmed H/L pair supersedes FORMING | One active FORMING per side; SUPERSEDED audit event |
| S1-05 | Trigger bar creates slightly deeper wick, depth stays healthy | May READY; no arbitrary 'wick moved P' rejection |
| S1-06 | Pullback crosses 0.75 depth or frozen L/H endpoint | Terminal INVALIDATED, original pair never resurrects |
| S1-07 | M5 wick breaches 2-bar high; close does not | No READY; closed-bar baseline holds |
| S1-08 | First executable quote after M5 close arrives late | MISSED_DATA_GAP; never fictitious bar-close fill |
| S1-09 | Long ASK or short BID already outside first-quote chase bound | MISSED_PRICE_CHASE, not READY |
| S1-10 | READY price leaves then returns to band within TTL | Same signal ID with reversible EXECUTION_BLOCKED overlay |
| S1-11 | Before entry long BID hits stop or short ASK hits stop | Terminal INVALIDATED, no reactivation |
| S1-12 | Bid spread expansion hits long stop; mid chart did not | Respect actual BID and broker trigger convention |
| S1-13 | Short stop would differ if bid high used instead of ask high | Use ASK high + buffer for short SL |
| S1-14 | TP1 touches, TP2 does not, later SL hits | Full-TP2 baseline is losing, no fake 50% TP1 win |
| S1-15 | Operator reports a worse actual fill than E0 | Preserve original proposal; calculate actual R, OFF_PLAN if invalid band |
| S1-16 | SL and TP2 both touched within same unsequenced OHLC minute | INDETERMINATE until tick order known |
| S1-17 | Replay same valid tick stream twice with same config | Identical pivots, IDs, states, original prices and result |
| S1-18 | ATR zero, partial EMA warm-up, wrong precision or stale feed | No actionable READY, explicit reason |
| S1-19 | Most recent M15 pivot is older than provisional 48-bar window | M15 UNKNOWN, no fabricated new level |
| S1-20 | Same frozen pair 'triggers' again after expiry/invalidation | No duplicate new signal without new structural pair |

## 8. Additional adversarial checks (ADV)

These are separate from S1-01..20 to retain important historical failure-study coverage:

- **ADV-01**: A scheduled macro event was **not known** as of the signal's decision timestamp; backtest must not retroactively exclude the trade based on later data.
- **ADV-02**: A **known** high-impact event is approaching and **approved** blackout active; no new READY during that window.
- **ADV-03**: Spread doubles before READY or during valid band; apply declared cost overlay/expiry; do not reuse original cost assumption.
- **ADV-04**: A filter removes 70% of losers but 90% of winners; compare net total R, expectancy, opportunity rate and drawdown, not filter precision.
- **ADV-05**: Signal BUY with BID=4000, ASK=4000.20, stop=3998, target BID=4004.60; later manual ASK=4001.10. Original R 2.20 and gross 2R, actual R 3.10 and potential gross **~1.13R** before fees. No retroactive improvement.
- **ADV-06**: Candidate shows attractive market structure while live feed is disconnected; new signals suspended and open trade monitoring marked unavailable.
- **ADV-07**: Restart with broker position possibly manually closed; operator reconciliation required, no assumed closing fill.
- **ADV-08**: New configuration chosen after inspecting final holdout; label old holdout used, require new untouched final test; do not claim independent validation.
- **ADV-09**: Soft M15 contextual score changes but trade choices stay identical; show **no improvement in realized expectancy** from cosmetics alone.
- **ADV-10**: Same signal IDs on multiple ticks or restart; exactly one persistent READY original, no duplicated gains or exposure.
- **ADV-11**: Strict H1/M15/M5 candle-color unanimity rejects corrective pullbacks; show missed positive-expectancy opportunities and compare soft vs veto.
- **ADV-12**: Different provider/candle/price-side histories; do not assume simulated and live SL/TP have identical broker execution.

## 9. Trial protocol and overfitting safeguards

1. **Freeze** exact formulas, parameter candidates (I0–I8), stop/target exit policy, quote timestamps, cost assumptions, news calendar sources, manual-entry delay scenarios and performance measures.
2. Import/validate data, then select historical windows chronologically. Use rolling/expanding walk-forward splits with gaps if overlapping lookback/outcome windows risk leakage.
3. Run baseline with robust transaction costs and log every trial, including failures and all rejected signals; record reasons at event time.
4. Evaluate one variation at a time, first on development/validation only; report trade counts, sessions, market regimes, and net differences including **rejected winners**.
5. Stress costs, slippage, delays, feed gaps, session/news extremes and mild parameter changes. Look for **stable neighborhoods**, not one perfect setting.
6. Reserve final untouched test and evaluate **once after selection is frozen**. On failure, reject/promote-no further using that holdout; future changes need fresh unseen data.
7. Conduct a representative live paper-trading period before real-capital use, track actual user fill delays and broker divergence. Validation thresholds and minimum sample remain OPEN and must be pre-registered, not invented.
8. Distinguish **offered signals**, **valid eligible signals**, **hypothetically fillable signals**, **actual manually entered trades** and their distinct P/L statistics. No survivorship by only journaling trades a human happened to take.

Do not treat overlapping intraday trades as independent for uncertainty: cluster/bootstrap by session/day and show subgroup sample sizes.

## 10. Mandatory reporting

- Per strategy/version/variant and per regime/session: exact offered/ready/filled/rejected counts, mean/median/worst-period net R, total net R at fixed risk, win rate, average win/loss, profit factor, tail loss and maximum drawdown.
- Timeliness: latency from trigger bar closure to READY and from READY to plausible manual fill; expired/chased signal counts.
- Execution: realized/projected spread in R, slippage, fees, missed fills, stop/target ambiguity and data gap exclusions.
- Selection: rejected losers **and rejected winners**, incremental effect on net R/drawdown, zero-signal days, quality-score calibration *only if explicitly defined*, and uncertainty intervals.
- Reproducibility: version, source/checksum, broker specs, config hash, historical windows, software versions, UTC/DST policy and a precise account of every trial.
- **Replay run identity (R0, docs/14 F-09):** `run_id` hashes code version **and an engine source hash** (`engine_code_hash`: sha256 over the domain, market_data, analysis, strategies, signals, risk packages and `replay/runner.py`, LF-normalized), report version, source, data hash, config hash, strategy/signal parameter hashes, window and cost scenario. Editing engine code without a version bump yields a new run; stored runs are never re-used for different code. `code_version` is stored as `<version>+engine.<hash12>`.
- **Replay window semantics (R0, docs/14 F-10):** `--to` is exclusive on **provider time**; quotes at or after it are not processed, so a simulated exit after `--to` stays `OPEN` with `END_OF_DATA_UNRESOLVED` (never extrapolated). `--from` selects the visible decision window on provider time while earlier quotes are processed as pre-roll. The simulated fill time is reported at the READY quote's **received** time (availability clock) while exit times are reported at the exit quote's **provider** time; reports must not subtract the two as a latency. Gap detection uses provider time. A `DATA_GAP` between fill and exit makes the outcome `INDETERMINATE`. This documents implemented behavior; it changes no rule.

## 11. Acceptance gates, scope and escalation

No claim of "best combo", "90% accurate", profitable backtest or live-trading readiness without real evidence. **Offline REPLAY S1 coding (M04–M06) is allowed after the user's explicit START under [10 — Roadmap](10-roadmap.md), using canonical frozen experimental parameters and synthetic fixture contracts.** An actual broker, live staleness/spread/risk cutoffs and empirical performance thresholds are **NOT** prerequisites for those simulated modules, but they **ARE** prerequisites for publishing broker-verified live price/lot sizing, trade readiness and real-money performance claims. Unknown values remain UNKNOWN; no optimistic fill model.

**No code, tests or historical trading results were executed or produced by consolidating this document.**

## 12. References

Relevant research sources and limitations are in [12 — Research references](12-references.md). Key sources include TradingView's repainting guidance, MetaTrader 5's real-tick testing, Fidelity's ATR guidance, Batten et al. (2018) precious-metals moving-average study, Bailey et al. on backtest overfitting, CME macro-event studies and the World Gold Council's gold OTC/futures market-structure overview. These motivate rigorous tests; none verifies S1 profitability.

## 13. Phase 18 — signal-selection evaluation and quality-score discipline

**Status: TEST PLAN ONLY; not run and not evidence of edge.** Source behavior is the canonical [06 — Signal Engine, Section 10](06-signals-and-scoring.md). All tests must use only as-of-time input and **freeze the candidate and original READY event**, even when later outcomes are known.

### 13.1 Hypotheses to falsify

| Hypothesis | Primary experiment | Rejection criterion |
| --- | --- | --- |
| Raw evidence is sufficient before we have a validated score | Compare S1 eligible signals with/without *display-only* M15/context rubric | Any claim of economic gain when actual trade choices unchanged |
| M15 opposition should veto trades | Soft-context baseline vs veto on **same** S1 entries and costs | Better in-sample loss rate but worse net OOS R, drawdown or opportunity coverage |
| Near opposing structure materially reduces useful target reward | Compare congestion warning vs **pre-signal** structural-target/ranking rule | No robust gain after cost or removes too many attractive winners |
| Stronger M5 trigger improves entries | One close/body rule at a time vs unchanged S1 M5 baseline | Added indicator-like rules merely reduce trade count without net gain |
| Better manual-entry control protects economics | Same signals with measured signal-to-fill delay and frozen vs actual quote/reward | Simulated profits disappear under realistic executable prices |
| Extra ranking adds value when signals truly conflict | Fixed deterministic transparent display vs *pre-registered* quality rank (only if evidence sufficient) | Ranked variant not reliably better or increase drawdown; no forced rank |
| Waiting out temporary initial spread anomalies could help | Original first-quote rejection vs explicitly versioned, bounded pending-trigger recovery | Not robust after time-delay, spread normalization and lost fillability |

**Research sequencing:** Use a single pre-registered indicator baseline (initial candidate I1) for Phase 18. **Do not multiply** every signal-filter trial by all I0–I8 indicator variants or quietly optimize countless combinations on the same dataset. Add one independent experiment at a time; log every attempted configuration. Select a fresh untouched evaluation period when new research uses information from a previous final holdout.

### 13.2 Every setup must leave a reconstructible decision trace

Required test artifact per **unique pivot-pair candidate**, not per tick:
- Candidate identity, source/timeframes and exact as-of-time H1/M15/M5 evidence; detection and first-trigger availability times.
- Original executable quote BID/ASK, strategy plan, approved safety gates and **all** reason-code outcomes.
- Whether it was FORMING, READY, blocked, invalidated, expired, skipped, manually entered, paper-filled or actually closed.
- Subsequent quote updates and block/unblock events recorded separately from **one** original signal.
- Counterfactual outcomes for valid candidates rejected by each experimental soft filter, using **the same** fill/SL/TP/cost assumptions and full versioned strategy definition; label counterfactual, **not an executed or guaranteed trade**.
- Outcome attribution by strategy, real market session, available news context, spread, fill delay, volatility and sample count.
- Clean distinction between **first-issued proposal**, **hypothetical cost-adjusted fill**, and **operator-confirmed realized trade**.

A good experimental filter cannot claim success simply because rejected trades include many losing outcomes. It must account for rejected winners, fillability, market-hours coverage, variance, net return and risk under the same model.

### 13.3 Acceptance fixtures SQ-01 through SQ-18 (synthetic, not executed)

| ID | Fixture / trigger | Expected test assertion |
| --- | --- | --- |
| SQ-01 | S1 H1 UP, M15 CORRECTIVE, completed M5 BUY trigger, good quote and approved execution gates | READY BUY **without** numeric score threshold |
| SQ-02 | Same as SQ-01 but completed M5 trigger absent | FORMING, not READY; evidence says trigger pending |
| SQ-03 | H1 UNKNOWN / quote stale but unusually high hypothetical rubric | NO READY, independent of score |
| SQ-04 | M15 OPPOSING but strategy intact; baseline soft-only variant | Warning/evidence, not automatic veto |
| SQ-05 | M15 OPPOSING, separately *enabled and versioned* strict-veto experiment | No READY; record potential counterfactual if historical fill can be evaluated |
| SQ-06 | Two market updates with same frozen S1 pair and READY | Exactly one signal ID/trade count; preserve immutable issuance |
| SQ-07 | READY briefly leaves bid/ask entry band, later reenters before TTL and stop touch | Same signal resumes, block/unblock audit; no fresh signal or reset expiry |
| SQ-08 | READY underlying structural stop touched before entry | Terminal INVALIDATED, never resurrect same pair |
| SQ-09 | H1 current unclosed bar turns down but last H1 confirmed UP | No future-data contamination or invented H1 flip |
| SQ-10 | Signal looks good at mid price but ASK/BID or contract details unavailable | WAIT/no executable recommendation; reason surfaced |
| SQ-11 | Signal formed on M5 close but next executable quote arrives late/beyond chasing limit | Historical close is **not** counted as filled; MISSED reason |
| SQ-12 | Score changes only on screen, identical eligibilities and fills | **Identical trade P/L and counts**; no claimed economic improvement |
| SQ-13 | Hard gate fails but a fictitious score is >90/100 | Hard gate wins, no READY |
| SQ-14 | Two overlapping/contradictory valid opportunities and no approved exposure policy | Explicit conflict/review; no invented "best" or compounded position |
| SQ-15 | Score feature is missing M15 context but safety inputs remain valid | Evidence UNKNOWN; no silent zero or manufactured probability; soft unknown not an unapproved veto |
| SQ-16 | Cost/spread/entry-condition temporary failure on **first post-trigger quote** | Under original baseline NO READY; experimental recovery must be separately versioned, with no backdated issuance |
| SQ-17 | First quote initially expensive, transient condition clears within experimental bounded grace | Recovery variant may issue **new first** READY at actual valid quote time if all original frozen constraints still pass; never use blocked historical quote as a fill |
| SQ-18 | New quality rule lowers loss fraction but eliminates a larger net-positive subset of available trades | Reject as unproven improvement when net OOS expectancy/total return/frequency deteriorates |

Each fixture must cover direction reversal, timestamp/expiry boundary and broker-side price convention where relevant. **Tests are documents only until Grok is explicitly authorized to implement them.**

### 13.4 Score design and calibration experiments (future)

- A proposed 100-point quality rubric is **not** an estimated probability. Do not implement numerical display if scoring axes lack frozen sub-feature equations, weights, normalization, missing-data policy and versioned cutoffs.
- If a score is later used to *rank* trade opportunities, predefine exactly which trade would be selected versus a no-score baseline; replay both with identical quote availability, fills and costs. A mere new sort order with no changed executions has no performance impact.
- If a true event probability is researched, first define the binary outcome (e.g. **full TP2-before-SL** under an immutable tested exit policy), eligibility universe and sample inclusion. Use chronological training, independent calibration, truly untouched evaluation, reliability diagrams, bin counts and confidence intervals; include net R because even calibrated accuracy does not equal positive expectancy. **No probability** in UI until credible independent calibration and forward paper-trading.
- Samples from adjacent intraday trades are dependent. Avoid misleading narrow confidence intervals from treating tick observations or overlapping trades as independent; stratify/block by day or session, report distribution of outcomes and regime shifts.

A typical calibration definition is: among forecasts claiming around 0.8 for a precisely defined event, that event should occur around 80% of the time in comparable **unseen** observations. That *illustrates* calibration, not a Grog result. Reference: [scikit-learn Probability calibration](https://scikit-learn.org/stable/modules/calibration).

### 13.5 Required Phase 18 report before promoting a change

Report (a) offered candidates vs unique valid READY vs realistically fillable signals, (b) net R per fill, total net R under equal risk and drawdown, (c) winners and losers removed by every veto, (d) number of eligible trades/day and days with zero opportunity, (e) spread, quoted-vs-actual entry lateness, target feasibility and market regime, (f) uncertainty and untouched evaluation period, and (g) code/data/settings version plus all negative tests.

**Promotion rule (qualitative until data supports numeric approval):** accept only if a change creates a demonstrable *out-of-sample* improvement in executable net economics or risk stability while preserving an agreed practical opportunity rate, including a forward-paper sample. A lower loss fraction, a higher nominal quality score or a marketing win-rate claim is **not** enough. No hidden feature-growth or live-account automation.

**External research notes:** [Bailey et al. on backtest overfitting](https://scholarworks.wmich.edu/math_pubs/42/) and [scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration) explain risks in selecting overfit strategies and interpreting probability claims. Neither validates an S1 trading edge or tells us an optimal ranking threshold.


## 14. Market-data and execution-source acceptance — 2026-10-31

**RESEARCH / TEST SPECIFICATION. No feed, external service or broker has been connected, and no test has been executed.** The canonical data contract is [03 — Market Data](03-market-data.md); SL/TP and P/L conventions are [07 — Risk & Monitoring](07-risk-and-monitoring.md). Do not create a second feed adapter or add more indicators as a substitute for price-data correctness.

### 14.1 Three evaluation stages (must remain distinct)

1. **Broker-neutral offline importer/replay** — synthetic fixtures plus permitted historical BID/ASK (e.g. Dukascopy once verified); establishes deterministic parsing and calculations **without a broker account**. It is **not** proof of broker-matched execution.
2. **Chosen broker data trial** — read-only demo source, XAUUSD symbol metadata, measured quote continuity/latency, spread profile, full MTF aggregation and restarts; verify limitations transparently. A reliable real-time source is required for actual signal monitoring.
3. **Broker-matched historical and forward cost validation** — true ordered bid/ask ticks and realistic manual-entry timing. Evidence from another broker remains labeled **PROXY**, not a confirmed live outcome. Only after source integrity and cost validity can S1 performance studies be meaningful.

**Pass criteria are operational, not profitable-trading criteria.** A feed PASS must never promote S1 to VALIDATED or authorize real-money use.

### 14.2 Synthetic feed and time fixtures MD-01..MD-22

| Test | Scenario | Required assertion |
| --- | --- | --- |
| MD-01 | Multiple distinct quotes share identical source millisecond | Retain all by stable event sequence/index; no timestamp-only dedup |
| MD-02 | Replayed range overlaps previous batch at inclusive boundary | Exact prior retransmissions idempotent, distinct same-ms updates kept |
| MD-03 | BID changes, ASK unchanged per source flags | Carry forward last known ASK with provenance; don't invent identical BID/ASK |
| MD-04 | ASK < BID or <=0 quote | Invalid source quote quarantined, no READY from invalid tick |
| MD-05 | Clock offset changes or provider time ahead of receipt | Log skew, no negative fictitious latency or fake freshest status |
| MD-06 | Local receive timestamp after candle interval end | Bar finalized only on actual subsequent valid event; no backdated READY |
| MD-07 | New H1/M15 bar is unfinished while M5 trigger closes | Only last finalized H1/M15 used, no higher-timeframe future leakage |
| MD-08 | Several quote gaps during known active session | Flag affected intervals; block new READY until data integrity restored |
| MD-09 | Market is legitimately closed with no tick updates | Show CLOSED/OFFLINE distinction using broker hours + heartbeat, not necessarily a false feed outage |
| MD-10 | App reconnects, fetches pre-disconnect historical ticks | Mark BACKFILL; repair research history, **no retroactive live entry alert** |
| MD-11 | MT5 callback coalescence during busy handler | Bounded CopyTicksRange catch-up yields detected count/coverage or explicit irrecoverable-gap flag |
| MD-12 | cTrader tick response hasMore and partial window | Retrieve complete permitted chunks with paging/backoff, not falsely mark completed |
| MD-13 | Two sources report same XAUUSD with different spreads/prices | Keep source labels; never merge into synthetic "universal broker" quotes |
| MD-14 | XAUUSD broker symbol suffix/digits/tick_size changes | Metadata version invalidated/reloaded; no old tick rounding or sizing |
| MD-15 | Broker profit currency != trader reporting currency | Require valid conversion or show native profit currency only, no guessed exchange rate |
| MD-16 | Bid/ask-price entry and close already contain spread | Net P/L subtracts distinct commissions/slippage **once**, not spread twice |
| MD-17 | Long stop touched by BID only, short stop touched by ASK only | Assess broker-side touches independently; do not use midpoint |
| MD-18 | Both stop and TP within one OHLC bar, order not known | INDETERMINATE, never optimistic win without ordered ticks |
| MD-19 | Quote exporter crashes mid-batch and restarts | Recover from durable cursor/checkpoint without silent data loss or repeated unique market signals |
| MD-20 | Bar construction crosses broker rollover, weekend or US DST transition | UTC intervals remain correct; session hours/gaps interpreted from broker/IANA metadata |
| MD-21 | Last M5 close exists but first new quote arrives past measured latency tolerance | No fictitious earlier price or READY; MISSED_DATA_GAP |
| MD-22 | Two independent replays use identical raw source, broker metadata and adapter config | Bit-for-bit equivalent normalized stream/candles/decision eligibility (within explicitly stated serialization precision) |

Each fixture requires provenance timestamps, exact synthetic ticks, expected rejection/normalization reason codes, negative counterexample and buy/sell price-side coverage where relevant. Test initial cases and failure cases **before** any market-strategy performance analysis.

### 14.3 Feed-candidate research scorecard — avoid arbitrary weighted score

Record evidence, **not** a marketing-style 90/100 provider rating:

| Area | Result field | Minimum evidence for a candidate to be considered |
| --- | --- | --- |
| Execution matching | MATCHED / PROXY / UNKNOWN | Same broker/instrument that would execute user's manual trades, or clearly labeled alternative |
| Data fidelity | FULL BID_ASK / PARTIAL / BARS_ONLY | Ordered executable-side quote history plus precision and coverage metadata |
| Timeliness | PASS / CONDITIONAL / FAIL | Observed source/receipt latency distribution, disconnect/reconnect behavior, quote-age UI |
| Recovery | PASS / CONDITIONAL / FAIL | Reconnect catch-up/no duplicates or an explicit DATA_GAP failure state |
| Contract accuracy | PASS / CONDITIONAL / FAIL | Lot min/max/step, tick size/value, contract/profit currency, trading hours, stop mechanics |
| Economics | VERIFIED / ESTIMATED / UNKNOWN | Spread by session, commission and execution assumptions with timestamps |
| Integration complexity | LOW / MEDIUM / HIGH | Ubuntu runtime, credentials/permissions, recoverability, maintenance |
| Legal/data rights | OK / RESTRICTED / UNKNOWN | Explicit allowed data access and storage use |
| Read-only safety | PASS / FAIL | No call path that submits, modifies or closes a broker order |

**Decision 2026-10-31:** MT5+Wine and a minimal read-only exporter are the **preferred reference-feed integration**, independent of which broker the user eventually trades. This does **not** mean a specific MT5 demo server or data source has been approved or connected. A broker-neutral offline importer/replay is the first engineering step and is not blocked on broker selection. cTrader is a future fallback, **not a parallel build**; Dukascopy may support legally permitted offline research but cannot establish execution-broker realized spreads or slippage.

### 14.4 Execution-cost experiment protocol

For the *same frozen S1 signals*, compare:
- Original idealized M5 close (diagnostic **unexecutable reference**, never published as performance)
- First valid post-confirmation ASK/BID (replay baseline)
- Actual delayed manual-entry quote (predefined delay windows)
- Moderate/extreme widening spread, nonzero commissions, stop slippage and no-fill assumptions
- Alternative broker-specific contract profiles **only if explicitly available**, labeled separately

Report distributions of spread in price/R units, manual-delay lost R, offered vs fillable signals, unknown SL/TP event ordering, fee/currency data coverage, net expectancy and rejected winning opportunities. A gross 2R output **does not imply** 2R executable after costs.

**Beware spread double-counting:** BID/ASK execution already contains the spread. Never add a separate full-spread charge on top of those execution-side prices. Report spread as a diagnostic and other distinct fees/slippage separately.

### 14.5 Preflight handoff boundary to Grok

When the user explicitly authorizes the offline R0 build, Grok may complete **M00–M08** in order under [10](10-roadmap.md), including the **simulated research S1 engine** once its independent data/analysis prerequisites pass. This does **NOT** authorize a live broker connection, unapproved EA, Wine/MT5 installation, proprietary dataset access, live credentials, broker orders or any claims of strategy profitability. Build only the read-only abstraction until M09 is separately approved.

**Reference documentation:** MT5 `CopyTicksRange` and `OnTick` event semantics, cTrader historical quote data + `hasMore`, Dukascopy historical BID/ASK widget, MQL5 symbol properties, and MT5 real-vs-generated ticks. Cite links in [12 — References](12-references.md). These prove API capabilities/limitations, **not** S1 trade profitability.

## 15. R0 implementation acceptance: CLI, terminal, journal and persistence

**Status: SPECIFIED, NOT EXECUTED.** Complements MD-01..22, S1-01..20, SQ-01..18, ADV and I0-I8. Use Python 3.11, isolated pytest `tmp_path`, synthetic XAUUSD BID/ASK and virtual UTC clock. Textual's `App.run_test()` and `Pilot` support keyboard/responsive tests: https://textual.textualize.io/guide/testing/

### 15.1 CL-01..CL-12 — CLI and data

| Case | Input / operation | Required result |
| --- | --- | --- |
| CL-01 | Fresh checkout with resolved `uv.lock` | Locked install and CLI help/version work |
| CL-02 | `grog doctor` with empty test state | Read-only, no broker/network |
| CL-03 | Valid CSV with distinct same-millisecond quotes | Correct event count/order/Decimal prices |
| CL-04 | Reimport identical source and SHA256 | Idempotent, no duplicate batch |
| CL-05 | Missing header, NaN, negative BID, crossed quote, bad UTC ms | Clear row/field error, no partial commit |
| CL-06 | Identical quotes from two source IDs | Kept distinct, never merged |
| CL-07 | Single invalid row inside valid batch | Strict whole batch reject |
| CL-08 | Import crashes before transaction commit | Retry/recovery without phantom batch |
| CL-09 | Identical replay/config twice | Same signals/events and deterministic result |
| CL-10 | Report nonexistent run ID | Explicit NOT_FOUND, nonzero exit |
| CL-11 | Naive timestamp/unknown command or mode | Clear validation error, no guessed timezone |
| CL-12 | Live reference command without MT5 connection | NOT_CONFIGURED, not fabricated live prices |

### 15.2 UI-01..UI-22 — Textual UX

| Case | Input / action | Expected behavior |
| --- | --- | --- |
| UI-01 | 120x34 REPLAY screen | Five views, quote/context/forming/ready/positions readable |
| UI-02 | 80x24 screen | Responsive stacking and signal detail SL/TP accessible |
| UI-03 | 70x18 screen | Scroll/resize guidance, no corrupted critical state |
| UI-04 | Press 1..5/arrows while market data updates | Correct focus/navigation and retained selection |
| UI-05 | Help ?, Esc, Enter | Safe overlay and detail, no journal mutation |
| UI-06 | Type e/s/p/m/x into focused input | No global shortcut activated |
| UI-07 | Try Record Entry on FORMING candidate | NOT TRADABLE YET, no on-plan local entry |
| UI-08 | H1 UP/M15 CORRECTIVE, M5 trigger missing | FORMING, exact reason |
| UI-09 | Simulated READY BUY/SELL | Correct ASK/BID entry, SL/TP sides, TTL, SIMULATED |
| UI-10 | Read-only MT5 reference connected later | INDICATIVE, verify actual broker, never falsely verified |
| UI-11 | Quote stale/gap/ATR history insufficient | UNKNOWN/NO TRADE, no invented score |
| UI-12 | Current H1 bullish but last confirmed H1 bearish | Last confirmed used, provisional labeled |
| UI-13 | READY blocked and restored before expiry | Same ID/original prices/TTL |
| UI-14 | Original stop touched or TTL expired | Terminal invalidation/expiry, no resurrection |
| UI-15 | Record-entry modal | Mandatory actual fill/time/size, Cancel default and risk preview |
| UI-16 | Partial close quantity exceeds remaining | Reject, DB unchanged |
| UI-17 | Confirm local manual closure | Only journal updated; no broker action |
| UI-18 | App restart with recorded open position | RECONCILIATION_REQUIRED |
| UI-19 | REPLAY ended or paused | Virtual last UTC time, not false live feed |
| UI-20 | Quit with recorded open position | Explain broker order is untouched, persist state |
| UI-21 | Trader records a manual XAUUSD entry unrelated to READY or after expired plan | Explicit OFF_PLAN local record, optional historical signal link, no signal resurrection or broker order |
| UI-22 | REPLAY starts paused after causal pre-roll; press Space, . and +/- controls | Events progress in order, confirmed lookback valid, UI pace does not change outcomes or current wall-clock statuses |

### 15.3 ST-01..ST-15 — Persistence, costs and recovery

| Case | Condition | Required invariant |
| --- | --- | --- |
| ST-01 | New local SQLite schema | Versioned migrations, foreign keys, no wallet/orders tables |
| ST-02 | Same candidate/trigger replayed | One original READY signal/issuance event |
| ST-03 | READY blocked/unblocked | E0/SL/TP/TTL immutable |
| ST-04 | DB write fails mid-position transaction | No partial position change or false UI success |
| ST-05 | Duplicate user event submission | Idempotent event ID |
| ST-06 | Recorded entry reloaded after restart | Reconciliation required |
| ST-07 | Partial closes and fees | Remaining size/realized costs correct |
| ST-08 | True ASK/BID trade path | Spread charged once, commissions separate |
| ST-09 | Broker contract missing | Gross price R in SIMULATED; currency P/L UNKNOWN |
| ST-10 | Synthetic fixture tick size 0.01 | Correct rounding, never treated as real broker size |
| ST-11 | Market source changes | Original source attribution preserved |
| ST-12 | Two events with identical ms | Both retained in ingest order |
| ST-13 | Reconnect backfill | No retrospective LIVE READY |
| ST-14 | Same closed M5 bar reprocessed | No duplicate pivot or signal |
| ST-15 | Additive SQLite schema migration | Historic events preserved |

### 15.4 R0-ACC — operator acceptance (added by the R0 audit, [14](14-r0-acceptance-audit.md))

Executed over the deterministic SYNTHETIC fixture through the real CLI import and the REPLAY workstation, with thresholds from `config/synthetic-demo.fixture-only.toml` (demo/test-only, never a real-feed value). Files: `tests/acceptance/test_r0_operator_journey.py`, `tests/acceptance/test_r0_error_paths.py`; layout: `tests/ui/test_r0_layout.py`, `tests/ui/test_r0_views.py`.

| ID | Case | Expected |
| --- | --- | --- |
| ACC-01 | Journey: import → FORMING → READY → detail → record entry → economics → monitoring mark → partial → modify stop → close → unlinked OFF_PLAN fill → skip next READY → re-press shows "already USER_SKIPPED" → restart → RECONCILIATION_REQUIRED → confirm open → MONITORING | append-only position events in sequence; exactly one first operator action per signal; no order/broker/wallet tables; imported market files byte-identical |
| ACC-02 | Missing/invalid price, NaN, negative, quantity 0 / negative | `NOT SAVED`, nothing persisted, form stays open |
| ACC-03 | Duplicate confirm; second entry/skip on an entered signal | one position; overlay "already ENTERED" |
| ACC-04 | Late/out-of-band entry | OFF_PLAN with `OUTSIDE_ENTRY_BAND`; immutable signal plan unchanged |
| ACC-05 | Default config (thresholds unset) | feed UNKNOWN, `STALE_THRESHOLD_UNSET`, no READY, marks flagged UNVERIFIED |
| ACC-06 | Injected DB failure after event insert | `NOT SAVED`, zero rows; retry of the same form saves exactly once |
| ACC-07 | Replay end | `REPLAY ENDED`, mark not fresh, stepping adds no quote |
| ACC-08 | Insufficient history | `INSUFFICIENT HISTORY` banner, no READY, Diagnostics `[ERROR]` |
| ACC-09 | 70×18 terminal | resize notice; keyboard entry still recorded; modal opens at identity with Cancel focused |
| ACC-10 | Typing in any modal field | never triggers a view/record hotkey |

### 15.5 REF — M09-A reference adapter, offline (recorded-format FIXTURE files only)

Files: `tests/unit/test_reference_format.py`, `tests/integration/test_reference_feed.py`, `tests/integration/test_reference_session.py`, `tests/integration/test_reference_cli.py`, `tests/unit/test_reference_safety.py`, `tests/unit/test_replay_identity.py`; fixture `tests/fixtures/reference/`. Covers MD-11/12/19/22 offline. **Nothing here proves behavior of a real MT5 terminal.**

| ID | Case | Expected |
| --- | --- | --- |
| REF-01 | Record parsing | exact Decimal prices from text, precision ≤ digits, strict arity/fields, codes for every rejection |
| REF-02 | UTC conversion | `time_msc − server_offset`; an offset change applies forward only **and** latches `OFFSET_CHANGED` (history across an offset change blocks READY) |
| REF-03 | Several ticks in one ms, incl. identical content | all kept, distinct keys (occurrence index) |
| REF-04 | BID-only / ASK-only updates | other side carried with `*_CARRIED` flag; unknown side held out (`SIDE_UNKNOWN`) |
| REF-05 | Invalid, crossed, non-quote, duplicate (catch-up overlap), out-of-order | rejected with code and counted; never fed to the engine |
| REF-06 | Torn line, rotation, missing `Z`, sequence gap | complete lines only; `PARTIAL_LINE_DISCARDED`, `FILE_ENDED_WITHOUT_Z`, `TRANSPORT_SEQ_GAP` counted **and latched as integrity faults** (link `INTEGRITY_FAULT`) |
| REF-07 | Restart / crash before commit | every tick after the committed cursor delivered exactly once; engine warmed up from retained files |
| REF-08 | Backfill vs live | catch-up, late backlog, startup backlog (fence) and unset freshness ⇒ BACKFILL; READY from BACKFILL never actionable |
| REF-09 | Timer-driven link/feed | OFFLINE / STALE without any new tick; DISCONNECTED; MARKET_CLOSED; CATCHING_UP; UNKNOWN when heartbeat threshold unset; NO_DATA |
| REF-10 | Engine compatibility | live READY plan identical to the REPLAY pipeline on the same ticks; replay engine hash and config hash unaffected |
| REF-11 | No journal / no trade API | prices create no journal record (DB bytes unchanged); runtime imports no journal/broker module; Python + MQL5 scan for order/position/account mutation calls is empty |
| REF-12 | NOT_CONFIGURED / labels | no `[reference]` ⇒ `NOT_CONFIGURED` in CLI and UI; fixture files read `FIXTURE · SIMULATED`, never `REFERENCE · INDICATIVE`; never broker-verified |

### 15.6 M09-H — integrity hardening (offline, H1–H4)

File: `tests/acceptance/test_m09_integrity.py` (ported from the read-only review's scratch repros: each failed before its fix). Producer-byte fixture: `tests/fixtures/reference_producer_bytes/`. **Offline only — MT5 runtime behavior stays UNVERIFIED (M09-B).**

| ID | Defect / case | Expected |
| --- | --- | --- |
| REF-13 | Producer bytes: CR LF, code page, `FILE_TXT`/`FILE_ANSI` in the exporter | exporter source writes binary UTF-8 + LF; CR LF and non-UTF-8 lines rejected (`BAD_LINE_END`/`BAD_ENCODING`) and latched; the documented producer-byte fixture passes end to end |
| REF-14 | Inclusive `CopyTicksRange` windows | exporter windows `[a, b−1]` (source check); identical re-delivery at a block start dropped; genuine identical same-ms live tick after a block kept (exact count and order) |
| REF-15 | Failed / partial history | `G` record and `E` count mismatch latch `SOURCE_GAP` / `CATCHUP_COUNT_MISMATCH`; never marked complete; exporter retries then emits `G` (source check) |
| REF-16 | Writes and watermark | exporter checks every write, saves the watermark atomically and never past unwritten data; same-second restart never reuses a file name (source checks); truncated / replaced / missing cursor file ⇒ fault |
| REF-17 | Time boundary | future provider time never LIVE; offset change and catch-up before the first offset observation flagged/latched; `TIME_BASIS_UNVERIFIED` and `FUTURE_SKEW_TOLERANCE_UNSET` block actionable READY |
| REF-18 | Metadata | changed server/symbol/digits/producer, malformed META and source mismatch reject the file's records and latch a fault; no inheritance of an earlier file's META |
| REF-19 | Integrity link state | sequence gap / unexpected EOF ⇒ link `INTEGRITY_FAULT`, nothing actionable |
| REF-20 | Side semantics | unchanged-flag side with a contradicting value ⇒ `SIDE_INCONSISTENT` fault |
| REF-21 | Fixture lane | FIXTURE READY never actionable; shown only in the simulated lane |
| REF-22 | Recovery | warm-up RECONSTRUCTED and historical; startup fence; corrupt cursor ⇒ `CURSOR_CORRUPT`; second writer ⇒ `CURSOR_LOCKED` |
| REF-23 | Bounded ingestion | streaming reader; RSS ceiling on a large synthetic file; idle polls write nothing |
| REF-24 | UI-R1 | a triggered candidate with an issued signal is not listed again as FORMING |

**Measured ingestion (2026-10-31, this box, synthetic FIXTURE catch-up file, one `B…E` block, Python 3.11).** Before = `667d8ef` reader (whole remainder read + event list); after = M09-H streaming reader.

| Lines (file size) | Path | Before: time · throughput · peak RSS | After: time · throughput · peak RSS |
| --- | --- | --- | --- |
| 200 k (8.5 MB) | reader | 2.9 s · 69 k lines/s · 219 MiB | 2.3 s · 86 k lines/s · 38 MiB |
| 1 M (43 MB) | reader | 15.2 s · 66 k lines/s · 992 MiB | 12.2 s · 82 k lines/s · 39 MiB |
| 2 M (87 MB) | reader | 31.0 s · 64 k lines/s · 1 958 MiB | 23.6 s · 85 k lines/s · 39 MiB |
| 1 M (43 MB) | session incl. S1 pipeline | 25.6 s · 39 k lines/s · 993 MiB | 25.9 s · 39 k lines/s · 44 MiB |
| idle timer poll | session | 7 ms, rewrote an 820 KB cursor with fsync each poll | 0.04 ms, no write |

The RSS ceiling test (`test_large_history_is_streamed_with_bounded_memory`, 400 k lines in a subprocess, ceiling 200 MiB as an engineering guard) measured 514 MiB before and 39 MiB after.


## 16. Milestone-to-test acceptance matrix

| Milestone | Case groups | Mandatory evidence |
| --- | --- | --- |
| M00 | CL-01/02/11 | locked install, CLI, local lint and tests |
| M01 | CL-03..08, MD-01..05/13/14/19 | import/checksum/idempotency |
| M02 | MD-06..10/17/20/21/22 | exact causal 4-timeframe bars and gaps |
| M03 | S1-01..03/17..19 | EMA/ATR/pivot numeric and causal proofs |
| M04 | S1-01..07/17..20 | S1 frozen pair and state trace |
| M05 | S1-08..16, SQ-01..18, ST-02/03/09/10 | first executable quote, zero fake confidence |
| M06 | CL-09/10, MD-18, ADV-04/08, ST-11..14 | identical replay, cost caveats |
| M07 | UI-01..14/19/20/22 | Textual Pilot and small terminal tests |
| M08 | UI-15..18/20/21, ST-01..08/15 | safe local journal/reconciliation |
| R0 acceptance | ACC-01..10 | executed; counts in [14 §5](14-r0-acceptance-audit.md) |
| M09-A | REF-01..12 | offline adapter on FIXTURE files (executed) |
| M09-H | REF-13..24 | offline integrity hardening (executed); MT5 behavior UNVERIFIED |
| M09-B LATER | MD-11/19, CL-12, UI-10, [10 §9](10-roadmap.md) acceptance | user-approved read-only demo connection |
| M10 LATER | I0..I8, walk-forward and paper trial | independent empirical results |

**R0 PASS** means an offline program passes specified functional tests under documented synthetic/proxy assumptions. It does **NOT** establish profitable S1 signals or verified broker fills. Documented cases are not executed test results: Grok must create tests, run them and report actual pass/fail counts and commit SHAs as required by [10](10-roadmap.md).

## 17. Pre-registered research questions (not runtime options)

### RQ-H1 — H1 invalidation while READY

- **Baseline (runtime, PROVISIONAL):** H1-STRICT ([05 §8](05-strategies.md)) — a newly confirmed H1 bar with any bias other than the side's required bias (NEUTRAL, UNKNOWN or opposite) invalidates READY.
- **Alternative (research only):** H1-OPPOSITE — only a newly confirmed *opposite* H1 bias invalidates; NEUTRAL/UNKNOWN keep READY until TTL or another terminal rule.
- The alternative is never selectable in the workstation or live session. It may only be evaluated offline as a counterfactual over the same READY set, under the M10 comparison protocol (§18), on real permitted BID/ASK data. No result is claimed.

## 18. M10 research readiness — protocol structure (no data downloaded, no result claimed)

Status: **STRUCTURE DEFINED, every numeric value OPEN for the owner.** Nothing in this section has been executed. No new indicator or strategy is introduced; the only S1 variant under comparison is RQ-H1 (§17). Synthetic data are used for software tests only and are **never** used to fit or choose a parameter.

### 18.1 Real BID/ASK dataset quality checks (run before any evaluation)

| Check | Measure (reported, never silently repaired) | Pass rule |
| --- | --- | --- |
| Provenance | source, server, symbol, licence/permission, export tool and version, file sha256 | recorded, permission explicit |
| Schema | strict CSV v1 / `GROG-MT5-REF/1` import, zero unexplained rejects | rejects listed by code |
| Time | UTC conversion method and server offset history (DST), monotonic provider time, provider-vs-receipt skew | offset documented per period |
| Both sides | share of ticks with BID and ASK present; carried-side share | threshold OPEN |
| Integrity | crossed, zero/negative, duplicate keys, same-ms multiplicity, out-of-order | counts per day |
| Spread | distribution per hour/session and around rollover | reported; limit OPEN ([11 §6](11-decisions.md)) |
| Gaps | M1 DATA_GAP vs declared MARKET_CLOSED, longest gap, gaps inside READY/position intervals | affected signals INDETERMINATE |
| Density | ticks per minute per session; abnormal bursts/spikes flagged (not deleted) | reported |
| Coverage | calendar span, regimes (trend/range, high/low volatility by ATR terciles of the dev window) | each window non-empty |
| Cross-check | overlap with the M09 reference feed (if both exist): price/spread differences | reported |

### 18.2 Manual entry-delay scenarios

Replay currently models only `D0 = ZERO_DELAY_AT_FIRST_QUOTE`. M10 adds explicit scenarios, each a separate report (never averaged into one number):

| Scenario | Entry rule | Parameter |
| --- | --- | --- |
| D0 | first executable post-trigger quote (current) | — |
| D1 | first quote at or after READY + `d1` | `d1` OPEN (owner) |
| D2 | first quote at or after READY + `d2` (> `d1`) | `d2` OPEN |
| D-obs | empirical delays from the operator journal (forward paper) | measured, not assumed |

A delayed entry outside the frozen band or after TTL is `MISSED` (not filled); fills use the executable side (BUY ASK, SELL BID).

### 18.3 Broker-specific fee and spread modeling inputs

Required per named venue before any net figure: contract size, trade tick size and tick value (from read-only `SymbolInfo*`), volume step/min, commission per lot round-turn, swap/financing rule, stop/freeze level, and slippage scenarios (OPEN). The observed BID/ASK spread is already in the fills and is **never** charged again. Missing input ⇒ net R and currency `UNKNOWN`, gross only.

### 18.4 Development, validation and untouched test windows

Chronological, non-overlapping, declared with exact UTC boundaries **before** any outcome is computed: development (walk-forward folds inside it), validation, and a final untouched test window evaluated **once** after all choices are frozen. An embargo of at least one TTL plus maximum holding time separates windows (length OPEN). Window boundaries, fold count and minimum span are OPEN for the owner.

### 18.5 Objective comparison: H1-STRICT baseline vs H1-OPPOSITE (RQ-H1)

- Same data, costs, delay scenario and READY set; H1-OPPOSITE evaluated as a counterfactual on the signals H1-STRICT invalidated.
- Paired per-signal outcomes; report count, net expectancy (R), dispersion, max drawdown (R), longest losing run, and how many extra signals each rule creates or removes.
- Decision rule (pre-registered): adopt the alternative only if on **validation** it improves net expectancy by at least `ΔE` with drawdown no worse than `ΔDD`, and the result holds on the untouched test window; otherwise H1-STRICT remains the baseline. `ΔE`, `ΔDD` OPEN.

### 18.6 Pre-registered net-expectancy and drawdown criteria (values OPEN)

| Criterion | Definition | Value |
| --- | --- | --- |
| Minimum sample | evaluable READY signals per window | OPEN |
| Net expectancy | mean net R per signal; lower bound of a pre-declared confidence interval | OPEN |
| Max drawdown | peak-to-trough cumulative net R | OPEN |
| Losing run | longest consecutive net losses | OPEN |
| Robustness | share of walk-forward folds with positive net expectancy | OPEN |
| Cost sensitivity | expectancy with spread/commission stressed by a declared factor | OPEN |
| Delay sensitivity | criteria re-checked under D1/D2 | OPEN |

All criteria are fixed in this document (dated commit) before the validation window is evaluated. Failing any criterion ⇒ S1 stays EXPERIMENTAL / UNVALIDATED.

### 18.7 Forward-paper monitoring

Requires M09-B (authorized reference feed). For a pre-declared period (OPEN): every READY is journaled as ENTERED (paper) or USER_SKIPPED with reason; record actual delay and the reference prices at entry/exit; weekly report comparing forward vs validation distributions (count, net R, drawdown, delay, spread). Stop rules (OPEN): drawdown breach, feed-quality failure rate, or criteria drift ⇒ pause and report. Paper results are labelled PAPER/INDICATIVE, never broker-verified or live-money results.

## 19. Native desktop GUI acceptance cases (2026-11-07)

Qt UI tests are separate from trading-strategy performance claims. The probe is not a functional workstation.

| ID | Scenario | Required outcome |
| --- | --- | --- |
| GUI-01 | Qt unavailable | Existing CLI/TUI unaffected; safe error, no persisted changes |
| GUI-02 | Qt probe | Offscreen/native widgets initialize and close without market/journal access |
| GUI-03 | Number display | Decimal digits/trailing zeros preserved; no implicit rounding or unknown=0 |
| GUI-04 | Overview | No trade/forming/ready/blocked match the same engine snapshot and source |
| GUI-05 | Replay | Same ordered events, signal IDs, timestamps and prices as Textual/R0 |
| GUI-06 | Journal | Entry/skip/partial/modify/close/unlinked and restart reconcile persist correctly |
| GUI-07 | Stale dialog | Changed/terminal/used signal never silently records on-plan |
| GUI-08 | Threading | Widgets only touched in GUI thread; no dropped input/event ordering |
| GUI-09 | Usability | Resolution, DPI, keyboard, errors, empty states and precision verified visually |
| GUI-10 | Cutover | `gold` changes only after full parity and owner approval; TUI retained |

D00 can verify pure formatter tests here. GUI-02 remains **PENDING formal acceptance**: the owner reports an ephemeral PySide6-Essentials 6.11.3 launch on Ubuntu, but Qt in a regenerated project lock, reproducible offscreen smoke and the current GUI regression suite remain unverified.

## 20. Complete native desktop acceptance matrix and verification protocol (2026-11-07)

**Status:** This is the **original D00–D05 functional acceptance contract**, written before those phases were implemented by `c0ef834`. It remains binding as a regression suite for owner-approved U0–U5 visual redesign; [§21](#21-desktop-uiux-v2-additional-acceptance--owner-approved-2026-11-07) adds theme/readability cases. See [02 §16](02-workflows-and-ux.md), [09 §13](09-architecture.md) and [10 §13](10-roadmap.md). GUI-01..10 (§19), GUI-11..62, R0 UI-01..22, ST-01..15, M09 reference fixtures and R0-ACC remain mandatory. Prior test claims are historical evidence, **not substitutes for fresh tests in each U-phase**.

### 20.1 Deterministic test harness rules

- Use the existing synthetic replay fixtures and `tests/ui_support.py`; compare **same source ID, same policy/config hash, same pre-roll window and same ordered normalized quotes** through desktop and Textual read models. Assert raw Decimal equality and integer UTC-millisecond equality before formatted text equality. Use both BUY and SELL, high-precision and trailing-zero examples, at least two independent source IDs and one same-provider-millisecond multi-quote input.
- For GUI tests, set `QT_QPA_PLATFORM=offscreen` before creating `QApplication`; `QApplication` must be created exactly once per process and disposed cleanly. Offscreen tests do **not** replace the required **visible native Ubuntu GNOME** launch. Test QThread signal delivery with `QSignalSpy`/event loop waits or equivalent bounded deterministic synchronization, **not** sleeps with arbitrary timing assumptions.
- Use disposable temporary state dirs and one authorized test journal per fixture; no real broker, MT5/Wine terminal, network feed, credentials or production server. Never use `/tmp/grog-demo` as a test that can modify the user's own demo state unless the test creates/owns it. Inject test clock and temporary SQLite connections; close each worker/thread.
- Under faults, verify **no inserted/changed row**, correctly preserved action_id on retry, exact error notice, and equivalent state after restart. Inspect DB outputs via existing service/test helpers, not GUI SQL. Assert **no Qt import or broker execution API** on core CLI/TUI path.
- Full suite for each implementation phase: targeted pytest cases, all relevant R0 regression cases, `uv run ruff check .`, `uv run ruff format --check .`, and report exact commands/pass/fail/skip count. Before D05: `uv run pytest -q` full project, including optional Qt-enabled tests under resolved desktop extra. Qt tests skipped due to missing optional dependency **do not** count as a desktop acceptance pass.

### 20.2 Foundation, numeric fidelity and replay (D00–D01)

| ID | Fixture/action | Pass criterion |
| --- | --- | --- |
| GUI-11 | Import package with no Qt extra; run `grog --help`, `grog doctor`, `grog ui` test harness | No Qt import or missing-module crash on existing CLI/TUI paths; default installation stays Textual |
| GUI-12 | Actually resolve optional Essentials extra then `uv sync --locked --extra desktop`; probe offscreen and normal GNOME | `pyproject.toml` and genuinely generated `uv.lock` consistent; Qt version logged; no system GNOME edits |
| GUI-13 | GNOME terminal succeeds, editor inherited environment fails as reported | Capture precise environment difference and root cause before app-scoped remedy; both terminals either work or editor limitation documented without damaging the system |
| GUI-14 | Source absent, empty, corrupt/import-incompatible, permission denied or changing beneath load | Explicit nonfabricated error or chooser; no created source, no data corruption, no unhandled exception |
| GUI-15 | Startup pre-roll insufficient, exactly at threshold, and supplied `--from` | Confirmed H1/M15/M5/ATR sufficiency and pre-roll count exactly match R0; no future bar or fabricated EMA; starts paused at correct cursor |
| GUI-16 | 50/500/FAST replay, toggle Pause, paused Step, replay End, restart | One Step processes **one** normalized quote; no events skipped at FAST; ended never resumes; sources/cursors match corresponding R0 outcomes |
| GUI-17 | Replay same recorded tick stream with different Qt redraw frequency, long render, frozen GUI | Identical source order, S1 candidate IDs, READY/blocked/expiry, event timestamps and research outputs; only paint count differs |
| GUI-18 | Two distinct quotes with same provider UTC millisecond | Both quotes processed in stable source order with independent side values; no timestamp-key dedup in GUI |
| GUI-19 | Quote/SL/TP/R/fees Decimal scalars including 4119.9600, 0.00001, -0.00, long fractional scale, NaN/Infinity and None | All finite source digits and sign preserved as appropriate; invalid/absent values UNKNOWN/—; no implicit 2-digit rounding, float conversion, guessed tick |
| GUI-20 | GUI signal/candidate detail at H1/M15/M5 boundary, provisional bar available | Confirmed-vs-provisional tags and exact bar available_at times; no provisional-trigger READY or lookahead |
| GUI-21 | Multiple READYs, blocked READY, entered/skipped overlay and replay-ended last quote | Decision lane truthfully shows counts/blocked/current state; no extra signal, no automatic ranking, no fake live source |
| GUI-22 | Open dialog during PLAYING and click Step/Space or source switch | Worker acknowledges pause/cursor first; no replay advance or source switch behind modal; stays paused on closing, no hidden duplicate journal action |

### 20.3 Signals and information architecture (D02)

| ID | Fixture/action | Pass criterion |
| --- | --- | --- |
| GUI-23 | FORMING candidate with numeric trigger and with UNKNOWN threshold | Non-actionable watchlist explains next completed BID M5 close exactly; missing level is unavailable not 0 |
| GUI-24 | READY BUY and READY SELL | Correct ask/bid entry, corresponding closeable SL/TP side, immutable E0/SL/TP1/TP2/band/ATR/TTL/strategy/reason codes from engine |
| GUI-25 | READY issued, then execution-blocked, unblocked, invalidated or expired | Issued-at READY/history immutable; current status changes separately; no terminal resurrection or wrong action enable |
| GUI-26 | PRE-ROLL issued, duplicate structural pair, both same-side/opposite manual exposure | History explicitly PRE-ROLL, no fresh alert; duplicates suppressed by engine; exposure factual warning only, no invented limit |
| GUI-27 | Signal claimed ENTERED or USER_SKIPPED in second DB connection, then GUI refreshed | No duplicate fresh opportunity, on-plan action disabled, overlay and full source ID preserved |
| GUI-28 | Sort/filter/move row READY→History while detail is open | Stable full row ID/selection, moved-state message, no discarded details or silent replacement with different signal |
| GUI-29 | No current signal but historical MISSED/NOT_ISSUED/EXPIRED events | Histories correctly label actual event kind; no fabricated SignalRecord or retroactive READY |

### 20.4 Positions, manual journal and transaction races (D03)

| ID | Fixture/action | Pass criterion |
| --- | --- | --- |
| GUI-30 | REPLAY READY record entry at valid ASK/BID band/time; confirm and cancel alternatives | Exact mandatory input, source/fidelity and immutable PlanRef; preview matches domain EntryPreview; Cancel makes zero writes; Confirm makes one local event only |
| GUI-31 | Blank required price/qty/time; negative/zero/NaN/Infinity, malformed UTC, fees blank versus fees=0 | Per-field errors, exact Decimal parsing; UNKNOWN fee not coerced to zero; invalid input unchanged DB |
| GUI-32 | Late fill, outside band, wrong side/stop/target, before issuance/after expiry | Correct OFF_PLAN reasons, actual gross risk/reward comparison, no on-plan mislabeling and no plan mutation |
| GUI-33 | Inactive or blocked READY becomes terminal/claimed while dialog open | Pre-commit revalidation prevents on-plan entry/skip; explicit newly acknowledged OFF_PLAN path only, never automatic conversion |
| GUI-34 | Skip unused READY, repeat skip, skip racing entry on second connection | One USER_SKIPPED overlay, stable action id, no entry after skip; original signal remains untouched |
| GUI-35 | Unlinked/off-plan BUY or SELL with optional informational historical signal | Saves local OFF_PLAN entry, no signal resurrection/claim, with source and execution-fidelity caveat |
| GUI-36 | Record partial <remaining, =remaining, >remaining, with exit before entry, after earlier partial | Correct changed gross realized/remaining, reject full-as-partial, oversize/time invalid and stale quantity transactionally |
| GUI-37 | Record full close of remaining; another process partially closes before submit | Close only full currently remaining, no double close/negative quantity, no broker write |
| GUI-38 | Modify SL, target, no values, stop moved farther away, invalid target/time | Domain `current_risk` and farther-away warning correct, unchanged frozen initial denominator, only one MODIFY event on success |
| GUI-39 | Genuine quote touches STOP/TP1/TP2; no operator fill | Touch advisory only; remaining/position event list unchanged; no automatic partial/close |
| GUI-40 | Mark BUY at BID and SELL at ASK with same/other source, quote before actual fill, stale/replay ended | Exact closeable side and freshness labels, unavailable for wrong source/pre-fill, no false real-money P&L |
| GUI-41 | Gross move R vs realized+remaining R after partial | Same original full-position risk denominator across states; net R and money UNKNOWN when contract/fees absent |
| GUI-42 | Restart writable desktop with MONITORING and already RECONCILIATION_REQUIRED | First becomes RECONCILIATION_REQUIRED exactly once, second unchanged; no confirmed held-status claim; full worklist rendered |
| GUI-43 | Reconciliation required and operator confirms actual broker open; concurrent duplicate confirm | One CONFIRMED_OPEN action, MONITORING projection only after explicit consent; still no broker sync |
| GUI-44 | Start desktop with DB read-only, migration needed, locked DB or disk fault | No false empty overlay, no invented reconciliation, honest UNVERIFIED/read-only mode, no partial destructive migration; error actionable |
| GUI-45 | Double-click Confirm, transient DB error after event insert, retry same payload/action_id; retry changed payload | Exactly one durable event on same payload retry, rollback on failure, reject reused ID/different data, no premature success |
| GUI-46 | External second local instance races entry/skip, partial/close, restore and record modify | Existing `BEGIN IMMEDIATE` service serializes; no lost updates/first-action conflicts, journal survives restart |
| GUI-47 | Dirty form Esc/Cancel; typing `e s q p m x n space 1 2 3` into fields; keyboard-only | Dirty Esc explicitly confirms discard; no global actions through inputs, no accidental save; Cancel initially focused |
| GUI-48 | Long mixed journal history, operator events + session SIM ENGINE and pre-roll, filter by ID/date/source/type | Correct provenance; operator rows persist, replay-derived events explicitly reconstructible but not asserted persisted; sorting stable, full detail accessible; all events still stored/available regardless of visible page limit |
| GUI-49 | Operator event has same millisecond as separate event; filters and row refresh | Stable unique event IDs/tie order, no duplicate/drop, exact event UTC separate from recorded UTC |
| GUI-50 | Attempt to correct historical event or delete via GUI | No unsupported editor/delete/correction UI or direct SQL mutation; gap presented as future approval-gated enhancement |

### 20.5 Diagnostics, resilience, performance and visual parity (D04–D05)

| ID | Fixture/action | Pass criterion |
| --- | --- | --- |
| GUI-51 | Source health UNKNOWN with unset freshness threshold, degraded, stale, market closed; separate replay PAUSED/ENDED | Accurate status/reason, never claim FRESH from playback, no fake LIVE or executable signal |
| GUI-52 | Full Diagnostics for valid and missing data | Raw/canonical symbol, source/origin, provider/receive UTC, gaps/bars/warm-up, hashes/config/schema, clock/quote age all equal authoritative snapshot; missing is UNKNOWN |
| GUI-53 | M09 reference-status NOT_CONFIGURED, FIXTURE, INTEGRITY_FAULT, disconnected and reconstructed | Only read-only status labels/counters/blockers; fixture SIMULATED; no live data connection, automated recovery or new broker privileges |
| GUI-54 | Worker emits many quotes rapidly, UI intentionally stalls, source switches mid-load | Full engine event count/sequence and touch observations preserved, only paint frames coalesced; no cross-source stale quote or SQLite thread misuse |
| GUI-55 | Worker/process failure while loading, after snapshot, before/during DB commit, on quit | Last reliable snapshot labeled stale/unavailable; inputs guarded, pending journal result committed/failed truthfully, close SQLite in owner thread, threads exit cleanly |
| GUI-56 | Open every view at 1366×768, 1920×1080 and 820×620 logical px | Safety banner/source/fidelity/decision/actions never clipped; all other content accessible by scroll/drawer, no layout collision |
| GUI-57 | Native 100/125/150/200% DPI and enlarged system font, no font installed | True Qt logical scaling; prices/badges/buttons readable, keyboard focus visible, no fixed text cutoffs |
| GUI-58 | Keyboard-only all five screens, mixed dialog/filter focus, high-contrast color-blind audit | All actions reachable, full IDs and precision in details, semantic text labels not color alone, no input-triggered hotkeys |
| GUI-59 | Visual QA against §16 design after each page milestone | Coherent dark theme, clear decision-first hierarchy, readable bid/ask/spread, narrow sidebar, restrained gold, no information overload/terminal-looking UI; screenshots reviewed by owner |
| GUI-60 | Run full engine/CLI/TUI/SQLite/M09 tests with Qt installed, then without optional Qt | All preexisting tests still pass on their relevant platforms; no new broker calls/strategy changes; exact pass/skip counts recorded |
| GUI-61 | Existing `gold` alias before cutover; Desktop wrapper after owner approval; explicit `grog ui` fallback | Before sign-off alias unchanged; after sign-off one-word desktop launch from durable selected source and installed extra; fallback remains operational and source-safe |
| GUI-62 | Compare complete replay outcomes, signal IDs and the full operator journey in Textual vs Qt | Same ordered quote/S1/signal events, exact plans/Decimals/UTC and local journal projection/event bytes apart from expected action IDs/record time; no behavior loss |

### 20.6 Evidence and sign-off protocol

For each D0x phase, Grok's report must include: baseline and new Git commit SHA, changed files (limited to phase), explicit source/strategy non-change statement or rationale for **any** changed line outside desktop/tests/docs, commands and exact outcomes (pass/fail/skip), failing fixture reproduction before fix when practical, number of event records before/after, startup/migration observations, Qt/offscreen and **visible** screenshots for newly delivered screens, known gaps, and next gate. If a Qt test skips because the extra isn't installed, report it **PENDING**, never PASS.

**D05 hard gate:** GUI-01..62 relevant cases (plus all TUI/R0 acceptance/integration suites) PASS with no unapproved source-fidelity, trading formula, journal-data or broker-side behavior changes; all five screens usable in a normal Ubuntu terminal, startup-state selection tested without ephemeral demo dependence; restart reconciliation and data-loss fault tests PASS; no unsupported broker permissions; owner explicitly signs off before altering the `gold` command. A test suite alone does not validate strategy profitability or a live executable recommendation.

## 21. Desktop UI/UX V2 additional acceptance — owner-approved 2026-11-07

These `UXV2-` checks **add** to, never replace, GUI-01..62 in §20 and every existing R0/SQLite/replay safety gate. Use the approved [desktop-visual-redesign.md](desktop-visual-redesign.md) as the single **presentation** test target. All screenshot data must be unmistakably offline REPLAY/SIMULATED or deliberately injected fault state, never presented as a true live broker quote. Qt offscreen tests are necessary but do not substitute for the owner's visible GNOME review.

| ID | Test stimulus | Acceptance |
| --- | --- | --- |
| UXV2-01 | Fresh user preferences, reopen app | Default **Dark** with neutral charcoal colors; no new source/journal entries; default time display PKT |
| UXV2-02 | Manually select **Light**, restart | Warm-white palette applied to every page, dialog and popup; persists and does not follow later OS changes |
| UXV2-03 | Manually select **Dark**, restart | Neutral charcoal palette applied uniformly; persists and ignores OS Light change |
| UXV2-04 | Choose **System** on an OS exposing Dark, then switch OS to Light and back while app/dialogs exist | Effective theme follows OS at startup and on supported appearance-change notification; no app restart, stale per-widget palette or lost focus; saved choice remains System |
| UXV2-05 | Qt platform reports Unknown, unsupported changes or missing scheme signal | System choice remains visible, **effective Dark fallback** explained honestly; retry detection next launch, no crash or misleading success |
| UXV2-06 | Malformed/missing/read-only UI preference store | Safe default or read-only session notice; no modification of D05 source selection or journal DB, and no unsolicited files in source state |
| UXV2-07 | Choose PKT then UTC with provider/event/received/available/recorded timestamps, DST-boundary-like sample dates | Compact times have explicit **PKT/UTC** labels; source roles remain distinct; exact UTC milliseconds, order and stored integer timestamps unchanged; source virtual clock controls replay TTL |
| UXV2-08 | Decimal fixtures 4119.9600, 0.00001, -0.00, long scales, missing/NaN, typed manual values | Exact actionable quotes, E0, stop, TP1/TP2, qty, fees and all audit detail; UNKNOWN ≠ zero; optional shortened *secondary* metrics do not change any Decimal or parsing |
| UXV2-09 | Render all Overview states and 2+ READY signals on live replay fixtures | True decision first, next condition grounded, no ranked READY, FORMING not actionable, fault/reconciliation outranks decoration, all quote sides precise |
| UXV2-10 | Search/filter/sort/change signal selection as replay advances | Readable Developing/READY-blocked/History; full IDs/plan and exact dates in detail; stable keyed selection, no false signals or hidden safety block |
| UXV2-11 | Change theme and PKT/UTC while replay is paused/playing | No replay cursor move, new signal issuance, action gate change, false freshness, source switch, SQLite mutation or journal write due to preference alone |
| UXV2-12 | Show Open/Needs reconciliation/Closed/UNVERIFIED/mark-stale positions | Readable financial/risk info with no invented USD/net value; manual/not broker-synced warnings; chronology distinguishes event and recorded time |
| UXV2-13 | Long journal of operator and SIM ENGINE events, filters and selected detail | Producer/provenance labels and chronological order preserved; no row loss under clipping; exact payload/ID/codes discoverable; no unsupported correction/delete controls |
| UXV2-14 | All seven action dialogs with invalid, valid, duplicate and uncertain-save states | Required before advanced fields; inline errors and preview readable; Cancel focused, Confirm reachable, exact plan/qty; same action_id retry and save-time recheck preserved |
| UXV2-15 | Diagnostics valid/degraded/integrity-fault/reference-NOT_CONFIGURED/DB-unavailable | Severity and safe recovery summary before technical detail, full hashes/codes retained, never synthetic-to-LIVE or “all healthy” for unreadable journal |
| UXV2-16 | Chooser empty/missing/corrupt state and Help keyboard-only, in both themes | Readable state/source/Remember warning, safe no-data guidance; no imported data created; help matches current shortcut bindings |
| UXV2-17 | 820×620, 1366×768, 1920×1080; 100/125/150/200%; long IDs and full precision | **Every** screen, Settings, modal, popup and source chooser usable without clipped warning or unreachable Cancel/Confirm; all full values available in details |
| UXV2-18 | End-to-end replay+manual record parity to existing R0, Qt enabled and optional-Qt absent | Exact engine/position/journal/source outputs unchanged; all tests/ruff pass (no hidden skips); visible paired Dark/Light screenshots and System runtime evidence, owner review; `gold` alias unmodified |

**Evidence:** screenshots or annotated visible captures must record screen state, viewport logical size, scaling and effective theme; tests must record exact pass/fail/skip and run provenance. A screenshot alone cannot validate database integrity, price math or LIVE readiness. The errors owner promised to provide later are **not** silently assumed fixed by this design milestone.
