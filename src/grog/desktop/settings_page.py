"""Unnumbered UI Settings page: appearance and time display only.

All settings are presentation preferences; they cannot change a replay, source,
signal eligibility, journal record or real broker operation.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from grog.desktop.display_preferences import APPEARANCES, TIME_ZONES, DisplayPreferences
from grog.desktop.theme import SPACE, Card, label


class SettingsPage(QWidget):
    """Native radio controls with retained keyboard/focus behavior and honest fallback."""

    def __init__(self, preferences: DisplayPreferences) -> None:
        super().__init__()
        self.preferences = preferences
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE[4], SPACE[4], SPACE[4], SPACE[4])
        layout.setSpacing(SPACE[3])
        layout.addWidget(label("Settings", "pageTitle"))
        layout.addWidget(
            label(
                "These options only change how Grog looks and displays dates. "
                "They do not control live feeds, trading or the local journal.",
                "pagePurpose",
                wrap=True,
            )
        )
        appearance = Card("Appearance")
        self.appearance_group = QButtonGroup(self)
        self.appearance_buttons: dict[str, QRadioButton] = {}
        for value in APPEARANCES:
            control = QRadioButton(value)
            control.setObjectName(f"appearance{value}")
            control.setAccessibleName(f"Appearance {value}")
            control.setChecked(value == preferences.appearance)
            self.appearance_group.addButton(control)
            appearance.body.addWidget(control)
            control.toggled.connect(
                lambda checked, choice=value: self._choose_appearance(checked, choice)
            )
            self.appearance_buttons[value] = control
        self.effective_note = label("", "meta", wrap=True, select=True)
        appearance.body.addWidget(self.effective_note)
        layout.addWidget(appearance)

        time_card = Card("Time display")
        self.time_group = QButtonGroup(self)
        self.time_buttons: dict[str, QRadioButton] = {}
        for value in TIME_ZONES:
            control = QRadioButton(value)
            control.setObjectName(f"timeZone{value}")
            control.setAccessibleName(f"Display time {value}")
            control.setChecked(value == preferences.time_zone)
            self.time_group.addButton(control)
            time_card.body.addWidget(control)
            control.toggled.connect(
                lambda checked, choice=value: self._choose_time_zone(checked, choice)
            )
            self.time_buttons[value] = control
        time_card.body.addWidget(
            label(
                "PKT is Asia/Karachi. Replay, provider and recorded times remain "
                "exact UTC integers internally; audits retain UTC milliseconds.",
                "meta",
                wrap=True,
            )
        )
        layout.addWidget(time_card)

        safety = Card("Data and safety")
        safety.body.addWidget(
            label(
                "Replay is SIMULATED. Local manual records are NOT BROKER-SYNCED. "
                "Grog cannot execute orders. Source selection and journal records "
                "are independent of these preferences.",
                "body",
                wrap=True,
            )
        )
        layout.addWidget(safety)
        layout.addStretch()
        preferences.changed.connect(self._update_note)
        self._update_note()

    def _choose_appearance(self, checked: bool, choice: str) -> None:
        if checked:
            self.preferences.set_appearance(choice)

    def _choose_time_zone(self, checked: bool, choice: str) -> None:
        if checked:
            self.preferences.set_time_zone(choice)

    def _update_note(self) -> None:
        pref = self.preferences
        shown = f"Effective appearance: {pref.effective_theme}"
        if pref.appearance == "System":
            shown += " (following the OS when available)"
        if pref.note:
            shown += f"\n{pref.note}"
        self.effective_note.setText(shown)
