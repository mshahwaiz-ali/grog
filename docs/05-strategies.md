# Strategy Specifications — S1 Trend Pullback

**Topic owner:** Strategy selection, conditions, setup detection and trigger logic. Updated 2026-10-30.  
**Status:** Strategy candidates and S1 v0.2 algorithm are **PROPOSED EXPERIMENTS**, not proven or approved live rules. No automated trading, AI runtime, LLM, wallet or unrelated feature belongs here.

**Single source of truth:** Use this document for strategy behavior; [04](04-analysis-engine.md) for the **one definition** of EMA/ATR/MTF/pivots, [06](06-signals-and-scoring.md) for state/quality/expiry, [07](07-risk-and-monitoring.md) for entry-stop-target economics/monitoring and [08](08-validation.md) for tests and indicator comparisons. Superseded research drafts are [archived](archive/2026-10-30/README.md), **not implementation contracts**.

## 1. Strategy-selection policy

- Start with **S1 Trend Pullback** as the first research candidate. S1 is a **trend continuation**, not an all-market strategy.
- **S2 Level Sweep & Reclaim** is a separate future candidate for defined level breaches and failure to sustain; it must not be silently combined with S1.
- **S3 Breakout & Retest** is later research only; no initial implementation.
- On XAUUSD in a range, transition, known high-impact dislocation or unreliable feed, S1 may legitimately show WAIT/NO TRADE.
- Multi-timeframe correction is **not** automatic disqualification: H1 UP, M15 CORRECTIVE, M5 BUY trigger is a valid candidate subject to gates.
- An actionable signal is not an order. Grog never opens/closes broker trades.

## 2. Contract and traceability

Proposed strategy interface concepts (architecture eventually formalizes types):
- `discover(context, timestamp)` produces possible setups using only known prices.
- `form(candidate, last_closed_M5, timestamp)` maintains pullback state and contextual observations.
- `confirm(candidate, last_closed_M5, first_subsequent_valid_quote)` produces a proposed entry event, only if constraints pass.
- `invalidate(candidate, quote_or_closed_bar, timestamp)` produces a cause and terminal state where appropriate.
- `monitor_held(position, current_quote, newly_closed_bars)` **observes** a manually entered position; no order operations.

For audit every S1 event carries: `strategy_id=S1`, `strategy_version=v0.2-proposal`, symbol/venue/source, direction, decision UTC/arrival time, pivot pair, H1/M15/M5 snapshot IDs, ATR and parameters, trigger timestamp, data-health flags, previous state, new state, reason codes, and immutable raw signal ID. Same event stream/config must replay identically.

Use finalized data at actual `available_at`, as specified in [03](03-market-data.md) and [04](04-analysis-engine.md). Never backdate a READY event to a pivot or candle-close timestamp before actual availability.

## 3. Direction and eligibility (initial hypothesis)

- Full S1 **long** can become READY only when latest *confirmed* H1 bias is **UP**.
- Full S1 **short** can become READY only when H1 bias is **DOWN**.
- If H1 NEUTRAL or UNKNOWN, S1 cannot become READY; still show broad market observation without making a false actionable signal.
- M15 context SUPPORTIVE/CORRECTIVE/OPPOSING/UNKNOWN as computed in [04](04-analysis-engine.md) is recorded; OPPOSING is **soft adverse context** in the basic candidate, not a hard veto. The strict veto is a separate backtest variant.
- Other hard gates on input freshness, first quote, spread/cost, event policy and exposure are defined by [03](03-market-data.md), [06](06-signals-and-scoring.md) and [07](07-risk-and-monitoring.md). **Numeric limits remain OPEN**. Do not invent them in code.
- Diagnostic benchmark I0 removes H1 directional eligibility **only in historical comparative experiments** to isolate H1's benefit; not permission to trade against H1 in live S1.

## 4. S1 v0.2: impulse pair selection (candidate settings)

Precondition: EMA/ATR/pivots from [04](04-analysis-engine.md) are causally computed. M5 pivot width is preliminarily 2/2. Process newly confirmed pivots in deterministic event-time order.

### Long impulse

1. On a **newly confirmed M5 pivot high H**, choose the most recent *already confirmed* M5 pivot low L with `L.pivot_bar_time < H.pivot_bar_time`. Use most recent **pivot-bar index**, with stable IDs/tie handling.
2. Compute `I = H.bid_high - L.bid_low`. Only retain when `I>0`, `I >= 1.0 * ATR14_M5_at_H_confirmation`, and `(H.index-L.index)<=12` completed M5 bars.
3. The preliminary `1.0 ATR` and `12 bars` are **experimental research parameters**, not known optimal thresholds.
4. Freeze `pair_key=(S1_version, LONG, L.bar_id, H.bar_id)`, L/H price, pivot time, **confirmation time**, contemporaneous ATR and impulse I. Never mutate these after new price movement.

### Short impulse

1. On a **newly confirmed M5 pivot low L**, choose most recent confirmed preceding pivot high H.
2. Apply `I = H.bid_high - L.bid_low >0`, `I>=1.0*ATR_at_L_confirmation`, and bar-age <=12, freeze `(S1_version, SHORT, H.bar_id, L.bar_id)`.
3. Direction-specific short risk pricing is governed by **ASK** levels in [07](07-risk-and-monitoring.md), not bid-only chart appearances.

### Multiple or repeated pairs

- **Research default:** maximum **one active FORMING candidate per direction**. When a later valid newly confirmed pair arrives, transition previous FORMING candidate to `SUPERSEDED` with reason/time and activate the new pair.
- Do not silently erase or rewrite a previous **READY** or **ENTERED** signal. These are independently auditable under [06](06-signals-and-scoring.md).
- No same-pair regeneration after EXPIRED/INVALIDATED/SUPERSEDED.
- Counterfactual variant (one forming vs several) is OPEN; do not implement alternate policies as unseen features.

## 5. S1 pullback formation and objective invalidation

Once pivot pair exists, **include only fully completed M5 bars whose index is greater than the final impulse pivot bar**. The two right-side M5 bars needed to confirm that pivot can contribute **only after they are actually closed**. Do not retrospectively emit READY during them.

### Long
- Let `P_bid = MIN(BID low)` over all completed post-H M5 bars up to the current candidate bar.
- Require at least 2 completed post-H M5 bars.
- Define `d = (H.bid_high - P_bid)/I`.
- Candidate healthy research zone: **0.25 <= d <= 0.75**, with `L.bid_low < P_bid < H.bid_high`.
- If `d < 0.25`, display FORMING / PULLBACK_SHALLOW, **not** READY.
- If `d > 0.75`, or **actual observed BID <= L.bid_low**, mark INVALIDATED with timestamp/reason. These terminal events are not undone if price rebounds.
- Candidate expires after **more than 12 completed post-H M5 bars** without valid READY (proposed TTL for FORMING, not validated).

### Short (mirror)
- After final pivot low L, `P_bid = MAX(BID high)` of completed M5 bars and `d=(P_bid-L.bid_low)/I`.
- Require >=2 post-L completed bars, research zone 0.25–0.75, and `L.bid_low < P_bid < H.bid_high`.
- INVALIDATED on depth >0.75 or **actual observed BID >= H.bid_high**. SELL stop uses separate ASK extreme in [07](07-risk-and-monitoring.md).
- Same >12 M5 post-pivot bar-age hypothesis.

**Clarification versus archived draft 14:** The M5 trigger bar's adverse wick **may** create a new pullback extreme. Add the **completed trigger bar** into P and recalculate depth **before** accepting the trigger; do not reject solely for a new wick if the fixed structural invalidation and depth bounds remain intact. This choice remains subject to comparative validation.

## 6. S1 M5 actionable trigger (closed-bar baseline)

Let **j** be the newly finalized M5 candle. Do not issue a trigger retrospectively for a bar that closed before the pair became observable.

**BUY** requires:
- H1 UP, valid frozen LONG pair, >=2 completed post-H bars, healthy final depth and no hard invalidation.
- `Close_bid[j] > MAX(High_bid[j-1], High_bid[j-2])` (strict).
- `Close_bid[j] > Open_bid[j]` (bullish completed body).

**SELL** requires:
- H1 DOWN, valid SHORT pair, >=2 completed post-L bars, healthy final depth and no hard invalidation.
- `Close_bid[j] < MIN(Low_bid[j-1], Low_bid[j-2])` (strict).
- `Close_bid[j] < Open_bid[j]` (bearish completed body).

Bar j and j-1/j-2 must have correct source and valid finalized availability; never use the current bar's own high/low in the **previous two bar** threshold. For a trigger bar, first finish updating its post-impulse pullback P (Section 5) and check the fixed invalidation rules. A wick crossing the level without a closing confirmation is **not** sufficient.

On a valid trigger, create an immutable **trigger observation** with reference bar/threshold, then validate the **first executable subsequent BID/ASK quote** and current eligibility under [06 — Signals](06-signals-and-scoring.md). Any delay/gap or execution constraint can prevent READY. **Never fill a simulated trade at a past M5 close merely because the bar formed a signal.**

## 7. Early M1 timing is a separate experiment

Do not require M1 confirmation in the baseline. If tested independently:
- H1 and M15 context and an existing M5 FORMING pair must already be available.
- Only a newly finalized M1 close, using previously finalized M1 references, may trigger a **separately versioned EARLY_ENTRY branch**.
- Its own risk/entry/expiry contract and replay tests are mandatory; it cannot borrow a future M5 close or be advertised as the same confirmed signal.
- Compare net expectancy, spread sensitivity, missed opportunities, stop-outs and manual execution timing to the M5-only baseline before approval.

## 8. Failure modes and handling

| Risk | Strategy response (research design) |
| --- | --- |
| A pullback becomes a true reversal | Hard invalidate frozen L/H structural thesis and never resurrect same pair |
| Single candle spike then immediate failure | Keep closed-M5 trigger as baseline; test trigger-strength/retest filters separately |
| Higher H1 trend changes before manual entry | Invalidate READY when **newly confirmed H1** no longer matches S1; no repainting |
| M15 corrective while H1 trends | Watch/score rather than veto; test strict veto separately |
| M15 opposing | Explain structural warning, compare soft penalty vs veto; not hidden certainty |
| Candidate ages without M5 recovery | EXPIRED; require a new valid impulse pair |
| Breakout is far away at first subsequent quote | No chasing; quote and cost rules in [06] and [07] |
| A target is blocked by nearby structural level | Display opposing level; only experimentally change target policy |
| Known major release or unreliable feed | Respect configured event/feed gates, never claim to foresee the release |
| Multiple overlapping long/short signals | Signal allocator/dedup policy in [06] (open exposure rules require review) |

More filtering is **not** assumed better: see comparative research [08](08-validation.md) for losing vs rejected winning trades and net performance.

## 9. Other strategy candidates (not part of S1 implementation)

### S2: Level Sweep & Reclaim — later research
Select confirmed historical highs/lows, observe a genuine breach and reclaim in a bounded window, then test an entry and stop beyond the observed extreme. Failing to sustain a breakout does **not** prove market manipulation. Requires its own exact equations, expiration, bid/ask execution and out-of-sample tests before code.

### S3: Breakout & Retest — future backlog
Define a range **before** breakout, a closed-bar displacement and a confirmed retest/continuation. Fails under false breakout, gap/no retest and crowded targets; no implementation or promotion until S1 and S2 research justify it.

## 10. Grok implementation guardrails

**Implementation distinction:** The user's explicit **START** instruction authorizes Grok to build the existing S1_RESEARCH_V0_2 **offline/synthetic replay** logic after M00–M03, using the candidate values already specified here; a real execution broker and live risk limits are **NOT** prerequisites for that research-only work. Before presenting any S1 result as **broker-verified live executable advice**, separately resolve and approve all corresponding OPEN contract, spread, latency, risk and event decisions in [11 — Decisions](11-decisions.md). Work through [10 — Roadmap](10-roadmap.md) milestones rather than issuing a new broad prompt for each module. Grok must not invent unknown broker spread, cost, latency, risk, event, contract or strategy thresholds. No fixed '90% accurate' claim; no future candles; no automatic orders; no strategy creep. Each code change requires deterministic positive and negative fixtures from [08](08-validation.md) and the exact resulting commit/test evidence.

**Offline implementation handoff (2026-10-31):** When the user explicitly authorizes Grok to **START**, this frozen **S1_RESEARCH_V0_2** candidate logic may be implemented for SYNTHETIC/HISTORICAL REPLAY only. Strategy parameters are reproducible **research defaults**, not empirically chosen profitable settings. No additional indicator, strategy, dynamic tuning, auto execution, real-money position sizing or live signal-promoting numeric gate may be invented. Follow [10](10-roadmap.md) in small milestones and preserve all failed/missed candidate traces. **No strategy code has been written by this documentation work.**
