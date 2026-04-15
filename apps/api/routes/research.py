from __future__ import annotations

from services.research_store import (
    DEFAULT_RESEARCH_PROVIDER,
    ingest_research_snapshots,
    list_latest_research_snapshots,
    load_latest_research_snapshot,
    load_provider_status,
    load_research_snapshots,
)


def _query_provider(query: dict[str, list[str]]) -> str:
    return ((query.get("provider") or [DEFAULT_RESEARCH_PROVIDER])[0] or DEFAULT_RESEARCH_PROVIDER).strip().lower()


def handle_candidate_monitor_watchlist(query: dict[str, list[str]]):
    from routes.candidate_monitor import handle_candidate_monitor_watchlist as _impl

    return _impl(query)


def _iso_or_empty(value: object) -> str:
    return str(value or "").strip()


def _active_monitor_research_status(provider: str) -> dict | None:
    try:
        status_code, payload = handle_candidate_monitor_watchlist({
            "refresh": ["1"],
            "limit": ["200"],
            "mode": ["missing_or_stale"],
        })
    except Exception:
        return None
    if status_code != 200 or not isinstance(payload, dict):
        return None
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if not items:
        return None

    active_keys: set[tuple[str, str]] = set()
    latest_watchlist_generated_at = ""
    latest_snapshot_generated_at = ""
    fresh_count = 0
    stale_count = 0
    missing_count = 0

    for watchlist in items:
        if not isinstance(watchlist, dict):
            continue
        state = watchlist.get("state") if isinstance(watchlist.get("state"), dict) else {}
        generated_at = _iso_or_empty(state.get("generated_at"))
        if generated_at and generated_at > latest_watchlist_generated_at:
            latest_watchlist_generated_at = generated_at
        market_fallback = str(watchlist.get("market") or "").strip().upper()
        active_slots = watchlist.get("active_slots") if isinstance(watchlist.get("active_slots"), list) else []
        for slot in active_slots:
            if not isinstance(slot, dict):
                continue
            symbol = str(slot.get("symbol") or slot.get("code") or "").strip().upper()
            market = str(slot.get("market") or market_fallback or "").strip().upper()
            if not symbol or not market:
                continue
            active_keys.add((symbol, market))

    if not active_keys:
        return None

    for symbol, market in sorted(active_keys):
        snapshot = load_latest_research_snapshot(symbol, market, provider=provider)
        if not isinstance(snapshot, dict):
            missing_count += 1
            continue
        generated_at = _iso_or_empty(snapshot.get("generated_at"))
        if generated_at and generated_at > latest_snapshot_generated_at:
            latest_snapshot_generated_at = generated_at
        freshness = str(
            snapshot.get("freshness")
            or (snapshot.get("freshness_detail") if isinstance(snapshot.get("freshness_detail"), dict) else {}).get("status")
            or "missing"
        ).strip().lower()
        if freshness == "fresh":
            fresh_count += 1
        elif freshness in {"stale", "invalid"}:
            stale_count += 1
        else:
            missing_count += 1

    active_slot_count = len(active_keys)
    if fresh_count > 0 and stale_count == 0 and missing_count == 0:
        freshness = "fresh"
        status = "healthy"
    elif fresh_count == 0 and stale_count == 0 and missing_count > 0:
        freshness = "missing"
        status = "missing"
    else:
        freshness = "stale"
        status = "stale_ingest"

    return {
        "status": status,
        "freshness": freshness,
        "source_of_truth": "candidate_monitor_active_slots",
        "source": "candidate_monitor_active_slots",
        "active_slot_count": active_slot_count,
        "active_fresh_symbol_count": fresh_count,
        "active_stale_symbol_count": stale_count,
        "active_missing_symbol_count": missing_count,
        "active_watchlist_generated_at": latest_watchlist_generated_at,
        "last_generated_at": latest_snapshot_generated_at,
    }


def handle_research_ingest_bulk(payload: dict) -> tuple[int, dict]:
    try:
        result = ingest_research_snapshots(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
    status_code = 200 if result.get("accepted", 0) > 0 or result.get("rejected", 0) == 0 else 400
    return status_code, result


def handle_research_status(query: dict[str, list[str]]) -> tuple[int, dict]:
    provider = _query_provider(query)
    try:
        payload = load_provider_status(provider)
        active_status = _active_monitor_research_status(provider)
        if active_status:
            payload = {
                **payload,
                "storage_coverage_count": payload.get("coverage_count"),
                "storage_fresh_symbol_count": payload.get("fresh_symbol_count"),
                "storage_stale_symbol_count": payload.get("stale_symbol_count"),
                **active_status,
            }
        return 200, payload
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_research_latest_snapshot(query: dict[str, list[str]]) -> tuple[int, dict]:
    symbol = ((query.get("symbol") or [""])[0] or "").strip().upper()
    market = ((query.get("market") or [""])[0] or "").strip().upper()
    provider = _query_provider(query)
    if not symbol or not market:
        return 400, {"ok": False, "error": "symbol_market_required"}
    try:
        snapshot = load_latest_research_snapshot(symbol, market, provider=provider)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
    if not snapshot:
        return 404, {"ok": False, "error": "snapshot_not_found", "symbol": symbol, "market": market, "provider": provider}
    return 200, {"ok": True, "provider": provider, "symbol": symbol, "market": market, "snapshot": snapshot}


def _parse_limit_query(value: str | None, default_value: int = 50) -> int:
    if value is None:
        return default_value
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_value
    return max(0, parsed)


def _parse_bool_query(value: str | None) -> bool:
    if value is None:
        return True
    lowered = value.lower().strip()
    return lowered in {"1", "true", "yes", "y"}


def handle_research_snapshots(query: dict[str, list[str]]) -> tuple[int, dict]:
    symbol = ((query.get("symbol") or [""])[0] or "").strip().upper()
    market = ((query.get("market") or [""])[0] or "").strip().upper()
    provider = _query_provider(query)
    bucket_start = ((query.get("bucket_start") or [""])[0] or "").strip() or None
    bucket_end = ((query.get("bucket_end") or [""])[0] or "").strip() or None
    limit = _parse_limit_query((query.get("limit") or [None])[0], default_value=50)
    descending = _parse_bool_query((query.get("descending") or [None])[0])

    try:
        if not symbol and not market:
            snapshots = list_latest_research_snapshots(provider=provider, limit=limit)
            return 200, {
                "ok": True,
                "provider": provider,
                "symbol": "",
                "market": "",
                "bucket_start": "",
                "bucket_end": "",
                "descending": True,
                "limit": limit,
                "count": len(snapshots),
                "snapshots": snapshots,
                "source": "latest_snapshot_directory",
            }

        if not symbol or not market:
            return 400, {"ok": False, "error": "symbol_market_required"}

        snapshots = load_research_snapshots(
            symbol,
            market,
            provider=provider,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            limit=limit,
            descending=descending,
        )
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}

    return 200, {
        "ok": True,
        "provider": provider,
        "symbol": symbol,
        "market": market,
        "bucket_start": bucket_start or "",
        "bucket_end": bucket_end or "",
        "descending": descending,
        "limit": limit,
        "count": len(snapshots),
        "snapshots": snapshots,
    }
