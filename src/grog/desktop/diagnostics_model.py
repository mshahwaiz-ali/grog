"""Diagnostics read model (D04). Pure, Qt-free, detached values only.

Groups follow docs/02 §16.6. The source/feed/bars/warm-up/integrity checks are the R0
``grog.ui.panels.diagnostics_lines`` verdicts converted to detached rows (no duplicated
health or bar logic); this module adds the engine, read-only reference-adapter and local
journal groups. Built on the replay owner thread from the engine snapshot (source part)
and on the GUI thread from the detached ``JournalSnapshot`` (journal part).

Reference adapter: REPLAY never configures or instantiates M09-A/H; the status is the
existing ``not_configured`` ReferenceStatus label — no live data, exporter or broker.
"""

from __future__ import annotations

from dataclasses import dataclass

from grog.desktop.journal_model import JournalMode, JournalSnapshot
from grog.live.session import not_configured
from grog.ui.panels import diagnostics_lines

VERDICTS = ("OK", "INFO", "UNKNOWN", "NOT CONFIGURED", "DEGRADED", "ERROR")


@dataclass(frozen=True, slots=True)
class DiagRow:
    verdict: str  # one of VERDICTS ("" for a plain line)
    text: str


@dataclass(frozen=True, slots=True)
class DiagGroup:
    title: str
    rows: tuple[DiagRow, ...]

    @property
    def worst(self) -> str:
        ranks = [VERDICTS.index(r.verdict) for r in self.rows if r.verdict in VERDICTS]
        return VERDICTS[max(ranks)] if ranks else "INFO"


@dataclass(frozen=True, slots=True)
class DiagnosticsFacts:
    summary: str
    mode_line: str
    groups: tuple[DiagGroup, ...]

    def text(self) -> str:
        out = [self.summary, self.mode_line]
        for g in self.groups:
            out.append(g.title)
            out += [f"  [{r.verdict}] {r.text}" if r.verdict else f"  {r.text}" for r in g.rows]
        return "\n".join(out)


REFERENCE_TITLE = "REFERENCE ADAPTER (READ-ONLY)"
ATTENTION = ("UNKNOWN", "DEGRADED", "ERROR")


def overall(groups: tuple[DiagGroup, ...], *, stale: bool = False) -> tuple[str, str]:
    """Whole-page verdict over EVERY group, journal included (tone, text).

    The R0 terminal summary covers only the replay source checks, so it is never used as
    the page's overall health. NOT CONFIGURED counts as expected only for the read-only
    reference adapter in REPLAY (it is named, never called OK); anywhere else it needs
    attention like UNKNOWN / DEGRADED / ERROR."""
    attention = []
    for g in groups:
        bad = [
            r.verdict
            for r in g.rows
            if r.verdict in ATTENTION
            or (r.verdict == "NOT CONFIGURED" and g.title != REFERENCE_TITLE)
        ]
        if bad:
            attention.append((g.title, max(bad, key=VERDICTS.index)))
    prefix = "Overall (STALE — last good values, not current)" if stale else "Overall"
    reference = any(g.title == REFERENCE_TITLE for g in groups)
    note = (
        " · reference adapter NOT CONFIGURED (expected in REPLAY; nothing is live-validated)"
        if reference
        else ""
    )
    if attention:
        tone = "error" if any(v == "ERROR" for _t, v in attention) else "warning"
        items = "; ".join(f"{t} {v}" for t, v in attention)
        return tone, f"{prefix}: NEEDS ATTENTION — {items}{note}"
    if not reference:  # no source facts: never "OK" from the journal card alone
        return "warning", f"{prefix}: INCOMPLETE — no replay source diagnostics"
    return ("warning" if stale else "ok"), f"{prefix}: no problems found in any group{note}"


def _row(line) -> DiagRow:
    texts = [t for t, _style in line]
    if len(texts) >= 2 and texts[0].strip().startswith("[") and "]" in texts[0]:
        return DiagRow(texts[0].strip()[1:-1], "".join(texts[1:]).strip())
    return DiagRow("", "".join(texts).strip())


def _full_hashes(group: DiagGroup, snap) -> DiagGroup:
    """The terminal R0 view shortens the config sha256 to 16 hex for width; the desktop
    shows the same value in full (exact 64 hex, selectable). No other text changes."""
    full = getattr(snap.source, "config_hash", None) or ""
    short = f"Config sha256: {full[:16]} "
    if len(full) != 64:
        return group
    rows = tuple(
        DiagRow(r.verdict, r.text.replace(short, f"Config sha256: {full} ", 1)) for r in group.rows
    )
    return DiagGroup(group.title, rows)


def source_diagnostics(snap, *, strategy_version: str, cursor: int) -> DiagnosticsFacts:
    """Owner thread: R0 verdicts regrouped, plus engine and read-only reference groups."""
    lines = diagnostics_lines(snap)
    summary = _row(lines[1]).text
    mode_line = _row(lines[2]).text
    groups: list[DiagGroup] = []
    title, rows = None, []
    for line in lines[3:]:
        if len(line) == 1 and line[0][1] == "gold":
            if title is not None:
                groups.append(DiagGroup(title, tuple(rows)))
            title, rows = line[0][0], []
        else:
            rows.append(_row(line))
    if title is not None:
        groups.append(DiagGroup(title, tuple(rows)))
    groups = [_full_hashes(g, snap) for g in groups]
    groups.append(
        DiagGroup(
            "ENGINE / ELIGIBILITY",
            (
                DiagRow("INFO", f"Strategy version: {strategy_version}"),
                DiagRow("INFO", f"Replay cursor (quotes processed): {cursor:,}"),
                DiagRow("INFO", f"Signal triggers observed: {snap.triggers_observed}"),
            ),
        )
    )
    ref = not_configured(snap.virtual_time_ms or 0)
    groups.append(
        DiagGroup(
            REFERENCE_TITLE,
            (
                DiagRow(
                    "NOT CONFIGURED",
                    f"M09-A/H reference status: {ref.label} ({', '.join(ref.reasons)}); "
                    "REPLAY never connects to MT5, starts an exporter or reads a broker",
                ),
                DiagRow(
                    "INFO", "M09-B live validation and M10 remain pending and separately gated"
                ),
            ),
        )
    )
    return DiagnosticsFacts(summary, mode_line, tuple(groups))


def journal_group(snap: JournalSnapshot | None) -> DiagGroup:
    """GUI thread: the local journal state from the journal owner's detached snapshot."""
    if snap is None:
        why = (
            "Journal not opened — it opens only after the source loads; "
            "nothing was created or changed"
        )
        return DiagGroup("LOCAL JOURNAL / ERRORS", (DiagRow("UNKNOWN", why),))
    verdict = {
        JournalMode.WRITABLE: "OK",
        JournalMode.READ_ONLY: "DEGRADED",
        JournalMode.OPENING: "UNKNOWN",
        JournalMode.UNAVAILABLE: "ERROR",
    }[snap.mode]
    rows = [DiagRow(verdict, f"Journal {snap.mode.value}: {snap.reason}")]
    if snap.readable:
        rr = len(snap.needs_reconciliation())
        rows.append(
            DiagRow(
                "DEGRADED" if rr else "OK",
                f"Positions: {len(snap.open_positions())} open, {rr} need reconciliation; "
                f"{len(snap.events)} operator event(s), {len(snap.decisions)} skip decision(s)",
            )
        )
    else:
        rows.append(DiagRow("UNKNOWN", "Saved records could not be read; nothing is assumed"))
    return DiagGroup("LOCAL JOURNAL / ERRORS", tuple(rows))
