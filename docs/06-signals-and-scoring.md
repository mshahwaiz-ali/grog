# Signal Engine — Eligibility, Lifecycle, Entry Validity and Quality

**Topic owner:** Readiness, observable signal changes, scoring, expiry and conflict handling. Updated 2026-10-30. **Status:** Overall workflow APPROVED; numbers and scoring policy below are RESEARCH HYPOTHESES pending broker data and performance tests.

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
