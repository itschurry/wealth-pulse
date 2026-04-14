from __future__ import annotations

from typing import Any

from services.candidate_monitor_service import (
    list_market_watchlists,
    list_pending_research_targets,
    list_recent_promotion_events,
    summarize_market_watchlists,
)
from services.execution_service import get_execution_service

_DEFAULT_MARKETS = ["KOSPI", "NASDAQ"]


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


def _normalize_markets(query: dict[str, list[str]]) -> list[str]:
    items = [str(item or "").strip().upper() for item in (query.get("market") or []) if str(item or "").strip()]
    return items or list(_DEFAULT_MARKETS)


def _load_runtime_account() -> dict[str, Any]:
    try:
        _, payload = get_execution_service().paper_account(False)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    account = payload.get("account")
    return account if isinstance(account, dict) else payload


def handle_candidate_monitor_watchlist(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = _to_bool((query.get("refresh") or ["0"])[0], False)
        markets = _normalize_markets(query)
        account = _load_runtime_account()
        items = list_market_watchlists(markets, refresh=refresh, account=account)
        mode = ((query.get("mode") or ["missing_or_stale"])[0] or "missing_or_stale").strip().lower()
        limit_raw = (query.get("limit") or ["30"])[0]
        try:
            limit = max(1, min(200, int(limit_raw or 30)))
        except (TypeError, ValueError):
            limit = 30
        pending_items = list_pending_research_targets(items, mode=mode, limit=limit)
        return 200, {
            "ok": True,
            "markets": markets,
            "count": len(items),
            "items": items,
            "pending_count": len(pending_items),
            "pending_items": pending_items,
            "source": "candidate_monitor_sqlite",
            "refresh": refresh,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_candidate_monitor_status(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = _to_bool((query.get("refresh") or ["0"])[0], False)
        markets = _normalize_markets(query)
        account = _load_runtime_account()
        items = list_market_watchlists(markets, refresh=refresh, account=account)
        summary = summarize_market_watchlists(items)
        return 200, {
            "ok": True,
            "markets": markets,
            "items": summary,
            "count": len(summary),
            "source": "candidate_monitor_sqlite",
            "refresh": refresh,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_candidate_monitor_promotions(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = _to_bool((query.get("refresh") or ["0"])[0], False)
        markets = _normalize_markets(query)
        account = _load_runtime_account()
        if refresh:
            list_market_watchlists(markets, refresh=True, account=account)
        limit_raw = (query.get("limit") or ["50"])[0]
        try:
            limit = max(1, min(200, int(limit_raw or 50)))
        except (TypeError, ValueError):
            limit = 50
        items = list_recent_promotion_events(markets, limit=limit)
        return 200, {
            "ok": True,
            "markets": markets,
            "items": items,
            "count": len(items),
            "source": "candidate_monitor_sqlite",
            "refresh": refresh,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
