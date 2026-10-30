# Signal Engine — Eligibility, Lifecycle, Entry Validity and Quality

**Topic owner:** Readiness, observable signal changes, scoring, expiry and conflict handling. Updated 2026-10-31. **Status:** Overall workflow APPROVED; numbers and scoring policy below are RESEARCH HYPOTHESES pending broker data and performance tests.

**Authority:** Formula for price structure, EMA, ATR, timeframes → [04](04-analysis-engine.md). Strategy setup/trigger → [05](05-strategies.md). BID/ASK SL/TP and position management → [07](07-risk-and-monitoring.md). Test cases/performance → [08](08-validation.md). No archival research document overrides these.

## 1. Why signal quality has two separate stages

1. **Hard eligibility** asks: Is it objectively possible and sufficiently safe to display an actionable signal under agreed constraints? A failure cannot be compensated for by a high score.
2. **Quality ranking** asks: Among valid candidates, which have stronger measurable historical evidence? This stage is **not** a win-probability model and is **not** authorized to manufacture signals.

Consequently Grog must explain **DEVELOPING**, **READY**, **WAIT**, or **NO TRADE** using reasons rather than manipulating indicator scores to get desired trade frequency.

## 2. Candidate and signal states

Canonical state names:
- `DETECTED`: candidate structural observations identified but not complete.
- `FORMING`: proposed strategy setup developing, missing confirmed trigger or other requirements.
- `READY`: unique issued signal with immutable original plan, valid until manually acted upon, expired or invalidated.
- `SUPERSEDED`: earlier FORMING candidate replaced by newer valid pivot pair.
- `EXPIRED`: opportunity ended without a valid operator entry; cannot restart same pair.
- `INVALIDATED`: frozen structural/stop/thesis condition failed, never revive same ID.
- `SKIPPED` / `MISSED`: operator decision or a documented missed opportunity. Preserve in journal.
- `ENTERED`: operator manually reports an actual fill; subsequent lifecycle is `MONITORING` then `CLOSED` or `RECONCILIATION_REQUIRED` via [07](07-risk-and-monitoring.md).

**Overlay, NOT persistent state:** `EXECUTION_BLOCKED(reason)` while a still-alive READY signal temporarily fails reversible checks (spread, execution price band, temporary weak confirmation, feed degraded). If eligible again **before** original TTL and structural failure, reuse the same signal ID and preserve all block/unblock events.

Hard structural invalidation, a prior stop touch, H1 directional invalidation or expired TTL is **terminal**, even if price subsequently rebounds.

**No resurrection:** Previously issued signals/pairs cannot be silently replaced with a better historical timestamp or repeated after expiration. A genuinely new confirmed structural pair may produce a new candidate ID under [05](05-strategies.md).

## 3. Required gates and how to classify them

**Strict correctness gates (never optional):**
- Fresh, ordered, trustworthy BID/ASK quotes; enough history and actual confirmed feature availability.
- Valid contract/broker price precision, relevant metadata, recognized symbol and trading hours; no invalid/zero ATR or impossible stop.
- Strategy trigger and thesis valid at decision time, direction consistent with S1 confirmed H1 bias, no already-expired/duplicate pair.
- Quote used **after** M5 trigger became available, without retroactive candle-close fill.
- Current entry not already beyond frozen stop; no invalid source/feed status.

**Risk / execution policy gates requiring explicit approval before code:**
- Maximum acceptable spread/estimated full roundtrip costs (expressed in R and broker units); manual delay; minimum net reward/risk; maximum position risk/exposure; event blackout windows; maximum first-quote delay after closed bar.
- Treat undefined broker/cost limits as **OPEN**, not as silently invented universal constants. Until the material metadata needed for executable risk is available, display setup analysis but **do not imply an actionable sized trade**.
- Do not use an indicator's 'confidence' to bypass an approved cost or safety rule.

**Soft explanatory evidence** (do NOT automatically veto): M15 CORRECTIVE / OPPOSING context unless strict-veto research variant explicitly chosen; normalized trend strength; retracement quality; adverse wick; distance to opposing level; time-of-day, volatility regime, repeated recent failures. Distinguish observation from predicted result.

## 4. First actionable quote (proposed S1 benchmark)

S1's M5 strategy trigger is defined in [05](05-strategies.md). Its completed-bar **closing price is NOT an executable entry**.

On the **first causally subsequent valid quote** after the completed trigger bar is finalized:
1. Verify the actual quote was observed within the agreed maximum delay (**OPEN**; do not guess).
2. Freeze `atr0 = ATR14_M5` known when issued, `trigger_close_bid`, `trigger_two_bar_threshold`, `entry_timestamp_utc`, and quote `BID0/ASK0`.
3. **Long:** `E0=ASK0`; proposed first-quote no-chase test `E0 <= trigger_close_bid + 0.20*atr0`.
4. **Short:** `E0=BID0`; proposed first-quote no-chase test `E0 >= trigger_close_bid - 0.20*atr0`.
5. Evaluate correct SL/TP, spread, cost and risk using [07](07-risk-and-monitoring.md); if failed, record an explicit `MISSED_*` / gate rejection rather than fabricating READY.
6. If eligible, emit READY with **immutable** `signal_id`, original quote, entry/stop/targets, MTF evidence, scoring version and first-issued timestamp.

**The numbers 0.20 and ATR14 are provisional research parameters, not known profitable thresholds.** Cost/spread gates remain open until a broker is chosen.

## 5. While READY: valid manual-entry band and expiry (research hypothesis)

At the moment of issuance, freeze:
- **Long ASK execution band:** `[E0 − 0.10*atr0, E0 + 0.20*atr0]`.
- **Short BID execution band:** `[E0 − 0.20*atr0, E0 + 0.10*atr0]`.
- Confirmation retention check: long live BID `>= frozen_trigger_threshold − 0.10*atr0`; short live BID `<= frozen_trigger_threshold + 0.10*atr0`.
- **TTL:** up to the **next finalized M5 bar close** after READY (typically <=5 minutes, but depends on actual quote/finalization). Define expiry by event time and process as soon as knowable, never by UI-render timing.

On every valid quote, recompute **current eligibility** (band, spread, contract/trading hours and defined safety checks). Temporarily outside band or spread too high → `EXECUTION_BLOCKED` overlay; restored inside original frozen constraints before expiry → same READY ID. A confirmed H1 opposite bias, fixed structural invalidation, frozen stop touched before entry or TTL crossed → terminal INVALIDATED/EXPIRED.

If first quote is already too far away (fail no-chase) or delayed (missing quote beyond approved limit), record **MISSED_PRICE_CHASE / MISSED_DATA_GAP** and do not issue. If the user still reports an actual late fill, permit journaling with `OFF_PLAN` status and recompute actual economics, but never rewrite the original signal to pretend it was well timed.

**Entry execution cannot be guaranteed.** A displayed price zone is a guideline based on observed broker prices, not an order or promise of fill.

## 6. Proposed 100-point rubric — NOT a calibrated probability

| Axis | Max points | Observable evidence |
| --- | ---: | --- |
| H1 market context / direction | 25 | Confirmed bias, normalized EMA slope/gap |
| S1 setup geometry | 25 | Observed impulse strength, retracement depth, usable structural range |
| M5 entry confirmation | 20 | Valid completed trigger; strength measures only if separately tested |
| Execution conditions | 20 | Current bid/ask, roundtrip cost as R, price lateness |
| Target quality | 10 | Net reward/risk and known opposing level distance |
| **Total** | **100** | **Quality rubric only** |

**IMPORTANT:** The table assigns broad **candidate weights**, not detailed point allocation equations. **No score is implementable yet** because exact normalization, thresholds, missing-value handling, score weights and promotion cutoffs remain OPEN. Grok **must not invent** sub-score formulas, claims like '85% chance', or mandatory score cutoffs. Until a complete frozen, experimentally calibrated rubric exists, the UI should use transparent raw evidence and objective READY/WAIT reasons without displaying an arbitrary numerical score.

Once evaluated, use per-strategy out-of-sample calibration and sample-count uncertainty before *ever* using win-probability wording.

## 7. Conflict and signal-selection policy

- All candidates have stable structural-pair and signal IDs; de-duplicate same S1 pivot pair across repeated quotes/restarts.
- One active FORMING pair per direction is the current S1 research hypothesis; READY and existing manual positions are separate persistent records.
- If multiple future strategies or opposite sides produce candidates, show them as developing observations. **Do not recommend simultaneous overlapping or contradictory exposures** until a concrete policy for multiple positions, risk caps and ranking is approved.
- If the selected risk policy allows only one active trade, offer the independently most appropriate candidate after validated ranking. The exact conflict resolution is **OPEN**; do not invent preferred strategy order.
- Do not force READY trades to meet a target number per day; track rejected *winning* opportunities as well as avoided losses.

## 8. Output contract for operators

Every READY card should show: `signal_id`, date/time and quote age, XAUUSD venue/price source, BUY/SELL, S1 version, H1 bias / M15 context / M5 trigger, original and current BID/ASK, valid **execution-side** entry band, initial SL and TP1/TP2 with their broker price-side conventions, gross and **estimated net** R/R if cost metadata known, hard eligibility status, exact expiry, reason codes, quality evidence, and latest monitoring/re-evaluation timestamp.

Forming cards show missing trigger(s), watched price levels, reasons for WAIT and known deadlines. NO TRADE shows the primary blocked reason, not a synthetic score.

Operator's actual fill price is recorded **separately** in [07](07-risk-and-monitoring.md).

## 9. Required acceptance scenarios

The canonical S1 synthetic fixtures and test IDs are in [08 — Validation](08-validation.md). Minimum invariants:
- Same finalized tick stream and frozen config yields same original signal, ID, time, economics and rejection reasons.
- No H1/M15/M5 future data or unconfirmed pivot in READY.
- Temporary reversibility preserves signal ID; final invalidation/TTL cannot resurrect an old signal.
- Bid/ask mismatch or delayed operator fill recalculates economics without rewriting original.
- No unsupported win-probability label, confidence formula, trade execution or fabricated quote.

**All proposed numeric bands/TTLs are research settings; production acceptance requires broker-matched bid/ask replay, validation and explicit approval.**

## 10. Phase 18 — signal-quality decision policy (PROPOSED, NOT VALIDATED)

**Single goal:** improve whether Grog proposes a worthwhile manually executable **XAUUSD** trade. This phase **does not** add another indicator, strategy, platform feature, LLM or auto-trading component. Its job is to give the existing S1 evidence a precise selection order, without promoting the unvalidated 100-point rubric into a fictitious success probability.

### 10.1 Ordered decision contract

On each newly available market event, evaluate in this exact order:

1. **Information integrity:** Is the quote source correct, fresh and internally consistent; are all required candles/indicators and pivots *available at decision time*? If not, `DATA_UNAVAILABLE` / WAIT; no new READY.
2. **Strategy-specific formation:** Has S1 found a causally valid H1 direction, frozen M5 L/H pair, allowable pullback and a completed M5 trigger? If not, DETECTED/FORMING or a terminal invalidation with precise reason. M15 CORRECTIVE by itself is not a veto.
3. **Plan construction:** Use the first actual executable post-trigger quote and broker price conventions. Compute original entry side, frozen structural SL, TP1/TP2, gross risk/reward and *estimated* net costs if inputs support them. Impossible, incomplete or already-broken plan => do not issue READY.
4. **Approved safety/eligibility gates:** Apply session/quote/contract, entry validity, signal TTL, known-event restrictions and position/exposure policy. Numerical spread, latency and reward thresholds are **OPEN** until approved. An explicit unsafe state outranks any visual indicator score.
5. **Supporting evidence:** Record H1 strength, M15 SUPPORTIVE/CORRECTIVE/OPPOSING, M5 geometry/trigger, target congestion, entry distance and roundtrip cost burden. These are **measured observations**, not claims of outcome probability.
6. **Decision:** If required strategy and safety gates pass, show READY under the versioned S1 rules *without* requiring any arbitrary score cutoff. If a temporary reversible execution condition fails on an **already READY** signal, show the existing `EXECUTION_BLOCKED(reason)` overlay; keep original ID, original prices and original TTL. Hard invalidation and expiry remain terminal.
7. **Prioritization / allocation (only when needed):** Collapse duplicate same-pair proposals; show any truly distinct valid opportunities with exact reasons. Until an evidence-based conflict/exposure policy is approved, **do not manufacture a numeric "best" ranking, silently open another exposure, or issue contradictory positions as independent recommendations**.

A valid signal is not promised to win; a high-potential-looking forming setup is **not** a recommendation to enter.

### 10.2 Strict versus soft: no indicator voting contest

| Evidence or event | Initial handling | Rationale |
| --- | --- | --- |
| Unconfirmed H1/M15 pivot, stale data, unknown execution side | Correctness gate | Cannot trust information or executable prices |
| H1 UP/DOWN needed for S1 side, M5 trigger closed, fixed pivot thesis intact | Strategy-specific requirement | Defines S1, not an arbitrary extra filter |
| M15 normal correction against H1 | Soft observation | A correction can be the trade setup |
| M15 OPPOSING despite H1 bias | Soft warning in baseline; veto only in separately tested variant | Trend conflict may or may not outweigh lost opportunities |
| Strong/weak M5 candle body or wick | Recorded feature, optional **separate** experiment | Avoid over-filtering via redundant confirmation |
| Opposing confirmed structural level before TP2 | Target congestion observation, then optional tested target variant | A nearby level may reduce available upside, but is not automatically fatal |
| Actual spread, quote age, entry lateness, wrong lot/price precision | Objective values; safety thresholds require broker-defined policy | Prevent fictitious fills and unrealistic reward |
| RSI, ADX, MACD, extra "institutional" indicator | **Not included** | No proven incremental usefulness over price/EMA/ATR baseline |

**No market condition is treated as "manipulation detected".** Grog observes only data available from its chosen feed; order-flow claims need their own valid source.

### 10.3 Trade-quality evidence snapshot (future software contract)

Each candidate, READY and rejection event should have the following **timestamped, versioned** evidence fields (specific schema/type definitions in [09](09-architecture.md) when implementation is authorized):

| Field group | Required observations |
| --- | --- |
| Identity | `candidate_id`, `pair_id`, `signal_id` if issued, `strategy_id/version`, `side`, `decision_time_utc`, `available_at` |
| Context | Last **confirmed** H1/M15/M5 bar IDs; H1 UP/DOWN/NEUTRAL/UNKNOWN; M15 SUPPORTIVE/CORRECTIVE/OPPOSING/UNKNOWN; source and health |
| Geometry | Frozen L/H prices & pivot-confirmation times; impulse/ATR; retracement fraction; M5 trigger reference and closed-bar timestamp |
| Execution | Actual BID/ASK snapshot, spread, first eligible quote time, entry-band boundaries, price distance to E0 in ATR/R, original SL, TP1/TP2 |
| Economics | Gross risk and reward; fee/slippage assumptions, estimated **net** R/R when knowable; structural congestion distance in R |
| Decision | All evaluated gate results `PASS/FAIL/UNKNOWN/NOT_APPLICABLE`, exact versioned reason codes, current/terminal state, expiry time |
| Outcome (separate, later) | Whether *offered*, *fillably eligible*, *paper-filled*, *actually manually entered*, *skipped*, *expired* or *closed*; never backfill a previously unknown outcome as an earlier decision feature |

An important missing required input is **UNKNOWN**, not zero and not silently replaced by a best-looking value. **No READY** if execution or source safety cannot be established. Soft M15 UNKNOWN should be disclosed but must not become a hidden mandatory veto.

### 10.4 Reason-code vocabulary and precedence

Provisional stable codes (exact naming/API to freeze with implementation):

- **Data:** `DATA_STALE`, `DATA_GAP`, `QUOTE_INVALID`, `HISTORY_INCOMPLETE`, `CONTRACT_UNDEFINED`.
- **Setup:** `H1_BIAS_MISMATCH`, `PIVOT_UNCONFIRMED`, `PULLBACK_SHALLOW`, `PULLBACK_INVALID`, `TRIGGER_NOT_CLOSED`, `STRUCTURE_INVALIDATED`.
- **Execution:** `ENTRY_CHASE`, `SPREAD_OVER_LIMIT`, `COST_UNAVAILABLE`, `QUOTE_DELAY`, `SIGNAL_TTL_EXPIRED`, `PRE_ENTRY_STOP_TOUCH`.
- **Policy:** `MARKET_CLOSED`, `EVENT_RISK_BLOCK`, `EXPOSURE_REVIEW_REQUIRED`, `DUPLICATE_PAIR`.
- **Soft context only:** `M15_OPPOSING`, `TARGET_CONGESTED`, `WEAK_TRIGGER_BODY`, `REGIME_TRANSITION`.

Report **all** evaluated reason codes, but show the **highest-priority actionable reason** first: data/unsafe execution > invalidated thesis/expired > approved policy block > missing strategy trigger > soft warnings. This display priority does not alter historical eligibility.

### 10.5 Multiple candidates, overlap and restrained ranking

**S1-only baseline:** One currently FORMING pair per side according to [05](05-strategies.md), and at most one distinct original signal per pivot pair. Multiple quote updates to one READY do not count as separate trade opportunities. Log competing candidate reasons even when a candidate loses a deterministic replacement rule.

**When more than one independently valid idea appears:**
- Group/deduplicate by the same underlying impulse/pivot pair, direction and overlapping entry risk; don't count repeated price updates as trades.
- If another *manual* XAUUSD position is known, show conflict/exposure warning and require a separately approved overlapping-position policy. Do not use an arbitrary score to justify doubled risk.
- If two distinct choices remain and ranking policy is not proven, display their **objective differences** (entry validity, target congestion, costs, M15 context), rather than claiming one has a higher success chance.
- No minimum number of trades/day. A NO TRADE outcome is valid if no executable, in-scope setup survives.

**First-quote transient spread issue (OPEN research decision):** Current baseline issues no READY when the initial post-trigger quote fails an approved cost gate. Research separately whether preserving a *not-yet-issued* trigger observation for a short, frozen deadline, then allowing its **first** READY only after quote normalization, improves results. Do **not** silently equate this with unblocking an already-issued READY or reset the original trigger timestamp. Until approved, preserve the existing initial-gate rule.

### 10.6 Quality rubric and calibrated probabilities — separate future layers

The proposed five-axis 100-point table in Section 6 is **only a rubric outline**. It has no authorized numeric per-feature formula, calibration or entry threshold. The initial usable Grog design is **reasoned, evidence-based eligibility without a fake score**.

To experiment with numeric **trade-quality ranking** later:
1. Freeze the data window, normalized inputs, missing-value behavior, candidate features, point formula/weights and the specific decision a score would change (e.g., preference between two valid signals).
2. Keep core eligibility and execution gates **independent** of the score.
3. Compare raw-signal baseline vs scored ranking **on the same realistically fillable signals and costs**. Merely changing the display score cannot improve net trade outcomes.
4. Use chronological out-of-sample and paper-trading data, report realized net expectancy, drawdown, frequency and rejected winning opportunities.
5. If score adds no robust incremental value, **don't implement or show it**.

**Optional true win probability is an even later problem:** Only define the target outcome precisely (for example, TP2 reached before SL under frozen fill policy), then build/calibrate empirical estimates on proper disjoint data and show sample uncertainty. A score of 85/100 **never** means 85% chance of a profitable trade. A calibrated event probability would still not guarantee attractive net expectancy or large profits.

### 10.7 Worked decision scenarios (illustrations only)

| Scenario at actual decision time | Grog should display | Why |
| --- | --- | --- |
| H1 UP, M15 CORRECTIVE, M5 pullback still missing closed trigger | **FORMING** | M15 correction is not wrong; M5 is incomplete |
| H1 UP, M15 CORRECTIVE, M5 trigger confirmed; first quote valid, plan/cost gates pass | **READY BUY** | Full strategy + executable trade, no artificial 80/100 threshold |
| H1 UP but current unclosed H1 temporarily turns DOWN | Reassess only using **last confirmed H1** | No repainting/future leak |
| Only mid-chart prices imply a good stop/TP; ASK/BID costs or metadata unavailable | **WAIT / no actionable entry** | Unexecutable or unsafe plan |
| READY BUY temporarily moves outside entry band and returns before fixed TTL | **Same signal ID**, temporarily EXECUTION_BLOCKED then READY | No repeated signal/new winning trade counted |
| READY BUY touches original stop or passes TTL before trader enters | **INVALIDATED/EXPIRED** | Cannot revive historical trade after failure |
| Two valid but contradictory or overlapping XAUUSD opportunities | **Display conflict**, no unsupported ranking or doubled-risk suggestion | Exposure policy remains OPEN |
| Strong M5 trigger but H1 neutral or setup not intact | **No S1 READY** | Strategy definition not satisfied |

**Boundary:** No implementation was authorized and these illustrations are not evidence that S1 succeeds. Required adversarial fixtures, rejected-winner analysis and score experiments belong only in [08 — Validation](08-validation.md).

