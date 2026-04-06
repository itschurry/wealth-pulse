from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from services.json_utils import json_dump_compact, json_dump_text, read_json_file_cached
from services.research_contract import normalize_and_validate_warning_codes, normalize_tags
from market_utils import normalize_market


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
        payload = read_json_file_cached(path)
    except OSError:
        return dict(default)
    except Exception:
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json_dump_text(payload, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(f"{json_dump_compact(payload)}\n")


def _safe_key(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in str(value or "").strip()) or "default"


def _normalize_market_input(value: str) -> str:
    normalized = normalize_market(value)
    return str(normalized or "").strip().upper()


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
    normalized_market = _normalize_market_input(market)
    return RESEARCH_LATEST_DIR / f"{_safe_key(provider)}__{_safe_key(normalized_market)}__{_safe_key(symbol.upper())}.json"


def _history_snapshot_path(provider: str, market: str, symbol: str) -> Path:
    normalized_market = _normalize_market_input(market)
    return RESEARCH_DIR / "history" / f"{_safe_key(provider)}__{_safe_key(normalized_market)}__{_safe_key(symbol.upper())}.jsonl"


def _normalize_bucket_ts(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError("invalid_timestamp")
    normalized = parsed.astimezone(parsed.tzinfo or datetime.timezone.utc)
    normalized = normalized.replace(second=0, microsecond=0)
    return normalized.isoformat()


def _parse_score(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}_invalid")
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{field}_out_of_range")
    return score


def _snapshot_history_key(item: dict[str, Any]) -> str:
    return "|".join(
        [
            str(item.get("provider") or "").strip().lower(),
            str(item.get("symbol") or "").strip().upper(),
            _normalize_market_input(str(item.get("market") or "")),
            str(item.get("bucket_ts") or ""),
        ]
    )


def _is_newer_snapshot(left: dict[str, Any], right: dict[str, Any] | None) -> bool:
    if right is None:
        return True
    if not isinstance(right, dict):
        return True
    if not right.get("bucket_ts") and not right.get("generated_at") and not right.get("ingested_at"):
        return True

    left_bucket = _parse_datetime(left.get("bucket_ts"))
    right_bucket = _parse_datetime(right.get("bucket_ts"))
    if left_bucket is not None and right_bucket is not None:
        if left_bucket > right_bucket:
            return True
        if left_bucket < right_bucket:
            return False

    left_generated = _parse_datetime(left.get("generated_at"))
    right_generated = _parse_datetime(right.get("generated_at"))
    if left_generated is not None and right_generated is not None:
        if left_generated > right_generated:
            return True
        if left_generated < right_generated:
            return False

    left_ingested = _parse_datetime(left.get("ingested_at"))
    right_ingested = _parse_datetime(right.get("ingested_at"))
    if left_ingested is not None and right_ingested is not None:
        if left_ingested > right_ingested:
            return True
        if left_ingested < right_ingested:
            return False

    return False


def _iter_history_rows(path: Path) -> list[dict[str, Any]]:
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
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _write_history_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    _ensure_parent(path)
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(f"{json.dumps(row, ensure_ascii=False, separators=(',', ':'))}\n")


def _dedupe_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    newest_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _snapshot_history_key(row)
        if key in newest_by_key and _is_newer_snapshot(row, newest_by_key[key]):
            newest_by_key[key] = row
        elif key not in newest_by_key:
            newest_by_key[key] = row
    return list(newest_by_key.values())


def _history_sort_key(item: dict[str, Any]) -> tuple[datetime.datetime, datetime.datetime, str]:
    bucket_dt = _parse_datetime(item.get("bucket_ts")) or datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
    ingested_dt = _parse_datetime(item.get("ingested_at")) or bucket_dt
    return (bucket_dt, ingested_dt, str(item.get("run_id") or ""))


def _normalize_components(value: Any) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("components_must_be_object")

    components: dict[str, float] = {}
    for key, item in value.items():
        score = _parse_score(item, field="component_score")
        if score is None:
            raise ValueError("component_score_invalid")
        components[str(key)] = score
    return components


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
    market = _normalize_market_input(str(item.get("market") or ""))
    if not symbol or not market:
        raise ValueError("symbol_market_required")

    generated_at = str(item.get("generated_at") or default_generated_at or "").strip()
    if not generated_at:
        raise ValueError("generated_at_required")

    bucket_ts = str(item.get("bucket_ts") or "").strip()
    if not bucket_ts:
        raise ValueError("bucket_ts_required")

    generated_at = _normalize_bucket_ts(generated_at)
    bucket_ts = _normalize_bucket_ts(bucket_ts)

    ttl_raw = item.get("ttl_minutes")
    if ttl_raw is None:
        ttl_minutes = 120
    else:
        try:
            ttl_minutes = int(ttl_raw)
        except (TypeError, ValueError):
            raise ValueError("ttl_minutes_invalid") from None
        if ttl_minutes <= 0:
            raise ValueError("ttl_minutes_invalid")

    return {
        "provider": provider,
        "schema_version": schema_version,
        "run_id": run_id,
        "symbol": symbol,
        "market": market,
        "bucket_ts": bucket_ts,
        "generated_at": generated_at,
        "ingested_at": ingested_at,
        "research_score": _parse_score(item.get("research_score"), field="research_score"),
        "components": _normalize_components(item.get("components")),
        "warnings": normalize_and_validate_warning_codes(item.get("warnings", [])),
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
            "received_valid": 0,
            "deduped_count": 0,
            "rejected": 1,
            "errors": [{"index": -1, "error": "provider_mismatch"}],
        }

    if schema_version != OPENCLAW_SCHEMA_VERSION:
        return {
            "ok": False,
            "provider": provider,
            "run_id": "",
            "accepted": 0,
            "received_valid": 0,
            "deduped_count": 0,
            "rejected": 1,
            "errors": [{"index": -1, "error": "schema_version_unsupported"}],
        }

    run_id = str(payload.get("run_id") or "").strip() or f"{provider}-{_now_iso()}"
    generated_at = str(payload.get("generated_at") or _now_iso()).strip()
    if not generated_at:
        return {
            "ok": False,
            "provider": provider,
            "run_id": run_id,
            "accepted": 0,
            "received_valid": 0,
            "deduped_count": 0,
            "rejected": 1,
            "errors": [{"index": -1, "error": "generated_at_required"}],
        }

    items = payload.get("items")
    if not isinstance(items, list):
        return {
            "ok": False,
            "provider": provider,
            "run_id": run_id,
            "accepted": 0,
            "received_valid": 0,
            "deduped_count": 0,
            "rejected": 0,
            "errors": [{"index": -1, "error": "items_must_be_list"}],
        }

    ingested_at = _now_iso()
    accepted_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    validated_item_count = 0
    batch_unique_by_key: dict[str, dict[str, Any]] = {}
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
        validated_item_count += 1

        key = _snapshot_history_key(normalized)
        if key in batch_unique_by_key and not _is_newer_snapshot(normalized, batch_unique_by_key[key]):
            continue
        batch_unique_by_key[key] = normalized

    for item in batch_unique_by_key.values():
        history_path = _history_snapshot_path(item["provider"], item["market"], item["symbol"])
        accepted_items.append(item)

    accepted_by_path: dict[Path, list[dict[str, Any]]] = {}
    for item in accepted_items:
        path = _history_snapshot_path(item["provider"], item["market"], item["symbol"])
        accepted_by_path.setdefault(path, []).append(item)

    persisted_count = 0
    for path, items in accepted_by_path.items():
        existing_rows = _iter_history_rows(path)
        existing_by_key = {_snapshot_history_key(row): row for row in _dedupe_history_rows(existing_rows)}
        for item in items:
            key = _snapshot_history_key(item)
            existing = existing_by_key.get(key)
            if existing is None or _is_newer_snapshot(item, existing):
                persisted_count += 1
        merged_rows = _dedupe_history_rows(existing_rows + items)
        merged_rows.sort(key=_history_sort_key, reverse=True)
        _write_history_rows(path, merged_rows)

    for item in accepted_items:
        _append_jsonl(RESEARCH_INGEST_LOG_PATH, item)

        latest_path = _latest_snapshot_path(provider, item["market"], item["symbol"])
        existing_latest = _read_json(latest_path, {})
        if _is_newer_snapshot(item, existing_latest if isinstance(existing_latest, dict) else None):
            _write_json(latest_path, item)

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
        "accepted_last_run": persisted_count,
        "received_valid_last_run": validated_item_count,
        "deduped_count_last_run": max(0, validated_item_count - persisted_count),
        "rejected_last_run": len(errors),
        "fresh_until": fresh_until,
    }
    _write_json(RESEARCH_PROVIDER_STATE_PATH, {"providers": providers})

    return {
        "ok": not errors,
        "provider": provider,
        "run_id": run_id,
        "accepted": persisted_count,
        "received_valid": validated_item_count,
        "deduped_count": max(0, validated_item_count - persisted_count),
        "rejected": len(errors),
        "errors": errors,
    }


def _resolve_market_aliases(market: str) -> list[str]:
    normalized = _normalize_market_input(market)
    raw = str(market or "").strip().upper()
    if normalized and raw and raw != normalized:
        return [normalized, raw]
    if normalized:
        return [normalized]
    return [raw] if raw else []


def _history_candidate_paths(provider: str, symbol: str, market: str) -> list[Path]:
    paths: list[Path] = []
    for normalized_market in _resolve_market_aliases(market):
        paths.append(_history_snapshot_path(provider, normalized_market, symbol))
    return list(dict.fromkeys(paths))


def _latest_snapshot_candidates(provider: str, symbol: str, market: str) -> list[Path]:
    paths: list[Path] = []
    for normalized_market in _resolve_market_aliases(market):
        paths.append(_latest_snapshot_path(provider, normalized_market, symbol))
    return list(dict.fromkeys(paths))


def load_provider_status(provider: str = OPENCLAW_PROVIDER) -> dict[str, Any]:
    """Compute provider status from latest snapshot files and provider ingest metadata."""
    provider_key = str(provider).strip().lower() or OPENCLAW_PROVIDER
    payload = _read_json(RESEARCH_PROVIDER_STATE_PATH, {"providers": {}})
    providers = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
    state = providers.get(provider_key)

    latest_snapshot_candidates_map: dict[str, dict[str, Any]] = {}
    for path in RESEARCH_LATEST_DIR.glob("*.json"):
        payload = _read_json(path, {})
        if str(payload.get("provider") or "").strip().lower() != provider_key:
            continue
        if str(payload.get("symbol") or "").strip() == "":
            continue
        normalized_market = _normalize_market_input(str(payload.get("market") or ""))
        if not normalized_market:
            continue
        key = (
            str(payload.get("provider") or "").strip().lower()
            + "|"
            + str(payload.get("symbol") or "").strip().upper()
            + "|"
            + normalized_market
        )
        existing = latest_snapshot_candidates_map.get(key)
        if existing is None or _is_newer_snapshot(payload, existing):
            latest_snapshot_candidates_map[key] = payload

    latest_snapshots = list(latest_snapshot_candidates_map.values())

    now = datetime.datetime.now(datetime.timezone.utc)
    if not latest_snapshots:
        return {
            "ok": True,
            "provider": provider_key,
            "status": "missing",
            "freshness": "missing",
            "source": "latest_snapshot_directory",
            "source_of_truth": "latest_snapshot_directory",
            "last_received_at": "",
            "last_generated_at": "",
            "last_run_id": "",
            "accepted_last_run": 0,
            "rejected_last_run": 0,
            "received_valid_last_run": 0,
            "deduped_count_last_run": 0,
            "coverage_count": 0,
            "fresh_symbol_count": 0,
            "stale_symbol_count": 0,
            "latest_bucket_ts": "",
            "accept_ratio": 0.0,
        }

    stale_symbol_count = 0
    fresh_symbol_count = 0
    latest_bucket_dt = None
    for snapshot in latest_snapshots:
        generated_at = _parse_datetime(snapshot.get("generated_at"))
        ttl_minutes = int(snapshot.get("ttl_minutes") or 0)
        bucket_dt = _parse_datetime(snapshot.get("bucket_ts"))

        if generated_at is None or ttl_minutes <= 0:
            stale_symbol_count += 1
        else:
            stale_at = generated_at + datetime.timedelta(minutes=ttl_minutes)
            if now > stale_at:
                stale_symbol_count += 1
            else:
                fresh_symbol_count += 1

        if latest_bucket_dt is None or (bucket_dt is not None and bucket_dt > latest_bucket_dt):
            latest_bucket_dt = bucket_dt

    total_count = len(latest_snapshots)
    accepted_last_run = int(state.get("accepted_last_run") or 0) if isinstance(state, dict) else 0
    rejected_last_run = int(state.get("rejected_last_run") or 0) if isinstance(state, dict) else 0
    received_valid_last_run = int(state.get("received_valid_last_run") or 0) if isinstance(state, dict) else 0
    deduped_count_last_run = int(state.get("deduped_count_last_run") or 0) if isinstance(state, dict) else 0
    total_run_count = accepted_last_run + rejected_last_run
    accept_ratio = (accepted_last_run / total_run_count) if total_run_count > 0 else 0.0
    freshness = "fresh" if (fresh_symbol_count > 0 and stale_symbol_count == 0) else "stale"
    status = "healthy"
    if freshness == "stale":
        status = "stale_ingest"
    elif rejected_last_run > 0:
        status = "degraded"

    return {
        "ok": True,
        "provider": provider_key,
        "status": status,
        "freshness": freshness,
        "source_of_truth": "latest_snapshot_directory",
        "source": "latest_snapshot_directory",
        "last_received_at": str(state.get("last_received_at") or ""),
        "last_generated_at": str(state.get("last_generated_at") or ""),
        "last_run_id": str(state.get("last_run_id") or ""),
        "accepted_last_run": accepted_last_run,
        "rejected_last_run": rejected_last_run,
        "received_valid_last_run": received_valid_last_run,
        "deduped_count_last_run": deduped_count_last_run,
        "coverage_count": total_count,
        "fresh_symbol_count": fresh_symbol_count,
        "stale_symbol_count": stale_symbol_count,
        "latest_bucket_ts": latest_bucket_dt.isoformat() if latest_bucket_dt else "",
        "accept_ratio": round(accept_ratio, 4),
    }


def load_latest_research_snapshot(symbol: str, market: str, *, provider: str = "openclaw") -> dict[str, Any] | None:
    provider = str(provider or "").strip().lower() or OPENCLAW_PROVIDER
    symbol = str(symbol or "").strip().upper()
    selected: dict[str, Any] | None = None
    for path in _latest_snapshot_candidates(provider, symbol, market):
        payload = _read_json(path, {})
        if not payload:
            continue
        if selected is None or _is_newer_snapshot(payload, selected):
            selected = payload
    return selected


def list_latest_research_snapshots(
    *,
    provider: str = OPENCLAW_PROVIDER,
    market: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    provider_key = str(provider or "").strip().lower() or OPENCLAW_PROVIDER
    normalized_market = _normalize_market_input(market or "") if market else ""
    newest_by_symbol_market: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in RESEARCH_LATEST_DIR.glob("*.json"):
        payload = _read_json(path, {})
        if not payload:
            continue
        payload_provider = str(payload.get("provider") or "").strip().lower()
        payload_symbol = str(payload.get("symbol") or "").strip().upper()
        payload_market = _normalize_market_input(str(payload.get("market") or ""))
        if payload_provider != provider_key:
            continue
        if not payload_symbol or not payload_market:
            continue
        if normalized_market and payload_market != normalized_market:
            continue
        dedupe_key = (payload_provider, payload_symbol, payload_market)
        existing = newest_by_symbol_market.get(dedupe_key)
        if existing is None or _is_newer_snapshot(payload, existing):
            normalized_payload = dict(payload)
            normalized_payload["market"] = payload_market
            newest_by_symbol_market[dedupe_key] = normalized_payload

    rows = list(newest_by_symbol_market.values())
    rows.sort(key=_history_sort_key, reverse=True)
    if limit > 0:
        rows = rows[:limit]
    return rows


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

    rows: list[dict[str, Any]] = []
    normalized_symbol = symbol.strip().upper()
    normalized_market = _normalize_market_input(market)
    for path in _history_candidate_paths(provider, normalized_symbol, normalized_market):
        rows.extend(_iter_history_rows(path))
    if not rows:
        return []

    normalized_provider = str(provider).strip().lower()

    filtered_rows: list[dict[str, Any]] = []
    for item in rows:
        if str(item.get("provider") or provider).strip().lower() != normalized_provider:
            continue
        if str(item.get("symbol") or "").strip().upper() != normalized_symbol:
            continue
        if _normalize_market_input(str(item.get("market") or "")) != normalized_market:
            continue

        bucket_dt = _parse_datetime(item.get("bucket_ts"))
        if bucket_dt is None:
            continue

        if start_dt is not None and bucket_dt < start_dt:
            continue
        if end_dt is not None and bucket_dt > end_dt:
            continue
        filtered_rows.append(item)

    rows = _dedupe_history_rows(filtered_rows)

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
    """Select the best snapshot candidate for the requested timestamp.

    This function only performs bucket-aware lookup, it does not enforce TTL.
    Staleness is evaluated by runtime scorer (StoredResearchScorer).
    """
    parsed = _parse_datetime(request_timestamp)
    if parsed is None:
        return load_latest_research_snapshot(symbol, market, provider=provider)

    request_bucket = _normalize_bucket_ts(parsed.isoformat())
    candidates = load_research_snapshots(
        symbol,
        market,
        provider=provider,
        bucket_end=request_bucket,
        descending=True,
        limit=1,
    )
    if not candidates:
        return None
    return candidates[0]
