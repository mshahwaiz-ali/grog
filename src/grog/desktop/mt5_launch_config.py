"""Pure preview of a dedicated, non-trading MetaTrader 5 reference startup.

This module renders text only. It does not create MT5 profiles/presets, alter
common.ini, launch Wine, attach an EA, or access accounts. The output MUST NOT
be executed until the dedicated profile, preset, compiled EA and demo account
have been independently verified on the native host.
"""

from __future__ import annotations

from dataclasses import dataclass

from grog.domain.ids import is_valid_source_id

PROFILE_NAME = "Grog-Reference"
EXPERT_NAME = "GrogReferenceExporterFullUAT"
PRESET_NAME = "GrogReferenceTradeFinder.set"
CONFIG_NAME = "grog-reference.ini"


@dataclass(frozen=True, slots=True)
class ReferenceLaunchFiles:
    source_id: str
    config_name: str
    preset_name: str
    profile_name: str
    config_text: str
    preset_text: str


def render_reference_launch_files(source_id: str) -> ReferenceLaunchFiles:
    """Build a startup config and source-specific .set preset without side effects.

    No numeric trading policy is introduced here: the existing FullUAT EA
    retains its compiled input defaults except for the fresh source ID.

    The profile MUST be created and checked separately. An incorrect /profile
    or /config argument may silently fall back to a default MT5 configuration;
    the future runner must fail closed on missing paths, not trust these texts.
    """
    if not is_valid_source_id(source_id) or "__" in source_id:
        raise ValueError("source_id must be a safe MQL5 exporter identifier without '__'")

    # MetaTrader 5 official startup configuration syntax:
    # https://www.metatrader5.com/en/terminal/help/start_advanced/start
    lines = (
        "[Charts]",
        f"ProfileLast={PROFILE_NAME}",
        "",
        "[Experts]",
        "AllowLiveTrading=0",
        "AllowDllImport=0",
        "Enabled=1",
        "Account=1",
        "Profile=1",
        "",
        "[StartUp]",
        f"Expert={EXPERT_NAME}",
        f"ExpertParameters={PRESET_NAME}",
        "Symbol=XAUUSD",
        "Period=M1",
    )
    config_text = "\r\n".join(lines) + "\r\n"
    # MQL5 string inputs in .set files use Name=Value. This is an unexecuted
    # preview; terminal acceptance of the preset must be checked after setup.
    preset_text = f"InpSourceId={source_id}\r\n"
    return ReferenceLaunchFiles(
        source_id,
        CONFIG_NAME,
        PRESET_NAME,
        PROFILE_NAME,
        config_text,
        preset_text,
    )


def main(argv: list[str] | None = None) -> int:
    """Print a startup preview only; does NOT write files or start MT5."""
    import argparse

    parser = argparse.ArgumentParser(description="Preview non-trading MT5 startup config")
    parser.add_argument("--source-id", required=True)
    args = parser.parse_args(argv)
    try:
        files = render_reference_launch_files(args.source_id)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"=== {files.config_name} (PREVIEW ONLY) ===")
    print(files.config_text, end="")
    print(f"=== {files.preset_name} (PREVIEW ONLY) ===")
    print(files.preset_text, end="")
    print("NOT READY: verify a dedicated empty profile, demo account, compiled exporter,")
    print("preset loading, new source ID, process isolation and fresh live ticks.")
    print("NO FILES WRITTEN. NO MT5 PROCESS STARTED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
