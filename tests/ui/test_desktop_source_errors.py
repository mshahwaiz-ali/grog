"""GUI-01/GUI-14: the desktop preview refuses unusable sources without writes or tracebacks.

Every case uses a disposable state directory holding an imported source and one recorded
manual journal position. Error paths return before any QApplication is created, so no
window opens; the state database (journal included) must stay byte-identical.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import sys
from pathlib import Path

import pytest

from grog.cli import build_ui_session
from grog.cli import main as grog
from grog.desktop.main import main as desktop
from grog.domain.clock import SystemClock
from grog.journal.positions import PositionJournal
from grog.journal.store import STATE_DB_FILENAME, Store
from grog.replay import synthetic
from ui_support import open_journal, record_unlinked

SOURCE = "syn"
UNREADABLE = "is missing, unreadable or not valid compressed data"
MISMATCH = "does not match its recorded checksum or row count"


def _files(root: Path) -> dict[str, tuple[object, ...]]:
    """SHA-256 of every file's bytes (stat for files the test made unreadable)."""
    result: dict[str, tuple[object, ...]] = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.name.endswith(("-wal", "-shm")):
            continue
        st = p.stat()
        try:
            digest: object = hashlib.sha256(p.read_bytes()).hexdigest()
        except PermissionError:
            digest = "unreadable"
        result[str(p.relative_to(root))] = (digest, st.st_size, st.st_mode)
    return result


def _import(csv: Path, state_dir: Path, env: dict[str, str]) -> tuple[int, str]:
    argv = ["import-ticks", "--file", str(csv), "--source-id", SOURCE, "--origin", "SYNTHETIC"]
    argv += ["--state-dir", str(state_dir)]
    out, err = io.StringIO(), io.StringIO()
    return grog(argv, env=env, stdout=out, stderr=err), out.getvalue()


@pytest.fixture
def csv(tmp_path: Path) -> Path:
    path = tmp_path / "syn.csv"
    path.write_bytes(synthetic.generate_csv(days=2))
    return path


@pytest.fixture
def state(tmp_path: Path, csv: Path, isolated_env: dict[str, str]) -> Path:
    state_dir = tmp_path / "state"
    assert _import(csv, state_dir, isolated_env)[0] == 0
    store, journal = open_journal(tmp_path)  # same tmp_path/state database
    try:
        record_unlinked(journal)
    finally:
        store.close()
    return state_dir


def _journal_positions(state_dir: Path) -> int:
    with Store.open_read_only(state_dir / STATE_DB_FILENAME, SystemClock()) as store:
        return len(PositionJournal(store).positions())


def _batch(state_dir: Path) -> Path:
    (batch,) = (state_dir / "market").rglob("*.csv.gz")
    return batch


def _run(state_dir: Path, capsys: pytest.CaptureFixture[str], source: str = SOURCE):
    before = _files(state_dir) if state_dir.exists() else {}
    code = desktop(["--source-id", source, "--state-dir", str(state_dir)])
    after = _files(state_dir) if state_dir.exists() else {}
    return code, capsys.readouterr().err, before == after


def test_missing_qt_is_a_safe_error_without_state_access(
    state: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", None)
    code, err, unchanged = _run(state, capsys)
    assert code == 3 and "PySide6-Essentials" in err and unchanged


@pytest.fixture
def qt(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def test_absent_state_is_not_created(
    qt: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent"
    code, err, _ = _run(missing, capsys)
    assert code == 5 and "no imported state" in err
    assert not missing.exists()


def test_unknown_source_is_not_found(
    qt: None, state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err, unchanged = _run(state, capsys, source="other")
    assert code == 5 and "'other' was not found" in err and unchanged


def test_empty_database_file_is_refused_not_migrated(
    qt: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / STATE_DB_FILENAME).write_bytes(b"")
    code, err, unchanged = _run(state_dir, capsys)
    assert code == 3 and "could not open the replay" in err and unchanged
    assert (state_dir / STATE_DB_FILENAME).read_bytes() == b""


def test_corrupt_database_is_refused(
    qt: None, state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = state / STATE_DB_FILENAME
    db.write_bytes(b"not a sqlite database" * 64)
    code, err, unchanged = _run(state, capsys)
    assert code == 3 and "could not open the replay" in err and unchanged


def _damage(batch: Path, damage: str) -> None:
    if damage == "changed":  # valid gzip, bytes changed beneath the catalog after import
        raw = gzip.decompress(batch.read_bytes())
        batch.write_bytes(gzip.compress(raw.replace(b"\n", b"\r\n", 1)))
    elif damage == "not-gzip":
        batch.write_bytes(b"not gzip")
    elif damage == "deflate":  # valid gzip header, invalid DEFLATE block type -> zlib.error
        data = bytearray(batch.read_bytes())
        data[10] = 0xFF
        batch.write_bytes(bytes(data))
    elif damage == "missing":
        batch.unlink()
    elif damage == "unreadable":
        if os.geteuid() == 0:
            pytest.skip("root ignores file permissions")
        batch.chmod(0)
    else:  # pragma: no cover
        raise AssertionError(damage)


@pytest.mark.parametrize(
    ("damage", "wording"),
    [
        ("changed", MISMATCH),
        ("not-gzip", UNREADABLE),
        ("deflate", UNREADABLE),
        ("missing", UNREADABLE),
        ("unreadable", UNREADABLE),
    ],
)
def test_damaged_stored_batch_is_refused_without_traceback(
    qt: None, state: Path, capsys: pytest.CaptureFixture[str], damage: str, wording: str
) -> None:
    batch = _batch(state)
    _damage(batch, damage)
    try:
        code, err, unchanged = _run(state, capsys)
    finally:
        if batch.exists():
            batch.chmod(0o644)
    assert code == 3 and unchanged
    assert f"refused source '{SOURCE}'" in err and wording in err
    assert "journal and state were not modified" in err
    assert "same --source-id and --state-dir" in err
    assert "fresh state directory" not in err
    assert "Traceback" not in err
    assert _journal_positions(state) == 1


@pytest.mark.parametrize("damage", ["changed", "deflate", "missing"])
def test_suggested_reimport_repairs_in_place_and_keeps_journal(
    state: Path, csv: Path, isolated_env: dict[str, str], damage: str
) -> None:
    """The refusal message's remedy works in the same state directory (no Qt needed)."""
    batch = _batch(state)
    original = batch.read_bytes()
    _damage(batch, damage)
    code, out = _import(csv, state, isolated_env)
    assert code == 0 and "ALREADY_IMPORTED" in out
    assert batch.read_bytes() == original
    assert _journal_positions(state) == 1
    args = argparse.Namespace(config=None, from_ts=None, state_dir=str(state), source_id=SOURCE)
    session = build_ui_session(args, isolated_env)
    assert session is not None and session.quotes
