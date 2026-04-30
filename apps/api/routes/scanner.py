from __future__ import annotations

import threading
from typing import Any

from services.runtime_execution_service import get_execution_service
from services.strategy_engine import build_signal_book
from services.strategy_registry import list_strategies

_REFRESH_LOCK = threading.Lock()
_REFRESH_RUNNING = False


def _normalize_markets(query: dict[str, list[str]]) -> list[str]:
    return [str(item or "").strip().upper() for item in query.get("market", []) if str(item or "").strip()]


def _filter_rows(rows: list[dict[str, Any]], markets: list[str]) -> list[dict[str, Any]]:
    if not markets:
        return rows
    allowed = {str(item).upper() for item in markets}
    return [item for item in rows if str(item.get("market") or "").upper() in allowed or str(item.get("market") or "").upper() == "ALL"]


def _strategy_support_count(markets: list[str]) -> int:
    allowed = {str(item).upper() for item in markets if str(item).strip()}
    count = 0
    for item in list_strategies():
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled")):
            continue
        market = str(item.get("market") or "").upper()
        if allowed and market not in allowed:
            continue
        count += 1
    return count


def _build_common_pool_rows(markets: list[str], account: dict[str, Any], *, refresh: bool = False) -> list[dict[str, Any]]:
    selected_markets = markets or ["KOSPI", "NASDAQ"]
    payload = build_signal_book(
        markets=selected_markets,
        cfg={"refresh_scanner": refresh},
        account=account,
    )
    signals = [item for item in (payload.get("signals") or []) if isinstance(item, dict)]
    for index, item in enumerate(signals, start=1):
        item.setdefault("candidate_rank", index)
    row = {
        "strategy_id": "common_candidate_pool",
        "strategy_name": "공통 후보 풀",
        "approval_status": "runtime",
        "enabled": True,
        "market": "ALL" if len(selected_markets) > 1 else selected_markets[0],
        "markets": selected_markets,
        "universe_rule": "runtime_universe",
        "scan_cycle": "runtime",
        "last_scan_at": payload.get("generated_at") or "",
        "next_scan_at": "",
        "candidate_count": len(signals),
        "scanned_symbol_count": len(signals),
        "universe_symbol_count": len(signals),
        "scan_duration_ms": 0,
        "top_candidates": signals,
        "status": "running",
        "source": payload.get("candidate_generation_mode") or "common_candidate_pool",
        "strategy_role": "auxiliary",
        "strategy_support_count": _strategy_support_count(selected_markets),
        "risk_guard_state": payload.get("risk_guard_state") if isinstance(payload.get("risk_guard_state"), dict) else {},
    }
    return _filter_rows([row], markets)


def _refresh_scans_in_background(markets: list[str], account: dict[str, Any]) -> None:
    global _REFRESH_RUNNING
    with _REFRESH_LOCK:
        if _REFRESH_RUNNING:
            return
        _REFRESH_RUNNING = True

    def _runner() -> None:
        global _REFRESH_RUNNING
        try:
            _build_common_pool_rows(markets, account, refresh=True)
        finally:
            with _REFRESH_LOCK:
                _REFRESH_RUNNING = False

    threading.Thread(target=_runner, daemon=True, name="scanner-status-refresh").start()



def _to_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if value in {"0", "false", "f", "no", "n", "off", ""}:
            return False
        return default
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return bool(raw)
    return default


def handle_scanner_status(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = _to_bool((query.get("refresh", ["0"])[0] or "0"), False)
        cache_only = _to_bool((query.get("cache_only", ["0"])[0] or "0"), False)
        markets = _normalize_markets(query)
        _, execution_payload = get_execution_service().runtime_engine_status()
        account = execution_payload.get("account") if isinstance(execution_payload, dict) else {}
        account = account if isinstance(account, dict) else {}

        common_rows = _build_common_pool_rows(markets, account, refresh=False)
        if cache_only:
            return 200, {
                "ok": True,
                "items": common_rows,
                "count": len(common_rows),
                "refreshing": False,
                "source": "common_candidate_pool",
                "strategy_role": "auxiliary",
            }
        if refresh:
            _refresh_scans_in_background(markets, account)
            return 200, {
                "ok": True,
                "items": common_rows,
                "count": len(common_rows),
                "refreshing": True,
                "source": "common_candidate_pool",
                "strategy_role": "auxiliary",
            }

        return 200, {
            "ok": True,
            "items": common_rows,
            "count": len(common_rows),
            "refreshing": False,
            "source": "common_candidate_pool",
            "strategy_role": "auxiliary",
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
