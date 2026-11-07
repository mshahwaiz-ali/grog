#!/usr/bin/env bash
# One-command Gold desktop (D05). Opens the source you choose: explicit arguments, else
# your saved choice ($XDG_CONFIG_HOME/grog/desktop-source.toml), else the source chooser.
# Separate from the existing 'gold' alias, which is intentionally unchanged (TUI).
# Textual fallback: uv run grog ui --mode replay --source-id ID [--state-dir DIR]
# Works from any directory and through a symlink; relative paths stay relative to the
# directory you run it from (the repository is located with --project, cwd is kept).
set -euo pipefail
script=$(readlink -f -- "${BASH_SOURCE[0]}")
repo_root=$(cd -- "$(dirname -- "$script")/.." && pwd -P)
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' \
    "Gold desktop: 'uv' was not found on PATH; nothing was started or changed." \
    "Install uv (https://docs.astral.sh/uv/), then once: cd $(printf %q "$repo_root") && uv sync --locked --extra desktop" \
    "Textual fallback (also needs uv): uv run grog ui --mode replay --source-id ID --state-dir DIR" >&2
  exit 3
fi
exec uv run --project "$repo_root" --locked --extra desktop python -m grog.desktop.launcher "$@"
