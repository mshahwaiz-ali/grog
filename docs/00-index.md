# Grog Documentation Index — Canonical Specifications

**Updated:** 2026-11-07 · **Project stage:** offline R0 (M00–M08) implemented and acceptance-audited — verdict CONDITIONAL ([14](14-r0-acceptance-audit.md) §5); M09-A offline reference-adapter parts implemented on fixtures, M09-B (real MT5 demo) BLOCKED on external permission; M10 protocol structure defined with values OPEN; no strategy edge validated.

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

**Implementation status:** R0 code exists on `main` with local tests (run instructions in the [README](../README.md)); **no live feed has been connected and no performance test on real data has been run**. Approved engineering direction does not make S1 strategy thresholds validated or profitable.

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
