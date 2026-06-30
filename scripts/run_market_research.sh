#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${WEALTHPULSE_REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
LOG_ROOT="${LOGS_DIR:-$REPO_DIR/storage/logs}"
LOG_DIR="$LOG_ROOT/runtime"
LOG_FILE="$LOG_DIR/openai_research_runner.log"
LOCK_FILE="/tmp/wealthpulse_market_research.lock"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

printf '\n[%s] wealthpulse-market-research start\n' "$(date --iso-8601=seconds)"

export PATH="${HOME:-}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export WEALTHPULSE_API_BASE_URL="${WEALTHPULSE_API_BASE_URL:-http://127.0.0.1:8001}"
export PYTHONUNBUFFERED=1

cd "$REPO_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '[%s] wealthpulse-market-research skipped reason=lock_held\n' "$(date --iso-8601=seconds)"
  exit 0
fi

if [[ -n "${WEALTHPULSE_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$WEALTHPULSE_PYTHON_BIN"
elif [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_DIR/.venv/bin/python"
else
  PYTHON_BIN="python"
fi
printf '[%s] wealthpulse-market-research python_bin=%s\n' "$(date --iso-8601=seconds)" "$PYTHON_BIN"

set +e
market_status="$("$PYTHON_BIN" - <<'PY'
import json
import sys
from pathlib import Path

repo = Path.cwd()
sys.path.insert(0, str(repo / "apps/api"))

from config.market_calendar import get_market_local_dt, is_market_open, is_market_trading_day

checks = [
    ("KOSPI", "KR"),
]
open_markets = []
rows = []
for research_market, calendar_market in checks:
    local_dt = get_market_local_dt(calendar_market)
    trading_day = is_market_trading_day(calendar_market)
    market_open = is_market_open(calendar_market)
    rows.append({
        "research_market": research_market,
        "calendar_market": calendar_market,
        "local_time": local_dt.isoformat(timespec="seconds"),
        "trading_day": trading_day,
        "open": market_open,
    })
    if market_open:
        open_markets.append(research_market)

if len(open_markets) > 1:
    print(json.dumps({"status": "ambiguous", "open_markets": open_markets, "checks": rows}, ensure_ascii=False))
    raise SystemExit(3)
if not open_markets:
    print(json.dumps({"status": "closed", "open_markets": [], "checks": rows}, ensure_ascii=False))
    raise SystemExit(2)
print(json.dumps({"status": "open", "market": open_markets[0], "checks": rows}, ensure_ascii=False))
PY
)"
calendar_status=$?
set -e

printf '[%s] wealthpulse-market-research market_status=%s\n' "$(date --iso-8601=seconds)" "$market_status"
if [[ "$calendar_status" == "2" ]]; then
  printf '[%s] wealthpulse-market-research skipped reason=market_closed\n' "$(date --iso-8601=seconds)"
  exit 0
fi
if [[ "$calendar_status" != "0" ]]; then
  printf '[%s] wealthpulse-market-research failed reason=market_calendar_error exit_code=%s\n' "$(date --iso-8601=seconds)" "$calendar_status"
  exit "$calendar_status"
fi

research_market="$("$PYTHON_BIN" - "$market_status" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
print(payload["market"])
PY
)"

case "$research_market" in
  KOSPI)
    limit="${WEALTHPULSE_RESEARCH_LIMIT:-30}"
    mode="${WEALTHPULSE_RESEARCH_MODE:-missing_or_stale}"
    timeout="${WEALTHPULSE_RESEARCH_TIMEOUT:-600}"
    concurrency="${WEALTHPULSE_RESEARCH_CONCURRENCY:-3}"
    dry_run="${WEALTHPULSE_RESEARCH_DRY_RUN:-0}"
    ;;
  *)
    printf '[%s] wealthpulse-market-research failed reason=unsupported_market market=%s\n' "$(date --iso-8601=seconds)" "$research_market"
    exit 1
    ;;
esac

args=(
  "$PYTHON_BIN" apps/api/scripts/openai_research_runner.py
  --market "$research_market"
  --limit "$limit"
  --mode "$mode"
  --api-base-url "$WEALTHPULSE_API_BASE_URL"
  --timeout "$timeout"
  --concurrency "$concurrency"
)

if [[ "$dry_run" == "1" ]]; then
  args+=(--dry-run)
fi

printf '[%s] wealthpulse-market-research run market=%s limit=%s mode=%s concurrency=%s timeout=%s dry_run=%s\n' \
  "$(date --iso-8601=seconds)" "$research_market" "$limit" "$mode" "$concurrency" "$timeout" "$dry_run"

set +e
"${args[@]}"
status=$?
set -e

printf '[%s] wealthpulse-market-research finish market=%s exit_code=%s\n' "$(date --iso-8601=seconds)" "$research_market" "$status"
exit "$status"
