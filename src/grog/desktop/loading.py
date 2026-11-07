"""Source loading and read-only journal access for the desktop replay owner (no Qt).

Everything here runs on the replay worker thread: the source catalog is opened read-only,
quotes are verified and the causal pre-roll happens inside the existing
``build_ui_session``; the journal is opened read-only, read and closed on the same
thread. Nothing here writes, migrates or reconciles operator records.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from grog.market_data.batches import BatchIntegrityError
from grog.settings import STATE_DB_FILENAME, ConfigError, resolve_state_dir

if TYPE_CHECKING:
    from grog.journal.positions import ManualPosition
    from grog.replay.session import ReplaySession

EXIT_LOAD_FAILED = 3
EXIT_NOT_FOUND = 5


@dataclass(frozen=True, slots=True)
class LoadRequest:
    source_id: str
    config: str | None = None
    state_dir: str | None = None
    from_ts: str | None = None

    def namespace(self) -> argparse.Namespace:
        return argparse.Namespace(
            source_id=self.source_id,
            config=self.config,
            state_dir=self.state_dir,
            from_ts=self.from_ts,
        )


class SourceNotFound(LookupError):
    pass


def database_path(request: LoadRequest, env: Mapping[str, str] | None = None):
    state_dir, _origin = resolve_state_dir(request.state_dir, os.environ if env is None else env)
    return state_dir, state_dir / STATE_DB_FILENAME


def load_session(request: LoadRequest, env: Mapping[str, str] | None = None) -> ReplaySession:
    """Existing source checks, quote verification and causal pre-roll (may take seconds)."""
    from grog.cli import build_ui_session

    session = build_ui_session(request.namespace(), os.environ if env is None else env)
    if session is None:
        state_dir, _db = database_path(request, env)
        raise SourceNotFound(f"source {request.source_id!r} was not found in {state_dir}")
    return session


def read_journal(
    request: LoadRequest, env: Mapping[str, str] | None = None
) -> tuple[dict[str, tuple[str, str | None]] | None, list[ManualPosition] | None, str]:
    """One read-only journal read on the calling thread; ``None`` when it is unreadable."""
    from grog.domain.clock import SystemClock
    from grog.journal.positions import PositionJournal
    from grog.journal.store import Store

    _state_dir, db = database_path(request, env)
    note = "Read-only snapshot of stored records · restart reconciliation not performed"
    try:
        with Store.open_read_only(db, SystemClock()) as store:
            journal = PositionJournal(store)
            return journal.signal_actions(request.source_id), journal.open_positions(), note
    except (OSError, ValueError, sqlite3.Error) as exc:
        return None, None, f"Journal unavailable (read-only open failed: {exc})"


def describe_failure(exc: BaseException, source_id: str) -> tuple[int, str]:
    """Exit code and truthful message for a load failure (same wording as D00)."""
    if isinstance(exc, SourceNotFound):
        return EXIT_NOT_FOUND, f"Gold desktop: {exc}"
    if isinstance(exc, BatchIntegrityError):
        # read_batch_quotes chains the I/O or decompression error for an unreadable file
        # and raises without a cause when readable content disagrees with the catalog.
        if exc.__cause__ is not None:
            problem = "is missing, unreadable or not valid compressed data"
        else:
            problem = "does not match its recorded checksum or row count"
        return EXIT_LOAD_FAILED, (
            f"Gold desktop refused source {source_id!r}: {exc}. The stored quote batch "
            f"{problem}. Nothing was changed: the journal and state were not modified. "
            "Restore that batch file from a backup, or re-import the original CSV with "
            "'grog import-ticks' using the same --source-id and --state-dir to repair it."
        )
    if isinstance(exc, (OSError, ValueError, sqlite3.Error, ConfigError)):
        return EXIT_LOAD_FAILED, f"Gold desktop could not open the replay: {exc}"
    return EXIT_LOAD_FAILED, f"Gold desktop stopped: unexpected {type(exc).__name__}: {exc}"
