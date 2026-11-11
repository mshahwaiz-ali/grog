"""Pure, permission-gated MT5 startup preflight. Never starts or stops a process.

The output is a plan, NOT a running terminal or verified XAUUSD feed.
Even READY_TO_START must be rechecked under an exclusive launcher lock immediately
before a later process-start integration; a /proc inventory is not proof of absence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from grog.desktop.mt5_discovery import LocalMT5
from grog.desktop.mt5_process import ProcessInventory, ProcessState


class StartupState(StrEnum):
    SETUP_REQUIRED = "SETUP_REQUIRED"
    PROCESS_AMBIGUOUS = "PROCESS_AMBIGUOUS"
    REUSE_EXISTING = "REUSE_EXISTING"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    PROFILE_UNVERIFIED = "PROFILE_UNVERIFIED"
    READY_TO_START = "READY_TO_START"


@dataclass(frozen=True, slots=True)
class StartupPlan:
    state: StartupState
    reasons: tuple[str, ...]
    argv: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()

    @property
    def may_start(self) -> bool:
        return self.state is StartupState.READY_TO_START


def _missing(local: LocalMT5) -> tuple[str, ...]:
    """Recheck discovered paths: files can disappear after initial discovery."""
    issues = list(local.issues)
    wine = local.wine_binary
    if wine is None or not wine.is_absolute() or not wine.is_file() or not os.access(wine, os.X_OK):
        issues.append("WINE_NOT_FOUND")
    if not local.prefix.is_absolute() or not local.prefix.is_dir():
        issues.append("PREFIX_NOT_FOUND")
    expected = local.prefix / "drive_c/Program Files/MetaTrader 5/terminal64.exe"
    if (
        not local.terminal.is_absolute()
        or not local.terminal.is_file()
        or local.terminal.resolve() != expected.resolve()
    ):
        issues.append("TERMINAL_NOT_FOUND")
    if not local.exporter_directory.is_dir():
        issues.append("EXPORTER_DIRECTORY_NOT_FOUND")
    return tuple(dict.fromkeys(issues))


def plan_mt5_startup(
    local: LocalMT5,
    inventory: ProcessInventory,
    *,
    allow_local_launch: bool = False,
    dedicated_read_only_profile_verified: bool = False,
) -> StartupPlan:
    """Decide next step without I/O other than local file existence checks.

    No actual process launch occurs here. An explicit permission alone is insufficient:
    a dedicated non-trading MT5 profile must also be verified before allowing a
    future launcher to start a terminal (existing profiles may contain trading EAs).
    """
    missing = _missing(local)
    if missing:
        return StartupPlan(StartupState.SETUP_REQUIRED, missing)
    if (
        inventory.state is ProcessState.AMBIGUOUS
        or inventory.uncertain_pids
        or len(inventory.matching_pids) > 1
    ):
        return StartupPlan(StartupState.PROCESS_AMBIGUOUS, ("PROCESS_OWNERSHIP_UNVERIFIED",))
    if inventory.state is ProcessState.RUNNING_CANDIDATE:
        if len(inventory.matching_pids) != 1:
            return StartupPlan(StartupState.PROCESS_AMBIGUOUS, ("PROCESS_INVENTORY_INCONSISTENT",))
        return StartupPlan(StartupState.REUSE_EXISTING, ("MT5_PROCESS_CANDIDATE_ONLY",))
    if inventory.state is not ProcessState.NO_CANDIDATE or inventory.matching_pids:
        return StartupPlan(StartupState.PROCESS_AMBIGUOUS, ("PROCESS_INVENTORY_INCONSISTENT",))
    if not allow_local_launch:
        return StartupPlan(StartupState.PERMISSION_REQUIRED, ("LOCAL_MT5_LAUNCH_NOT_APPROVED",))
    if not dedicated_read_only_profile_verified:
        return StartupPlan(
            StartupState.PROFILE_UNVERIFIED, ("DEDICATED_READ_ONLY_PROFILE_UNVERIFIED",)
        )
    # Return command as argv, never a shell string. No global environment changed.
    # A later launcher MUST re-inventory under a lock just before using this plan.
    return StartupPlan(
        StartupState.READY_TO_START,
        ("LAUNCH_PREFLIGHT_ONLY",),
        (str(local.wine_binary), str(local.terminal)),
        (("WINEPREFIX", str(local.prefix)),),
    )
