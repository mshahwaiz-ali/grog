"""Read-only discovery of a previously installed local Wine/MetaTrader 5.

Presence of local files is *not* evidence of a connected, fresh XAUUSD feed.
No subprocess, network, MT5 API, account access, or filesystem writes are used.
"""

from __future__ import annotations

import os
import pwd
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LocalMT5:
    """Known local paths and unmet setup checks (not a feed-health assessment)."""

    prefix: Path
    wine_binary: Path | None
    terminal: Path
    exporter_directory: Path
    issues: tuple[str, ...]

    @property
    def files_found(self) -> bool:
        return not self.issues


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def discover_mt5(
    *,
    home: Path | None = None,
    prefix: Path | None = None,
    wine_binary: Path | None = None,
    wine_user: str | None = None,
) -> LocalMT5:
    """Inspect known Ubuntu/Wine paths without launching or configuring anything.

    Explicit wine_binary is authoritative: an invalid choice must not silently
    fall back to a different Wine installation. Missing exporter files are reported,
    never created. No discovery result alone should enable REFERENCE_LIVE.
    """
    home = Path.home() if home is None else Path(home).expanduser()
    prefix = home / ".mt5" if prefix is None else Path(prefix).expanduser()
    wine_user = pwd.getpwuid(os.getuid()).pw_name if wine_user is None else wine_user
    if not wine_user or wine_user in (".", "..") or "/" in wine_user or "\\" in wine_user:
        raise ValueError("wine_user must be one directory name")

    if wine_binary is not None:
        candidate = Path(wine_binary).expanduser()
        wine = candidate if _executable(candidate) else None
    else:
        fallback = shutil.which("wine")
        candidates = [Path("/opt/wine-staging/bin/wine")]
        if fallback:
            candidates.append(Path(fallback))
        wine = next((p for p in candidates if _executable(p)), None)

    terminal = prefix / "drive_c/Program Files/MetaTrader 5/terminal64.exe"
    user_files = prefix / "drive_c" / "users" / wine_user
    exporter = user_files / "AppData/Roaming/MetaQuotes/Terminal/Common/Files/grog"
    issues = []
    if wine is None:
        issues.append("WINE_NOT_FOUND")
    if not prefix.is_dir():
        issues.append("PREFIX_NOT_FOUND")
    if not terminal.is_file():
        issues.append("TERMINAL_NOT_FOUND")
    if not exporter.is_dir():
        issues.append("EXPORTER_DIRECTORY_NOT_FOUND")
    return LocalMT5(prefix, wine, terminal, exporter, tuple(issues))


def main(argv: list[str] | None = None) -> int:
    """Developer/onboarding check; not required during ordinary daily operation."""
    import argparse

    parser = argparse.ArgumentParser(description="Inspect local MT5 paths (read-only)")
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--wine", type=Path)
    parser.add_argument("--wine-user")
    args = parser.parse_args(argv)
    result = discover_mt5(prefix=args.prefix, wine_binary=args.wine, wine_user=args.wine_user)
    print("WINE:", result.wine_binary or "NOT FOUND")
    print("PREFIX:", result.prefix)
    print("TERMINAL:", result.terminal if result.terminal.is_file() else "NOT FOUND")
    exporter = result.exporter_directory if result.exporter_directory.is_dir() else "NOT FOUND"
    print("EXPORTER DIRECTORY:", exporter)
    print("STATUS:", "LOCAL_FILES_FOUND" if result.files_found else ", ".join(result.issues))
    print("NOTE: No MT5 login, active connection, live ticks or clock accuracy verified.")
    return 0 if result.files_found else 3


if __name__ == "__main__":
    raise SystemExit(main())
