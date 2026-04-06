from __future__ import annotations

import threading
from typing import Any

from services.execution_service import get_execution_service
from services.live_signal_engine import scan_live_strategies
from services.paper_runtime_store import list_strategy_scans
from services.strategy_registry import list_strategies

_REFRESH_LOCK = threading.Lock()
_REFRESH_RUNNING = False


def _normalize_markets(query: dict[str, list[str]]) -> list[str]:
    return [str(item or "").strip().upper() for item in query.get("market", []) if str(item or "").strip()]


def _filter_rows(rows: list[dict[str, Any]], markets: list[str]) -> list[dict[str, Any]]:
    if not markets:
        return rows
    allowed = {str(item).upper() for item in markets}
    return [item for item in rows if str(item.get("market") or "").upper() in allowed]


def _load_cached_rows(markets: list[str]) -> list[dict[str, Any]]:
    rows = list_strategy_scans()
    safe_rows = [item for item in rows if isinstance(item, dict)]
    current_strategy_ids = {
        str(item.get("strategy_id") or "").strip()
        for item in list_strategies()
        if isinstance(item, dict) and str(item.get("strategy_id") or "").strip()
    }
    if current_strategy_ids:
        safe_rows = [
            item for item in safe_rows
            if str(item.get("strategy_id") or "").strip() in current_strategy_ids
        ]
    return _filter_rows(safe_rows, markets)


def _refresh_scans_in_background(markets: list[str], account: dict[str, Any]) -> None:
    global _REFRESH_RUNNING
    with _REFRESH_LOCK:
        if _REFRESH_RUNNING:
            return
        _REFRESH_RUNNING = True

    def _runner() -> None:
        global _REFRESH_RUNNING
        try:
            scan_live_strategies(markets=markets or None, account=account, refresh=True)
        finally:
            with _REFRESH_LOCK:
                _REFRESH_RUNNING = False

    threading.Thread(target=_runner, daemon=True, name="scanner-status-refresh").start()



def handle_scanner_status(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = (query.get("refresh", ["0"])[0] or "0").strip() == "1"
        cache_only = (query.get("cache_only", ["0"])[0] or "0").strip() == "1"
        markets = _normalize_markets(query)
        _, execution_payload = get_execution_service().paper_engine_status()
        account = execution_payload.get("account") if isinstance(execution_payload, dict) else {}
        account = account if isinstance(account, dict) else {}

        cached_rows = _load_cached_rows(markets)
        if cache_only:
            return 200, {
                "ok": True,
                "items": cached_rows,
                "count": len(cached_rows),
                "refreshing": False,
                "source": "strategy_scan_cache",
            }
        if refresh:
            _refresh_scans_in_background(markets, account)
            return 200, {
                "ok": True,
                "items": cached_rows,
                "count": len(cached_rows),
                "refreshing": True,
                "source": "strategy_scan_cache",
            }

        if cached_rows:
            return 200, {
                "ok": True,
                "items": cached_rows,
                "count": len(cached_rows),
                "refreshing": False,
                "source": "strategy_scan_cache",
            }

        rows = scan_live_strategies(markets=markets or None, account=account, refresh=False)
        return 200, {
            "ok": True,
            "items": rows,
            "count": len(rows),
            "refreshing": False,
            "source": "live_scan",
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
