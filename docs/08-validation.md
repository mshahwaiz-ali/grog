# Research Validation, Backtesting, Indicator Comparison and Adversarial Tests

**Topic owner:** All S1 research experiments, quality/performance acceptance criteria, adversarial fixtures, win/loss attribution and overfitting controls. Updated 2026-10-30.  
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

## 11. Acceptance gates, scope and escalation

No claim of "best combo", "90% accurate", profitable backtest or live-trading readiness without real evidence. Before Grok codes trading rules, obtain explicit choices for broker/source, market-hours/fee/slippage model, warm-up, maximum quote staleness, cost/risk thresholds, trigger/stop conventions, overlap risk and acceptable signal-frequency/validation thresholds in [11 — Decisions](11-decisions.md). If unclear, implement only independently approved **non-trading foundations** with deterministic fixtures.

**No code, tests or historical trading results were executed or produced by consolidating this document.**

## 12. References

Relevant research sources and limitations are in [12 — Research references](12-references.md). Key sources include TradingView's repainting guidance, MetaTrader 5's real-tick testing, Fidelity's ATR guidance, Batten et al. (2018) precious-metals moving-average study, Bailey et al. on backtest overfitting, CME macro-event studies and the World Gold Council's gold OTC/futures market-structure overview. These motivate rigorous tests; none verifies S1 profitability.
