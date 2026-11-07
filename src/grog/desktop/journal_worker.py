"""The single local-journal owner: one QObject living on its own QThread (D03).

This is the only desktop object that opens a writable SQLite connection. It opens the
existing state database with ``Store.open`` (which applies pending migrations after the
documented pre-migration backup), runs ``PositionJournal.restore_on_startup`` exactly
once per open, and then executes manual-record commands through the validated
``PositionJournal`` write methods only. If the writable open or the restart
reconciliation fails it falls back to ``Store.open_read_only``: saved records are then
shown READ ONLY / UNVERIFIED and every command is refused. It never creates a missing
database. All results cross to the GUI as detached immutable values; the GUI never sees
the Store, the connection or a live record.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from grog.desktop.journal_model import (
    Command,
    CommandResult,
    JournalMode,
    JournalSnapshot,
    execute,
    read_snapshot,
)
from grog.desktop.loading import LoadRequest, database_path
from grog.domain.clock import SystemClock
from grog.journal.positions import PositionJournal, PositionState
from grog.journal.store import Store

WRITABLE_NOTE = "Writable local journal (manual records only, no broker connection)"
READ_ONLY_NOTE = (
    "READ ONLY — saved records are shown UNVERIFIED; restart reconciliation was not "
    "performed and nothing can be recorded"
)

Opener = Callable[[Path], Store]


def _writable(db: Path) -> Store:
    return Store.open(db, SystemClock())


def _read_only(db: Path) -> Store:
    """SQLite read-only open. A WAL database in a directory the user cannot write cannot
    create its shared-memory file; it is then read as an immutable file, but only when no
    write-ahead log exists (otherwise committed records could be missing: refuse)."""
    store = None
    try:
        store = Store.open_read_only(db, SystemClock())
        store._conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return store
    except sqlite3.OperationalError:
        if store is not None:
            store.close()
        wal = db.with_name(db.name + "-wal")
        if wal.exists() and wal.stat().st_size > 0:
            raise
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    store = Store(conn, SystemClock(), db)
    store.frozen_snapshot = True  # type: ignore[attr-defined] - desktop-side marker only
    return store


class JournalWorker(QObject):
    """Owns at most one Store at a time. All slots run on the journal thread."""

    snapshot = Signal(object)  # JournalSnapshot
    result = Signal(object)  # CommandResult
    stopped = Signal()

    def __init__(
        self,
        writable_opener: Opener = _writable,
        read_only_opener: Opener = _read_only,
        configure: Callable[[PositionJournal], None] | None = None,  # tests: fault hooks
    ) -> None:
        super().__init__()
        self._open_writable = writable_opener
        self._open_read_only = read_only_opener
        self._configure = configure
        self._store: Store | None = None
        self._journal: PositionJournal | None = None
        self._mode = JournalMode.OPENING
        self._reason = ""
        self._restored: tuple[str, ...] = ()
        self._source_id = ""
        self._generation = 0
        self._sequence = 0
        self._closed = False
        self.owner_thread_name: str | None = None  # test evidence only

    # ------------------------------------------------------------------ helpers

    def _close(self) -> None:
        store, self._store, self._journal = self._store, None, None
        if store is not None:
            try:
                store.close()
            except sqlite3.Error:
                pass

    def _publish(self) -> None:
        self._sequence += 1
        journal = self._journal
        if journal is not None:
            try:
                snap = read_snapshot(
                    journal,
                    generation=self._generation,
                    sequence=self._sequence,
                    source_id=self._source_id,
                    mode=self._mode,
                    reason=self._reason,
                    restored=self._restored,
                )
            except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
                # Fail closed: never an invented empty overlay or position list.
                self._close()
                self._mode = JournalMode.UNAVAILABLE
                self._reason = (
                    f"Local journal unreadable ({type(exc).__name__}: {exc}); nothing is "
                    f"assumed · {self._reason}"
                )
            else:
                self.snapshot.emit(snap)
                return
        self.snapshot.emit(
            JournalSnapshot(
                self._generation,
                self._sequence,
                self._source_id,
                self._mode,
                self._reason,
                (),
                (),
                (),
                (),
            )
        )

    # ------------------------------------------------------------------ slots

    @Slot(object, int)
    def open(self, request: LoadRequest, generation: int) -> None:
        """Open the journal for one source generation (startup or source switch)."""
        import threading

        self.owner_thread_name = threading.current_thread().name
        if self._closed:
            return
        self._close()
        self._source_id, self._generation, self._sequence = request.source_id, generation, 0
        self._restored = ()
        try:
            _state_dir, db = database_path(request)
        except Exception as exc:  # noqa: BLE001 - reported, never assumed
            self._mode, self._reason = JournalMode.UNAVAILABLE, f"State directory invalid: {exc}"
            self._publish()
            return
        if not Path(db).is_file():  # never create a database from the desktop
            self._mode = JournalMode.UNAVAILABLE
            self._reason = f"No local state database at {db}; nothing can be recorded"
            self._publish()
            return
        failure = ""
        store = None
        try:
            store = self._open_writable(Path(db))
            journal = PositionJournal(store)
            if self._configure is not None:
                self._configure(journal)
            with store.transaction():  # write-lock probe first: a busy/locked DB is not
                pass  # "writable", and restart reconciliation is then not attempted
            monitoring = {
                p.position_id
                for p in journal.open_positions()
                if p.state is PositionState.MONITORING
            }
            # the service returns every open position afterwards; report only those this
            # start actually marked RECONCILIATION_REQUIRED
            restored = [p for p in journal.restore_on_startup() if p.position_id in monitoring]
        except Exception as exc:  # noqa: BLE001 - locked/read-only/corrupt: fall back safely
            if store is not None:
                try:
                    store.close()
                except sqlite3.Error:
                    pass
            failure = f"{type(exc).__name__}: {exc}"
        else:
            self._store, self._journal = store, journal
            self._mode, self._restored = (
                JournalMode.WRITABLE,
                tuple(p.position_id for p in restored),
            )
            n = len(self._restored)
            self._reason = (
                f"{WRITABLE_NOTE}: {n} open position(s) from earlier sessions marked "
                "RECONCILIATION REQUIRED at this start — verify them at your broker"
                if n
                else f"{WRITABLE_NOTE}: no position needed restart reconciliation now"
            )
            self._publish()
            return
        try:
            store = self._open_read_only(Path(db))
            self._store, self._journal = store, PositionJournal(store)
            self._mode = JournalMode.READ_ONLY
            self._reason = f"{READ_ONLY_NOTE} (writable open failed: {failure})"
            if getattr(store, "frozen_snapshot", False):
                self._reason += (
                    " · FROZEN SNAPSHOT: the file was opened immutable at start (its folder is "
                    "not writable and no write-ahead log was pending); Refresh does not see "
                    "changes made later by another program — restart Gold to re-read"
                )
        except Exception as exc:  # noqa: BLE001
            self._mode = JournalMode.UNAVAILABLE
            self._reason = (
                f"Local journal unavailable (writable open failed: {failure}; read-only open "
                f"failed: {type(exc).__name__}: {exc})"
            )
        self._publish()

    @Slot(int)
    def reload(self, generation: int) -> None:
        if self._closed or generation != self._generation:
            return
        self._publish()

    @Slot(object)
    def submit(self, cmd: Command) -> None:
        """Execute one confirmed command; the result is truthful about what was saved."""

        def refuse(code: str, message: str) -> None:
            self.result.emit(
                CommandResult(
                    cmd.token,
                    cmd.kind,
                    cmd.action_id,
                    False,
                    False,
                    code,
                    f"NOT SAVED — {code}: {message}",
                    cmd.position_id,
                )
            )

        if self._closed:
            refuse("SHUTTING_DOWN", "Grog is closing; nothing was written")
            return
        if cmd.generation != self._generation or cmd.source_id != self._source_id:
            refuse("STALE_SOURCE", "the source changed since this form opened")
            return
        if self._mode is not JournalMode.WRITABLE or self._journal is None:
            refuse("READ_ONLY", f"the local journal is {self._mode.value}: {self._reason}")
            return
        res = execute(self._journal, cmd)
        self._publish()  # the GUI sees the records the result describes before the result
        self.result.emit(res)

    @Slot()
    def shutdown(self) -> None:
        """Queued after any submitted command, so an in-flight write finishes first."""
        self._closed = True
        self._close()
        self.stopped.emit()
