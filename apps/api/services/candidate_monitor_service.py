from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from services import candidate_monitor_store as store
from services.paper_runtime_store import list_strategy_scans

DEFAULT_POOL_LIMIT = 40
DEFAULT_CORE_LIMIT = 12
DEFAULT_PROMOTION_LIMIT = 3
DEFAULT_PROMOTION_EVENT_LIMIT = 50

_ACTION_WEIGHT = {
    "review_for_entry": 1000.0,
    "watch_only": 700.0,
    "do_not_touch": 250.0,
    "blocked": 100.0,
}
_SIGNAL_STATE_WEIGHT = {
    "entry": 300.0,
    "watch": 180.0,
    "exit": 0.0,
}


def _now_local() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone()


def _session_date(now: datetime.datetime | None = None) -> str:
    return (now or _now_local()).date().isoformat()


def _normalize_market(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _iter_positions(account: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = account or {}
    raw_positions = payload.get("positions")
    if isinstance(raw_positions, dict):
        items = raw_positions.values()
    elif isinstance(raw_positions, list):
        items = raw_positions
    else:
        items = []
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _held_symbols(account: dict[str, Any] | None, market: str) -> set[str]:
    normalized_market = _normalize_market(market)
    result: set[str] = set()
    for item in _iter_positions(account):
        if _normalize_market(item.get("market")) != normalized_market:
            continue
        symbol = _normalize_symbol(item.get("code") or item.get("symbol"))
        if symbol:
            result.add(symbol)
    return result


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_interest_watchlist(market: str) -> dict[str, dict[str, Any]]:
    normalized_market = _normalize_market(market)
    raw = _read_json(LOGS_DIR / "watchlist.json")
    if not isinstance(raw, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        if _normalize_market(item.get("market")) != normalized_market:
            continue
        symbol = _normalize_symbol(item.get("code") or item.get("symbol"))
        if not symbol:
            continue
        rows[symbol] = {
            "code": symbol,
            "symbol": symbol,
            "market": normalized_market,
            "name": str(item.get("name") or "").strip(),
            "current_price": item.get("price"),
            "change_pct": item.get("change_pct"),
            "candidate_source": "user_watchlist",
            "final_action": "watch_only",
            "signal_state": "watch",
            "score": 0,
        }
    return rows


def _load_latest_research_snapshot(symbol: str, market: str) -> dict[str, Any]:
    path = LOGS_DIR / "research_snapshots" / "latest" / f"default__{_normalize_market(market)}__{_normalize_symbol(symbol)}.json"
    data = _read_json(path)
    return data if isinstance(data, dict) else {}


def _technical_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    for key in ("technical_snapshot", "technicals", "technical_features"):
        value = candidate.get(key)
        if isinstance(value, dict):
            return value
    layer_c = candidate.get("layer_c") if isinstance(candidate.get("layer_c"), dict) else {}
    value = layer_c.get("technical_features")
    return value if isinstance(value, dict) else {}


def _first_number(candidate: dict[str, Any], technical: dict[str, Any], *names: str) -> float:
    for name in names:
        if candidate.get(name) not in (None, ""):
            value = _to_float(candidate.get(name), 0.0)
            if value != 0.0:
                return value
        if technical.get(name) not in (None, ""):
            value = _to_float(technical.get(name), 0.0)
            if value != 0.0:
                return value
    return 0.0


def _news_surge_score(candidate: dict[str, Any], snapshot: dict[str, Any]) -> float:
    explicit = _first_number(
        candidate,
        {},
        "news_surge_score",
        "news_momentum_score",
        "news_count_delta",
        "mention_count_delta",
        "buzz_score",
    )
    news_inputs = snapshot.get("news_inputs") if isinstance(snapshot.get("news_inputs"), list) else []
    evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), list) else []
    source = str(candidate.get("candidate_source") or snapshot.get("candidate_source") or "").lower()
    text_blob = json.dumps(candidate, ensure_ascii=False).lower()[:4000]
    score = explicit
    score += min(len(news_inputs), 10) * 12.0
    score += min(len(evidence), 10) * 5.0
    if "news" in source or "뉴스" in source or "news" in text_blob or "뉴스" in text_blob:
        score += 60.0
    return score


def _selection_meta(candidate: dict[str, Any], *, held_symbols: set[str], interest_symbols: set[str]) -> dict[str, Any]:
    symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
    market = _normalize_market(candidate.get("market"))
    technical = _technical_payload(candidate)
    price = _first_number(candidate, technical, "current_price", "price", "close")
    volume = _first_number(candidate, technical, "volume", "accumulated_volume", "acml_vol")
    trading_value = _first_number(candidate, technical, "trading_value", "trade_value", "accumulated_trade_value", "acml_tr_pbmn")
    if trading_value <= 0 and price > 0 and volume > 0:
        trading_value = price * volume
    change_pct = _first_number(candidate, technical, "change_pct", "change_rate", "fluctuation_rate")
    snapshot = _load_latest_research_snapshot(symbol, market) if symbol and market else {}
    news_score = _news_surge_score(candidate, snapshot)
    sources: list[str] = []
    if trading_value > 0:
        sources.append("trading_value_top")
    if change_pct > 0:
        sources.append("change_rate_top")
    if news_score > 0:
        sources.append("news_surge")
    if symbol in held_symbols:
        sources.append("held_position")
    if symbol in interest_symbols:
        sources.append("user_watchlist")
    return {
        "symbol": symbol,
        "market": market,
        "trading_value": trading_value,
        "change_pct": change_pct,
        "news_surge_score": news_score,
        "candidate_sources": sources,
        "technical_snapshot": technical or candidate.get("technical_snapshot"),
    }


def _extract_candidate_freshness(candidate: dict[str, Any]) -> tuple[bool, str]:
    layer_c = candidate.get("layer_c") if isinstance(candidate.get("layer_c"), dict) else {}
    freshness = str(layer_c.get("freshness") or candidate.get("research_status") or "").strip().lower()
    if freshness == "healthy":
        freshness = "fresh"
    if freshness in {"fresh", "derived"}:
        return True, freshness
    return False, freshness or "missing"


def _snapshot_meta(candidate: dict[str, Any]) -> dict[str, Any]:
    layer_c = candidate.get("layer_c") if isinstance(candidate.get("layer_c"), dict) else {}
    validation = layer_c.get("validation") if isinstance(layer_c.get("validation"), dict) else {}
    fresh, freshness = _extract_candidate_freshness(candidate)
    generated_at = str(layer_c.get("generated_at") or candidate.get("generated_at") or candidate.get("fetched_at") or "")
    research_score = layer_c.get("research_score")
    if research_score in (None, ""):
        research_score = candidate.get("research_score")
    snapshot_exists = freshness not in {"missing", "research_unavailable", ""} or bool(generated_at) or research_score not in (None, "")
    return {
        "snapshot_exists": bool(snapshot_exists),
        "snapshot_fresh": bool(fresh),
        "snapshot_generated_at": generated_at,
        "snapshot_research_score": research_score,
        "validation_grade": str(validation.get("grade") or "").upper(),
    }


def _candidate_priority(candidate: dict[str, Any], *, held_symbols: set[str], interest_symbols: set[str] | None = None) -> float:
    interest_symbols = interest_symbols or set()
    symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
    action = str(candidate.get("final_action") or "").strip().lower()
    signal_state = str(candidate.get("signal_state") or "watch").strip().lower()
    rank_raw = candidate.get("candidate_rank")
    try:
        rank = int(rank_raw) if rank_raw is not None else 999999
    except (TypeError, ValueError):
        rank = 999999
    score = _to_float(candidate.get("score"), 0.0)
    fresh, freshness = _extract_candidate_freshness(candidate)
    bonus = 0.0
    if symbol in held_symbols:
        bonus += 1500.0
    if symbol in interest_symbols:
        bonus += 520.0
    if fresh:
        bonus += 120.0
    elif freshness == "stale_ingest":
        bonus -= 40.0
    elif freshness in {"missing", "research_unavailable"}:
        bonus -= 80.0
    sources = candidate.get("candidate_sources") if isinstance(candidate.get("candidate_sources"), list) else []
    if "news_surge" in sources:
        bonus += 1150.0 + min(_to_float(candidate.get("news_surge_score"), 0.0), 300.0)
    if "trading_value_top" in sources:
        bonus += 420.0
    if "change_rate_top" in sources:
        bonus += 260.0 + max(0.0, min(_to_float(candidate.get("change_pct"), 0.0), 30.0)) * 6.0
    return (
        _ACTION_WEIGHT.get(action, 200.0)
        + _SIGNAL_STATE_WEIGHT.get(signal_state, 50.0)
        + max(0.0, 200.0 - min(rank, 200))
        + score
        + bonus
    )


def _merge_candidate(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return dict(incoming)
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "candidate_sources":
            current = [str(item) for item in merged.get("candidate_sources", []) if item]
            for item in value if isinstance(value, list) else []:
                label = str(item)
                if label and label not in current:
                    current.append(label)
            merged[key] = current
            continue
        if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    if _to_float(incoming.get("monitor_priority"), 0.0) > _to_float(merged.get("monitor_priority"), 0.0):
        for key in ("strategy_id", "strategy_name", "candidate_rank", "final_action", "signal_state", "score", "monitor_priority"):
            if incoming.get(key) not in (None, ""):
                merged[key] = incoming[key]
    return merged


def _annotate_standard_sources(rows: list[dict[str, Any]], *, held_symbols: set[str], interest_symbols: set[str]) -> list[dict[str, Any]]:
    for row in rows:
        meta = _selection_meta(row, held_symbols=held_symbols, interest_symbols=interest_symbols)
        for key, value in meta.items():
            if key == "candidate_sources":
                row[key] = value
            elif value not in (None, "", [], {}):
                row[key] = value
    def _ranked(items: list[dict[str, Any]], key: str, limit: int, *, positive_only: bool = True) -> list[dict[str, Any]]:
        filtered = [item for item in items if (not positive_only or _to_float(item.get(key), 0.0) > 0)]
        filtered.sort(key=lambda item: (_to_float(item.get(key), 0.0), _to_float(item.get("score"), 0.0)), reverse=True)
        return filtered[:limit]
    source_rankings = {
        "news_surge": _ranked(rows, "news_surge_score", 14),
        "trading_value_top": _ranked(rows, "trading_value", 14),
        "change_rate_top": _ranked(rows, "change_pct", 12),
    }
    for source, ranked_rows in source_rankings.items():
        for idx, item in enumerate(ranked_rows, start=1):
            sources = item.get("candidate_sources") if isinstance(item.get("candidate_sources"), list) else []
            if source not in sources:
                sources.append(source)
            item["candidate_sources"] = sources
            ranks = item.get("source_ranks") if isinstance(item.get("source_ranks"), dict) else {}
            ranks[source] = idx
            item["source_ranks"] = ranks
    for item in rows:
        sources = item.get("candidate_sources") if isinstance(item.get("candidate_sources"), list) else []
        if not sources:
            sources = ["strategy_scan_fallback"]
        item["candidate_sources"] = sources
        item["candidate_source"] = "news_surge" if "news_surge" in sources else sources[0]
        item["selection_reason"] = ",".join(sources)
        item["selection_criteria"] = {
            "trading_value": item.get("trading_value"),
            "change_pct": item.get("change_pct"),
            "news_surge_score": item.get("news_surge_score"),
            "source_ranks": item.get("source_ranks") if isinstance(item.get("source_ranks"), dict) else {},
        }
        item["monitor_priority"] = _candidate_priority(item, held_symbols=held_symbols, interest_symbols=interest_symbols)
    return rows


def _dedupe_market_candidates(market: str, *, account: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized_market = _normalize_market(market)
    held_symbols = _held_symbols(account, normalized_market)
    interest_rows = _load_interest_watchlist(normalized_market)
    interest_symbols = set(interest_rows)
    best_by_symbol: dict[str, dict[str, Any]] = {}
    for scan in list_strategy_scans():
        if not isinstance(scan, dict):
            continue
        if _normalize_market(scan.get("market")) != normalized_market:
            continue
        for candidate in scan.get("top_candidates") or []:
            if not isinstance(candidate, dict):
                continue
            symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
            if not symbol:
                continue
            merged = dict(candidate)
            merged.setdefault("code", symbol)
            merged.setdefault("symbol", symbol)
            merged.setdefault("market", normalized_market)
            merged.setdefault("strategy_id", scan.get("strategy_id"))
            merged.setdefault("strategy_name", scan.get("strategy_name"))
            merged.setdefault("last_scanned_at", candidate.get("fetched_at") or scan.get("last_scan_at"))
            merged.update(_snapshot_meta(merged))
            best_by_symbol[symbol] = _merge_candidate(best_by_symbol.get(symbol), merged)
    for symbol in sorted(held_symbols):
        if symbol not in best_by_symbol:
            best_by_symbol[symbol] = {
                "code": symbol,
                "symbol": symbol,
                "market": normalized_market,
                "candidate_source": "held_position",
                "final_action": "watch_only",
                "signal_state": "watch",
                "score": 0,
                "candidate_rank": 999999,
                "last_scanned_at": _now_local().isoformat(timespec="seconds"),
            }
    for symbol, row in interest_rows.items():
        best_by_symbol[symbol] = _merge_candidate(best_by_symbol.get(symbol), row)
    rows = _annotate_standard_sources(list(best_by_symbol.values()), held_symbols=held_symbols, interest_symbols=interest_symbols)
    rows.sort(
        key=lambda item: (
            float(item.get("monitor_priority") or 0.0),
            -int(item.get("candidate_rank") or 999999) if item.get("candidate_rank") is not None else -999999,
            float(item.get("score") or 0.0),
            _normalize_symbol(item.get("code") or item.get("symbol")),
        ),
        reverse=True,
    )
    return rows


def build_market_watchlist(
    market: str,
    *,
    account: dict[str, Any] | None = None,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    core_limit: int = DEFAULT_CORE_LIMIT,
    promotion_limit: int = DEFAULT_PROMOTION_LIMIT,
    source: str = "strategy_scan_cache",
) -> dict[str, Any]:
    normalized_market = _normalize_market(market)
    pool_limit = max(1, int(pool_limit or DEFAULT_POOL_LIMIT))
    core_limit = max(1, int(core_limit or DEFAULT_CORE_LIMIT))
    promotion_limit = max(0, int(promotion_limit or DEFAULT_PROMOTION_LIMIT))
    held_symbols = _held_symbols(account, normalized_market)
    now_iso = _now_local().isoformat(timespec="seconds")

    previous_active = {row["symbol"]: row for row in store.list_active_slots(normalized_market)}
    pool = _dedupe_market_candidates(normalized_market, account=account)[:pool_limit]
    store.replace_candidate_pool(normalized_market, pool, updated_at=now_iso)

    active_rows: list[dict[str, Any]] = []
    used_symbols: set[str] = set()
    held_count = 0
    for candidate in pool:
        symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
        if symbol in held_symbols and symbol not in used_symbols:
            active_rows.append({**candidate, "symbol": symbol, "slot_type": "held", "priority": int(candidate.get("monitor_priority") or 0), "reason": "held_position"})
            used_symbols.add(symbol)
            held_count += 1

    core_selected = 0
    for candidate in pool:
        if core_selected >= core_limit:
            break
        symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
        if symbol in used_symbols:
            continue
        reason = str(candidate.get("candidate_source") or candidate.get("selection_reason") or "core_watch")
        active_rows.append({**candidate, "symbol": symbol, "slot_type": "core", "priority": int(candidate.get("monitor_priority") or 0), "reason": reason})
        used_symbols.add(symbol)
        core_selected += 1

    promotion_selected = 0
    for candidate in pool:
        if promotion_selected >= promotion_limit:
            break
        symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
        if symbol in used_symbols:
            continue
        reason = str(candidate.get("candidate_source") or candidate.get("selection_reason") or "promotion_slot")
        active_rows.append({**candidate, "symbol": symbol, "slot_type": "promotion", "priority": int(candidate.get("monitor_priority") or 0), "reason": reason})
        used_symbols.add(symbol)
        promotion_selected += 1

    store.replace_active_slots(normalized_market, active_rows, selected_at=now_iso)
    source_counts: dict[str, int] = {}
    for row in pool:
        for source_name in row.get("candidate_sources") if isinstance(row.get("candidate_sources"), list) else []:
            source_counts[str(source_name)] = source_counts.get(str(source_name), 0) + 1
    store.save_market_state(
        normalized_market,
        source=source,
        session_date=_session_date(),
        core_limit=core_limit,
        promotion_limit=promotion_limit,
        candidate_pool_count=len(pool),
        active_count=len(active_rows),
        held_count=held_count,
        generated_at=now_iso,
        metadata={
            "pool_limit": pool_limit,
            "core_selected": core_selected,
            "promotion_selected": promotion_selected,
            "held_symbols": sorted(held_symbols),
            "standard_candidate_sources": [
                "trading_value_top",
                "change_rate_top",
                "news_surge",
                "held_position",
                "user_watchlist",
            ],
            "source_counts": source_counts,
            "news_surge_priority": "highest",
        },
    )

    previous_symbols = set(previous_active)
    current_by_symbol = {row["symbol"]: row for row in active_rows if row.get("symbol")}
    current_symbols = set(current_by_symbol)
    for symbol in sorted(current_symbols - previous_symbols):
        row = current_by_symbol[symbol]
        store.append_promotion_event(normalized_market, symbol, "entered_watch", str(row.get("slot_type") or "watch"), row, created_at=now_iso)
    for symbol in sorted(previous_symbols - current_symbols):
        store.append_promotion_event(normalized_market, symbol, "left_watch", str(previous_active[symbol].get("slot_type") or "watch"), previous_active[symbol], created_at=now_iso)

    return get_market_watchlist(normalized_market)


def get_market_watchlist(market: str) -> dict[str, Any]:
    normalized_market = _normalize_market(market)
    market_state = store.load_market_state(normalized_market) or {}
    pool = store.list_candidate_pool(normalized_market)
    active = store.list_active_slots(normalized_market)
    events = store.list_promotion_events(normalized_market, limit=20)
    return {
        "ok": True,
        "market": normalized_market,
        "state": market_state,
        "candidate_pool": pool,
        "active_slots": active,
        "events": events,
        "core_slots": [row for row in active if row.get("slot_type") == "core"],
        "promotion_slots": [row for row in active if row.get("slot_type") == "promotion"],
        "held_slots": [row for row in active if row.get("slot_type") == "held"],
    }


def list_market_watchlists(
    markets: list[str] | None = None,
    *,
    refresh: bool = False,
    account: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized_markets: list[str] = []
    for market in markets or ["KOSPI", "NASDAQ"]:
        normalized = _normalize_market(market)
        if normalized and normalized not in normalized_markets:
            normalized_markets.append(normalized)
    if not normalized_markets:
        normalized_markets = ["KOSPI", "NASDAQ"]
    return [
        build_market_watchlist(market, account=account) if refresh else get_market_watchlist(market)
        for market in normalized_markets
    ]


def summarize_market_watchlists(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for item in items:
        state = item.get("state") if isinstance(item.get("state"), dict) else {}
        summary.append({
            "market": item.get("market"),
            "candidate_pool_count": len(item.get("candidate_pool") or []),
            "active_count": len(item.get("active_slots") or []),
            "core_count": len(item.get("core_slots") or []),
            "promotion_count": len(item.get("promotion_slots") or []),
            "held_count": len(item.get("held_slots") or []),
            "generated_at": state.get("generated_at") or "",
            "session_date": state.get("session_date") or "",
            "source": state.get("source") or "candidate_monitor",
            "metadata": state.get("metadata") if isinstance(state.get("metadata"), dict) else {},
        })
    return summary


def _matches_pending_mode(item: dict[str, Any], mode: str) -> bool:
    snapshot_exists = bool(item.get("snapshot_exists"))
    snapshot_fresh = bool(item.get("snapshot_fresh"))
    normalized_mode = str(mode or "missing_or_stale").strip().lower()
    if normalized_mode == "missing_only":
        return not snapshot_exists
    if normalized_mode == "stale_only":
        return snapshot_exists and not snapshot_fresh
    return (not snapshot_exists) or (not snapshot_fresh)


def list_pending_research_targets(
    items: list[dict[str, Any]],
    *,
    mode: str = "missing_or_stale",
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for watchlist in items:
        active_rows = watchlist.get("active_slots") if isinstance(watchlist.get("active_slots"), list) else []
        for row in active_rows:
            if not isinstance(row, dict):
                continue
            key = (_normalize_market(row.get("market") or watchlist.get("market")), _normalize_symbol(row.get("symbol") or row.get("code")))
            if not key[0] or not key[1] or key in seen:
                continue
            if not _matches_pending_mode(row, mode):
                continue
            seen.add(key)
            rows.append(row)
    rows.sort(
        key=lambda item: (
            int(item.get("priority") or item.get("monitor_priority") or 0),
            -int(item.get("candidate_rank") or 999999) if item.get("candidate_rank") is not None else -999999,
            str(item.get("market") or ""),
            str(item.get("symbol") or item.get("code") or ""),
        ),
        reverse=True,
    )
    capped = max(0, int(limit or 0))
    return rows[:capped] if capped > 0 else rows


def list_recent_promotion_events(markets: list[str] | None = None, *, limit: int = DEFAULT_PROMOTION_EVENT_LIMIT) -> list[dict[str, Any]]:
    normalized_markets: list[str] = []
    for market in markets or ["KOSPI", "NASDAQ"]:
        normalized = _normalize_market(market)
        if normalized and normalized not in normalized_markets:
            normalized_markets.append(normalized)
    rows: list[dict[str, Any]] = []
    for market in normalized_markets or ["KOSPI", "NASDAQ"]:
        rows.extend(store.list_promotion_events(market, limit=limit))
    rows.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
    capped = max(1, int(limit or DEFAULT_PROMOTION_EVENT_LIMIT))
    return rows[:capped]
