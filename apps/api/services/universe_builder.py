from __future__ import annotations

import copy
import datetime
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from market_utils import normalize_market
from services.json_utils import read_json_file_cached

UNIVERSE_RULE_ALIASES = {
    "top_liquidity_200": "kospi",
    "us_mega_cap": "sp500",
    "volatility_breakout_pool": "sp500",
    "kr_core_bluechips": "kospi",
}
_ALIASES_BY_RULE = {}
for _legacy_rule, _canonical_rule in UNIVERSE_RULE_ALIASES.items():
    _ALIASES_BY_RULE.setdefault(_canonical_rule, []).append(_legacy_rule)

UNIVERSE_RULE_LABELS = {
    "kospi": "KOSPI",
    "sp500": "S&P500",
}

UNIVERSE_MARKET_BY_RULE = {
    "kospi": "KOSPI",
    "sp500": "US",
}

UNIVERSE_ROOT = LOGS_DIR / "universe_snapshots"

_DEFAULT_MAX_AGE_MINUTES = 60


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_rule(rule_name: str) -> str:
    return (
        "".join(
            ch for ch in str(rule_name or "").lower().replace(" ", "_")
            if ch.isalnum() or ch in {"_"}
        )
        or "kospi"
    )


def _normalize_rule(rule_name: str) -> str:
    normalized = _safe_rule(rule_name)
    return UNIVERSE_RULE_ALIASES.get(normalized, normalized)


def _snapshot_dir(rule_name: str) -> Path:
    return UNIVERSE_ROOT / _normalize_rule(rule_name)


def _latest_snapshot_path(rule_name: str) -> Path:
    return _snapshot_dir(rule_name) / "latest.json"


def _latest_summary_path(rule_name: str) -> Path:
    return _snapshot_dir(rule_name) / "latest.summary.json"


def _legacy_snapshot_path(rule_name: str) -> Path:
    return UNIVERSE_ROOT / f"{_safe_rule(rule_name)}.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = read_json_file_cached(path)
        return payload if isinstance(payload, dict) else {}
    except OSError:
        return {}
    except Exception:
        return {}


def _minutes_since(timestamp: str) -> float | None:
    try:
        parsed = datetime.datetime.fromisoformat(str(timestamp))
    except Exception:
        return None
    delta = datetime.datetime.now(datetime.timezone.utc) - parsed.astimezone(datetime.timezone.utc)
    return delta.total_seconds() / 60.0


def _normalize_snapshot_symbol(row: dict[str, Any]) -> dict[str, Any] | None:
    code = str(row.get("code") or "").strip().upper()
    if not code:
        return None

    name = str(row.get("name") or code).strip()
    market = normalize_market(str(row.get("market") or "").strip())
    return {
        "code": code,
        "name": name,
        "market": market or "KOSPI",
        "sector": str(row.get("sector") or "").strip() or None,
        "source": str(row.get("source") or "snapshot"),
    }


def _normalize_snapshot(payload: dict[str, Any], *, market: str | None = None) -> dict[str, Any]:
    normalized_rule = _normalize_rule(str(payload.get("rule_name") or payload.get("universe") or "kospi"))
    normalized_market = normalize_market(market or str(payload.get("market") or "").strip())
    symbols: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()

    for row in payload.get("symbols", []) if isinstance(payload.get("symbols"), list) else []:
        if not isinstance(row, dict):
            continue

        normalized = _normalize_snapshot_symbol(row)
        if normalized is None:
            continue
        symbol_market = normalized.get("market") or ""
        if normalized_market and symbol_market and symbol_market != normalized_market:
            continue

        code = str(normalized.get("code") or "").upper()
        if code in seen_symbols:
            continue
        seen_symbols.add(code)
        symbols.append(normalized)

    excluded = payload.get("excluded")
    normalized_excluded: list[dict[str, Any]] = []
    if isinstance(excluded, list):
        for row in excluded:
            if not isinstance(row, dict):
                continue
            normalized_row = _normalize_snapshot_symbol(row)
            if normalized_row is None:
                continue
            excluded_market = normalized_row.get("market") or ""
            if normalized_market and excluded_market and excluded_market != normalized_market:
                continue
            normalized_excluded.append(normalized_row)

    symbol_count = int(payload.get("symbol_count") or len(symbols))
    if symbol_count != len(symbols):
        symbol_count = len(symbols)

    return {
        "rule_name": normalized_rule,
        "universe": str(payload.get("universe") or normalized_rule),
        "market": normalized_market or str(payload.get("market") or UNIVERSE_MARKET_BY_RULE.get(normalized_rule, "")),
        "as_of_date": str(payload.get("as_of_date") or ""),
        "generated_at": str(payload.get("generated_at") or payload.get("updated_at") or _now_iso()),
        "updated_at": str(payload.get("updated_at") or payload.get("generated_at") or _now_iso()),
        "created_at": str(payload.get("created_at") or ""),
        "schema_version": payload.get("schema_version", 1),
        "source": str(payload.get("source") or ""),
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        "symbol_count": symbol_count,
        "excluded_count": int(payload.get("excluded_count") or len(normalized_excluded)),
        "symbols": symbols,
        "excluded": normalized_excluded,
    }


def _empty_snapshot(rule_name: str) -> dict[str, Any]:
    normalized_rule = _normalize_rule(rule_name)
    return {
        "rule_name": normalized_rule,
        "universe": normalized_rule,
        "market": UNIVERSE_MARKET_BY_RULE.get(normalized_rule, ""),
        "schema_version": 1,
        "source": "snapshot_missing",
        "as_of_date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "generated_at": _now_iso(),
        "updated_at": _now_iso(),
        "symbols": [],
        "excluded": [],
        "symbol_count": 0,
        "excluded_count": 0,
        "meta": {"listing_key": UNIVERSE_RULE_LABELS.get(normalized_rule, normalized_rule), "status": "missing"},
    }


def _read_snapshot_summary(rule_name: str) -> dict[str, Any]:
    normalized_rule = _normalize_rule(rule_name)
    summary = _read_json(_latest_summary_path(normalized_rule))
    if summary:
        return summary

    latest_snapshot = _read_json(_latest_snapshot_path(normalized_rule))
    if latest_snapshot:
        return latest_snapshot

    legacy_snapshot = _read_json(_legacy_snapshot_path(normalized_rule))
    if legacy_snapshot:
        return legacy_snapshot

    for candidate_rule in _ALIASES_BY_RULE.get(normalized_rule, []):
        legacy = _read_json(_latest_summary_path(candidate_rule))
        if legacy:
            return legacy
        legacy = _read_json(_legacy_snapshot_path(candidate_rule))
        if legacy:
            return legacy
        legacy = _read_json(_latest_snapshot_path(candidate_rule))
        if legacy:
            return legacy

    legacy = _read_json(_latest_snapshot_path(UNIVERSE_RULE_ALIASES.get(normalized_rule, normalized_rule)))
    if legacy:
        return legacy

    return _empty_snapshot(normalized_rule)


def _read_snapshot_payload(rule_name: str) -> dict[str, Any]:
    normalized_rule = _normalize_rule(rule_name)
    snapshot = _read_json(_latest_snapshot_path(normalized_rule))
    if snapshot:
        return snapshot

    snapshot = _read_json(_legacy_snapshot_path(normalized_rule))
    if snapshot:
        return snapshot

    for candidate_rule in _ALIASES_BY_RULE.get(normalized_rule, []):
        legacy = _read_json(_legacy_snapshot_path(candidate_rule))
        if legacy:
            return legacy
        legacy = _read_json(_latest_snapshot_path(candidate_rule))
        if legacy:
            return legacy

    legacy = _read_json(_latest_snapshot_path(UNIVERSE_RULE_ALIASES.get(normalized_rule, normalized_rule)))
    if legacy:
        return legacy

    return _empty_snapshot(normalized_rule)


def build_universe_snapshot(rule_name: str, *, market: str | None = None) -> dict[str, Any]:
    payload = _read_snapshot_payload(rule_name)
    return _normalize_snapshot(payload, market=market)


def get_universe_snapshot_full(
    rule_name: str,
    *,
    market: str | None = None,
) -> dict[str, Any]:
    normalized_rule = _normalize_rule(rule_name)
    snapshot = _read_snapshot_payload(normalized_rule)
    normalized_snapshot = _normalize_snapshot(snapshot, market=market)
    return copy.deepcopy(normalized_snapshot)


def get_universe_snapshot(
    rule_name: str,
    *,
    market: str | None = None,
    refresh: bool = False,
    max_age_minutes: int = _DEFAULT_MAX_AGE_MINUTES,
) -> dict[str, Any]:
    normalized_rule = _normalize_rule(rule_name)
    summary = _read_snapshot_summary(normalized_rule)
    normalized_summary = _normalize_snapshot(summary, market=market)
    generated_at = str(normalized_summary.get("generated_at") or "")
    age_minutes = _minutes_since(generated_at)
    if (
        normalized_summary.get("source", "").lower() == "snapshot_missing"
        and normalized_summary.get("symbol_count", 0) == 0
    ):
        return copy.deepcopy(normalized_summary)

    if (
        not refresh
        and age_minutes is not None
        and age_minutes <= max_age_minutes
    ):
        return copy.deepcopy(normalized_summary)

    return get_universe_snapshot_full(normalized_rule, market=market)


def list_current_universes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not UNIVERSE_ROOT.exists():
        return rows

    for rule_dir in sorted((path for path in UNIVERSE_ROOT.iterdir() if path.is_dir())):
        payload = _read_json(rule_dir / "latest.summary.json")
        if not payload:
            payload = _read_json(rule_dir / "latest.json")
        if payload:
            rows.append(_normalize_snapshot({**payload, "rule_name": str(rule_dir.name)}))

    for path in sorted(UNIVERSE_ROOT.glob("*.json")):
        if path.name.endswith(".summary.json"):
            continue
        payload = _read_json(path)
        if payload:
            rows.append(_normalize_snapshot({**payload, "rule_name": path.stem}))

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("rule_name") or ""), str(row.get("market") or ""))
        if key not in deduped:
            deduped[key] = row

    result = list(deduped.values())
    result.sort(key=lambda item: str(item.get("updated_at") or item.get("generated_at") or item.get("as_of_date") or ""), reverse=True)
    return copy.deepcopy(result)
