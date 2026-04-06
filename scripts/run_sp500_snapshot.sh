#!/usr/bin/env bash
set -euo pipefail

cd /home/user/wealth-pulse
SCRIPT="apps/api/scripts/build_universe_snapshots.py"
if [ ! -f "$SCRIPT" ]; then
  echo "BUILDER_NOT_READY"
  exit 0
fi

exec .venv/bin/python "$SCRIPT" --universe sp500
