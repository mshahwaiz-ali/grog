"""Persistent UI-only preferences and effective Qt appearance resolution.

QSettings lives in the application's user configuration, not the D05 source
selection TOML or either SQLite database. No preference can mutate replay state.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QGuiApplication

APPEARANCES = ("Dark", "Light", "System")
TIME_ZONES = ("PKT", "UTC")
ORGANIZATION = "Grog"
APPLICATION = "GoldDesktop"


def resolve_appearance(
    appearance: str, system_scheme: Qt.ColorScheme
) -> tuple[str, bool]:
    """Return effective Dark/Light and whether System had to use a Dark fallback."""
    if appearance not in APPEARANCES:
        raise ValueError(f"Unsupported appearance: {appearance!r}")
    if appearance != "System":
        return appearance, False
    if system_scheme == Qt.ColorScheme.Light:
        return "Light", False
    if system_scheme == Qt.ColorScheme.Dark:
        return "Dark", False
    return "Dark", True


class DisplayPreferences(QObject):
    """Application-scoped controller; QSettings writes only after explicit edits."""

    changed = Signal()

    def __init__(
        self, settings: QSettings | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._settings = (
            settings
            if settings is not None
            else QSettings(
                QSettings.Format.IniFormat,
                QSettings.Scope.UserScope,
                ORGANIZATION,
                APPLICATION,
            )
        )
        self._settings.sync()
        raw_appearance = self._settings.value("appearance", "Dark")
        raw_zone = self._settings.value("time_zone", "PKT")
        good_store = self._settings.status() == QSettings.Status.NoError
        self.appearance = (
            raw_appearance if good_store and raw_appearance in APPEARANCES else "Dark"
        )
        self.time_zone = raw_zone if good_store and raw_zone in TIME_ZONES else "PKT"
        self._store_note = ""
        if not good_store:
            self._store_note = "UI preferences unreadable — using session defaults."
        elif raw_appearance not in APPEARANCES or raw_zone not in TIME_ZONES:
            self._store_note = "Invalid UI preference ignored — using safe defaults."
        self._style_hints = QGuiApplication.styleHints()
        self._style_hints.colorSchemeChanged.connect(self._on_scheme_change)
        self.effective_theme, self.system_fallback = resolve_appearance(
            self.appearance, self._style_hints.colorScheme()
        )

    @property
    def note(self) -> str:
        notes = []
        if self.system_fallback:
            notes.append("System appearance unavailable — using Dark.")
        if self._store_note:
            notes.append(self._store_note)
        return " ".join(notes)

    def set_appearance(self, value: str) -> None:
        if value not in APPEARANCES:
            raise ValueError(f"Unsupported appearance: {value!r}")
        if value == self.appearance:
            return
        self.appearance = value
        self._write("appearance", value)
        self._update_scheme(self._style_hints.colorScheme())

    def set_time_zone(self, value: str) -> None:
        if value not in TIME_ZONES:
            raise ValueError(f"Unsupported display time zone: {value!r}")
        if value == self.time_zone:
            return
        self.time_zone = value
        self._write("time_zone", value)
        self.changed.emit()

    def _write(self, key: str, value: str) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()
        self._store_note = (
            ""
            if self._settings.status() == QSettings.Status.NoError
            else "Could not save UI preferences — this session still uses your selection."
        )

    def _on_scheme_change(self, scheme: Qt.ColorScheme) -> None:
        if self.appearance == "System":
            self._update_scheme(scheme)

    def _update_scheme(self, scheme: Qt.ColorScheme) -> None:
        self.effective_theme, self.system_fallback = resolve_appearance(
            self.appearance, scheme
        )
        self.changed.emit()
