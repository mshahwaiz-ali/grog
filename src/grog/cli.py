"""Grog command line (docs/09-architecture.md Section 8; output format docs/02 Section 13).

Only finished commands are registered: ``version``, a read-only ``doctor``,
``import-ticks`` (M01, local state only), ``replay`` (M06, SIMULATED research run in local
state), a read-only ``report`` (M06) and the view-only Textual workstation ``ui`` (M07).
There are no buy/sell/trade/order commands, and none will be added: Grog never places
broker orders.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, TextIO

from grog import __version__
from grog.market_data.batches import CatalogError
from grog.market_data.import_csv import CsvImportError
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
EXIT_IMPORT_REJECTED = 4
EXIT_NOT_FOUND = 5


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
        epilog=(
            "Commands available in this build: version, doctor, import-ticks, replay, report, ui."
        ),
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
    imp = sub.add_parser(
        "import-ticks",
        help="strictly validate and durably import one canonical BID/ASK CSV v1 file",
        description=(
            "Validate a canonical CSV v1 file (provider_time_utc_ms,received_time_utc_ms,bid,ask) "
            "in full, checksum it and persist one immutable source batch in local Grog state. "
            "Any invalid row rejects the whole file; re-importing identical bytes is a no-op. "
            "Offline only: no broker, no network."
        ),
    )
    imp.add_argument("--file", required=True, metavar="PATH", help="canonical CSV v1 file")
    imp.add_argument("--source-id", required=True, metavar="ID", help="explicit source ID")
    imp.add_argument(
        "--origin", required=True, choices=["SYNTHETIC", "HISTORICAL"], help="source origin"
    )
    imp.add_argument(
        "--state-dir",
        metavar="PATH",
        help="isolated local state directory (default: $XDG_DATA_HOME/grog)",
    )
    rep = sub.add_parser(
        "replay",
        help="deterministic SIMULATED research replay of one imported source",
        description=(
            "Replay every committed quote of one source in stable order on a virtual UTC clock "
            "through bars, H1/M15/M5 context, S1 and signal eligibility; record a SIMULATED "
            "research run locally and print its evidence report. Quotes before --from are "
            "processed as pre-roll (history only); processing stops at --to. "
            "No real trades, no broker, no network."
        ),
    )
    rep.add_argument("--source-id", required=True, metavar="ID", help="imported source ID")
    rep.add_argument("--from", dest="from_ts", metavar="ISO_UTC", help="window start (Z/offset)")
    rep.add_argument("--to", dest="to_ts", metavar="ISO_UTC", help="window end (Z/offset)")
    rep.add_argument("--config", metavar="PATH", help="TOML config file (frozen into the run)")
    rep.add_argument(
        "--state-dir",
        metavar="PATH",
        help="isolated local state directory (default: $XDG_DATA_HOME/grog)",
    )
    rpt = sub.add_parser(
        "report",
        help="read-only summary of a recorded research run",
        description=(
            "Summarize a recorded research run: source fidelity, data gaps, assumptions, "
            "outcome caveats. Read-only; text by default, stable JSON optional."
        ),
    )
    rpt.add_argument("--run-id", required=True, metavar="ID", help="research run ID")
    rpt.add_argument("--format", choices=["text", "json"], default="text", help="output format")
    rpt.add_argument(
        "--state-dir",
        metavar="PATH",
        help="isolated local state directory (default: $XDG_DATA_HOME/grog); never created",
    )
    ui = sub.add_parser(
        "ui",
        help="interactive offline research workstation (Textual, view only)",
        description=(
            "Textual workstation over one imported source. REPLAY pre-rolls causal history "
            "for MTF warm-up and starts PAUSED: Space play/pause, . step one quote, +/- pacing "
            "50 ev/s, 500 ev/s, FAST. SIMULATED research only; no broker, no orders; writes "
            "nothing (state is opened read-only)."
        ),
    )
    ui.add_argument("--mode", required=True, choices=["replay", "reference"], help="UI mode")
    ui.add_argument("--source-id", metavar="ID", help="imported source ID (replay mode)")
    ui.add_argument("--from", dest="from_ts", metavar="ISO_UTC", help="visible window start")
    ui.add_argument("--config", metavar="PATH", help="TOML config file")
    ui.add_argument(
        "--state-dir",
        metavar="PATH",
        help="isolated local state directory (default: $XDG_DATA_HOME/grog); never created",
    )
    return parser


def build_ui_session(args: argparse.Namespace, env: Mapping[str, str]):
    """Load a source read-only and build the paused replay session (no writes)."""
    from grog.domain.clock import SystemClock
    from grog.journal.store import LATEST_SCHEMA_VERSION, Store
    from grog.market_data.batches import load_source_quotes
    from grog.replay.service import policy_from_settings
    from grog.replay.session import ReplaySession, SourceInfo
    from grog.settings import parse_utc_timestamp_ms

    settings = load_settings(args.config, env)
    from_ms = None if args.from_ts is None else parse_utc_timestamp_ms(args.from_ts, "--from")
    state_dir, _origin = resolve_state_dir(args.state_dir, env)
    db = state_dir / STATE_DB_FILENAME
    if not db.is_file():
        return None
    store = Store.open_read_only(db, SystemClock())
    try:
        source = store.get_source(args.source_id)
        if source is None:
            return None
        batches = store.list_batches(args.source_id)
        quotes = load_source_quotes(store, state_dir, args.source_id)
    finally:
        store.close()
    origins = {b.origin for b in batches}
    info = SourceInfo(
        source_id=source.source_id,
        origin="/".join(sorted(o.value for o in origins)) or source.kind.value,
        raw_symbol=quotes[0].raw_symbol if quotes else source.symbol,
        batch_sha256s=tuple(b.sha256 for b in batches),
        batch_paths=tuple(b.path for b in batches),
        config_hash=settings.config_hash,
        config_version=settings.config_version,
        state_schema_version=LATEST_SCHEMA_VERSION,
    )
    return ReplaySession(quotes, info, policy_from_settings(settings, origins), from_ms=from_ms)


def _cmd_ui(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, err: TextIO) -> int:
    if args.mode == "reference":
        err.write(
            "GROG ERROR code=NOT_CONFIGURED reason=no read-only reference feed is configured "
            "(later milestone); no live or mock quotes are shown\n"
        )
        err.write("Next: grog ui --mode replay --source-id ID [--state-dir PATH]\n")
        return EXIT_CONFIG
    if not args.source_id:
        raise UsageError("--source-id is required for --mode replay")
    session = build_ui_session(args, env)
    if session is None:
        return _not_found(err, f"source {args.source_id!r}")
    from grog.ui.app import GrogApp

    GrogApp(session).run()
    return EXIT_OK


def _cmd_replay(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, err: TextIO) -> int:
    from grog.domain.clock import SystemClock
    from grog.journal.research import comparable_runs
    from grog.journal.store import Store
    from grog.replay.report import render_text
    from grog.replay.service import replay_source
    from grog.settings import parse_utc_timestamp_ms

    settings = load_settings(args.config, env)
    from_ms = None if args.from_ts is None else parse_utc_timestamp_ms(args.from_ts, "--from")
    to_ms = None if args.to_ts is None else parse_utc_timestamp_ms(args.to_ts, "--to")
    if from_ms is not None and to_ms is not None and to_ms <= from_ms:
        raise UsageError("--to must be after --from")
    state_dir, _origin = resolve_state_dir(args.state_dir, env)
    db = state_dir / STATE_DB_FILENAME
    if not db.is_file():
        return _not_found(err, f"source {args.source_id!r} (no local state at {state_dir})")
    with Store.open(db, SystemClock()) as store:
        if store.get_source(args.source_id) is None:
            return _not_found(err, f"source {args.source_id!r}")
        _result, run = replay_source(
            store, state_dir, args.source_id, settings, from_ms=from_ms, to_ms=to_ms
        )
        others = comparable_runs(store._conn, run)
    out.write(render_text(run, others))
    out.write(f"Next: grog report --run-id {run.run_id} [--format json]\n")
    return EXIT_OK


def _not_found(out: TextIO, what: str) -> int:
    out.write(f"GROG ERROR code=NOT_FOUND reason={what} not found\n")
    return EXIT_NOT_FOUND


def _cmd_report(args: argparse.Namespace, env: Mapping[str, str], out: TextIO, err: TextIO) -> int:
    import json

    from grog.journal.research import comparable_runs, get_run, open_read_only
    from grog.replay.report import render_text

    state_dir, _origin = resolve_state_dir(args.state_dir, env)
    db = state_dir / STATE_DB_FILENAME
    if not db.is_file():
        return _not_found(err, f"run {args.run_id!r}")
    conn = open_read_only(db)
    try:
        has_runs = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_runs'"
        ).fetchone()
        run = get_run(conn, args.run_id) if has_runs else None
        if run is None or run.status != "COMPLETE":
            return _not_found(err, f"completed run {args.run_id!r}")
        others = comparable_runs(conn, run)
    finally:
        conn.close()
    if args.format == "json":
        doc = {
            "run": {
                "run_id": run.run_id,
                "status": run.status,
                "code_version": run.code_version,
                "config_hash": run.config_hash,
                "data_hash": run.data_hash,
                "params_hash": run.params_hash,
            },
            "result": run.result,
            "comparable_runs": [
                {"run_id": r.run_id, "config_hash": r.config_hash, "params_hash": r.params_hash}
                for r in others
            ],
        }
        out.write(json.dumps(doc, sort_keys=True, indent=2) + "\n")
    else:
        out.write(render_text(run, others))
    return EXIT_OK


def _cmd_version(out: TextIO) -> int:
    out.write(f"grog {__version__}\n")
    out.write(f"Config schema: {CONFIG_SCHEMA_VERSION}\n")
    from grog.journal.store import LATEST_SCHEMA_VERSION

    out.write(f"State schema: {LATEST_SCHEMA_VERSION}\n")
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
        "Next: import a synthetic BID/ASK fixture: grog import-ticks --file PATH "
        "--source-id ID --origin SYNTHETIC|HISTORICAL [--state-dir PATH]",
    ]
    out.write("\n".join(lines) + "\n")
    return EXIT_OK


def _fmt_utc(ms: int) -> str:
    stamp = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return stamp.strftime("%Y-%m-%d %H:%M:%S.") + f"{ms % 1000:03d} UTC"


def _cmd_import_ticks(args: argparse.Namespace, env: Mapping[str, str], out: TextIO) -> int:
    from grog.domain.clock import SystemClock
    from grog.journal.store import Store
    from grog.market_data.batches import import_parsed, read_and_parse

    state_dir, _origin = resolve_state_dir(args.state_dir, env)
    # Validate the whole file before touching local state at all.
    parsed, data = read_and_parse(Path(args.file), source_id=args.source_id, origin=args.origin)
    with Store.open(state_dir / STATE_DB_FILENAME, SystemClock()) as store:
        result = import_parsed(parsed, data, state_dir=state_dir, catalog=store)
    b, st = result.batch, result.stats
    lines = [
        f"GROG / IMPORT    STATUS: {result.status}  FIDELITY: {b.origin.value}",
        f"Source: {b.source_id}  Origin: {b.origin.value}  Symbol: XAUUSD",
        f"File: {args.file}",
        f"SHA256: {b.sha256}",
        f"Batch: {b.batch_id}",
        f"Rows: {st.row_count} accepted | 0 rejected (strict whole-file validation)",
        f"Range UTC (provider): {_fmt_utc(st.min_provider_ms)} .. {_fmt_utc(st.max_provider_ms)}",
        f"Same-ms distinct quotes retained: {st.same_ms_quote_count}",
        f"Provider time ahead of receipt: {st.provider_ahead_count} quotes "
        f"(max {st.max_provider_ahead_ms} ms; skew logged, not treated as latency)",
        f"Gaps: NOT EVALUATED (gap threshold OPEN); largest provider interval "
        f"{st.max_provider_interval_ms} ms",
        "Data fidelity: BID+ASK every row; contract/fees: UNKNOWN; broker-verified: NO",
        f"Stored: {result.stored_path}",
    ]
    if result.status == "ALREADY_IMPORTED":
        lines.append("Already imported: identical checksum for this source; nothing changed.")
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
        if args.command == "import-ticks":
            return _cmd_import_ticks(args, env, out)
        if args.command == "replay":
            return _cmd_replay(args, env, out, err)
        if args.command == "report":
            return _cmd_report(args, env, out, err)
        if args.command == "ui":
            return _cmd_ui(args, env, out, err)
    except UsageError as exc:
        err.write(f"GROG ERROR code=USAGE_ERROR reason={exc}\n")
        return EXIT_USAGE
    except CsvImportError as exc:
        err.write(f"{exc.describe()}; batch NOT committed; prior data unchanged.\n")
        err.write("Next: fix the named line/field or import another file.\n")
        return EXIT_IMPORT_REJECTED
    except CatalogError as exc:
        err.write(
            f"IMPORT_REJECTED line=0 field=--source-id reason={exc.reason.value} "
            f"detail={exc.detail}; batch NOT committed; prior data unchanged.\n"
        )
        err.write("Next: use a distinct source ID or a non-overlapping file.\n")
        return EXIT_IMPORT_REJECTED
    except ConfigError as exc:
        err.write(f"GROG ERROR {exc}\n")
        err.write(
            "Next: fix the named field (see config/research.example.toml); nothing was written.\n"
        )
        return EXIT_CONFIG
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover
