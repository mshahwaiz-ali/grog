"""Diagnostics page (D04). Qt GUI thread only; renders detached ``DiagnosticsFacts`` built
by the replay owner plus the journal group from the journal owner's snapshot.

After a source fault the last good diagnostics stay visible, explicitly labelled STALE with
the fault and the last known replay time — never presented as current. Every value is
selectable text; verdicts are words (OK / UNKNOWN / NOT CONFIGURED / DEGRADED / ERROR),
not colour alone (docs/02 §16.6, docs/08 GUI-52/53/58).
"""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from grog.desktop.diagnostics_model import DiagGroup, DiagnosticsFacts, journal_group, overall
from grog.desktop.journal_model import JournalSnapshot
from grog.desktop.theme import SPACE, Card, label, pill, set_tone

TONE = {
    "OK": "ok",
    "INFO": "info",
    "UNKNOWN": "warning",
    "NOT CONFIGURED": "warning",
    "DEGRADED": "warning",
    "ERROR": "error",
}


class DiagnosticsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.facts: DiagnosticsFacts | None = None
        self.journal: JournalSnapshot | None = None
        self.stale_reason: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE[4] + 4, SPACE[4], SPACE[4] + 4, SPACE[4])
        outer.setSpacing(SPACE[2])
        outer.addWidget(label("Diagnostics", "pageTitle"))
        outer.addWidget(
            label(
                "Technical evidence for the active source, engine and local journal. Read-only: "
                "nothing here changes policy, connects a feed or contacts a broker. UNKNOWN and "
                "NOT CONFIGURED are reported, never hidden.",
                "pagePurpose",
                wrap=True,
            )
        )
        self.stale = Card()
        self.stale_text = label("", "body", wrap=True, select=True)
        self.stale.body.addWidget(self.stale_text)
        self.stale.set_accent("error")
        self.stale.setVisible(False)
        outer.addWidget(self.stale)
        self.summary = label("Waiting for the first engine frame…", "cardTitle", wrap=True)
        self.summary.setAccessibleName("Overall diagnostics verdict")
        # The R0 terminal summary, explicitly scoped: it covers the replay source checks
        # only (not the journal or the reference adapter), so it is never the overall.
        self.source_summary = label("", "body", wrap=True, select=True)
        self.mode_line = label("", "meta", wrap=True, select=True)
        outer.addWidget(self.summary)
        outer.addWidget(self.source_summary)
        outer.addWidget(self.mode_line)
        self.health_note = label("", "overviewSummary", wrap=True, select=True)
        self.health_note.setAccessibleName("Operational implications")
        outer.addWidget(self.health_note)
        self.attention_note = label("", "body", wrap=True, select=True)
        self.attention_note.setAccessibleName("Diagnostic attention items")
        outer.addWidget(self.attention_note)
        self.evidence_toggle = QPushButton("Show complete technical evidence")
        self.evidence_toggle.setCheckable(True)
        self.evidence_toggle.setAccessibleName("Toggle complete diagnostic evidence")
        self.evidence_toggle.toggled.connect(self._toggle_evidence)
        outer.addWidget(self.evidence_toggle)
        self.evidence_host = QWidget()
        self.grid = QGridLayout(self.evidence_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(SPACE[3])
        self.grid.setVerticalSpacing(SPACE[3])
        outer.addWidget(self.evidence_host)
        self.evidence_host.setVisible(False)
        outer.addStretch()
        self.cards: list[Card] = []
        self.columns = 2
        self._shown: tuple = ()

    def _toggle_evidence(self, show: bool) -> None:
        self.evidence_host.setVisible(show)
        self.evidence_toggle.setText(
            "Hide complete technical evidence" if show else "Show complete technical evidence"
        )

    # ------------------------------------------------------------------ inputs

    def apply(self, facts: DiagnosticsFacts | None) -> None:
        self.facts, self.stale_reason = facts, None
        self._render()

    def apply_journal(self, snap: JournalSnapshot | None) -> None:
        self.journal = snap
        self._render()

    def mark_stale(self, reason: str, last_virtual_utc: str | None) -> None:
        """A fault after earlier frames: keep the last good evidence, labelled STALE."""
        when = f" Last good replay time: {last_virtual_utc}." if last_virtual_utc else ""
        self.stale_reason = (
            f"STALE — the source stopped ({reason}).{when} The values below are the last good "
            "diagnostics, not current."
            if self.facts is not None
            else f"UNAVAILABLE — {reason}. No diagnostics were produced for this source."
        )
        self._render()

    def set_layout_mode(self, mode: str) -> None:
        columns = 2 if mode == "wide" else 1
        if columns != self.columns:
            self.columns = columns
            self._shown = ()
            self._render()

    # ------------------------------------------------------------------ render

    def groups(self) -> tuple[DiagGroup, ...]:
        source = self.facts.groups if self.facts is not None else ()
        return (*source, journal_group(self.journal))

    def _render(self) -> None:
        self.stale.setVisible(self.stale_reason is not None)
        self.stale_text.setText(self.stale_reason or "")
        if self.facts is not None:
            groups = self.groups()
            tone, verdict = overall(groups, stale=self.stale_reason is not None)
            self.summary.setText(verdict)
            set_tone(self.summary, tone)
            scoped = self.facts.summary.removeprefix("Summary: ")
            self.source_summary.setText(f"Replay source checks only (terminal summary): {scoped}")
            self.mode_line.setText(self.facts.mode_line)
            issues = [
                (g.title, r.verdict, r.text)
                for g in groups
                for r in g.rows
                if r.verdict in ("ERROR", "DEGRADED", "UNKNOWN")
                or (
                    r.verdict == "NOT CONFIGURED"
                    and g.title != "REFERENCE ADAPTER (READ-ONLY)"
                )
            ]
            if self.stale_reason:
                self.health_note.setText(
                    "Source information is stale. Do not treat the last quote as current."
                )
                set_tone(self.health_note, "error")
            elif issues:
                self.health_note.setText(
                    f"{len(issues)} operational check(s) need attention. "
                    "Read the warnings before relying on this replay."
                )
                set_tone(self.health_note, "warning")
            else:
                self.health_note.setText(
                    "Replay checks and local journal have no reported problems. "
                    "The reference adapter is not connected; no live broker data is validated."
                )
                set_tone(self.health_note, "neutral")
            self.attention_note.setText(
                "\n".join(f"{title} · {status}: {detail}" for title, status, detail in issues)
                if issues
                else "No unresolved source or journal warnings in the available diagnostics."
            )
            set_tone(self.attention_note, "warning" if issues else "info")
        elif self.stale_reason is not None:  # startup fault: never "waiting" for a frame
            self.summary.setText("No diagnostics — this source did not load")
            set_tone(self.summary, "warning")
            self.source_summary.setText("")
            self.mode_line.setText("")
            self.health_note.setText("No source evidence is available.")
            set_tone(self.health_note, "warning")
            self.attention_note.setText(self.stale_reason)
            set_tone(self.attention_note, "error")
        else:
            # Source switching must never leave a previous source's "OK" summary visible.
            self.summary.setText("Waiting for source diagnostics…")
            set_tone(self.summary, "info")
            self.source_summary.setText("")
            self.mode_line.setText("")
            self.health_note.setText("Waiting for source diagnostics and local journal status.")
            self.attention_note.setText("")
        if not self.isVisible():
            return  # hidden page: rebuilt from the latest facts when shown (showEvent)
        groups = self.groups()
        key = (groups, self.columns)
        if key == self._shown:
            return
        self._shown = key
        for card in self.cards:
            self.grid.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = []
        for i, g in enumerate(groups):
            card = Card(g.title)
            card.setAccessibleName(f"{g.title} diagnostics")
            worst = pill(g.worst, TONE.get(g.worst, "info"))
            card.body.insertWidget(1, worst)
            for r in g.rows:
                text = f"{r.verdict}: {r.text}" if r.verdict else r.text
                line = label(text, "body", wrap=True, select=True)
                if r.verdict in ("UNKNOWN", "NOT CONFIGURED", "DEGRADED", "ERROR"):
                    set_tone(line, TONE[r.verdict])
                card.body.addWidget(line)
            self.grid.addWidget(card, i // self.columns, i % self.columns)
            self.cards.append(card)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._render()

    def text(self) -> str:
        parts = [self.stale_text.text() if self.stale_reason else "", self.summary.text()]
        parts.append(self.health_note.text())
        parts.append(self.attention_note.text())
        parts.append(self.source_summary.text())
        parts.append(self.mode_line.text())
        for g in self.groups():
            parts.append(f"{g.title} [{g.worst}]")
            parts += [f"{r.verdict}: {r.text}" if r.verdict else r.text for r in g.rows]
        return "\n".join(p for p in parts if p)
