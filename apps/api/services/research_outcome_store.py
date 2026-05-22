from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from config.settings import CACHE_DIR
from services.json_utils import clear_json_file_cache, json_dump_text, read_json_file_cached

OUTCOME_PATH = CACHE_DIR / "research_snapshots" / "outcomes.json"
HORIZONS = (1, 3, 5, 20)


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_dt(value: Any) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _outcome_key(snapshot: dict[str, Any]) -> str:
    return "|".join([
        str(snapshot.get("provider") or "default"),
        str(snapshot.get("market") or "").upper(),
        str(snapshot.get("symbol") or "").upper(),
        str(snapshot.get("run_id") or ""),
        str(snapshot.get("generated_at") or ""),
    ])


def _read_store() -> dict[str, Any]:
    try:
        payload = read_json_file_cached(OUTCOME_PATH)
    except OSError:
        return {"items": {}}
    except Exception:
        return {"items": {}}
    return payload if isinstance(payload, dict) else {"items": {}}


def _write_store(payload: dict[str, Any]) -> None:
    OUTCOME_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTCOME_PATH.write_text(json_dump_text(payload, indent=2), encoding="utf-8")
    clear_json_file_cache(OUTCOME_PATH)


def _price_at_research(snapshot: dict[str, Any]) -> float | None:
    technical = snapshot.get("technical_features") if isinstance(snapshot.get("technical_features"), dict) else {}
    for key in ("current_price", "close", "price"):
        price = _to_float(technical.get(key))
        if price is not None:
            return price
    trade_plan = snapshot.get("trade_plan") if isinstance(snapshot.get("trade_plan"), dict) else {}
    for key in ("entry_price", "reference_price"):
        price = _to_float(trade_plan.get(key))
        if price is not None:
            return price
    return None


def ensure_outcome_seed(snapshot: dict[str, Any]) -> dict[str, Any]:
    key = _outcome_key(snapshot)
    store = _read_store()
    items = store.get("items") if isinstance(store.get("items"), dict) else {}
    existing = items.get(key) if isinstance(items.get(key), dict) else {}
    if existing:
        return existing
    row = {
        "key": key,
        "provider": snapshot.get("provider") or "default",
        "symbol": str(snapshot.get("symbol") or "").upper(),
        "market": str(snapshot.get("market") or "").upper(),
        "run_id": snapshot.get("run_id") or "",
        "generated_at": snapshot.get("generated_at") or "",
        "rating": snapshot.get("rating") or "",
        "action": snapshot.get("action") or "",
        "research_score": snapshot.get("research_score"),
        "price_at_research": _price_at_research(snapshot),
        "return_1d": None,
        "return_3d": None,
        "return_5d": None,
        "return_20d": None,
        "max_drawdown_20d": None,
        "hit": None,
        "last_evaluated_at": "",
        "errors": [],
    }
    items[key] = row
    store["items"] = items
    _write_store(store)
    return row


def outcome_for_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    key = _outcome_key(snapshot)
    store = _read_store()
    items = store.get("items") if isinstance(store.get("items"), dict) else {}
    row = items.get(key)
    if isinstance(row, dict):
        return row
    return ensure_outcome_seed(snapshot)


def attach_outcome(snapshot: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(snapshot)
    enriched["outcomes"] = outcome_for_snapshot(enriched)
    return enriched


def _return_pct(base_price: float, current_price: float) -> float:
    return round(((current_price - base_price) / base_price) * 100.0, 4)


def _hit_for(row: dict[str, Any]) -> bool | None:
    action = str(row.get("action") or "").lower()
    rating = str(row.get("rating") or "").lower()
    direction = "buy" if action in {"buy", "buy_watch"} or rating in {"strong_buy", "overweight"} else "sell" if action in {"sell", "reduce"} or rating in {"sell", "underweight"} else ""
    if not direction:
        return None
    returns = [
        row.get("return_1d"),
        row.get("return_3d"),
        row.get("return_5d"),
        row.get("return_20d"),
    ]
    available = [float(item) for item in returns if isinstance(item, (int, float))]
    if not available:
        return None
    latest = available[-1]
    return latest > 0 if direction == "buy" else latest < 0


def evaluate_snapshot_outcome(snapshot: dict[str, Any], *, current_price: float, evaluated_at: str | None = None) -> dict[str, Any]:
    base_price = _price_at_research(snapshot)
    if base_price is None:
        raise ValueError("price_at_research_missing")
    generated_at = _parse_dt(snapshot.get("generated_at"))
    if generated_at is None:
        raise ValueError("generated_at_invalid")
    now = _parse_dt(evaluated_at) or _now_utc()
    row = ensure_outcome_seed(snapshot)
    returns_seen: list[float] = []
    for horizon in HORIZONS:
        if now < generated_at + datetime.timedelta(days=horizon):
            continue
        key = f"return_{horizon}d"
        if row.get(key) is None:
            row[key] = _return_pct(base_price, current_price)
        if isinstance(row.get(key), (int, float)):
            returns_seen.append(float(row[key]))
    if returns_seen:
        row["max_drawdown_20d"] = round(min(returns_seen), 4)
    row["hit"] = _hit_for(row)
    row["last_evaluated_at"] = (now.astimezone().isoformat(timespec="seconds"))

    store = _read_store()
    items = store.get("items") if isinstance(store.get("items"), dict) else {}
    items[row["key"]] = row
    store["items"] = items
    _write_store(store)
    return row


def load_outcome_summary() -> dict[str, Any]:
    store = _read_store()
    items = [item for item in (store.get("items") if isinstance(store.get("items"), dict) else {}).values() if isinstance(item, dict)]

    def _hit_rate(horizon: int) -> float | None:
        key = f"return_{horizon}d"
        rows = [
            item for item in items
            if isinstance(item.get(key), (int, float)) and item.get("hit") is not None
        ]
        if not rows:
            return None
        hits = sum(1 for item in rows if item.get("hit") is True)
        return round(hits / len(rows), 4)

    return {
        "outcome_count": len(items),
        "outcome_1d_hit_rate": _hit_rate(1),
        "outcome_3d_hit_rate": _hit_rate(3),
        "outcome_5d_hit_rate": _hit_rate(5),
        "outcome_20d_hit_rate": _hit_rate(20),
    }


def list_outcomes(limit: int = 200) -> list[dict[str, Any]]:
    store = _read_store()
    items = [item for item in (store.get("items") if isinstance(store.get("items"), dict) else {}).values() if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return items[:max(1, int(limit))]
