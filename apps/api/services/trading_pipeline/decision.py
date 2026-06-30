from __future__ import annotations

from typing import Any, Mapping

from domains.report.market_context_service import get_market_context
from helpers import _now_iso
from services.live_layers import build_layer_d_snapshot, build_layer_e_snapshot, build_layer_events
from services.risk_guard_service import build_risk_guard_state
from services.sizing_service import recommend_position_size
from services.trade_workflow import enrich_signal_payload

from .orchestrator import read_market_pipeline
from .research_queue import FRESH_STATUSES, _freshness, _read_latest_snapshot

DEFAULT_SIGNAL_MARKETS = ("KOSPI",)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_threshold(value: Any, default: float) -> float:
    normalized = _to_float(value, default)
    if 0 < normalized <= 1:
        normalized *= 100.0
    return max(0.0, normalized)


def context_snapshot() -> tuple[str, str]:
    payload = get_market_context()
    context = payload.get("context") if isinstance(payload, dict) else {}
    if not isinstance(context, dict):
        context = {}
    regime = str(context.get("regime") or "neutral").lower()
    risk_level = str(context.get("risk_level") or "중간")
    return regime, risk_level


def _risk_config(cfg: Mapping[str, Any]) -> dict[str, Any]:
    allocation_mode = str(cfg.get("allocation_mode") or "concentrated").strip().lower()
    normalized = {
        "daily_loss_limit_pct": _normalize_threshold(cfg.get("daily_loss_limit_pct"), 2.0),
        "max_symbol_weight_pct": _normalize_threshold(cfg.get("max_symbol_weight_pct"), 20.0),
        "max_sector_weight_pct": _normalize_threshold(cfg.get("max_sector_weight_pct"), 35.0),
        "max_market_exposure_pct": _normalize_threshold(cfg.get("max_market_exposure_pct"), 70.0),
        "block_buy_in_risk_off": bool(cfg.get("block_buy_in_risk_off", True)),
        "block_buy_when_risk_high": bool(cfg.get("block_buy_when_risk_high", True)),
        "max_consecutive_loss": max(1, int(cfg.get("max_consecutive_loss") or 3)),
        "cooldown_minutes": max(5, int(cfg.get("cooldown_minutes") or 120)),
    }
    if allocation_mode == "concentrated":
        bluechip_cap = _normalize_threshold(cfg.get("bluechip_max_symbol_weight_pct") or cfg.get("bluechip_max_symbol_position_ratio"), 40.0)
        normalized["max_symbol_weight_pct"] = max(normalized["max_symbol_weight_pct"], bluechip_cap)
    return normalized


def _signal_score(candidate: Mapping[str, Any]) -> float:
    monitor = _to_float(candidate.get("monitor_priority"), 0.0)
    scanner = _to_float(candidate.get("scanner_score"), 0.0)
    return max(0.0, min(100.0, max(monitor, scanner)))


def _risk_inputs(candidate: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, float]:
    stop_loss_pct = candidate.get("stop_loss_pct")
    if stop_loss_pct in (None, ""):
        stop_loss_pct = cfg.get("stop_loss_pct", 5.0)
    take_profit_pct = candidate.get("take_profit_pct")
    if take_profit_pct in (None, ""):
        take_profit_pct = cfg.get("take_profit_pct", 12.0)
    return {
        "stop_loss_pct": _to_float(stop_loss_pct, 5.0),
        "take_profit_pct": _to_float(take_profit_pct, 12.0),
    }


def _list_of_str(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _list_of_dict(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _research_validation(snapshot: Mapping[str, Any], freshness: str) -> dict[str, Any]:
    existing = snapshot.get("validation")
    if isinstance(existing, dict) and existing.get("grade"):
        return dict(existing)
    score = _to_float(snapshot.get("research_score"), 0.0)
    confidence = _to_float(snapshot.get("confidence"), 0.0)
    warnings = _list_of_str(snapshot.get("warnings"))
    action = str(snapshot.get("action") or "").lower()
    rating = str(snapshot.get("rating") or "").lower()
    buy_intent = action in {"buy", "buy_watch"} and rating in {"strong_buy", "overweight"}
    if freshness not in FRESH_STATUSES:
        grade = "C"
        reason = "stale_snapshot"
    elif warnings:
        grade = "B" if score >= 0.65 else "C"
        reason = "warning_codes_present"
    elif buy_intent and score >= 0.8 and confidence >= 0.75:
        grade = "A"
        reason = "fresh_agent_buy_candidate"
    elif score >= 0.45:
        grade = "B"
        reason = "fresh_usable_score"
    else:
        grade = "C"
        reason = "fresh_low_score"
    return {
        "grade": grade,
        "source": str(snapshot.get("provider") or "default"),
        "source_count": 1,
        "reason": reason,
        "notes": warnings,
        "exclusion_reason": None if grade in {"A", "B"} else reason,
    }


def _build_layer_c(symbol: str, market: str, timestamp: str) -> dict[str, Any]:
    snapshot = _read_latest_snapshot(symbol, market, provider="default")
    if not snapshot:
        return {
            "layer": "C",
            "provider": "default",
            "provider_status": "missing",
            "research_unavailable": True,
            "research_score": None,
            "components": {},
            "warnings": ["research_unavailable"],
            "tags": [],
            "summary": "",
            "ttl_minutes": 15,
            "generated_at": timestamp,
            "freshness": "missing",
            "freshness_detail": {"status": "missing", "is_stale": True, "reason": "snapshot_missing"},
            "validation": {"grade": "D", "source": "default", "source_count": 0, "reason": "snapshot_missing", "notes": ["research_unavailable"], "exclusion_reason": "research snapshot not found"},
            "rating": "",
            "action": "",
            "confidence": None,
            "technical_features": {},
            "news_inputs": [],
            "evidence": [],
            "data_quality": {},
            "research_quality": {},
        }
    freshness = str(snapshot.get("freshness") or "").strip().lower() or _freshness(snapshot)
    validation = _research_validation(snapshot, freshness)
    return {
        "layer": "C",
        "provider": str(snapshot.get("provider") or "default"),
        "provider_status": "healthy" if freshness in FRESH_STATUSES else "stale_ingest",
        "research_unavailable": freshness not in FRESH_STATUSES,
        "research_score": snapshot.get("research_score"),
        "components": _dict_or_empty(snapshot.get("components")),
        "warnings": _list_of_str(snapshot.get("warnings")),
        "tags": _list_of_str(snapshot.get("tags")),
        "summary": str(snapshot.get("summary") or ""),
        "ttl_minutes": int(snapshot.get("ttl_minutes") or 15),
        "generated_at": str(snapshot.get("generated_at") or timestamp),
        "freshness": freshness,
        "freshness_detail": {"status": freshness, "is_stale": freshness not in FRESH_STATUSES},
        "validation": validation,
        "rating": str(snapshot.get("rating") or ""),
        "action": str(snapshot.get("action") or ""),
        "confidence": snapshot.get("confidence"),
        "candidate_source": str(snapshot.get("candidate_source") or ""),
        "bull_case": _list_of_str(snapshot.get("bull_case")),
        "bear_case": _list_of_str(snapshot.get("bear_case")),
        "catalysts": _list_of_str(snapshot.get("catalysts")),
        "risks": _list_of_str(snapshot.get("risks")),
        "invalidation_trigger": _dict_or_empty(snapshot.get("invalidation_trigger")),
        "trade_plan": _dict_or_empty(snapshot.get("trade_plan")),
        "technical_features": _dict_or_empty(snapshot.get("technical_features")),
        "news_inputs": _list_of_dict(snapshot.get("news_inputs")),
        "evidence": _list_of_dict(snapshot.get("evidence")),
        "data_quality": _dict_or_empty(snapshot.get("data_quality")),
        "research_quality": _dict_or_empty(snapshot.get("research_quality")),
        "outcomes": _dict_or_empty(snapshot.get("outcomes")),
    }


def _build_signal(candidate: Mapping[str, Any], *, market: str, cfg: dict[str, Any], account: dict[str, Any], regime: str, risk_level: str) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or candidate.get("code") or "").strip().upper()
    if not symbol:
        raise ValueError("candidate_symbol_missing")
    technical = candidate.get("technical_snapshot") if isinstance(candidate.get("technical_snapshot"), dict) else {}
    current_price = _to_float(candidate.get("current_price"), _to_float(candidate.get("price"), _to_float(technical.get("current_price"), _to_float(technical.get("close"), 0.0))))
    if current_price <= 0:
        raise ValueError(f"candidate_price_missing:{market}:{symbol}")

    timestamp = _now_iso()
    score = _signal_score(candidate)
    reasons = [str(item) for item in (candidate.get("candidate_sources") or candidate.get("reason_codes") or []) if str(item)]
    signal_state = "entry" if score >= _to_float(cfg.get("min_score"), 50.0) else "watch"
    layer_c = _build_layer_c(symbol, market, timestamp)
    risk_inputs = _risk_inputs(candidate, cfg)
    risk_guard_state = build_risk_guard_state(
        account=account,
        cfg=_risk_config(cfg),
        regime=regime,
        risk_level=risk_level,
    )
    research_score = _to_float(layer_c.get("research_score"), 0.0)
    expected_value = max(0.0, min(2.5, (score / 100.0) * 0.45 + research_score * 0.55))
    reliability = "high" if research_score >= 0.75 else "medium" if research_score >= 0.55 else "low"
    size_recommendation = recommend_position_size(
        account=account,
        market=market,
        unit_price_local=current_price,
        stop_loss_pct=risk_inputs["stop_loss_pct"],
        expected_value=expected_value,
        reliability=reliability,
        risk_guard_state=risk_guard_state,
        cfg=cfg,
        symbol_key=f"{market}:{symbol}",
        sector=str(candidate.get("sector") or "미분류"),
        allocation_mode=str(cfg.get("allocation_mode") or "concentrated"),
        bluechip=bool(candidate.get("bluechip")),
    )
    gate_passed = bool(risk_guard_state.get("entry_allowed")) and int(size_recommendation.get("quantity") or 0) > 0
    risk_check = {
        "passed": gate_passed,
        "reason_code": "ok" if gate_passed else (risk_guard_state.get("reasons") or [size_recommendation.get("reason") or "blocked"])[0],
        "message": "risk_guard_and_sizing",
        "checks": [],
    }
    layer_d = build_layer_d_snapshot(
        risk_check=risk_check,
        size_recommendation=size_recommendation,
        risk_guard_state=risk_guard_state,
        research=layer_c,
    )
    layer_e = build_layer_e_snapshot(
        signal_state=signal_state,
        quant_score=score,
        research=layer_c,
        risk=layer_d,
        timestamp=timestamp,
        source_context={
            "strategy_id": "dynamic_market_scanner",
            "symbol": symbol,
            "market": market,
            "agent_execution_mode": cfg.get("agent_execution_mode") or cfg.get("execution_mode") or "agent_primary_quant_assisted",
        },
    )
    final_action = str(layer_e.get("final_action") or "do_not_touch")
    entry_allowed = final_action == "review_for_entry" and gate_passed
    payload = {
        **dict(candidate),
        "market": market,
        "code": symbol,
        "symbol": symbol,
        "name": candidate.get("name") or symbol,
        "price": current_price,
        "current_price": current_price,
        "last_price_local": current_price,
        "score": score,
        "signal_state": signal_state,
        "entry_intent": signal_state == "entry",
        "exit_intent": False,
        "entry_allowed": entry_allowed,
        "validation_snapshot": {
            "freshness": layer_c.get("freshness"),
            "validation": layer_c.get("validation") if isinstance(layer_c.get("validation"), dict) else {},
            "strategy_reliability": reliability,
            "passes_minimum_gate": final_action == "review_for_entry",
            "is_reliable": reliability in {"high", "medium"},
        },
        "risk_inputs": risk_inputs,
        "risk_guard_state": risk_guard_state,
        "strategy_type": "dynamic_market_scanner",
        "strategy_role": "primary",
        "candidate_primary_source": "dynamic_market_scanner",
        "allocation": {"enabled": True, "weight": 1.0},
        "allocation_mode": str(cfg.get("allocation_mode") or "concentrated"),
        "ev_metrics": {
            "expected_value": round(expected_value, 4),
            "reliability": reliability,
            "expected_return_model": {
                "monitor_score": round(score / 100.0, 4),
                "research_score": research_score,
            },
        },
        "size_recommendation": size_recommendation,
        "execution_realism": {"liquidity_gate_status": "ok" if gate_passed else "blocked"},
        "candidate_source_mode": "dynamic_market_scanner",
        "candidate_runtime_source_mode": "dynamic_market_scanner",
        "candidate_research_source": layer_c.get("provider"),
        "research_status": layer_c.get("provider_status"),
        "research_unavailable": layer_c.get("research_unavailable"),
        "research_score": layer_c.get("research_score"),
        "final_action": final_action,
        "final_action_snapshot": layer_e,
        "layer_c": layer_c,
        "layer_d": layer_d,
        "layer_e": layer_e,
        "layer_events": build_layer_events(
            layer_a={"layer": "A", "market": market, "source": "dynamic_market_listing"},
            layer_b={
                "layer": "B",
                "quant_score": round(score / 100.0, 4),
                "signal_state": signal_state,
                "quant_tags": reasons,
                "technical_snapshot": {
                    "current_price": current_price,
                    "volume_ratio": technical.get("volume_ratio"),
                    "rsi14": technical.get("rsi14"),
                    "atr14_pct": technical.get("atr14_pct"),
                },
            },
            layer_c=layer_c,
            layer_d=layer_d,
            layer_e=layer_e,
        ),
        "fetched_at": timestamp,
    }
    return enrich_signal_payload(payload)


def build_signal_book(
    *,
    markets: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or {}
    account = account or {}
    normalized_markets = [str(item or "").strip().upper() for item in (markets or []) if str(item or "").strip()]
    if not normalized_markets:
        normalized_markets = list(DEFAULT_SIGNAL_MARKETS)
    regime, risk_level = context_snapshot()

    signals: list[dict[str, Any]] = []
    risk_guard_state: dict[str, Any] = {}
    for market in normalized_markets:
        pipeline = read_market_pipeline(market)
        watchlist = pipeline.get("watchlist") if isinstance(pipeline.get("watchlist"), dict) else {}
        for candidate in watchlist.get("active_slots") or []:
            if not isinstance(candidate, dict):
                continue
            signal = _build_signal(candidate, market=market, cfg=cfg, account=account, regime=regime, risk_level=risk_level)
            signals.append(signal)
            if not risk_guard_state and isinstance(signal.get("risk_guard_state"), dict):
                risk_guard_state = dict(signal.get("risk_guard_state") or {})

    return {
        "generated_at": _now_iso(),
        "signals": signals,
        "count": len(signals),
        "blocked_count": sum(1 for item in signals if str(item.get("signal_state") or "") == "entry" and not bool(item.get("entry_allowed"))),
        "entry_allowed_count": sum(1 for item in signals if bool(item.get("entry_allowed"))),
        "risk_guard_state": risk_guard_state,
        "scanner": [],
        "regime": regime,
        "risk_level": risk_level,
        "candidate_generation_mode": "dynamic_market_scanner",
        "strategy_role": "primary",
        "markets": normalized_markets,
    }


def select_entry_candidates(
    *,
    market: str,
    cfg: dict[str, Any],
    account: dict[str, Any],
    max_count: int,
) -> list[dict[str, Any]]:
    book = build_signal_book(markets=[market], cfg=cfg, account=account)
    rows = [
        item for item in book.get("signals", [])
        if isinstance(item, dict)
        and str(item.get("market") or "").upper() == str(market or "").upper()
        and str(item.get("signal_state") or "") == "entry"
        and bool(item.get("entry_allowed"))
    ]
    rows.sort(
        key=lambda item: (
            _to_float(item.get("research_score"), 0.0),
            _to_float(item.get("score"), 0.0),
            -int(item.get("candidate_rank") or 999999),
        ),
        reverse=True,
    )
    return rows[: max(0, int(max_count))]
