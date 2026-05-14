#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="/home/user/wealth-pulse"
LOG_DIR="$REPO_DIR/storage/logs/runtime"
LOG_FILE="$LOG_DIR/hermes_research_runner.log"
LOCK_FILE="/tmp/wealthpulse_kospi_research.lock"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

printf '\n[%s] wealthpulse-kospi-research start\n' "$(date --iso-8601=seconds)"

export PATH="/home/user/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export WEALTHPULSE_API_BASE_URL="${WEALTHPULSE_API_BASE_URL:-http://127.0.0.1:8001}"
export WEALTHPULSE_HERMES_RESEARCH_COMMAND="${WEALTHPULSE_HERMES_RESEARCH_COMMAND:-/home/user/.local/bin/hermes chat -Q -t web -q}"
export PYTHONUNBUFFERED=1

cd "$REPO_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '[%s] wealthpulse-kospi-research skipped reason=lock_held\n' "$(date --iso-8601=seconds)"
  exit 0
fi

PYTHON_BIN="${WEALTHPULSE_PYTHON_BIN:-$REPO_DIR/.venv/bin/python}"
printf '[%s] wealthpulse-kospi-research python_bin=%s\n' "$(date --iso-8601=seconds)" "$PYTHON_BIN"

args=(
  "$PYTHON_BIN" apps/api/scripts/hermes_research_runner.py
  --market KOSPI
  --limit "${WEALTHPULSE_KOSPI_RESEARCH_LIMIT:-5}"
  --mode "${WEALTHPULSE_KOSPI_RESEARCH_MODE:-missing_or_stale}"
  --api-base-url "$WEALTHPULSE_API_BASE_URL"
  --timeout "${WEALTHPULSE_KOSPI_RESEARCH_TIMEOUT:-300}"
)

if [[ "${WEALTHPULSE_KOSPI_RESEARCH_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

set +e
"${args[@]}"
status=$?
set -e

printf '[%s] wealthpulse-kospi-research finish exit_code=%s\n' "$(date --iso-8601=seconds)" "$status"
exit "$status"
