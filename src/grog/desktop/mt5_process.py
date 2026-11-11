"""Read-only inventory of Linux Wine terminal64.exe processes.

Process names and WINEPREFIX identify candidates only. This is NOT evidence of
MT5 account connection, XAUUSD prices, an exporter, or permission to start/kill.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PureWindowsPath


class ProcessState(StrEnum):
    NO_CANDIDATE = "NO_CANDIDATE"
    RUNNING_CANDIDATE = "RUNNING_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class ProcessInventory:
    state: ProcessState
    matching_pids: tuple[int, ...]
    uncertain_pids: tuple[int, ...]
    other_prefix_pids: tuple[int, ...]


def _terminal_name(command: bytes, comm: str) -> bool:
    """Match a process executable name, not an arbitrary argument containing MT5."""
    if comm.casefold() == "terminal64.exe":
        return True
    first = command.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    return PureWindowsPath(first).name.casefold() == "terminal64.exe"


def _reported_prefix(environ: bytes) -> str | None:
    for item in environ.split(b"\x00"):
        if item.startswith(b"WINEPREFIX="):
            return os.fsdecode(item[len(b"WINEPREFIX=") :])
    return None


def inspect_mt5_processes(prefix: Path, *, proc_root: Path = Path("/proc")) -> ProcessInventory:
    """Inspect same-UID terminal candidates without mutating them.

    An inaccessible or absent WINEPREFIX makes ownership AMBIGUOUS. No match
    does not prove MT5 is stopped; alternate Wine process names may exist. An MT5
    process in another prefix is reported but never considered owned by Grog.
    """
    expected = Path(prefix).expanduser().resolve()
    matching: list[int] = []
    uncertain: list[int] = []
    other: list[int] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        raise OSError(f"Cannot inspect process inventory at {proc_root}") from exc
    for entry in entries:
        if not entry.name.isascii() or not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
            command = (entry / "cmdline").read_bytes()
        except FileNotFoundError:
            continue  # normal /proc race: the process exited during inspection
        except OSError:
            # Do not claim a clean "not running" if the same-user process is unreadable.
            uncertain.append(pid)
            continue
        if not _terminal_name(command, comm):
            continue
        try:
            name = _reported_prefix((entry / "environ").read_bytes())
        except FileNotFoundError:
            continue
        except OSError:
            uncertain.append(pid)
            continue
        if not name or not Path(name).is_absolute():
            uncertain.append(pid)
        elif Path(name).resolve() == expected:
            matching.append(pid)
        else:
            other.append(pid)
    if uncertain or len(matching) > 1:
        status = ProcessState.AMBIGUOUS
    elif matching:
        status = ProcessState.RUNNING_CANDIDATE
    else:
        status = ProcessState.NO_CANDIDATE
    return ProcessInventory(
        status, tuple(sorted(matching)), tuple(sorted(uncertain)), tuple(sorted(other))
    )


def main(argv: list[str] | None = None) -> int:
    """Optional developer diagnostic. Never launches, attaches or terminates MT5."""
    import argparse

    parser = argparse.ArgumentParser(description="Read-only local MT5 process inventory")
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".mt5")
    args = parser.parse_args(argv)
    inventory = inspect_mt5_processes(args.prefix)
    print("MT5 PROCESS:", inventory.state)
    print("MATCHED PIDS:", ",".join(map(str, inventory.matching_pids)) or "-")
    print("UNCERTAIN PIDS:", ",".join(map(str, inventory.uncertain_pids)) or "-")
    print("OTHER PREFIX COUNT:", len(inventory.other_prefix_pids))
    print("NOTE: Process detection does not prove live XAUUSD ticks, exporter or account health.")
    return 0 if inventory.state is not ProcessState.AMBIGUOUS else 3


if __name__ == "__main__":
    raise SystemExit(main())
