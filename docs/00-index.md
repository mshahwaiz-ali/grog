# Grog Documentation Index — Canonical Specifications

**Updated:** 2026-10-30 · **Project stage:** planning/research, NOT implemented or validated.

## How to read and change these documents

**One active authoritative document per topic.** New S1 revisions must **edit the owning document**, not create another `18-...`, `19-...` or competing "latest" file. The documents below are the **only active planning sources** for Grok. Historical drafts are preserved separately in [docs/archive/2026-10-30](archive/2026-10-30/README.md) and **must not be used as requirements**.

| File | Sole topic ownership |
| --- | --- |
| [01 — Product Vision](01-product-vision.md) | Goals, exclusions and outcomes |
| [02 — Terminal Workflow](02-workflows-and-ux.md) | User-facing sessions, entry confirmation and UI behavior |
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

This is our documentation structure; no code has been written.
