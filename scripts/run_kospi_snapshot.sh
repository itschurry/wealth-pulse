#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${WEALTHPULSE_REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

cd "$REPO_DIR"

SCRIPT="apps/api/scripts/build_universe_snapshots.py"
if [ ! -f "$SCRIPT" ]; then
  echo "BUILDER_NOT_READY"
  exit 0
fi

if [[ -n "${WEALTHPULSE_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$WEALTHPULSE_PYTHON_BIN"
elif [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_DIR/.venv/bin/python"
else
  PYTHON_BIN="python"
fi

exec "$PYTHON_BIN" "$SCRIPT" --universe kospi
