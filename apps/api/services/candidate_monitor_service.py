"""Candidate monitor compatibility API backed by the dynamic trading pipeline."""

from __future__ import annotations

from typing import Any, Mapping

from market_utils import normalize_market
from services.research_store import DEFAULT_RESEARCH_PROVIDER
from services.trading_pipeline.orchestrator import (
    DEFAULT_CORE_LIMIT,
    DEFAULT_POOL_LIMIT,
    DEFAULT_PROMOTION_LIMIT,
    read_market_pipeline,
    refresh_market_pipeline,
)
from services.trading_pipeline.research_queue import build_research_queue
from services.trading_pipeline.store import read_events

DEFAULT_PROMOTION_EVENT_LIMIT = 50


def _normalize_markets(markets: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for market in markets or ["KOSPI"]:
        item = normalize_market(market)
        if item and item not in normalized:
            normalized.append(item)
    return normalized or ["KOSPI"]


def build_market_watchlist(
    market: str,
    *,
    account: dict[str, Any] | None = None,
    refresh: bool = False,
    persist: bool = True,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    core_limit: int = DEFAULT_CORE_LIMIT,
    promotion_limit: int = DEFAULT_PROMOTION_LIMIT,
    source: str = "dynamic_trading_pipeline",
) -> dict[str, Any]:
    normalized_market = normalize_market(market)
    if refresh:
        result = refresh_market_pipeline(
            normalized_market,
            account=account,
            persist=persist,
            pool_limit=pool_limit,
            core_limit=core_limit,
            promotion_limit=promotion_limit,
            source=source,
        )
        return _with_research_state(dict(result["watchlist"]))
    result = read_market_pipeline(
        normalized_market,
        account=account,
        source=source,
        core_limit=core_limit,
        promotion_limit=promotion_limit,
    )
    return _with_research_state(dict(result["watchlist"]))


def get_market_watchlist(market: str) -> dict[str, Any]:
    return build_market_watchlist(market, refresh=False)


def list_market_watchlists(
    markets: list[str] | None = None,
    *,
    refresh: bool = False,
    account: dict[str, Any] | None = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    return [
        build_market_watchlist(market, refresh=refresh, account=account, persist=persist)
        for market in _normalize_markets(markets)
    ]


def summarize_market_watchlists(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        state = item.get("state") if isinstance(item.get("state"), dict) else {}
        rows.append(
            {
                "market": item.get("market"),
                "candidate_pool_count": len(item.get("candidate_pool") or []),
                "active_count": len(item.get("active_slots") or []),
                "core_count": len(item.get("core_slots") or []),
                "promotion_count": len(item.get("promotion_slots") or []),
                "held_count": len(item.get("held_slots") or []),
                "generated_at": state.get("generated_at") or "",
                "session_date": state.get("session_date") or "",
                "source": state.get("source") or "dynamic_trading_pipeline",
                "metadata": state.get("metadata") if isinstance(state.get("metadata"), dict) else {},
            }
        )
    return rows


def _ranked_from_watchlist(watchlist: Mapping[str, Any]) -> dict[str, Any]:
    market = str(watchlist.get("market") or "KOSPI")
    return {
        "schema_version": "trading_pipeline.rank.v1",
        "market": market,
        "generated_at": (watchlist.get("state") if isinstance(watchlist.get("state"), dict) else {}).get("generated_at") or "",
        "candidates": list(watchlist.get("candidate_pool") or []),
        "active_slots": list(watchlist.get("active_slots") or []),
    }


def _with_research_state(watchlist: dict[str, Any]) -> dict[str, Any]:
    queue = build_research_queue(
        _ranked_from_watchlist(watchlist),
        provider=DEFAULT_RESEARCH_PROVIDER,
        mode="all",
        limit=len(watchlist.get("active_slots") or []),
    )
    reviewed = [item for item in queue.get("reviewed_items") or [] if isinstance(item, dict)]
    if not reviewed:
        return watchlist
    by_symbol = {
        str(item.get("symbol") or item.get("code") or "").strip().upper(): item
        for item in reviewed
        if str(item.get("symbol") or item.get("code") or "").strip()
    }

    def enrich(rows: list[Any]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or row.get("code") or "").strip().upper()
            enriched.append(dict(by_symbol.get(symbol) or row))
        return enriched

    watchlist["active_slots"] = enrich(list(watchlist.get("active_slots") or []))
    watchlist["core_slots"] = enrich(list(watchlist.get("core_slots") or []))
    watchlist["promotion_slots"] = enrich(list(watchlist.get("promotion_slots") or []))
    watchlist["held_slots"] = enrich(list(watchlist.get("held_slots") or []))
    return watchlist


def list_pending_research_targets(
    items: list[dict[str, Any]],
    *,
    mode: str = "missing_or_stale",
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for watchlist in items:
        queue = build_research_queue(
            _ranked_from_watchlist(watchlist),
            provider=DEFAULT_RESEARCH_PROVIDER,
            mode=mode,
            limit=limit,
        )
        for item in queue.get("items") or []:
            key = (str(item.get("market") or watchlist.get("market") or "").upper(), str(item.get("symbol") or item.get("code") or "").upper())
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)
    rows.sort(
        key=lambda item: (
            float(item.get("research_priority") or item.get("monitor_priority") or 0),
            -int(item.get("candidate_rank") or 999999),
            str(item.get("market") or ""),
            str(item.get("symbol") or item.get("code") or ""),
        ),
        reverse=True,
    )
    capped = max(0, int(limit or 0))
    return rows[:capped] if capped > 0 else rows


def list_recent_promotion_events(markets: list[str] | None = None, *, limit: int = DEFAULT_PROMOTION_EVENT_LIMIT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market in _normalize_markets(markets):
        rows.extend(read_events("watchlist", market, limit=limit))
    rows.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    return rows[: max(1, int(limit or DEFAULT_PROMOTION_EVENT_LIMIT))]
