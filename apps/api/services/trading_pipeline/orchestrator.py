from __future__ import annotations

from typing import Any, Iterable, Mapping

from market_utils import normalize_market

from .ranker import rank_candidates
from .research_queue import build_research_queue
from .scanner import scan_universe
from .store import append_event, read_events, read_latest, utc_now_iso, write_latest
from .universe import build_dynamic_universe

DEFAULT_POOL_LIMIT = 100
DEFAULT_CORE_LIMIT = 24
DEFAULT_PROMOTION_LIMIT = 8


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().zfill(6)[-6:] if str(value or "").strip() else ""


def _held_symbols(account: Mapping[str, Any] | None, market: str) -> set[str]:
    if not isinstance(account, Mapping):
        return set()
    rows = account.get("positions")
    if not isinstance(rows, list):
        return set()
    held: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_market = normalize_market(row.get("market") or market)
        symbol = _normalize_symbol(row.get("symbol") or row.get("code"))
        quantity = float(row.get("quantity") or row.get("qty") or 0)
        if row_market == market and symbol and quantity > 0:
            held.add(symbol)
    return held


def _force_symbols(account: Mapping[str, Any] | None, market: str) -> list[str]:
    return sorted(_held_symbols(account, market))


def _slot_type(index: int, candidate: Mapping[str, Any], held: set[str], core_limit: int) -> str:
    symbol = _normalize_symbol(candidate.get("symbol") or candidate.get("code"))
    if symbol in held:
        return "held"
    if index <= core_limit:
        return "core"
    return "promotion"


def _format_watchlist(
    ranked_snapshot: Mapping[str, Any],
    *,
    source: str,
    held_symbols: set[str],
    core_limit: int,
    promotion_limit: int,
    persisted: bool,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_limit = core_limit + promotion_limit + len(held_symbols)
    active_rows: list[dict[str, Any]] = []
    used: set[str] = set()
    for candidate in ranked_snapshot.get("candidates") or []:
        symbol = _normalize_symbol(candidate.get("symbol") or candidate.get("code"))
        if not symbol or symbol in used:
            continue
        if len(active_rows) >= active_limit:
            break
        row = dict(candidate)
        row["symbol"] = symbol
        row["code"] = symbol
        row["slot_type"] = _slot_type(len(active_rows) + 1, row, held_symbols, core_limit)
        row["priority"] = int(float(row.get("monitor_priority") or 0))
        row["reason"] = str(row.get("selection_reason") or row.get("candidate_source") or "market_scanner")
        active_rows.append(row)
        used.add(symbol)

    core_slots = [row for row in active_rows if row.get("slot_type") == "core"]
    promotion_slots = [row for row in active_rows if row.get("slot_type") == "promotion"]
    held_slots = [row for row in active_rows if row.get("slot_type") == "held"]
    market = str(ranked_snapshot.get("market") or "KOSPI")
    generated_at = str(ranked_snapshot.get("generated_at") or utc_now_iso())
    metadata = {
        "pipeline": "trading_pipeline.v1",
        "universe_generation_mode": "dynamic_market_listing",
        "standard_candidate_sources": ["market_scanner", "realtime_mover", "trading_value_top", "change_rate_top", "volume_top", "held_position"],
        "source_counts": _source_counts(ranked_snapshot.get("candidates") or []),
        "pool_limit": int(ranked_snapshot.get("candidate_count") or 0),
        "core_selected": len(core_slots),
        "promotion_selected": len(promotion_slots),
        "held_symbols": sorted(held_symbols),
    }
    state = {
        "market": market,
        "generated_at": generated_at,
        "source": source,
        "session_date": generated_at[:10],
        "core_limit": core_limit,
        "promotion_limit": promotion_limit,
        "candidate_pool_count": len(ranked_snapshot.get("candidates") or []),
        "active_count": len(active_rows),
        "held_count": len(held_slots),
        "metadata": metadata,
    }
    return {
        "ok": True,
        "market": market,
        "state": state,
        "candidate_pool": list(ranked_snapshot.get("candidates") or []),
        "active_slots": active_rows,
        "events": events or [],
        "core_slots": core_slots,
        "promotion_slots": promotion_slots,
        "held_slots": held_slots,
        "persisted": persisted,
    }


def _source_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for source in row.get("candidate_sources") or []:
            key = str(source)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _append_watch_events(market: str, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    previous_rows = [row for row in previous.get("active_slots") or [] if isinstance(row, Mapping)]
    previous_by_symbol = {_normalize_symbol(row.get("symbol") or row.get("code")): row for row in previous_rows}
    previous_symbols = set(previous_by_symbol)
    current_rows = [row for row in current.get("active_slots") or [] if isinstance(row, Mapping)]
    current_by_symbol = {_normalize_symbol(row.get("symbol") or row.get("code")): row for row in current_rows}
    current_symbols = set(current_by_symbol)

    for symbol in sorted(current_symbols - previous_symbols):
        append_event("watchlist", market, {"symbol": symbol, "event": "entered_watch", "payload": current_by_symbol[symbol]})
    for symbol in sorted(previous_symbols - current_symbols):
        append_event("watchlist", market, {"symbol": symbol, "event": "left_watch", "payload": previous_by_symbol[symbol]})


def refresh_market_pipeline(
    market: str,
    *,
    account: Mapping[str, Any] | None = None,
    persist: bool = True,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    core_limit: int = DEFAULT_CORE_LIMIT,
    promotion_limit: int = DEFAULT_PROMOTION_LIMIT,
    source: str = "dynamic_trading_pipeline",
    source_rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_market = normalize_market(market)
    force_symbols = _force_symbols(account, normalized_market)
    universe = build_dynamic_universe(
        market=normalized_market,
        max_symbols=max(pool_limit * 3, pool_limit),
        source_rows=source_rows,
        force_symbols=force_symbols,
    )
    scan = scan_universe(universe, max_candidates=max(pool_limit * 2, pool_limit))
    ranked = rank_candidates(scan, max_candidates=pool_limit, active_limit=core_limit + promotion_limit + len(force_symbols))
    watchlist = _format_watchlist(
        ranked,
        source=source,
        held_symbols=set(force_symbols),
        core_limit=core_limit,
        promotion_limit=promotion_limit,
        persisted=persist,
    )
    ranked_for_queue = {**ranked, "active_slots": list(watchlist.get("active_slots") or [])}
    research_queue = build_research_queue(ranked_for_queue, limit=core_limit + promotion_limit)
    result = {
        "universe": universe,
        "scan": scan,
        "ranked": ranked,
        "watchlist": watchlist,
        "research_queue": research_queue,
    }
    if persist:
        previous_watchlist = read_latest("watchlist", normalized_market)
        write_latest("universe", normalized_market, universe)
        write_latest("scan", normalized_market, scan)
        write_latest("ranked", normalized_market, ranked)
        write_latest("watchlist", normalized_market, watchlist)
        write_latest("research_queue", normalized_market, research_queue)
        _append_watch_events(normalized_market, previous_watchlist, watchlist)
        persisted_events = read_events("watchlist", normalized_market, limit=20)
        watchlist["events"] = persisted_events
        write_latest("watchlist", normalized_market, watchlist)
    return result


def read_market_pipeline(
    market: str,
    *,
    source: str = "dynamic_trading_pipeline",
    account: Mapping[str, Any] | None = None,
    core_limit: int = DEFAULT_CORE_LIMIT,
    promotion_limit: int = DEFAULT_PROMOTION_LIMIT,
) -> dict[str, Any]:
    normalized_market = normalize_market(market)
    universe = read_latest("universe", normalized_market)
    scan = read_latest("scan", normalized_market)
    ranked = read_latest("ranked", normalized_market)
    watchlist = read_latest("watchlist", normalized_market)
    research_queue = read_latest("research_queue", normalized_market)
    if not watchlist and ranked:
        held = _held_symbols(account, normalized_market)
        watchlist = _format_watchlist(
            ranked,
            source=source,
            held_symbols=held,
            core_limit=core_limit,
            promotion_limit=promotion_limit,
            persisted=True,
            events=read_events("watchlist", normalized_market, limit=20),
        )
    return {
        "universe": universe,
        "scan": scan,
        "ranked": ranked,
        "watchlist": watchlist
        or {
            "ok": True,
            "market": normalized_market,
            "state": {},
            "candidate_pool": [],
            "active_slots": [],
            "events": [],
            "core_slots": [],
            "promotion_slots": [],
            "held_slots": [],
            "persisted": True,
        },
        "research_queue": research_queue,
    }
