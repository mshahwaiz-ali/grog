"""D05 one-command desktop launcher: ``python -m grog.desktop.launcher`` (wrapped by
``scripts/gold-desktop.sh``). Separate entrypoint; the existing ``gold`` alias, the
``grog`` CLI and the Textual fallback (``grog ui --mode replay …``) are unchanged.

Source resolution (never a hard-coded demo path): explicit ``--source-id`` arguments,
else the operator's saved selection (``$XDG_CONFIG_HOME/grog/desktop-source.toml``) if
its source is still present (checked read-only), else the source chooser
("NO DATA LOADED"). The chosen source then opens through the same
``grog.desktop.main`` path (same checks, exit codes and journal ownership).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from grog.desktop.source_select import Selection, plan_launch

EXIT_NO_QT = 3


def main_argv(sel: Selection, *, read_only: bool) -> list[str]:
    argv = ["--source-id", sel.source_id]
    if sel.state_dir:
        argv += ["--state-dir", sel.state_dir]
    if sel.config:
        argv += ["--config", sel.config]
    if sel.from_ts:
        argv += ["--from", sel.from_ts]
    if read_only:
        argv.append("--read-only")
    return argv


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gold-desktop",
        description="Gold desktop — offline replay of a local source you choose; manual "
        "records are local journal entries only (no broker orders)",
    )
    parser.add_argument("--source-id", help="imported source ID (skips the saved selection)")
    parser.add_argument("--state-dir", help="local state directory (never created)")
    parser.add_argument("--config", help="replay configuration TOML")
    parser.add_argument("--from", dest="from_ts", help="visible replay window start UTC")
    parser.add_argument("--read-only", action="store_true", help="open the journal read-only")
    parser.add_argument("--choose", action="store_true", help="always show the source chooser")
    args = parser.parse_args(argv)

    plan = plan_launch(
        args.source_id, args.state_dir, args.config, args.from_ts, choose=args.choose, env=env
    )
    selection = plan.selection
    if selection is None:
        try:
            from PySide6.QtWidgets import QApplication, QDialog
        except ImportError:
            print(
                "Gold desktop requires PySide6-Essentials (uv sync --locked --extra desktop). "
                f"{plan.reason}. The terminal app is unchanged: grog ui --mode replay …",
                file=sys.stderr,
            )
            return EXIT_NO_QT
        from grog.desktop.chooser import SourceChooser

        app = QApplication.instance() or QApplication(["gold-desktop"])  # noqa: F841
        chooser = SourceChooser(
            plan.reason, state_dir=args.state_dir or "", config=args.config or "", env=env
        )
        if chooser.exec() != QDialog.DialogCode.Accepted or chooser.selection is None:
            print("Gold desktop: no source opened; nothing was changed.", file=sys.stderr)
            return 0
        selection = chooser.selection
        if chooser.saved_to:
            print(f"Gold desktop: remembered source in {chooser.saved_to}", file=sys.stderr)
    else:
        where = selection.state_dir or "default state directory"
        print(
            f"Gold desktop: opening source '{selection.source_id}' from {where} "
            f"({plan.origin}); --choose shows the chooser",
            file=sys.stderr,
        )
    from grog.desktop.main import main as desktop_main

    return desktop_main(main_argv(selection, read_only=args.read_only))


if __name__ == "__main__":
    raise SystemExit(main())
