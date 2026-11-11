"""Bounded, read-only view of the last MT5 exporter records for one source.

For operator diagnostics only: no cursor writes, historical reconstruction, feed
qualification or trading decisions. ReferenceSession remains the health authority.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from grog.adapters.mt5_reference.format import (
    FILE_NAME,
    GapRecord,
    HeartbeatRecord,
    RecordError,
    TickRecord,
    parse_line,
)
from grog.domain.ids import is_valid_source_id

MAX_TAIL_BYTES = 65536


class TailState(StrEnum):
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    NO_COMPLETE_RECORDS = "NO_COMPLETE_RECORDS"
    MALFORMED_TAIL = "MALFORMED_TAIL"
    GAP_IN_TAIL = "GAP_IN_TAIL"
    HEARTBEAT_ONLY = "HEARTBEAT_ONLY"
    LIVE_TICK_IN_TAIL = "LIVE_TICK_IN_TAIL"
    NO_LIVE_TICK_IN_TAIL = "NO_LIVE_TICK_IN_TAIL"


@dataclass(frozen=True, slots=True)
class TailProbe:
    source_id: str
    file: Path | None
    state: TailState
    bytes_examined: int
    heartbeat_count: int
    live_tick_count: int
    backfill_tick_count: int
    malformed_count: int
    last_heartbeat: HeartbeatRecord | None = None
    last_live_tick: TickRecord | None = None
    last_gap: GapRecord | None = None

    @property
    def feed_verified(self) -> bool:
        return False  # Never elevate a bounded diagnostic to an actionable market feed.


def probe_exporter_tail(
    directory: Path, source_id: str, *, max_bytes: int = MAX_TAIL_BYTES
) -> TailProbe:
    """Inspect only the latest matching file's complete tail lines.

    A source can have earlier integrity gaps, offset changes, or a stale clock
    outside this tail. Thus LIVE_TICK_IN_TAIL is evidence of a *record*, not
    proof of a recent/valid tick, a connected broker, or an actionable signal.
    """
    if not is_valid_source_id(source_id):
        raise ValueError("invalid source ID")
    if not 0 < max_bytes <= 1_048_576:
        raise ValueError("max_bytes must be between 1 and 1048576")
    directory = Path(directory)
    files: list[Path] = []
    if directory.is_dir():
        for candidate in directory.iterdir():
            match = FILE_NAME.fullmatch(candidate.name)
            if (
                match is not None
                and match.group("source") == source_id
                and not candidate.is_symlink()
                and candidate.is_file()
            ):
                files.append(candidate)
    if not files:
        return TailProbe(source_id, None, TailState.SOURCE_NOT_FOUND, 0, 0, 0, 0, 0)

    selected = max(files, key=lambda path: path.name)
    with selected.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        offset = max(0, size - max_bytes)
        stream.seek(offset)
        data = stream.read(max_bytes)
    # Exclude partial first/last records; report no claims for omitted history.
    parts = data.split(b"\n")[:-1]
    if offset > 0 and parts:
        parts = parts[1:]

    heartbeat_count = live_tick_count = backfill_tick_count = malformed_count = 0
    last_heartbeat: HeartbeatRecord | None = None
    last_live_tick: TickRecord | None = None
    last_gap: GapRecord | None = None

    for line in parts:
        try:
            record = parse_line(line.decode("utf-8"))
        except (UnicodeDecodeError, RecordError):
            malformed_count += 1
            continue
        if isinstance(record, HeartbeatRecord):
            heartbeat_count += 1
            last_heartbeat = record
        elif isinstance(record, TickRecord):
            if record.mode == "L":
                live_tick_count += 1
                last_live_tick = record
            else:
                backfill_tick_count += 1
        elif isinstance(record, GapRecord):
            last_gap = record

    if malformed_count:
        state = TailState.MALFORMED_TAIL
    elif last_gap is not None:
        state = TailState.GAP_IN_TAIL
    elif live_tick_count:
        state = TailState.LIVE_TICK_IN_TAIL
    elif heartbeat_count:
        state = TailState.HEARTBEAT_ONLY
    elif parts:
        state = TailState.NO_LIVE_TICK_IN_TAIL
    else:
        state = TailState.NO_COMPLETE_RECORDS
    return TailProbe(
        source_id,
        selected,
        state,
        len(data),
        heartbeat_count,
        live_tick_count,
        backfill_tick_count,
        malformed_count,
        last_heartbeat,
        last_live_tick,
        last_gap,
    )


def main(argv: list[str] | None = None) -> int:
    """Optional bounded diagnostic; never starts MT5 or changes a source."""
    from grog.desktop.mt5_discovery import discover_mt5

    parser = argparse.ArgumentParser(description="Inspect latest MT5 exporter tail (read-only)")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args(argv)
    folder = args.directory if args.directory is not None else discover_mt5().exporter_directory
    try:
        result = probe_exporter_tail(folder, args.source_id)
    except (ValueError, OSError) as exc:
        print("PROBE ERROR:", exc)
        return 3
    print("SOURCE:", result.source_id)
    print("FILE:", result.file.name if result.file else "NOT FOUND")
    print("RECENT STATE:", result.state.value)
    print("BYTES EXAMINED:", result.bytes_examined)
    print("TAIL HEARTBEATS:", result.heartbeat_count)
    print("TAIL LIVE TICKS:", result.live_tick_count)
    print("TAIL BACKFILL TICKS:", result.backfill_tick_count)
    print("TAIL MALFORMED:", result.malformed_count)
    hb = result.last_heartbeat
    if hb is not None:
        print("LAST HEARTBEAT:", hb.server_time_msc, hb.connected, hb.session, hb.server_offset_s)
    tick = result.last_live_tick
    if tick is not None:
        print("LAST LIVE RECORD:", tick.time_msc, tick.bid, tick.ask)
    if result.last_gap is not None:
        print("RECENT GAP:", result.last_gap.error)
    print("NOT VERIFIED: a tail cannot establish UTC time, entire-file integrity or live READY.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
