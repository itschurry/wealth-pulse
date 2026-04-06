from __future__ import annotations

import datetime

from services.paper_runtime_store import list_strategy_scans
from services.research_store import (
    ingest_research_snapshots,
    list_latest_research_snapshots,
    load_latest_research_snapshot,
    load_provider_status,
    load_research_snapshots,
)


def handle_research_ingest_bulk(payload: dict) -> tuple[int, dict]:
    try:
        result = ingest_research_snapshots(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
    status_code = 200 if result.get("accepted", 0) > 0 or result.get("rejected", 0) == 0 else 400
    return status_code, result


def handle_research_status(query: dict[str, list[str]]) -> tuple[int, dict]:
    provider = (query.get("provider") or ["openclaw"])[0] or "openclaw"
    try:
        return 200, load_provider_status(provider)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_research_latest_snapshot(query: dict[str, list[str]]) -> tuple[int, dict]:
    symbol = ((query.get("symbol") or [""])[0] or "").strip().upper()
    market = ((query.get("market") or [""])[0] or "").strip().upper()
    provider = ((query.get("provider") or ["openclaw"])[0] or "openclaw").strip().lower()
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


def _parse_dt(value: str | None) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _snapshot_is_fresh(snapshot: dict | None, reference_at: str | None = None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    generated_at = _parse_dt(snapshot.get("generated_at"))
    ttl_minutes = int(snapshot.get("ttl_minutes") or 0)
    if generated_at is None or ttl_minutes <= 0:
        return False
    reference_dt = _parse_dt(reference_at) or datetime.datetime.now(datetime.timezone.utc)
    return reference_dt <= generated_at + datetime.timedelta(minutes=ttl_minutes)


def _collect_research_scanner_targets(provider: str, markets: set[str]) -> list[dict]:
    items: list[dict] = []
    deduped_by_key: dict[tuple[str, str], dict] = {}
    for row in list_strategy_scans():
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "").strip().upper()
        if markets and market not in markets:
            continue
        strategy_id = str(row.get("strategy_id") or "")
        strategy_name = str(row.get("strategy_name") or strategy_id)
        for candidate in row.get("top_candidates") or []:
            if not isinstance(candidate, dict):
                continue
            symbol = str(candidate.get("code") or "").strip().upper()
            candidate_market = str(candidate.get("market") or market).strip().upper()
            if not symbol or not candidate_market:
                continue
            snapshot = load_latest_research_snapshot(symbol, candidate_market, provider=provider)
            item = {
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "symbol": symbol,
                "market": candidate_market,
                "name": candidate.get("name") or "",
                "candidate_rank": candidate.get("candidate_rank"),
                "last_scanned_at": candidate.get("last_scanned_at") or row.get("last_scan_at") or "",
                "research_status": candidate.get("research_status"),
                "research_unavailable": candidate.get("research_unavailable"),
                "snapshot_exists": isinstance(snapshot, dict),
                "snapshot_fresh": _snapshot_is_fresh(snapshot, candidate.get("last_scanned_at") or row.get("last_scan_at") or None),
                "snapshot_generated_at": snapshot.get("generated_at") if isinstance(snapshot, dict) else "",
                "snapshot_research_score": snapshot.get("research_score") if isinstance(snapshot, dict) else None,
                "final_action": candidate.get("final_action"),
            }
            items.append(item)
            dedupe_key = (candidate_market, symbol)
            existing = deduped_by_key.get(dedupe_key)
            if existing is None:
                deduped_by_key[dedupe_key] = dict(item)
                continue
            existing_rank = existing.get("candidate_rank")
            item_rank = item.get("candidate_rank")
            try:
                existing_rank_num = int(existing_rank) if existing_rank is not None else 999999
            except (TypeError, ValueError):
                existing_rank_num = 999999
            try:
                item_rank_num = int(item_rank) if item_rank is not None else 999999
            except (TypeError, ValueError):
                item_rank_num = 999999
            if item_rank_num < existing_rank_num:
                deduped_by_key[dedupe_key] = dict(item)
    deduped_items = list(deduped_by_key.values())
    deduped_items.sort(key=lambda item: (not bool(item.get("snapshot_exists")), not bool(item.get("snapshot_fresh")), str(item.get("market") or ""), str(item.get("symbol") or "")))
    return deduped_items


def handle_research_scanner_targets(query: dict[str, list[str]]) -> tuple[int, dict]:
    provider = ((query.get("provider") or ["openclaw"])[0] or "openclaw").strip().lower()
    markets = {str(item or "").strip().upper() for item in (query.get("market") or []) if str(item or "").strip()}
    limit = _parse_limit_query((query.get("limit") or [None])[0], default_value=100)

    try:
        items = _collect_research_scanner_targets(provider, markets)
        if limit > 0:
            items = items[:limit]
        return 200, {
            "ok": True,
            "provider": provider,
            "count": len(items),
            "items": items,
            "missing_count": sum(1 for item in items if not item.get("snapshot_exists")),
            "stale_count": sum(1 for item in items if item.get("snapshot_exists") and not item.get("snapshot_fresh")),
            "fresh_count": sum(1 for item in items if item.get("snapshot_fresh")),
            "deduped": True,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_research_scanner_enrich_targets(query: dict[str, list[str]]) -> tuple[int, dict]:
    provider = ((query.get("provider") or ["openclaw"])[0] or "openclaw").strip().lower()
    markets = {str(item or "").strip().upper() for item in (query.get("market") or []) if str(item or "").strip()}
    limit = _parse_limit_query((query.get("limit") or [None])[0], default_value=30)
    mode = ((query.get("mode") or ["missing_or_stale"])[0] or "missing_or_stale").strip().lower()

    try:
        items = _collect_research_scanner_targets(provider, markets)
        if mode == "missing_only":
            filtered = [item for item in items if not item.get("snapshot_exists")]
        elif mode == "stale_only":
            filtered = [item for item in items if item.get("snapshot_exists") and not item.get("snapshot_fresh")]
        else:
            filtered = [item for item in items if (not item.get("snapshot_exists")) or (not item.get("snapshot_fresh"))]

        if limit > 0:
            filtered = filtered[:limit]

        return 200, {
            "ok": True,
            "provider": provider,
            "mode": mode,
            "count": len(filtered),
            "items": filtered,
            "targets": [
                {
                    "symbol": item.get("symbol"),
                    "market": item.get("market"),
                    "name": item.get("name"),
                }
                for item in filtered
            ],
            "missing_count": sum(1 for item in filtered if not item.get("snapshot_exists")),
            "stale_count": sum(1 for item in filtered if item.get("snapshot_exists") and not item.get("snapshot_fresh")),
            "fresh_count": sum(1 for item in filtered if item.get("snapshot_fresh")),
            "deduped": True,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_research_snapshots(query: dict[str, list[str]]) -> tuple[int, dict]:
    symbol = ((query.get("symbol") or [""])[0] or "").strip().upper()
    market = ((query.get("market") or [""])[0] or "").strip().upper()
    provider = ((query.get("provider") or ["openclaw"])[0] or "openclaw").strip().lower()
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
