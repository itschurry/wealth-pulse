from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from services.research_contract import clamp_normalized_score, normalize_components, normalize_tags, normalize_warning_codes


RESEARCH_DIR = LOGS_DIR / "research_snapshots"
RESEARCH_LATEST_DIR = RESEARCH_DIR / "latest"
RESEARCH_INGEST_LOG_PATH = RESEARCH_DIR / "ingest_history.jsonl"
RESEARCH_PROVIDER_STATE_PATH = RESEARCH_DIR / "provider_state.json"
OPENCLAW_PROVIDER = "openclaw"
OPENCLAW_SCHEMA_VERSION = "v1"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n")


def _safe_key(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in str(value or "").strip()) or "default"


def _parse_datetime(value: Any) -> datetime.datetime | None:
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


def _latest_snapshot_path(provider: str, market: str, symbol: str) -> Path:
    return RESEARCH_LATEST_DIR / f"{_safe_key(provider)}__{_safe_key(market.upper())}__{_safe_key(symbol.upper())}.json"


def _history_snapshot_path(provider: str, market: str, symbol: str) -> Path:
    return RESEARCH_DIR / "history" / f"{_safe_key(provider)}__{_safe_key(market.upper())}__{_safe_key(symbol.upper())}.jsonl"


def _normalize_bucket_ts(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError("invalid_timestamp")
    normalized = parsed.astimezone(parsed.tzinfo or datetime.timezone.utc)
    normalized = normalized.replace(second=0, microsecond=0)
    return normalized.isoformat()


def _normalize_item(
    item: dict[str, Any],
    *,
    provider: str,
    schema_version: str,
    run_id: str,
    default_generated_at: str,
    ingested_at: str,
) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "").strip().upper()
    market = str(item.get("market") or "").strip().upper()
    if not symbol or not market:
        raise ValueError("symbol_market_required")

    generated_at = str(item.get("generated_at") or default_generated_at or "").strip()
    if not generated_at:
        raise ValueError("generated_at_required")

    bucket_ts = str(item.get("bucket_ts") or generated_at or "").strip()
    if not generated_at or not bucket_ts:
        raise ValueError("bucket_ts_required")

    generated_at = _normalize_bucket_ts(generated_at)
    bucket_ts = _normalize_bucket_ts(bucket_ts)

    ttl_raw = item.get("ttl_minutes")
    try:
        ttl_minutes = max(1, min(1440, int(ttl_raw if ttl_raw is not None else 120)))
    except (TypeError, ValueError):
        raise ValueError("ttl_minutes_invalid") from None

    return {
        "provider": provider,
        "schema_version": schema_version,
        "run_id": run_id,
        "symbol": symbol,
        "market": market,
        "bucket_ts": bucket_ts,
        "generated_at": generated_at,
        "ingested_at": ingested_at,
        "research_score": clamp_normalized_score(item.get("research_score")),
        "components": normalize_components(item.get("components")),
        "warnings": normalize_warning_codes(item.get("warnings")),
        "tags": normalize_tags(item.get("tags")),
        "summary": str(item.get("summary") or "").strip(),
        "ttl_minutes": ttl_minutes,
    }


def ingest_research_snapshots(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or OPENCLAW_PROVIDER).strip().lower() or OPENCLAW_PROVIDER
    schema_version = str(payload.get("schema_version") or OPENCLAW_SCHEMA_VERSION).strip() or OPENCLAW_SCHEMA_VERSION
    if provider != OPENCLAW_PROVIDER:
        return {
            "ok": False,
            "provider": provider,
            "run_id": "",
            "accepted": 0,
            "rejected": 1,
            "errors": [{"index": -1, "error": "provider_mismatch"}],
        }
    if schema_version != OPENCLAW_SCHEMA_VERSION:
        return {
            "ok": False,
            "provider": provider,
            "run_id": "",
            "accepted": 0,
            "rejected": 1,
            "errors": [{"index": -1, "error": "schema_version_unsupported"}],
        }
    run_id = str(payload.get("run_id") or "").strip() or f"{provider}-{_now_iso()}"
    generated_at = str(payload.get("generated_at") or _now_iso()).strip()
    items = payload.get("items")
    if not isinstance(items, list):
        return {
            "ok": False,
            "provider": provider,
            "run_id": run_id,
            "accepted": 0,
            "rejected": 0,
            "errors": [{"index": -1, "error": "items_must_be_list"}],
        }

    ingested_at = _now_iso()
    accepted_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": index, "error": "item_must_be_object"})
            continue
        try:
            normalized = _normalize_item(
                item,
                provider=provider,
                schema_version=schema_version,
                run_id=run_id,
                default_generated_at=generated_at,
                ingested_at=ingested_at,
            )
        except ValueError as exc:
            errors.append({"index": index, "error": str(exc)})
            continue
        accepted_items.append(normalized)

    for item in accepted_items:
        _append_jsonl(RESEARCH_INGEST_LOG_PATH, item)
        _append_jsonl(_history_snapshot_path(item["provider"], item["market"], item["symbol"]), item)
        _write_json(_latest_snapshot_path(provider, item["market"], item["symbol"]), item)

    provider_state_payload = _read_json(RESEARCH_PROVIDER_STATE_PATH, {"providers": {}})
    providers = provider_state_payload.get("providers") if isinstance(provider_state_payload.get("providers"), dict) else {}
    max_ttl = max((int(item.get("ttl_minutes") or 0) for item in accepted_items), default=0)
    fresh_until = ""
    if accepted_items:
        latest_generated_at = max((str(item.get("generated_at") or "") for item in accepted_items), default=generated_at)
        latest_dt = _parse_datetime(latest_generated_at)
        if latest_dt is not None and max_ttl > 0:
            fresh_until = (latest_dt + datetime.timedelta(minutes=max_ttl)).astimezone().isoformat(timespec="seconds")
    else:
        latest_generated_at = generated_at
    providers[provider] = {
        "provider": provider,
        "last_received_at": ingested_at,
        "last_generated_at": latest_generated_at,
        "last_run_id": run_id,
        "accepted_last_run": len(accepted_items),
        "rejected_last_run": len(errors),
        "fresh_until": fresh_until,
    }
    _write_json(RESEARCH_PROVIDER_STATE_PATH, {"providers": providers})

    return {
        "ok": len(accepted_items) > 0 and not errors,
        "provider": provider,
        "run_id": run_id,
        "accepted": len(accepted_items),
        "rejected": len(errors),
        "errors": errors,
    }


def load_provider_status(provider: str = "openclaw") -> dict[str, Any]:
    payload = _read_json(RESEARCH_PROVIDER_STATE_PATH, {"providers": {}})
    providers = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
    state = providers.get(str(provider).strip().lower() or "openclaw")
    if not isinstance(state, dict) or not state:
        return {
            "ok": True,
            "provider": str(provider).strip().lower() or "openclaw",
            "status": "missing",
            "freshness": "missing",
            "last_received_at": "",
            "last_generated_at": "",
            "last_run_id": "",
            "accepted_last_run": 0,
            "rejected_last_run": 0,
        }

    fresh_until = _parse_datetime(state.get("fresh_until"))
    now = datetime.datetime.now(datetime.timezone.utc)
    freshness = "fresh"
    status = "healthy"
    if fresh_until is not None and now > fresh_until:
        freshness = "stale"
        status = "stale_ingest"
    elif int(state.get("rejected_last_run") or 0) > 0:
        status = "degraded"

    return {
        "ok": True,
        "provider": str(state.get("provider") or provider),
        "status": status,
        "freshness": freshness,
        "last_received_at": str(state.get("last_received_at") or ""),
        "last_generated_at": str(state.get("last_generated_at") or ""),
        "last_run_id": str(state.get("last_run_id") or ""),
        "accepted_last_run": int(state.get("accepted_last_run") or 0),
        "rejected_last_run": int(state.get("rejected_last_run") or 0),
    }


def load_latest_research_snapshot(symbol: str, market: str, *, provider: str = "openclaw") -> dict[str, Any] | None:
    path = _latest_snapshot_path(provider, market, symbol)
    payload = _read_json(path, {})
    return payload or None


def load_research_snapshots(
    symbol: str,
    market: str,
    *,
    provider: str = OPENCLAW_PROVIDER,
    bucket_start: str | None = None,
    bucket_end: str | None = None,
    limit: int = 50,
    descending: bool = True,
) -> list[dict[str, Any]]:
    start_dt = _parse_datetime(bucket_start or "")
    end_dt = _parse_datetime(bucket_end or "")
    if limit <= 0:
        limit = 0
    if start_dt is not None and end_dt is not None and end_dt < start_dt:
        return []

    path = _history_snapshot_path(provider, market, symbol)
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue

            item_provider = str(item.get("provider") or provider).lower()
            if item_provider != str(provider).lower():
                continue
            if str(item.get("symbol") or "").upper() != symbol.upper() or str(item.get("market") or "").upper() != market.upper():
                continue

            bucket_dt = _parse_datetime(item.get("bucket_ts"))
            if bucket_dt is None:
                continue

            if start_dt is not None and bucket_dt < start_dt:
                continue
            if end_dt is not None and bucket_dt > end_dt:
                continue

            rows.append(item)

    def sort_key(item: dict[str, Any]) -> tuple[datetime.datetime, datetime.datetime, str]:
        bucket_dt = _parse_datetime(item.get("bucket_ts")) or datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
        ingested_dt = _parse_datetime(item.get("ingested_at")) or bucket_dt
        return (bucket_dt, ingested_dt, str(item.get("run_id") or ""))

    rows.sort(key=sort_key, reverse=descending)
    if limit and len(rows) > limit:
        rows = rows[:limit]
    return rows


def load_research_snapshot_for_timestamp(
    symbol: str,
    market: str,
    request_timestamp: str,
    *,
    provider: str = OPENCLAW_PROVIDER,
) -> dict[str, Any] | None:
    parsed = _parse_datetime(request_timestamp)
    if parsed is None:
        return load_latest_research_snapshot(symbol, market, provider=provider)

    request_bucket = _normalize_bucket_ts(parsed.isoformat())
    candidates = load_research_snapshots(symbol, market, provider=provider, bucket_end=request_bucket, descending=True, limit=1)
    if candidates:
        return candidates[0]
    return None
