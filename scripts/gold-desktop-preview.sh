#!/usr/bin/env bash
# Read-only local Qt preview. The existing 'gold' alias is intentionally unchanged.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"
exec uv run --with pyside6-essentials==6.11.3 python -m grog.desktop.main \
    --source-id syn \
    --config config/synthetic-demo.fixture-only.toml \
    --state-dir /tmp/grog-demo \
    "$@"
