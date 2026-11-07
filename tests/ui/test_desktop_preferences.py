"""U1 display preference and appearance tests; never touch the source/journal store."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from grog.desktop import theme  # noqa: E402
from grog.desktop.display_preferences import DisplayPreferences, resolve_appearance  # noqa: E402
from grog.desktop.settings_page import SettingsPage  # noqa: E402


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["gold-display-preferences-test"])


def _store(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_neutral_palette_tokens_are_complete() -> None:
    try:
        for name, background in (("Dark", "#111111"), ("Light", "#FAFAF9")):
            theme.activate(name)
            assert theme.ACTIVE_NAME == name
            assert theme.BG == background
            assert background in theme.STYLESHEET
            assert "@BG@" not in theme.STYLESHEET
            assert "#0B111A" not in theme.STYLESHEET
            assert theme.TONES["warning"][0] != theme.TONES["ok"][0]
    finally:
        theme.activate("Dark")


def test_existing_pills_and_cards_recolor_without_reconstruction(app) -> None:
    root = QWidget()
    layout = QVBoxLayout(root)
    warning = theme.pill("Execution blocked", "warning")
    card = theme.Card("Test")
    card.set_accent("error")
    layout.addWidget(warning)
    layout.addWidget(card)
    try:
        theme.activate("Dark")
        theme.apply_to(root)
        before = (warning.styleSheet(), card.styleSheet())
        theme.activate("Light")
        theme.apply_to(root)
        assert before != (warning.styleSheet(), card.styleSheet())
        assert theme.TONES["warning"][0] in warning.styleSheet()
        assert theme.TONES["error"][0] in card.styleSheet()
        assert warning.text() == "Execution blocked"
    finally:
        root.close()
        theme.activate("Dark")


def test_fresh_defaults_and_isolated_preference_file(app, tmp_path) -> None:
    path = tmp_path / "ui-preferences.ini"
    prefs = DisplayPreferences(_store(path))
    assert (prefs.appearance, prefs.time_zone) == ("Dark", "PKT")
    assert prefs.effective_theme == "Dark"
    assert not path.exists()  # starting the app must not write defaults
    assert not (tmp_path / "desktop-source.toml").exists()
    assert not (tmp_path / "state.sqlite3").exists()


def test_manual_overrides_restart_and_time_zone_persist(app, tmp_path) -> None:
    path = tmp_path / "ui.ini"
    prefs = DisplayPreferences(_store(path))
    prefs.set_appearance("Light")
    prefs.set_time_zone("UTC")
    assert path.is_file()
    assert (prefs.appearance, prefs.effective_theme, prefs.time_zone) == (
        "Light", "Light", "UTC"
    )
    reopened = DisplayPreferences(_store(path))
    assert (reopened.appearance, reopened.time_zone) == ("Light", "UTC")
    assert reopened.note == ""
    reopened.set_appearance("Dark")
    assert DisplayPreferences(_store(path)).effective_theme == "Dark"


def test_invalid_saved_settings_use_safe_defaults(app, tmp_path) -> None:
    path = tmp_path / "invalid.ini"
    settings = _store(path)
    settings.setValue("appearance", "Neon")
    settings.setValue("time_zone", "LOCAL")
    settings.sync()
    raw = path.read_bytes()
    prefs = DisplayPreferences(_store(path))
    assert prefs.appearance == "Dark" and prefs.time_zone == "PKT"
    assert "Invalid UI preference ignored" in prefs.note
    assert path.read_bytes() == raw  # never rewrite malformed preferences on read


@pytest.mark.parametrize(
    ("scheme", "effective", "fallback"),
    [
        (Qt.ColorScheme.Dark, "Dark", False),
        (Qt.ColorScheme.Light, "Light", False),
        (Qt.ColorScheme.Unknown, "Dark", True),
    ],
)
def test_system_appearance_resolution(scheme, effective, fallback) -> None:
    assert resolve_appearance("System", scheme) == (effective, fallback)
    assert resolve_appearance("Light", scheme) == ("Light", False)
    assert resolve_appearance("Dark", scheme) == ("Dark", False)


def test_os_changes_follow_system_only_and_announce_unknown(app, tmp_path) -> None:
    prefs = DisplayPreferences(_store(tmp_path / "scheme.ini"))
    notifications = []
    prefs.changed.connect(lambda: notifications.append(prefs.effective_theme))
    prefs.set_appearance("System")
    prefs._on_scheme_change(Qt.ColorScheme.Light)
    assert prefs.effective_theme == "Light"
    prefs._on_scheme_change(Qt.ColorScheme.Unknown)
    assert prefs.effective_theme == "Dark"
    assert "System appearance unavailable" in prefs.note
    before = len(notifications)
    prefs.set_appearance("Light")
    prefs._on_scheme_change(Qt.ColorScheme.Dark)
    assert prefs.effective_theme == "Light"
    assert len(notifications) == before + 1
    prefs.set_appearance("System")
    prefs._on_scheme_change(Qt.ColorScheme.Dark)
    assert prefs.effective_theme == "Dark"
    assert "System appearance unavailable" not in prefs.note


def test_settings_page_controls_are_readable_and_write_only_display_prefs(app, tmp_path) -> None:
    prefs = DisplayPreferences(_store(tmp_path / "page.ini"))
    page = SettingsPage(prefs)
    page.show()
    app.processEvents()
    try:
        assert set(page.appearance_buttons) == {"Dark", "Light", "System"}
        assert set(page.time_buttons) == {"PKT", "UTC"}
        page.appearance_buttons["Light"].click()
        assert (prefs.appearance, prefs.effective_theme) == ("Light", "Light")
        assert "Effective appearance: Light" in page.effective_note.text()
        page.time_buttons["UTC"].click()
        assert prefs.time_zone == "UTC"
        assert "NOT BROKER-SYNCED" in " ".join(
            label.text() for label in page.findChildren(type(theme.label()))
        )
    finally:
        page.close()


def test_window_settings_preserve_replay_and_numbered_pages(app, tmp_path) -> None:
    from test_desktop_d03 import (
        at_ready,
        decisions,
        events,
        finish,
        make_state,
        pending,
        wait_until,
    )

    from grog.desktop.frames import OverviewFrame
    from grog.desktop.journal_worker import JournalWorker
    from grog.desktop.replay_worker import ReplayWorker
    from grog.desktop.window import GoldWindow

    session, _signal = at_ready()
    request = make_state(tmp_path)
    window = GoldWindow(
        request,
        worker=ReplayWorker(loader=lambda _request: session, journal_reader=pending),
        journal_worker=JournalWorker(),
        ui_settings=_store(tmp_path / "display.ini"),
    )
    window.resize(820, 620)
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first frame")
        wait_until(app, lambda: window.manual.snapshot is not None, "journal ready")
        before = (window.frame.tag, window.frame.transport.processed, session.cursor)
        assert window.clock_text.text().startswith("Replay ")
        assert window.clock_text.text().endswith("PKT")
        window.settings_button.click()
        assert window.page_index == 5
        window.settings_page.appearance_buttons["Light"].click()
        assert theme.ACTIVE_NAME == "Light"
        window.settings_page.time_buttons["UTC"].click()
        assert window.clock_text.text().endswith("UTC")
        window.settings_page.time_buttons["PKT"].click()
        assert window.clock_text.text().endswith("PKT")
        window.show_page(4)
        assert window.page_index == 4
        assert before == (window.frame.tag, window.frame.transport.processed, session.cursor)
        assert events(tmp_path) == [] and decisions(tmp_path) == []
        assert (tmp_path / "display.ini").is_file()
    finally:
        finish(app, window)
        theme.activate("Dark")
