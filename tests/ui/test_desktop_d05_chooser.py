"""D05 source chooser (docs/02 §16.9 "NO DATA LOADED"): read-only inspection, explicit
Open, optional remembered selection, nothing imported/created/copied."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from test_desktop_d03 import app, settle  # noqa: E402, F401

from grog.cli import main as grog  # noqa: E402
from grog.desktop.chooser import SourceChooser  # noqa: E402
from grog.desktop.source_select import read_selection, selection_path  # noqa: E402
from grog.replay import synthetic  # noqa: E402


def _digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.endswith(("-wal", "-shm"))
    }


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}


@pytest.fixture
def state(tmp_path: Path, env) -> Path:
    csv = tmp_path / "hist.csv"
    csv.write_bytes(synthetic.generate_csv(days=2))
    state_dir = tmp_path / "state"
    argv = ["import-ticks", "--file", str(csv), "--source-id", "syn", "--origin", "SYNTHETIC"]
    out, err = io.StringIO(), io.StringIO()
    assert grog([*argv, "--state-dir", str(state_dir)], env=env, stdout=out, stderr=err) == 0
    return state_dir


def test_no_data_loaded_shows_guidance_and_cannot_open(app, tmp_path, env):  # noqa: F811
    missing = tmp_path / "nothing-here"
    chooser = SourceChooser("No saved desktop source", state_dir=str(missing), env=env)
    chooser.show()
    settle(app)
    try:
        assert chooser.title.text().startswith("NO DATA LOADED")
        assert "NOT USABLE: No imported state database" in chooser.state_note.text()
        assert f"--state-dir {missing}" in chooser.guidance.text()
        assert chooser.table.rowCount() == 0 and not chooser.open_button.isEnabled()
        assert chooser.focusWidget() is chooser.quit_button  # safe default
        chooser.quit_button.click()
        settle(app)
        assert chooser.selection is None and not selection_path(env).exists()
        assert not missing.exists()
    finally:
        chooser.close()


def test_pick_source_open_and_remember_without_touching_state(app, state, env):  # noqa: F811
    before = _digest(state)
    chooser = SourceChooser("No saved desktop source", state_dir=str(state), env=env)
    chooser.show()
    settle(app)
    try:
        assert chooser.table.rowCount() == 1 and not chooser.open_button.isEnabled()
        assert chooser.table.item(0, 1).text() == "SYNTHETIC"
        assert "TEMPORARY location" in chooser.state_note.text()  # pytest tmp is /tmp
        chooser.table.selectRow(0)
        settle(app)
        assert chooser.open_button.isEnabled()
        assert "never current market data" in chooser.caution.text()
        chooser.from_edit.setText("2026-10-14T00:00:00Z")
        chooser.open_button.click()
        settle(app)
        sel, problem = read_selection(env)
        assert problem is None and chooser.selection == sel
        assert (sel.source_id, sel.state_dir, sel.from_ts) == (
            "syn",
            str(state),
            "2026-10-14T00:00:00Z",
        )
        assert _digest(state) == before
    finally:
        chooser.close()


def test_open_without_remember_writes_nothing(app, state, env):  # noqa: F811
    chooser = SourceChooser("--choose", state_dir=str(state), env=env)
    chooser.show()
    settle(app)
    try:
        chooser.remember.setChecked(False)
        chooser.table.selectRow(0)
        chooser.open_button.click()
        settle(app)
        assert chooser.selection.source_id == "syn" and chooser.saved_to is None
        assert not selection_path(env).exists()
    finally:
        chooser.close()


@pytest.mark.parametrize("size", [(820, 620), (1366, 768), (1920, 1080)])
def test_chooser_fits_without_horizontal_overflow_and_buttons_visible(app, state, env, size):  # noqa: F811
    from PySide6.QtWidgets import QScrollArea

    chooser = SourceChooser("layout", state_dir=str(state), env=env)
    chooser.resize(*size)
    chooser.show()
    settle(app)
    try:
        area = chooser.findChild(QScrollArea)
        assert area.horizontalScrollBar().maximum() == 0, size
        for button in (chooser.quit_button, chooser.open_button):
            assert button.isVisible() and button.width() >= button.sizeHint().width()
        assert chooser.table.height() >= 4 * chooser.table.verticalHeader().defaultSectionSize()
    finally:
        chooser.close()


def _pick(app, chooser):  # noqa: F811
    chooser.table.selectRow(0)
    settle(app)
    assert chooser.open_button.isEnabled()


def test_saved_config_is_absolute_and_bad_inputs_never_save_or_open(
    app,  # noqa: F811
    state,
    env,
    tmp_path,
    monkeypatch,
):
    cfg = tmp_path / "cfgdir" / "c.toml"
    cfg.parent.mkdir()
    cfg.write_text("")
    monkeypatch.chdir(cfg.parent)
    chooser = SourceChooser("t", state_dir=str(state), env=env)
    try:
        chooser.show()
        settle(app)
        _pick(app, chooser)
        chooser.from_edit.setText("yesterday")
        chooser.open_button.click()
        settle(app)
        assert chooser.selection is None and chooser.isVisible()
        assert not selection_path(env).exists() and "INVALID_TIMESTAMP" in chooser.caution.text()
        chooser.from_edit.setText("")
        chooser.config_edit.setText("missing.toml")
        chooser.open_button.click()
        settle(app)
        assert chooser.selection is None and "Config file not found" in chooser.caution.text()
        assert not selection_path(env).exists()
        chooser.config_edit.setText("c.toml")  # relative to the current directory
        chooser.open_button.click()
        settle(app)
        assert chooser.selection.config == str(cfg)
        assert read_selection(env)[0].config == str(cfg)
    finally:
        chooser.close()


def test_unwritable_config_dir_reports_and_opens_nothing(app, state, env, monkeypatch):  # noqa: F811
    import grog.desktop.chooser as mod

    def denied(*_a, **_k):
        raise PermissionError("read-only config dir (injected)")

    monkeypatch.setattr(mod, "write_selection", denied)
    chooser = SourceChooser("t", state_dir=str(state), env=env)
    try:
        chooser.show()
        settle(app)
        _pick(app, chooser)
        chooser.open_button.click()
        settle(app)
        assert chooser.selection is None and chooser.isVisible()
        assert "Could not remember this source (nothing opened)" in chooser.caution.text()
    finally:
        chooser.close()


def test_return_activates_only_the_focused_button_never_from_a_text_field(app, state, env):  # noqa: F811
    """Native finding: focused Quit took Space but not Return. Return/Enter now press the
    FOCUSED button only; in the state field Return re-inspects; in other fields it does
    nothing (never Open or Quit from typing)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    def fresh():
        c = SourceChooser("t", state_dir=str(state), env=env)
        c.show()
        c.activateWindow()
        settle(app)
        return c

    for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        c = fresh()
        try:
            assert c.focusWidget() is c.quit_button
            QTest.keyClick(c.quit_button, key)
            settle(app)
            assert c.result() == c.DialogCode.Rejected and not c.isVisible()
            assert c.selection is None and not selection_path(env).exists()
        finally:
            c.close()

    c = fresh()
    try:
        c.table.selectRow(0)
        settle(app)
        for edit in (c.config_edit, c.from_edit):
            edit.setFocus()
            QTest.keyClick(edit, Qt.Key.Key_Return)
            settle(app)
            assert c.isVisible() and c.selection is None
        calls = []
        c.inspect_button.clicked.connect(lambda: calls.append(1))
        c.state_edit.setFocus()
        QTest.keyClick(c.state_edit, Qt.Key.Key_Return)
        settle(app)
        assert c.isVisible() and c.selection is None and calls == [1]
        c.table.selectRow(0)
        settle(app)
        c.remember.setChecked(False)
        c.open_button.setFocus()
        QTest.keyClick(c.open_button, Qt.Key.Key_Return)
        settle(app)
        assert c.selection is not None and c.result() == c.DialogCode.Accepted
        assert not selection_path(env).exists()
    finally:
        c.close()


def test_tab_order_reaches_every_control_with_visible_focus(app, state, env):  # noqa: F811
    c = SourceChooser("t", state_dir=str(state), env=env)
    c.show()
    c.activateWindow()
    settle(app)
    try:
        wanted = {
            c.state_edit, c.inspect_button, c.config_edit, c.from_edit, c.table,
            c.remember, c.quit_button, c.open_button,
        }  # fmt: skip
        c.table.selectRow(0)  # Open is only focusable when enabled
        settle(app)
        c.quit_button.setFocus()
        seen = []
        for _ in range(40):
            c.focusNextChild()
            settle(app)
            w = c.focusWidget()
            seen.append(w)
            if w is c.quit_button:
                break
        assert wanted <= set(seen), [type(w).__name__ for w in seen]
        assert seen[-1] is c.quit_button  # the cycle closes: no focus trap
    finally:
        c.close()
