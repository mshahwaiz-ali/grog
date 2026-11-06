"""Standalone D01 read-only native replay Overview; no CLI or alias cutover."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gold desktop Overview — offline replay, simulated, read-only"
    )
    parser.add_argument("--source-id", required=True, help="existing imported quote source")
    parser.add_argument("--config", help="existing replay configuration TOML")
    parser.add_argument("--state-dir", help="existing local state directory")
    parser.add_argument("--from", dest="from_ts", help="visible replay window start UTC")
    args = parser.parse_args(argv)

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Gold desktop requires PySide6-Essentials. Use the tested optional Qt runtime; "
            "the terminal app is unchanged.",
            file=sys.stderr,
        )
        return 3

    from grog.cli import build_ui_session
    from grog.desktop.window import GoldWindow
    from grog.domain.clock import SystemClock
    from grog.journal.positions import PositionJournal
    from grog.journal.store import Store
    from grog.settings import STATE_DB_FILENAME, ConfigError, resolve_state_dir

    state_dir, _origin = resolve_state_dir(args.state_dir, os.environ)
    database = state_dir / STATE_DB_FILENAME
    if not database.is_file():
        print(f"Gold desktop: no imported state exists at {state_dir}", file=sys.stderr)
        return 5

    try:
        session = build_ui_session(args, os.environ)
        if session is None:
            print(
                f"Gold desktop: source {args.source_id!r} was not found in {state_dir}",
                file=sys.stderr,
            )
            return 5
        # Unlike the Textual journal, this preview never invokes restore_on_startup.
        # It must not update operator records or make unreconciled positions look verified.
        with Store.open_read_only(database, SystemClock()) as store:
            journal = PositionJournal(store)
            application = QApplication.instance() or QApplication(["gold-desktop"])
            window = GoldWindow(session, journal)
            window.show()
            return int(application.exec())
    except (OSError, ValueError, sqlite3.Error, ConfigError) as exc:
        print(f"Gold desktop could not open the replay: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
