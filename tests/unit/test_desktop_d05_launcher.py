"""D05 launcher/source selection (GUI-10/GUI-61 boundaries): explicit or saved source
only, read-only inspection, no database creation/copy, existing alias untouched."""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import pytest

from grog.cli import main as grog
from grog.desktop import launcher
from grog.desktop.source_select import (
    Selection,
    import_guidance,
    inspect_state,
    is_temporary,
    plan_launch,
    read_selection,
    selection_path,
    write_selection,
)
from grog.replay import synthetic

REPO = Path(__file__).resolve().parents[2]


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
def state(tmp_path: Path, env: dict[str, str]) -> Path:
    csv = tmp_path / "syn.csv"
    csv.write_bytes(synthetic.generate_csv(days=2))
    state_dir = tmp_path / "durable" / "state"
    argv = ["import-ticks", "--file", str(csv), "--source-id", "syn", "--origin", "SYNTHETIC"]
    out, err = io.StringIO(), io.StringIO()
    assert grog([*argv, "--state-dir", str(state_dir)], env=env, stdout=out, stderr=err) == 0
    return state_dir


def test_selection_round_trip_is_explicit_atomic_and_quoted(env, tmp_path):
    assert read_selection(env) == (None, f"No saved desktop source ({selection_path(env)})")
    sel = Selection('s"1', str(tmp_path / 'we\\ird "dir"'), None, "2026-10-14T00:00:00Z")
    path = write_selection(sel, env)
    assert path == selection_path(env) and path.parent.name == "grog"
    assert read_selection(env) == (sel, None)
    assert [p.name for p in path.parent.iterdir()] == ["desktop-source.toml"]  # no temp left


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("source_id = [", "unreadable"),
        ('source_id = "a"\nstate_dir = "/x"\nbroker = "y"\n', "unknown keys: broker"),
        ('state_dir = "/x"\n', "needs source_id and state_dir"),
        ('source_id = "a"\nstate_dir = "/x"\nconfig = 3\n', "config must be a string"),
    ],
)
def test_broken_saved_selection_is_reported_not_repaired(env, text, needle):
    path = selection_path(env)
    path.parent.mkdir(parents=True)
    path.write_text(text)
    sel, problem = read_selection(env)
    assert sel is None and needle in problem
    assert path.read_text() == text


def test_inspect_lists_sources_read_only_and_never_creates(state, tmp_path, env):
    before = _digest(state)
    info = inspect_state(str(state), env)
    assert info.ok and info.temporary  # pytest tmp is under /tmp: flagged, still readable
    (src,) = info.sources
    assert (src.source_id, src.origin, src.symbol, src.batches) == ("syn", "SYNTHETIC", "XAUUSD", 1)
    assert src.quotes > 0 and src.first_utc.endswith("Z") and src.last_utc > src.first_utc
    assert "never current market data" in src.caution
    assert _digest(state) == before  # byte-identical: read-only inspection

    missing = tmp_path / "absent"
    info = inspect_state(str(missing), env)
    assert not info.ok and "No imported state database" in info.problem
    assert not missing.exists()

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "state.sqlite3").write_bytes(b"")
    info = inspect_state(str(empty), env)
    assert not info.ok and (empty / "state.sqlite3").read_bytes() == b""  # never migrated


def test_temporary_locations_are_flagged(tmp_path):
    assert is_temporary("/tmp/grog-demo")
    assert not is_temporary("/home/owner/.local/share/grog")


def test_plan_prefers_arguments_then_valid_saved_then_chooser(state, env, tmp_path):
    plan = plan_launch("x", "/s", None, None, env=env)
    assert plan.origin == "arguments" and plan.selection == Selection("x", "/s")
    plan = plan_launch(None, None, None, None, env=env)
    assert plan.selection is None and "No saved desktop source" in plan.reason
    write_selection(Selection("syn", str(state)), env)
    plan = plan_launch(None, None, None, None, env=env)
    assert plan.origin == "saved" and plan.selection.source_id == "syn"
    assert plan_launch(None, None, None, None, choose=True, env=env).origin == "chooser"
    write_selection(Selection("gone", str(state)), env)
    plan = plan_launch(None, None, None, None, env=env)
    assert plan.selection is None and "'gone' is not in" in plan.reason
    write_selection(Selection("syn", str(tmp_path / "nowhere")), env)
    plan = plan_launch(None, None, None, None, env=env)
    assert plan.selection is None and "unusable" in plan.reason
    assert not (tmp_path / "nowhere").exists()
    write_selection(Selection("syn", str(state), str(tmp_path / "missing.toml")), env)
    assert "does not exist" in plan_launch(None, None, None, None, env=env).reason


def test_launcher_passes_the_saved_source_to_the_existing_desktop_main(
    state, env, monkeypatch, capsys
):
    seen = []
    monkeypatch.setattr("grog.desktop.main.main", lambda argv: seen.append(argv) or 0)
    write_selection(Selection("syn", str(state), None, "2026-10-14T00:00:00Z"), env)
    assert launcher.main(["--read-only"], env=env) == 0
    assert seen == [
        ["--source-id", "syn", "--state-dir", str(state), "--from", "2026-10-14T00:00:00Z",
         "--read-only"]
    ]  # fmt: skip
    assert "(saved)" in capsys.readouterr().err


def test_launcher_without_qt_and_without_source_is_a_safe_message(env, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", None)
    assert launcher.main([], env=env) == launcher.EXIT_NO_QT
    err = capsys.readouterr().err
    assert "No saved desktop source" in err and "grog ui --mode replay" in err
    assert not selection_path(env).exists()


def test_guidance_spells_out_the_existing_import_command():
    text = import_guidance("/data/grog")
    assert "uv run grog import-ticks --file" in text and "--state-dir /data/grog" in text
    assert "nothing is downloaded or imported automatically" in text


def test_launcher_and_wrapper_have_no_hard_coded_demo_path_and_alias_is_untouched():
    script = (REPO / "scripts" / "gold-desktop.sh").read_text()
    code = (REPO / "src" / "grog" / "desktop" / "launcher.py").read_text()
    for text in (script, code):
        assert "/tmp/grog-demo" not in text and "synthetic-demo" not in text
    assert "grog.desktop.launcher" in script and "alias" not in script.replace(
        "'gold' alias, which is intentionally unchanged", ""
    )


def test_inspect_during_a_live_writer_sees_committed_wal_data_and_changes_nothing(state, env):
    """A Grog app holding the state open (WAL, uncheckpointed commit plus an open write
    transaction) must not block or be disturbed by read-only inspection."""
    import sqlite3

    from grog.domain.clock import SystemClock
    from grog.journal.store import STATE_DB_FILENAME, Store

    db = state / STATE_DB_FILENAME
    writer = Store.open(db, SystemClock())
    raw = sqlite3.connect(db)
    try:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        raw.execute("PRAGMA wal_autocheckpoint = 0")
        raw.execute("CREATE TABLE d05_probe (x INTEGER)")  # committed, only in the WAL
        raw.execute("BEGIN IMMEDIATE")  # an open write transaction held by "the app"
        raw.execute("INSERT INTO d05_probe VALUES (1)")
        main_before = db.read_bytes()
        wal_before = (state / (STATE_DB_FILENAME + "-wal")).read_bytes()
        info = inspect_state(str(state), env)
        assert info.ok and [s.source_id for s in info.sources] == ["syn"]
        assert db.read_bytes() == main_before
        assert (state / (STATE_DB_FILENAME + "-wal")).read_bytes() == wal_before
        raw.execute("ROLLBACK")
    finally:
        raw.close()
        writer.close()


def test_failed_save_keeps_the_previous_file_and_leaves_no_temp(env, monkeypatch):
    import os

    first = Selection("syn", "/data/one")
    path = write_selection(first, env)
    assert (path.stat().st_mode & 0o777) == 0o600  # private to the operator

    def boom(*_a, **_k):
        raise OSError("disk full (injected)")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="injected"):
        write_selection(Selection("other", "/data/two"), env)
    assert read_selection(env) == (first, None)
    assert [p.name for p in path.parent.iterdir()] == ["desktop-source.toml"]


def test_launcher_end_to_end_refusals_are_clean_and_write_nothing(state, env, tmp_path, capsys):
    """Through the real desktop entrypoint (no window is created on these paths)."""
    pytest.importorskip("PySide6.QtWidgets")
    before = _digest(state)
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("this is = = not toml\n")
    cases = [
        (["--source-id", "syn", "--state-dir", str(tmp_path / "nodb")], "no imported state"),
        (["--source-id", "nope", "--state-dir", str(state)], "nope"),
        (["--source-id", "syn", "--state-dir", str(state), "--config", str(bad_cfg)], "bad.toml"),
    ]
    for argv, needle in cases:
        code = launcher.main(argv, env=env)
        err = capsys.readouterr().err
        assert code != 0 and needle in err, (argv, code, err)
        assert "Traceback" not in err
    assert _digest(state) == before
    assert not (tmp_path / "nodb").exists() and not selection_path(env).exists()


def _fake_uv(bin_dir: Path) -> Path:
    """A stand-in ``uv`` that records its cwd and argv (no project sync, no network)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    uv = bin_dir / "uv"
    uv.write_text('#!/usr/bin/env bash\nprintf "cwd=%s\\n" "$PWD"\nprintf "arg=%s\\n" "$@"\n')
    uv.chmod(0o755)
    return uv


def test_wrapper_runs_from_any_cwd_through_a_symlink_and_keeps_relative_paths(tmp_path):
    import subprocess

    bin_dir = tmp_path / "fake bin"
    _fake_uv(bin_dir)
    where = tmp_path / "some where"
    where.mkdir()
    link = tmp_path / "my bin" / "gold-desktop"
    link.parent.mkdir()
    link.symlink_to(REPO / "scripts" / "gold-desktop.sh")
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    out = subprocess.run(
        ["bash", str(link), "--state-dir", "./rel dir", "--source-id", "a b'c"],
        cwd=where, env=env, capture_output=True, text=True, check=True,
    ).stdout.splitlines()  # fmt: skip
    assert out[0] == f"cwd={where}"  # caller's directory kept: ./rel dir means HERE
    assert out[1:] == [
        "arg=run", "arg=--project", f"arg={REPO.resolve()}", "arg=--locked", "arg=--extra",
        "arg=desktop", "arg=python", "arg=-m", "arg=grog.desktop.launcher",
        "arg=--state-dir", "arg=./rel dir", "arg=--source-id", "arg=a b'c",
    ]  # fmt: skip


def test_wrapper_without_uv_explains_and_starts_nothing(tmp_path):
    import shutil
    import subprocess

    empty = tmp_path / "bin"
    empty.mkdir()
    for tool in ("readlink", "dirname"):  # coreutils only; deliberately no uv
        (empty / tool).symlink_to(shutil.which(tool))
    before = sorted(p.name for p in tmp_path.rglob("*"))
    res = subprocess.run(
        ["/bin/bash", str(REPO / "scripts" / "gold-desktop.sh")],
        cwd=tmp_path, env={"PATH": str(empty), "HOME": str(tmp_path)},
        capture_output=True, text=True,
    )  # fmt: skip
    assert res.returncode == 3 and res.stdout == ""
    assert "'uv' was not found on PATH; nothing was started or changed" in res.stderr
    assert "grog ui --mode replay" in res.stderr  # the Textual fallback is named
    assert sorted(p.name for p in tmp_path.rglob("*")) == before  # nothing created


def test_selection_with_control_characters_round_trips(env):
    for value in ["/n\nl", "/c\x01x", "/t\tab", "/d\x7f", '/q"\\']:
        sel = Selection("syn", value)
        write_selection(sel, env)
        assert read_selection(env) == (sel, None), repr(value)


def test_guidance_quotes_paths_with_spaces():
    assert "--state-dir '/a b/it'\"'\"'s'" in import_guidance("/a b/it's")
