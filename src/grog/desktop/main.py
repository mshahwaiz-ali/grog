"""Standalone native Gold desktop (replay-backed; D03 local manual records); no CLI or
alias cutover.

The window opens immediately; the source is verified, loaded and causally pre-rolled on
the replay owner thread. A source that cannot be loaded before the first engine frame
ends the program with the same messages and exit codes as before (3 or 5), unchanged
state and no traceback.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gold desktop — offline replay, simulated; manual records are local "
        "journal entries only (no broker orders)"
    )
    parser.add_argument("--source-id", required=True, help="existing imported quote source")
    parser.add_argument("--config", help="existing replay configuration TOML")
    parser.add_argument("--state-dir", help="existing local state directory")
    parser.add_argument("--from", dest="from_ts", help="visible replay window start UTC")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="open the local journal read-only (saved records UNVERIFIED, nothing recorded)",
    )
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

    from grog.desktop.journal_worker import JournalWorker
    from grog.desktop.loading import EXIT_NOT_FOUND, LoadRequest, database_path
    from grog.desktop.replay_worker import ReplayWorker
    from grog.desktop.window import GoldWindow

    request = LoadRequest(args.source_id, args.config, args.state_dir, args.from_ts)
    state_dir, database = database_path(request)
    if not database.is_file():
        print(f"Gold desktop: no imported state exists at {state_dir}", file=sys.stderr)
        return EXIT_NOT_FOUND

    application = QApplication.instance() or QApplication(["gold-desktop"])
    failure: list[int] = []

    def startup_failed(code: int, message: str) -> None:
        print(message, file=sys.stderr)
        failure.append(code)
        window.close()
        application.exit(code)

    def pending_journal(_request: LoadRequest):
        # The journal owner thread reads (and alone writes) records and pushes them.
        return None, None, "Opening the local journal…"

    def refuse_writable(_db):
        raise PermissionError("--read-only requested")

    journal = JournalWorker(writable_opener=refuse_writable) if args.read_only else JournalWorker()
    window = GoldWindow(
        request,
        worker=ReplayWorker(journal_reader=pending_journal),
        journal_worker=journal,
        on_startup_failure=startup_failed,
    )
    window.show()
    code = int(application.exec())
    window.shutdown()
    return failure[0] if failure else code


if __name__ == "__main__":
    raise SystemExit(main())
