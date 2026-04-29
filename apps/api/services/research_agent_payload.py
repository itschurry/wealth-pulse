from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from market_utils import normalize_market
from services.research_contract import normalize_tags, normalize_warning_codes
from services.research_store import (
    ALLOWED_AGENT_ACTIONS,
    ALLOWED_AGENT_RATINGS,
    DEFAULT_RESEARCH_PROVIDER,
)

MAX_AGENT_SIZE_INTENT_PCT = 5.0
DEFAULT_AGENT_TTL_MINUTES = 180


def _now_local() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()


def _minute_iso(value: Any | None = None) -> str:
    if value is None or value == "":
        parsed = _now_local()
    elif isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = dt.datetime.fromisoformat(str(value).strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone().replace(second=0, microsecond=0).isoformat()


def _as_score(value: Any, *, field: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}_invalid") from None
    if score > 1.0:
        score = score / 100.0
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{field}_out_of_range")
    return round(score, 4)


def _optional_score(value: Any, *, field: str) -> float | None:
    if value is None or value == "":
        return None
    return _as_score(value, field=field)


def _text(value: Any, *, field: str, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field}_required")
    return text


def _text_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field}_must_be_list")
    return [str(item).strip() for item in value if str(item).strip()]


def _object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field}_must_be_object")
    return dict(value)


def _object_list(value: Any, *, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field}_must_be_list")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field}_item_must_be_object")
        rows.append(dict(item))
    return rows


def _rating(value: Any) -> str:
    rating = _text(value, field="rating", required=True).lower()
    if rating not in ALLOWED_AGENT_RATINGS:
        raise ValueError("rating_unsupported")
    return rating


def _action(value: Any) -> str:
    action = _text(value, field="action", required=True).lower()
    if action not in ALLOWED_AGENT_ACTIONS:
        raise ValueError("action_unsupported")
    return action


def _is_buy_intent(rating: str, action: str) -> bool:
    return rating in {"strong_buy", "overweight"} and action in {"buy", "buy_watch"}


def _clamped_trade_plan(raw_plan: Any) -> dict[str, Any]:
    plan = _object(raw_plan, field="trade_plan")
    if "size_intent_pct" in plan:
        try:
            size_intent = float(plan.get("size_intent_pct"))
        except (TypeError, ValueError):
            raise ValueError("size_intent_pct_invalid") from None
        plan["size_intent_pct"] = round(max(0.0, min(MAX_AGENT_SIZE_INTENT_PCT, size_intent)), 4)
    plan.setdefault("sizing", "risk_guard_clamped")
    plan.setdefault("entry", "runtime_and_risk_guard_only")
    return plan


def _components(raw: Any, *, confidence: float, technical_features: dict[str, Any], news_inputs: list[dict[str, Any]]) -> dict[str, float]:
    components: dict[str, float] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            score = _optional_score(value, field="component_score")
            if score is not None:
                components[str(key)] = score
    components.setdefault("confidence_score", confidence)
    if technical_features:
        components.setdefault("technical_quality", 1.0)
    if news_inputs:
        components.setdefault("news_quality", 1.0)
    components.setdefault("freshness_score", 1.0)
    return components


def _analysis_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("items"), list):
        return [dict(item) for item in payload["items"] if isinstance(item, dict)]
    if isinstance(payload.get("analysis"), list):
        return [dict(item) for item in payload["analysis"] if isinstance(item, dict)]
    return [dict(payload)]


def _normalize_agent_item(item: dict[str, Any], *, default_generated_at: str, default_bucket_ts: str) -> dict[str, Any]:
    symbol = _text(item.get("symbol"), field="symbol", required=True).upper()
    market = normalize_market(_text(item.get("market"), field="market", required=True)).upper()
    if not market:
        raise ValueError("market_required")

    rating = _rating(item.get("rating"))
    action = _action(item.get("action"))
    confidence = _as_score(item.get("confidence"), field="confidence")
    research_score = _optional_score(item.get("research_score"), field="research_score")
    if research_score is None:
        research_score = confidence

    summary = _text(item.get("summary") or item.get("thesis"), field="summary", required=True)
    technical_features = _object(item.get("technical_features"), field="technical_features")
    news_inputs = _object_list(item.get("news_inputs"), field="news_inputs")
    evidence = _object_list(item.get("evidence"), field="evidence")
    data_quality = _object(item.get("data_quality"), field="data_quality")

    if _is_buy_intent(rating, action):
        if not technical_features:
            raise ValueError("technical_features_required_for_buy_intent")
        if not evidence:
            raise ValueError("evidence_required_for_buy_intent")

    data_quality.setdefault("has_recent_price", bool(technical_features))
    data_quality.setdefault("has_technical_features", bool(technical_features))
    data_quality.setdefault("has_news", bool(news_inputs))
    data_quality.setdefault("analysis_mode", "agent_research")

    tags = normalize_tags([*normalize_tags(item.get("tags")), "agent_research"])
    warnings = normalize_warning_codes(item.get("warnings"))
    generated_at = _minute_iso(item.get("generated_at") or default_generated_at)
    bucket_ts = _minute_iso(item.get("bucket_ts") or default_bucket_ts)

    ttl_raw = item.get("ttl_minutes", DEFAULT_AGENT_TTL_MINUTES)
    try:
        ttl_minutes = int(ttl_raw)
    except (TypeError, ValueError):
        raise ValueError("ttl_minutes_invalid") from None
    if ttl_minutes <= 0:
        raise ValueError("ttl_minutes_invalid")

    return {
        "symbol": symbol,
        "market": market,
        "bucket_ts": bucket_ts,
        "generated_at": generated_at,
        "research_score": research_score,
        "components": _components(item.get("components"), confidence=confidence, technical_features=technical_features, news_inputs=news_inputs),
        "warnings": warnings,
        "tags": tags,
        "summary": summary,
        "ttl_minutes": ttl_minutes,
        "confidence": confidence,
        "time_horizon_days": int(item.get("time_horizon_days") or 3),
        "rating": rating,
        "action": action,
        "candidate_source": _text(item.get("candidate_source") or "hermes_agent", field="candidate_source"),
        "bull_case": _text_list(item.get("bull_case"), field="bull_case"),
        "bear_case": _text_list(item.get("bear_case"), field="bear_case"),
        "catalysts": _text_list(item.get("catalysts"), field="catalysts"),
        "risks": _text_list(item.get("risks"), field="risks"),
        "invalidation_trigger": _object(item.get("invalidation_trigger"), field="invalidation_trigger"),
        "trade_plan": _clamped_trade_plan(item.get("trade_plan")),
        "technical_features": technical_features,
        "news_inputs": news_inputs,
        "evidence": evidence,
        "data_quality": data_quality,
    }


def build_agent_research_ingest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload_must_be_object")
    generated_at = _minute_iso(payload.get("generated_at"))
    bucket_ts = _minute_iso(payload.get("bucket_ts") or generated_at)
    items = [_normalize_agent_item(item, default_generated_at=generated_at, default_bucket_ts=bucket_ts) for item in _analysis_items(payload)]
    if not items:
        raise ValueError("items_required")
    return {
        "provider": DEFAULT_RESEARCH_PROVIDER,
        "schema_version": "v2",
        "source": "hermes-agent",
        "run_id": _text(payload.get("run_id") or f"hermes-agent-{uuid.uuid4().hex[:12]}", field="run_id"),
        "generated_at": generated_at,
        "items": items,
    }
