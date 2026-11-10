# Grog Documentation Index — Canonical Specifications

**Latest 2026-11-11 product decision:** [Trade-First Redesign](trade-first-redesign.md) — **no watch/position monitoring in the new daily application**. Supersedes previous watch-first one-click handoff, while preserving older tested software and all safety gates.

**Updated:** 2026-11-11 · **Project stage:** R0 offline research + five-page Qt desktop implemented; owner-tested Ubuntu/Wine MT5 demo exporter and read-only clock probe show actual broker-server tick timestamps, but a prior G/4022 source gap, missing verified T/L live stream, historical DST uncertainty and unset real-data policies still block live readiness. **One-click LIVE workstation approved as a direction and implementation scope**, not yet built or independently accepted. See [11 §18](11-decisions.md#18-one-click-live-reference-workstation--owner-direction-2026-11-11) and [10 §14](10-roadmap.md#14-lwx-implementation--one-click-live-workstation).

## How to read and change these documents

**One active authoritative document per topic.** New S1 revisions must **edit the owning document**, not create another `18-...`, `19-...` or competing "latest" file. The documents below are the **only active planning sources** for Grok. Historical drafts are preserved separately in [docs/archive/2026-10-30](archive/2026-10-30/README.md) and **must not be used as requirements**.

| File | Sole topic ownership |
| --- | --- |
| [01 — Product Vision](01-product-vision.md) | Goals, exclusions and outcomes |
| [02 — Workstation UX](02-workflows-and-ux.md) | User-facing sessions, entry confirmation and UI behavior |
| [03 — Market Data](03-market-data.md) | BID/ASK ticks, closed bars, data quality, time and calendars |
| [04 — Market Analysis](04-analysis-engine.md) | MTF roles, pivot/EMA/ATR formulas, H1/M15 interpretation |
| [05 — Trading Strategies](05-strategies.md) | S1 impulse/pullback/entry trigger and S2/S3 backlog |
| [06 — Signals & Scoring](06-signals-and-scoring.md) | Candidate/READY lifecycle, bands, TTL and scoring |
| [07 — Risk & Monitoring](07-risk-and-monitoring.md) | Bid/ask SL/TP, fill economics and open-position monitoring |
| [08 — Validation & Experiments](08-validation.md) | I0–I8 indicator research, S1/ADV fixtures, cost-aware testing |
| [09 — Architecture](09-architecture.md) | Module boundaries, data flow and technical options |
| [10 — Roadmap](10-roadmap.md) | Ordered development phases and acceptance gates |
| [11 — Decisions](11-decisions.md) | Approved directions, open blockers and change control |
| [12 — References](12-references.md) | Source links and technical research context |
| [13 — Competitor Research](13-competitor-research.md) | Reference research only, NOT automatically approved features |
| [14 — R0 Acceptance Audit](14-r0-acceptance-audit.md) | R0 audit evidence: baseline, findings, fix log and acceptance verdict (owns no product rule) |

## Implementation entry point for Grok

When the user tells Grok to **start**, the sole external agent instructions are at [AGENTS.md](../AGENTS.md). It leads to [11 — Decisions](11-decisions.md) and the ordered [10 — Roadmap](10-roadmap.md). This is **not** a Grog application agent or feature. The first independent offline release M00–M08 requires **no execution broker**. MT5 demo bridge and performance qualification are later permission/evidence-gated milestones. Terminal wireframes/keyboard/modal behavior reside in [02 — UX](02-workflows-and-ux.md); storage/data contracts in [09 — Architecture](09-architecture.md); test IDs and milestone coverage in [08 — Validation](08-validation.md).

**Implementation status (2026-11-11):** R0 and the replay desktop exist; the user's local MT5 demo ran exporters and a clock probe, but the persistent LIVE workstation is not wired or qualified, and no strategy performance evidence has been completed. Approved engineering direction does not make S1 strategy thresholds validated or profitable.

## Source precedence

1. **Explicitly approved scope/direction:** [11 — Decisions](11-decisions.md).
2. **Canonical topic document** for exact mathematical/functional rules, noting each item's status.
3. [08 — Validation](08-validation.md) for evidence needed before experimental promotion.
4. **ARCHIVED docs:** historical provenance only, never override the above.

**Status labels:** APPROVED = user-agreed direction; PROPOSED = recommended but not frozen; EXPERIMENTAL = requiring data/testing; OPEN = undecided; ARCHIVED = obsolete historical context; VALIDATED = backed by reproducible evidence. No currently proposed S1 strategy has a proven live edge. **An APPROVED direction is not blanket coding authorization.**

## Modification checklist

- Identify the topic owner and read its current contents before any edit.
- Improve/rewrite that **existing** file; don't fork topic logic into new active docs.
- Do not silently choose numeric thresholds, broker contracts, AI agents, auto-trading or extra product features.
- Reference other topics by links, not duplicated competing equations.
- Record decisions/unknowns in [11](11-decisions.md); keep dated commit history.
- Maintain correct internal links and README index; preserve important superseded drafts only when necessary in archive.
- Before Grok implementation, provide exact source documents, frozen testable behavior, expected positive/negative tests and explicit OPEN blockers.
- In this planning stage do **not** claim an accurate/profitable trading product or paper-trading results.

**Latest research milestones:** Phase 18 refined evidence-first signal decisions in [06](06-signals-and-scoring.md) and SQ-01..SQ-18 in [08](08-validation.md). Market-data research now **selects MT5 as the preferred read-only reference adapter** while leaving real-money broker selection optional for early development, as recorded in [11](11-decisions.md). Feed integrity, demo-server requirements and offline replay are in [03](03-market-data.md), real bid/ask economics in [07](07-risk-and-monitoring.md), and MD-01..MD-22 test cases in [08](08-validation.md). Unapproved choices are logged in [11](11-decisions.md). No new active topic file was created.

**Approved GUI direction (2026-11-07):** a native Qt Widgets frontend ([11 D-014](11-decisions.md)), with UX in [02 §15](02-workflows-and-ux.md), architecture in [09 §12](09-architecture.md), and gated build steps in [10 §11](10-roadmap.md). The existing Textual R0 UI stays supported during migration.

This is our documentation structure; implementation status is tracked in [10 §8](10-roadmap.md) and desktop progress in [10 §11](10-roadmap.md).

**Historical D00–D05 implementation handoff (completed by `c0ef834`):** [02 §16](02-workflows-and-ux.md) governs five-screen behavior, dialogs, focus and responsive handling; [09 §13](09-architecture.md) governs Qt/replay/journal ownership; [08 §20](08-validation.md) defines GUI-11..62; [10 §12](10-roadmap.md) preserves the original D-phase gates; [11 §16](11-decisions.md) records safeguards. All five Qt pages, the local journal workflows, chooser and launcher are now implemented. **These historical D00–D05 instructions are not a request to rebuild the desktop**. Textual remains supported; `gold` alias cutover and MT5 demo connection are still not authorized.

**Owner-approved V2 visual/presentation companion (2026-11-07):** [GROG Desktop Visual & Interaction Redesign V2](desktop-visual-redesign.md). This is a **single implementation-facing style/human-readability checklist** for Grok, NOT a competing source of trading rules. [02 §16](02-workflows-and-ux.md) remains the functional UX authority; [11 D-015](11-decisions.md) records Dark/Light/**System** and PKT/UTC approval; [10 §13](10-roadmap.md) orders U0–U5; [08 §21](08-validation.md) tests it. The D00–D05 native desktop already exists by `c0ef834`; do not treat old 'D01 preview' notes as current. No `gold` alias cutover or MT5/live authorization.

**Current implementation handoff (2026-11-11):** Primary user goal is one-command Gold desktop with automatic read-only MT5 demo supervision, objectively calculated BUY/SELL/NO TRADE and a **watch-only selected setup**. The functional authority is [02 §17](02-workflows-and-ux.md#17-daily-one-click-live-workflow--2026-11-11); market-time evidence [03 §11](03-market-data.md#11-november-2026-mt5-time-and-source-integrity-evidence-operator-observed-2026-11-11); watch semantics [07 §13](07-risk-and-monitoring.md#13-selected-setup-watch--not-an-executed-position-approved-2026-11-11); integration [09 §14](09-architecture.md#14-one-click-live-workstation-integration--2026-11-11); tests [08 §22](08-validation.md#22-live-one-click-workstation-acceptance--lwx); order [10 §14](10-roadmap.md#14-lwx-implementation--one-click-live-workstation). Older docs that say M09-B access was never authorized describe the 2026-10-31 baseline. Existing gold alias unchanged until final sign-off; no trade execution.

**Newest priority (owner correction, 2026-11-11):** The **Trade Finder only** scope overrides the earlier one-click **Watch setup** specification for the primary app. The canonical status decision is [11 §19](11-decisions.md#19-trade-first-scope-correction--owner-approved-2026-11-11); the complete single handoff is **[GROG Trade-First Redesign](trade-first-redesign.md)**; implementation order is [10 §15](10-roadmap.md#15-tf--trade-finder-only-implementation-supersedes-watch-workflow). Do not build watch, manual position monitoring or journal screens into the new daily LIVE UI. Keep the older functions for compatibility and research; data health and honest strategy validation still apply. The preceding November 11 "watch-only" implementation paragraph is historical and superseded.
