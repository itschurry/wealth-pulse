from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Mapping

from config.settings import CACHE_DIR
from services.json_utils import read_json_file_cached
from services.research_store import DEFAULT_RESEARCH_PROVIDER

from .store import utc_now_iso

FRESH_STATUSES = {"fresh", "healthy", "derived"}
RESEARCH_LATEST_DIR = CACHE_DIR / "research_snapshots" / "latest"


def _safe_key(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in str(value or "").strip()) or "default"


def _latest_snapshot_path(provider: str, market: str, symbol: str) -> Path:
    return RESEARCH_LATEST_DIR / f"{_safe_key(provider)}__{_safe_key(market.upper())}__{_safe_key(symbol.upper())}.json"


def _parse_dt(value: Any) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _freshness(snapshot: Mapping[str, Any]) -> str:
    generated_at = _parse_dt(snapshot.get("generated_at"))
    if generated_at is None:
        return "invalid"
    ttl_minutes = int(snapshot.get("ttl_minutes") or 15)
    if ttl_minutes <= 0:
        return "invalid"
    return "fresh" if datetime.datetime.now(datetime.timezone.utc) <= generated_at + datetime.timedelta(minutes=ttl_minutes) else "stale"


def _read_latest_snapshot(symbol: str, market: str, *, provider: str) -> dict[str, Any] | None:
    path = _latest_snapshot_path(provider, market, symbol)
    if not path.exists():
        return None
    payload = read_json_file_cached(path)
    if not isinstance(payload, dict):
        raise ValueError(f"research snapshot is not an object: {path}")
    return payload


def _snapshot_state(candidate: Mapping[str, Any], *, provider: str) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or candidate.get("code") or "").strip().upper()
    market = str(candidate.get("market") or "").strip().upper()
    snapshot = _read_latest_snapshot(symbol, market, provider=provider)
    if not snapshot:
        return {
            "research_status": "missing",
            "snapshot_exists": False,
            "snapshot_fresh": False,
            "snapshot_generated_at": "",
            "snapshot_research_score": None,
            "validation_grade": "D",
        }

    freshness = str(snapshot.get("freshness") or "").strip().lower() or _freshness(snapshot)
    validation = snapshot.get("validation") if isinstance(snapshot.get("validation"), dict) else {}
    return {
        "research_status": freshness or "missing",
        "snapshot_exists": True,
        "snapshot_fresh": freshness in FRESH_STATUSES,
        "snapshot_generated_at": str(snapshot.get("generated_at") or ""),
        "snapshot_research_score": snapshot.get("research_score"),
        "snapshot_rating": str(snapshot.get("rating") or ""),
        "snapshot_action": str(snapshot.get("action") or ""),
        "validation_grade": str(validation.get("grade") or ""),
    }


def _is_pending(state: Mapping[str, Any], mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "missing_only":
        return not bool(state.get("snapshot_exists"))
    if mode == "stale_only":
        return bool(state.get("snapshot_exists")) and not bool(state.get("snapshot_fresh"))
    return not bool(state.get("snapshot_fresh"))


def build_research_queue(
    ranked_snapshot: Mapping[str, Any],
    *,
    provider: str = DEFAULT_RESEARCH_PROVIDER,
    mode: str = "missing_or_stale",
    limit: int = 30,
) -> dict[str, Any]:
    pending: list[dict[str, Any]] = []
    reviewed: list[dict[str, Any]] = []
    for candidate in ranked_snapshot.get("active_slots") or []:
        state = _snapshot_state(candidate, provider=provider)
        item = {**candidate, **state}
        reviewed.append(item)
        if _is_pending(state, mode):
            item["research_priority"] = float(candidate.get("monitor_priority") or 0)
            pending.append(item)

    pending.sort(key=lambda item: float(item.get("research_priority") or 0), reverse=True)
    selected = pending[: max(0, int(limit))]
    for index, item in enumerate(selected, start=1):
        item["research_rank"] = index

    return {
        "schema_version": "trading_pipeline.research_queue.v1",
        "market": ranked_snapshot.get("market"),
        "generated_at": utc_now_iso(),
        "provider": provider,
        "mode": mode,
        "reviewed_count": len(reviewed),
        "pending_count": len(selected),
        "items": selected,
        "reviewed_items": reviewed,
    }
