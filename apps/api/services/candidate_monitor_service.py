from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from config.settings import CACHE_DIR, CONFIG_STATE_DIR
from helpers import _is_active_research_market
from market_utils import lookup_company_listing
from services import candidate_monitor_store as store
from services.agent_config import default_risk_config_store
from services.bluechip_universe import bluechip_meta
from services.market_data_service import resolve_stock_quote
from services.research_store import DEFAULT_RESEARCH_PROVIDER, load_latest_research_snapshot
from services.runtime_store import list_strategy_scans

DEFAULT_POOL_LIMIT = 100
DEFAULT_CORE_LIMIT = 20
DEFAULT_PROMOTION_LIMIT = 12
DEFAULT_PROMOTION_EVENT_LIMIT = 50
DEFAULT_MARKET_EVIDENCE_LIMIT = 100
DEFAULT_MISSED_MOVER_LIMIT = 12
MOVER_MIN_CHANGE_PCT = 2.0
MOVER_MIN_TRADING_VALUE_KRW = 50_000_000_000.0

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
_MISSING_RANK_SENTINEL = 999999


def _now_local() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone()


def _session_date(now: datetime.datetime | None = None) -> str:
    return (now or _now_local()).date().isoformat()


def _normalize_market(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_candidate_rank(value: Any) -> int | None:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return None
    if rank <= 0 or rank >= _MISSING_RANK_SENTINEL:
        return None
    return rank


def _rank_sort_value(value: Any) -> int:
    return _normalize_candidate_rank(value) or _MISSING_RANK_SENTINEL


def _resolve_company_identity(symbol: str, market: str, name: Any = "") -> dict[str, str]:
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = _normalize_market(market)
    resolved_name = str(name or "").strip()
    resolved_sector = ""
    if normalized_symbol and (not resolved_name or resolved_name.upper() == normalized_symbol):
        try:
            listing = lookup_company_listing(code=normalized_symbol, market=normalized_market, scope="core") or {}
        except Exception:
            listing = {}
        candidate_name = str(listing.get("name") or "").strip()
        if candidate_name:
            resolved_name = candidate_name
        resolved_sector = str(listing.get("sector") or "").strip()
    return {"name": resolved_name, "sector": resolved_sector}


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


def _normalized_research_score(value: Any) -> float:
    score = _to_float(value, 0.0)
    if score > 1.0:
        score = score / 100.0
    return max(0.0, min(score, 1.0))


def _read_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_interest_watchlist(market: str) -> dict[str, dict[str, Any]]:
    normalized_market = _normalize_market(market)
    raw = _read_json(CONFIG_STATE_DIR / "watchlist.json")
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
        identity = _resolve_company_identity(symbol, normalized_market, item.get("name"))
        rows[symbol] = {
            "code": symbol,
            "symbol": symbol,
            "market": normalized_market,
            "name": identity["name"],
            "sector": identity["sector"] or str(item.get("sector") or "").strip(),
            "current_price": item.get("price"),
            "change_pct": item.get("change_pct"),
            "candidate_source": "user_watchlist",
            "final_action": "watch_only",
            "signal_state": "watch",
            "score": 0,
        }
    return rows


def _load_latest_research_snapshot(symbol: str, market: str) -> dict[str, Any]:
    path = CACHE_DIR / "research_snapshots" / "latest" / f"default__{_normalize_market(market)}__{_normalize_symbol(symbol)}.json"
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


def _snapshot_research_score(candidate: dict[str, Any], snapshot: dict[str, Any]) -> float:
    for source in (
        candidate.get("snapshot_research_score"),
        candidate.get("research_score"),
        snapshot.get("research_score"),
    ):
        score = _normalized_research_score(source)
        if score > 0:
            return score
    layer_c = candidate.get("layer_c") if isinstance(candidate.get("layer_c"), dict) else {}
    return _normalized_research_score(layer_c.get("research_score"))


def _selection_meta(candidate: dict[str, Any], *, held_symbols: set[str], interest_symbols: set[str]) -> dict[str, Any]:
    symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
    market = _normalize_market(candidate.get("market"))
    identity = _resolve_company_identity(symbol, market, candidate.get("name"))
    technical = _technical_payload(candidate)
    price = _first_number(candidate, technical, "current_price", "price", "close")
    volume = _first_number(candidate, technical, "volume", "accumulated_volume", "acml_vol")
    trading_value = _first_number(candidate, technical, "trading_value", "trade_value", "accumulated_trade_value", "acml_tr_pbmn")
    if trading_value <= 0 and price > 0 and volume > 0:
        trading_value = price * volume
    change_pct = _first_number(candidate, technical, "change_pct", "change_rate", "fluctuation_rate")
    snapshot = _load_latest_research_snapshot(symbol, market) if symbol and market else {}
    news_score = _news_surge_score(candidate, snapshot)
    research_score = _snapshot_research_score(candidate, snapshot)
    risk_config = default_risk_config_store().load()
    bluechip = bluechip_meta(symbol, market, risk_config)
    sources: list[str] = []
    if bluechip.get("bluechip"):
        sources.append("bluechip_core")
    if research_score >= 0.65:
        sources.append("research_high_score")
    if trading_value > 0:
        sources.append("trading_value_top")
    if change_pct > 0:
        sources.append("change_rate_top")
    if news_score > 0:
        sources.append("news_surge")
    source_hint = str(candidate.get("candidate_source") or "").strip()
    if source_hint and source_hint not in sources:
        sources.append(source_hint)
    if symbol in held_symbols and "held_position" not in sources:
        sources.append("held_position")
    if symbol in interest_symbols and "user_watchlist" not in sources:
        sources.append("user_watchlist")
    return {
        "symbol": symbol,
        "market": market,
        "name": identity["name"],
        "sector": identity["sector"],
        "trading_value": trading_value,
        "change_pct": change_pct,
        "news_surge_score": news_score,
        "snapshot_research_score": research_score,
        "candidate_sources": sources,
        "technical_snapshot": technical or candidate.get("technical_snapshot"),
        "allocation_mode": str(risk_config.get("allocation_mode") or "concentrated"),
        **bluechip,
    }


def _append_source(row: dict[str, Any], source: str) -> None:
    normalized = str(source or "").strip()
    if not normalized:
        return
    sources = row.get("candidate_sources") if isinstance(row.get("candidate_sources"), list) else []
    if normalized not in sources:
        sources.append(normalized)
    row["candidate_sources"] = sources


def _apply_realtime_market_evidence(row: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    technical = dict(updated.get("technical_snapshot")) if isinstance(updated.get("technical_snapshot"), dict) else {}
    price = quote.get("price")
    volume = quote.get("volume")
    trading_value = quote.get("trading_value")
    if trading_value in (None, "") and price not in (None, "") and volume not in (None, ""):
        trading_value = float(price) * float(volume)

    if price not in (None, ""):
        updated["price"] = price
        updated["current_price"] = price
        technical["current_price"] = price
        technical["close"] = price
    if quote.get("change_pct") not in (None, ""):
        updated["change_pct"] = quote.get("change_pct")
        technical["change_pct"] = quote.get("change_pct")
    if volume not in (None, ""):
        updated["volume"] = volume
        technical["volume"] = volume
    if trading_value not in (None, ""):
        updated["trading_value"] = trading_value
        technical["trading_value"] = trading_value
    technical["quote_source"] = str(quote.get("source") or "KIS")
    technical["quote_fetched_at"] = str(quote.get("fetched_at") or _now_local().isoformat(timespec="seconds"))
    technical["freshness"] = "fresh"
    technical["quote_is_stale"] = bool(quote.get("is_stale", False))
    updated["technical_snapshot"] = technical
    updated["last_scanned_at"] = technical["quote_fetched_at"]
    if _is_market_mover(updated):
        _append_source(updated, "realtime_mover")
    return updated


def _with_realtime_market_evidence(rows: list[dict[str, Any]], *, limit: int = DEFAULT_MARKET_EVIDENCE_LIMIT) -> list[dict[str, Any]]:
    capped = max(0, int(limit or 0))
    if capped <= 0:
        return rows
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index >= capped:
            enriched.append(row)
            continue
        symbol = _normalize_symbol(row.get("code") or row.get("symbol"))
        market = _normalize_market(row.get("market"))
        quote = resolve_stock_quote(symbol, market)
        enriched.append(_apply_realtime_market_evidence(row, quote))
    return enriched


def _is_market_mover(candidate: dict[str, Any]) -> bool:
    technical = _technical_payload(candidate)
    change_pct = _first_number(candidate, technical, "change_pct", "change_rate", "fluctuation_rate")
    trading_value = _first_number(candidate, technical, "trading_value", "trade_value", "accumulated_trade_value", "acml_tr_pbmn")
    return change_pct >= MOVER_MIN_CHANGE_PCT or trading_value >= MOVER_MIN_TRADING_VALUE_KRW


def _has_market_evidence(candidate: dict[str, Any]) -> bool:
    technical = _technical_payload(candidate)
    trading_value = _first_number(candidate, technical, "trading_value", "trade_value", "accumulated_trade_value", "acml_tr_pbmn")
    change_pct = _first_number(candidate, technical, "change_pct", "change_rate", "fluctuation_rate")
    volume = _first_number(candidate, technical, "volume", "accumulated_volume", "acml_vol")
    volume_ratio = _first_number(candidate, technical, "volume_ratio")
    return trading_value > 0 or change_pct != 0.0 or volume > 0 or volume_ratio > 0


def _market_mover_rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    technical = _technical_payload(candidate)
    change_pct = _first_number(candidate, technical, "change_pct", "change_rate", "fluctuation_rate")
    trading_value = _first_number(candidate, technical, "trading_value", "trade_value", "accumulated_trade_value", "acml_tr_pbmn")
    volume_ratio = _first_number(candidate, technical, "volume_ratio")
    return (
        1.0 if _is_market_mover(candidate) else 0.0,
        1.0 if change_pct > 0 else 0.0,
        change_pct,
        min(trading_value / 1_000_000_000.0, 1000.0),
        volume_ratio,
        _to_float(candidate.get("news_surge_score"), 0.0),
        _normalized_research_score(candidate.get("snapshot_research_score") or candidate.get("research_score")),
        _to_float(candidate.get("score"), 0.0),
    )


def _select_promotion_candidates(pool: list[dict[str, Any]], used_symbols: set[str], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    eligible: list[dict[str, Any]] = []
    for candidate in pool:
        symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
        if not symbol or symbol in used_symbols:
            continue
        sources = candidate.get("candidate_sources") if isinstance(candidate.get("candidate_sources"), list) else []
        if _is_market_mover(candidate) or "realtime_mover" in sources or "news_surge" in sources or "research_high_score" in sources:
            eligible.append(candidate)
    eligible.sort(key=_market_mover_rank, reverse=True)
    return eligible[:limit]


def _missed_market_movers(pool: list[dict[str, Any]], active_symbols: set[str], *, limit: int = DEFAULT_MISSED_MOVER_LIMIT) -> list[dict[str, Any]]:
    missed = [
        candidate for candidate in pool
        if _normalize_symbol(candidate.get("code") or candidate.get("symbol")) not in active_symbols
        and _is_market_mover(candidate)
    ]
    missed.sort(key=_market_mover_rank, reverse=True)
    return missed[: max(0, int(limit or 0))]


def _universe_rule_for_market(market: str) -> str:
    return "kospi"


def _configured_universe_candidates(market: str) -> list[dict[str, Any]]:
    normalized_market = _normalize_market(market)
    from services.universe_builder import get_configured_universe_snapshot

    universe = get_configured_universe_snapshot(_universe_rule_for_market(normalized_market), market=normalized_market)

    rows = universe.get("symbols") if isinstance(universe, dict) else []
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows if isinstance(rows, list) else [], start=1):
        if not isinstance(row, dict):
            continue
        symbol = _normalize_symbol(row.get("code") or row.get("symbol"))
        if not symbol:
            continue
        result.append({
            "code": symbol,
            "symbol": symbol,
            "market": normalized_market,
            "name": row.get("name") or symbol,
            "sector": row.get("sector") or "",
            "candidate_source": "config_universe",
            "final_action": "watch_only",
            "signal_state": "watch",
            "score": max(0.0, 100.0 - float(index)),
            "candidate_rank": index,
            "last_scanned_at": _now_local().isoformat(timespec="seconds"),
        })
    return result


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
    rank = _rank_sort_value(candidate.get("candidate_rank"))
    score = _to_float(candidate.get("score"), 0.0)
    research_score = _normalized_research_score(candidate.get("snapshot_research_score") or candidate.get("research_score"))
    trading_value = _to_float(candidate.get("trading_value"), 0.0)
    change_pct = _to_float(candidate.get("change_pct"), 0.0)
    news_score = _to_float(candidate.get("news_surge_score"), 0.0)
    is_bluechip = bool(candidate.get("bluechip"))
    allocation_mode = str(candidate.get("allocation_mode") or "").strip().lower()
    source_hint = str(candidate.get("candidate_source") or "").strip().lower()
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
    if is_bluechip:
        bonus += 760.0 if allocation_mode == "concentrated" else 320.0
    if research_score >= 0.75:
        bonus += 760.0
    elif research_score >= 0.65:
        bonus += 520.0
    elif research_score > 0:
        bonus += research_score * 260.0
    has_market_evidence = _has_market_evidence(candidate)
    if "realtime_mover" in sources:
        bonus += 1200.0
    if "news_surge" in sources and has_market_evidence:
        bonus += 1400.0 + min(news_score, 360.0)
    elif "news_surge" in sources:
        bonus += min(news_score, 120.0)
    if "trading_value_top" in sources:
        bonus += 620.0
    if "change_rate_top" in sources:
        bonus += 420.0 + max(0.0, min(change_pct, 30.0)) * 10.0
    if change_pct < 0:
        bonus -= min(abs(change_pct), 20.0) * 8.0
    if not has_market_evidence and "held_position" not in sources:
        bonus -= 350.0
    if source_hint == "config_universe" and not is_bluechip and not fresh and not has_market_evidence and research_score <= 0:
        bonus -= 220.0
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
    def _ranked(
        items: list[dict[str, Any]],
        key: str,
        limit: int,
        *,
        positive_only: bool = True,
        min_value: float | None = None,
    ) -> list[dict[str, Any]]:
        filtered = [item for item in items if (not positive_only or _to_float(item.get(key), 0.0) > 0)]
        if min_value is not None:
            filtered = [item for item in filtered if _to_float(item.get(key), 0.0) >= min_value]
        filtered.sort(key=lambda item: (_to_float(item.get(key), 0.0), _to_float(item.get("score"), 0.0)), reverse=True)
        return filtered[:limit]
    realtime_movers = [item for item in rows if _is_market_mover(item)]
    realtime_movers.sort(key=_market_mover_rank, reverse=True)
    source_rankings = {
        "realtime_mover": realtime_movers[:28],
        "news_surge": _ranked(rows, "news_surge_score", 24),
        "trading_value_top": _ranked(rows, "trading_value", 28),
        "change_rate_top": _ranked(rows, "change_pct", 24),
        "research_high_score": _ranked(rows, "snapshot_research_score", 24, min_value=0.65),
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
        symbol = _normalize_symbol(item.get("code") or item.get("symbol"))
        market = _normalize_market(item.get("market"))
        item["candidate_rank"] = _normalize_candidate_rank(item.get("candidate_rank"))
        identity = _resolve_company_identity(symbol, market, item.get("name"))
        if identity.get("name"):
            item["name"] = identity["name"]
        if identity.get("sector") and not item.get("sector"):
            item["sector"] = identity["sector"]
        sources = item.get("candidate_sources") if isinstance(item.get("candidate_sources"), list) else []
        if not sources:
            sources = ["strategy_scan"]
        item["candidate_sources"] = sources
        item["candidate_source"] = "realtime_mover" if "realtime_mover" in sources else "news_surge" if "news_surge" in sources else sources[0]
        item["selection_reason"] = ",".join(sources)
        item["selection_criteria"] = {
            "trading_value": item.get("trading_value"),
            "change_pct": item.get("change_pct"),
            "news_surge_score": item.get("news_surge_score"),
            "source_ranks": item.get("source_ranks") if isinstance(item.get("source_ranks"), dict) else {},
        }
        item["monitor_priority"] = _candidate_priority(item, held_symbols=held_symbols, interest_symbols=interest_symbols)
    return rows


def _strategy_scans_for_market(normalized_market: str) -> list[dict[str, Any]]:
    return [
        scan for scan in list_strategy_scans()
        if isinstance(scan, dict) and _normalize_market(scan.get("market")) == normalized_market
    ]


def _dedupe_market_candidates(
    market: str,
    *,
    account: dict[str, Any] | None = None,
    market_evidence_limit: int = DEFAULT_MARKET_EVIDENCE_LIMIT,
) -> list[dict[str, Any]]:
    normalized_market = _normalize_market(market)
    held_symbols = _held_symbols(account, normalized_market)
    interest_rows = _load_interest_watchlist(normalized_market)
    interest_symbols = set(interest_rows)
    best_by_symbol: dict[str, dict[str, Any]] = {}
    for scan in _strategy_scans_for_market(normalized_market):
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
    for candidate in _configured_universe_candidates(normalized_market):
        symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
        if not symbol:
            continue
        merged = dict(candidate)
        merged.update(_snapshot_meta(merged))
        best_by_symbol[symbol] = _merge_candidate(best_by_symbol.get(symbol), merged)
    for symbol in sorted(held_symbols):
        if symbol not in best_by_symbol:
            best_by_symbol[symbol] = {
                "code": symbol,
                "symbol": symbol,
                "market": normalized_market,
                **_resolve_company_identity(symbol, normalized_market),
                "candidate_source": "held_position",
                "final_action": "watch_only",
                "signal_state": "watch",
                "score": 0,
                "candidate_rank": None,
                "last_scanned_at": _now_local().isoformat(timespec="seconds"),
            }
    for symbol, row in interest_rows.items():
        best_by_symbol[symbol] = _merge_candidate(best_by_symbol.get(symbol), row)
    rows_with_market_evidence = _with_realtime_market_evidence(
        list(best_by_symbol.values()),
        limit=market_evidence_limit,
    )
    rows = _annotate_standard_sources(rows_with_market_evidence, held_symbols=held_symbols, interest_symbols=interest_symbols)
    rows.sort(
        key=lambda item: (
            float(item.get("monitor_priority") or 0.0),
            -_rank_sort_value(item.get("candidate_rank")),
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
    refresh: bool = False,
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
    pool = _dedupe_market_candidates(
        normalized_market,
        account=account,
        market_evidence_limit=max(pool_limit, DEFAULT_MARKET_EVIDENCE_LIMIT),
    )[:pool_limit]
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

    promotion_candidates = _select_promotion_candidates(pool, used_symbols, promotion_limit)
    promotion_selected = 0
    for candidate in promotion_candidates:
        symbol = _normalize_symbol(candidate.get("code") or candidate.get("symbol"))
        if symbol in used_symbols:
            continue
        reason = str(candidate.get("candidate_source") or candidate.get("selection_reason") or "promotion_slot")
        active_rows.append({**candidate, "symbol": symbol, "slot_type": "promotion", "priority": int(candidate.get("monitor_priority") or 0), "reason": reason})
        used_symbols.add(symbol)
        promotion_selected += 1

    store.replace_active_slots(normalized_market, active_rows, selected_at=now_iso)
    current_symbols_for_audit = {
        _normalize_symbol(row.get("symbol") or row.get("code"))
        for row in active_rows
        if _normalize_symbol(row.get("symbol") or row.get("code"))
    }
    missed_movers = _missed_market_movers(pool, current_symbols_for_audit)
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
                "bluechip_core",
                "research_high_score",
                "realtime_mover",
                "trading_value_top",
                "change_rate_top",
                "news_surge",
                "held_position",
                "user_watchlist",
            ],
            "source_counts": source_counts,
            "news_surge_priority": "requires_market_evidence_for_top_priority",
            "market_evidence_limit": max(pool_limit, DEFAULT_MARKET_EVIDENCE_LIMIT),
            "missed_mover_count": len(missed_movers),
            "missed_movers": [
                {
                    "symbol": _normalize_symbol(row.get("code") or row.get("symbol")),
                    "name": row.get("name"),
                    "change_pct": row.get("change_pct"),
                    "trading_value": row.get("trading_value"),
                    "monitor_priority": row.get("monitor_priority"),
                }
                for row in missed_movers
            ],
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
    for row in missed_movers:
        symbol = _normalize_symbol(row.get("code") or row.get("symbol"))
        if symbol:
            store.append_promotion_event(normalized_market, symbol, "missed_mover", "mover_not_active", row, created_at=now_iso)

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
    for market in markets or ["KOSPI"]:
        normalized = _normalize_market(market)
        if normalized and normalized not in normalized_markets:
            normalized_markets.append(normalized)
    if not normalized_markets:
        normalized_markets = ["KOSPI"]
    return [
        build_market_watchlist(market, account=account, refresh=refresh) if refresh else get_market_watchlist(market)
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
    if normalized_mode == "all":
        return True
    if normalized_mode == "missing_only":
        return not snapshot_exists
    if normalized_mode == "stale_only":
        return snapshot_exists and not snapshot_fresh
    return (not snapshot_exists) or (not snapshot_fresh)


def _with_latest_research_snapshot_meta(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    symbol = _normalize_symbol(row.get("symbol") or row.get("code"))
    market = _normalize_market(row.get("market"))
    if not symbol or not market:
        return row

    snapshot = load_latest_research_snapshot(symbol, market, provider=DEFAULT_RESEARCH_PROVIDER)
    if not isinstance(snapshot, dict):
        row.update({
            "snapshot_exists": False,
            "snapshot_fresh": False,
            "snapshot_generated_at": "",
            "snapshot_research_score": None,
            "research_status": "missing",
            "validation_grade": "",
        })
        return row

    freshness = str(
        snapshot.get("freshness")
        or (snapshot.get("freshness_detail") if isinstance(snapshot.get("freshness_detail"), dict) else {}).get("status")
        or "missing"
    ).strip().lower()
    validation = snapshot.get("validation") if isinstance(snapshot.get("validation"), dict) else {}
    row.update({
        "snapshot_exists": True,
        "snapshot_fresh": freshness == "fresh",
        "snapshot_generated_at": str(snapshot.get("generated_at") or ""),
        "snapshot_research_score": snapshot.get("research_score"),
        "research_status": freshness,
        "validation_grade": str(validation.get("grade") or "").upper(),
    })
    payload = dict(row.get("payload")) if isinstance(row.get("payload"), dict) else {}
    payload.update({
        "snapshot_exists": row["snapshot_exists"],
        "snapshot_fresh": row["snapshot_fresh"],
        "snapshot_generated_at": row["snapshot_generated_at"],
        "snapshot_research_score": row["snapshot_research_score"],
        "research_status": row["research_status"],
        "validation_grade": row["validation_grade"],
    })
    row["payload"] = payload
    return row


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
            if not _is_active_research_market(key[0]):
                continue
            if not key[0] or not key[1] or key in seen:
                continue
            row_with_meta = _with_latest_research_snapshot_meta(row)
            if not _matches_pending_mode(row_with_meta, mode):
                continue
            seen.add(key)
            rows.append(row_with_meta)
    rows.sort(
        key=lambda item: (
            int(item.get("priority") or item.get("monitor_priority") or 0),
            -_rank_sort_value(item.get("candidate_rank")),
            str(item.get("market") or ""),
            str(item.get("symbol") or item.get("code") or ""),
        ),
        reverse=True,
    )
    capped = max(0, int(limit or 0))
    return rows[:capped] if capped > 0 else rows


def list_recent_promotion_events(markets: list[str] | None = None, *, limit: int = DEFAULT_PROMOTION_EVENT_LIMIT) -> list[dict[str, Any]]:
    normalized_markets: list[str] = []
    for market in markets or ["KOSPI"]:
        normalized = _normalize_market(market)
        if normalized and normalized not in normalized_markets:
            normalized_markets.append(normalized)
    rows: list[dict[str, Any]] = []
    for market in normalized_markets or ["KOSPI"]:
        rows.extend(store.list_promotion_events(market, limit=limit))
    rows.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
    capped = max(1, int(limit or DEFAULT_PROMOTION_EVENT_LIMIT))
    return rows[:capped]
