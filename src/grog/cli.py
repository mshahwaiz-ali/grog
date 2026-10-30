"""Grog command line (docs/09-architecture.md Section 8; output format docs/02 Section 13).

Only finished commands are registered. This build (M00) exposes ``version`` and
a read-only ``doctor``. There are no buy/sell/trade/order commands, and none will
be added: Grog never places broker orders.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from typing import NoReturn, TextIO

from grog import __version__
from grog.settings import (
    CONFIG_SCHEMA_VERSION,
    STATE_DB_FILENAME,
    ConfigError,
    load_settings,
    resolve_state_dir,
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFIG = 3

STATE_SCHEMA_STATUS = "NOT DEFINED (first migration arrives with M01)"


class UsageError(Exception):
    """Raised instead of exiting so ``main`` can return a structured, testable exit code."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="grog",
        description=(
            "Grog — offline XAUUSD research and manual decision-support terminal. "
            "Rule-based local software: no AI agent, no broker orders, no automated trading."
        ),
        epilog="Commands available in this build: version, doctor.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", parser_class=_Parser)

    sub.add_parser(
        "version",
        help="print package, config schema and state schema versions",
        description="Print package, config schema and state schema versions. Writes nothing.",
    )

    doctor = sub.add_parser(
        "doctor",
        help="read-only environment and configuration report",
        description=(
            "Read-only environment, package/version, state-dir and configuration report. "
            "No install, no network, no broker connection, writes nothing."
        ),
    )
    doctor.add_argument(
        "--config",
        metavar="PATH",
        help="TOML config file (default: $XDG_CONFIG_HOME/grog/config.toml if present, "
        "else built-in offline defaults)",
    )
    doctor.add_argument(
        "--state-dir",
        metavar="PATH",
        help="isolated local state directory (default: $XDG_DATA_HOME/grog); never created",
    )
    return parser


def _cmd_version(out: TextIO) -> int:
    out.write(f"grog {__version__}\n")
    out.write(f"Config schema: {CONFIG_SCHEMA_VERSION}\n")
    out.write(f"State schema: {STATE_SCHEMA_STATUS}\n")
    return EXIT_OK


def _cmd_doctor(args: argparse.Namespace, env: Mapping[str, str], out: TextIO) -> int:
    settings = load_settings(args.config, env)
    state_dir, state_origin = resolve_state_dir(args.state_dir, env)
    # Existence checks only: never create directories or open/create the database.
    state_status = "EXISTS" if state_dir.is_dir() else "NOT CREATED"
    db_status = "AVAILABLE" if (state_dir / STATE_DB_FILENAME).is_file() else "NOT INITIALIZED"

    lines = [
        f"GROG / DOCTOR    MODE: {settings.mode}  VERSION: {__version__}",
        f"Python: {platform.python_version()}  ({sys.executable})",
        f"Config: {settings.config_source}  schema={settings.config_version}  "
        f"sha256={settings.config_hash[:12]}",
        f"Strategy profile: {settings.profile} (research only, not validated)",
        f"Symbol: {settings.symbol}  Source origin: {settings.source}  Source configured: NONE",
        f"Local state: {state_dir} [{state_origin}, {state_status}]  Database: {db_status}",
        "Market feed: NOT CONFIGURED [offline mode — expected]",
        "Live broker: NOT REQUIRED FOR REPLAY",
        f"Live safety policies unset: {len(settings.unset_live_policies())} "
        "(live readiness blocked until configured)",
        "Contract metadata: UNKNOWN  Numeric score: DISABLED",
        "Trading/orders: DISABLED",
        "Next: quote import (grog import-ticks) is not available in this build yet (M01).",
    ]
    out.write("\n".join(lines) + "\n")
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Entry point for ``grog`` and ``python -m grog``. Returns a process exit code."""
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    env = os.environ if env is None else env
    parser = _build_parser()
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except UsageError as exc:
        err.write(f"GROG ERROR code=USAGE_ERROR reason={exc}\n")
        err.write("Next: run 'grog --help' to list the commands available in this build.\n")
        return EXIT_USAGE
    except SystemExit as exc:  # --help exits through argparse after printing
        return int(exc.code or 0)

    if args.command is None:
        parser.print_help(out)
        return EXIT_OK
    try:
        if args.command == "version":
            return _cmd_version(out)
        if args.command == "doctor":
            return _cmd_doctor(args, env, out)
    except ConfigError as exc:
        err.write(f"GROG ERROR {exc}\n")
        err.write(
            "Next: fix the named field (see config/research.example.toml); nothing was written.\n"
        )
        return EXIT_CONFIG
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover
