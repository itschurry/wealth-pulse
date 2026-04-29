from __future__ import annotations

import os
from typing import Any

from services.research_scoring import ResearchScoreRequest, get_research_scorer


_AGENT_EXECUTION_MODES = {"quant_gated_agent", "agent_primary_quant_assisted", "agent_only_paper"}
_BUY_RATINGS = {"strong_buy", "overweight"}
_BUY_ACTIONS = {"buy", "buy_watch"}
_NEGATIVE_RATINGS = {"underweight", "sell"}
_NEGATIVE_ACTIONS = {"reduce", "sell", "block"}


def _normalized_execution_mode(source_context: dict[str, Any] | None) -> str:
    source_context = source_context if isinstance(source_context, dict) else {}
    raw = str(
        source_context.get("agent_execution_mode")
        or source_context.get("execution_mode")
        or os.getenv("WEALTHPULSE_AGENT_EXECUTION_MODE", "quant_gated_agent")
    ).strip().lower()
    return raw if raw in _AGENT_EXECUTION_MODES else "quant_gated_agent"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ok"}


def _grade_allows_entry(validation: dict[str, Any]) -> bool:
    grade = str((validation or {}).get("grade") or "").strip().upper()
    return grade in {"A", "B"}


def _technical_sanity_ok(research: dict[str, Any]) -> bool:
    features = research.get("technical_features") if isinstance(research.get("technical_features"), dict) else {}
    data_quality = research.get("data_quality") if isinstance(research.get("data_quality"), dict) else {}
    if data_quality and not _truthy(data_quality.get("has_recent_price")):
        return False
    if data_quality and not _truthy(data_quality.get("has_technical_features")):
        return False
    close_vs_sma20 = _as_float(features.get("close_vs_sma20"), 1.0)
    close_vs_sma60 = _as_float(features.get("close_vs_sma60"), 1.0)
    volume_ratio = _as_float(features.get("volume_ratio"), 1.0)
    rsi14 = _as_float(features.get("rsi14"), 50.0)
    if close_vs_sma20 < 0.985 and close_vs_sma60 < 0.985:
        return False
    if volume_ratio < 0.35:
        return False
    if rsi14 >= 88.0:
        return False
    return True


def _evidence_ok(research: dict[str, Any]) -> bool:
    evidence = research.get("evidence") if isinstance(research.get("evidence"), list) else []
    data_quality = research.get("data_quality") if isinstance(research.get("data_quality"), dict) else {}
    if evidence:
        return True
    return _truthy(data_quality.get("has_technical_features")) or _truthy(data_quality.get("has_news"))


def build_layer_a_snapshot(*, strategy: dict[str, Any], universe: dict[str, Any], symbol: dict[str, Any], scan_time: str) -> dict[str, Any]:
    return {
        "layer": "A",
        "universe_rule": strategy.get("universe_rule"),
        "scan_time": scan_time,
        "market": strategy.get("market"),
        "inclusion_reason": symbol.get("sector") or "universe_match",
        "source_context": {
            "strategy_id": strategy.get("strategy_id"),
            "universe_symbol_count": universe.get("symbol_count"),
        },
    }


def build_layer_b_snapshot(*, strategy: dict[str, Any], score: float, signal_state: str, reasons: list[str], technical_snapshot: dict[str, Any]) -> dict[str, Any]:
    quant_tags = [
        reason for reason in reasons
        if reason in {"macd_positive", "entry_signal_detected", "watch_candidate"} or ":" in reason
    ]
    return {
        "layer": "B",
        "strategy_id": strategy.get("strategy_id"),
        "quant_score": round(float(score or 0.0), 4),
        "signal_state": signal_state,
        "quant_tags": quant_tags,
        "technical_snapshot": {
            "current_price": technical_snapshot.get("current_price") or technical_snapshot.get("close"),
            "volume_ratio": technical_snapshot.get("volume_ratio"),
            "rsi14": technical_snapshot.get("rsi14"),
            "atr14_pct": technical_snapshot.get("atr14_pct"),
        },
    }


def build_layer_c_snapshot(*, symbol: str, market: str, timestamp: str, strategy: dict[str, Any], score: float, reasons: list[str], technical_snapshot: dict[str, Any]) -> dict[str, Any]:
    scorer = get_research_scorer()
    request = ResearchScoreRequest(
        symbol=symbol,
        market=market,
        timestamp=timestamp,
        context={
            "strategy_id": strategy.get("strategy_id"),
            "last_price": technical_snapshot.get("current_price") or technical_snapshot.get("close"),
            "change_pct": technical_snapshot.get("change_pct"),
            "volume_ratio": technical_snapshot.get("volume_ratio"),
            "quant_score": round(float(score or 0.0) / 100.0, 4),
            "scanner_reasons": reasons,
            "universe_tags": [str(strategy.get("universe_rule") or "")],
            "risk_flags": [],
        },
    )
    result = scorer.score(request)
    return {
        "layer": "C",
        "provider": result.source,
        "provider_status": result.status,
        "research_unavailable": not result.available,
        "research_score": result.research_score,
        "components": result.components,
        "warnings": result.warnings,
        "tags": result.tags,
        "summary": result.summary,
        "ttl_minutes": result.ttl_minutes,
        "generated_at": result.generated_at,
        "freshness": result.freshness,
        "freshness_detail": result.freshness_detail,
        "validation": result.validation,
        "rating": result.rating,
        "action": result.action,
        "confidence": result.confidence,
        "candidate_source": result.candidate_source,
        "bull_case": result.bull_case,
        "bear_case": result.bear_case,
        "catalysts": result.catalysts,
        "risks": result.risks,
        "invalidation_trigger": result.invalidation_trigger,
        "trade_plan": result.trade_plan,
        "technical_features": result.technical_features,
        "news_inputs": result.news_inputs,
        "evidence": result.evidence,
        "data_quality": result.data_quality,
        "agent_analysis": {
            "rating": result.rating,
            "action": result.action,
            "confidence": result.confidence,
            "candidate_source": result.candidate_source,
            "bull_case": result.bull_case,
            "bear_case": result.bear_case,
            "catalysts": result.catalysts,
            "risks": result.risks,
            "invalidation_trigger": result.invalidation_trigger,
            "trade_plan": result.trade_plan,
            "technical_features": result.technical_features,
            "news_inputs": result.news_inputs,
            "evidence": result.evidence,
            "data_quality": result.data_quality,
        },
    }


def build_layer_d_snapshot(*, risk_check: dict[str, Any], size_recommendation: dict[str, Any], risk_guard_state: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    if isinstance(risk_check, dict):
        if risk_check.get("reason_code"):
            reason_codes.append(str(risk_check.get("reason_code")))
        for item in risk_check.get("checks", []) or []:
            if isinstance(item, dict) and item.get("reason_code"):
                reason_codes.append(str(item.get("reason_code")))
    allowed = bool(risk_check.get("passed"))
    return {
        "layer": "D",
        "allowed": allowed,
        "blocked": not allowed,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "research_warnings": [str(item) for item in (research.get("warnings") or []) if str(item)],
        "final_allowed_size": int(size_recommendation.get("quantity") or 0),
        "execution_decision": "allow" if allowed else "block",
        "position_cap_state": size_recommendation.get("reason") or "sizing_pending",
        "liquidity_state": risk_check.get("message") or "unknown",
        "spread_state": "unknown",
        "risk_guard_state": risk_guard_state,
    }


def build_layer_e_snapshot(*, signal_state: str, quant_score: float, research: dict[str, Any], risk: dict[str, Any], timestamp: str, source_context: dict[str, Any]) -> dict[str, Any]:
    normalized_quant = _as_float(quant_score, 0.0) / 100.0
    research_score = research.get("research_score")
    warnings = [str(item) for item in (research.get("warnings") or []) if str(item) != "research_unavailable"]
    blocked = bool(risk.get("blocked"))
    execution_mode = _normalized_execution_mode(source_context)

    research_score_num = _as_float(research_score, -1.0) if research_score is not None else None
    quant_entry_ready = signal_state == "entry" and normalized_quant >= 0.5 and (research_score_num is None or research_score_num >= 0.45) and not warnings
    if signal_state == "exit":
        quant_decision = {"decision": "exit_signal", "order_ready": False, "reason": "exit_signal", "score": round(normalized_quant, 4)}
    elif quant_entry_ready:
        quant_decision = {"decision": "quant_entry", "order_ready": True, "reason": "quant_confirmed", "score": round(normalized_quant, 4)}
    elif signal_state == "entry" and normalized_quant >= 0.58:
        quant_decision = {"decision": "operator_review", "order_ready": False, "reason": "needs_operator_review", "score": round(normalized_quant, 4)}
    elif signal_state != "entry":
        quant_decision = {"decision": "watch_only" if normalized_quant >= 0.45 else "do_not_touch", "order_ready": False, "reason": "non_entry_signal", "score": round(normalized_quant, 4)}
    else:
        quant_decision = {"decision": "do_not_touch", "order_ready": False, "reason": "weak_quant", "score": round(normalized_quant, 4)}

    rating = str(research.get("rating") or "").strip().lower()
    action = str(research.get("action") or "").strip().lower()
    confidence = _as_float(research.get("confidence"), 0.0)
    validation = research.get("validation") if isinstance(research.get("validation"), dict) else {}
    confidence_threshold = 0.75 if action == "buy" else 0.65
    technical_ok = _technical_sanity_ok(research)
    evidence_ok = _evidence_ok(research)
    validation_ok = _grade_allows_entry(validation)
    buy_intent = rating in _BUY_RATINGS and action in _BUY_ACTIONS
    negative_intent = rating in _NEGATIVE_RATINGS or action in _NEGATIVE_ACTIONS

    if not rating and not action:
        agent_decision = {"decision": "no_agent_signal", "order_ready": False, "reason": "agent_fields_missing"}
    elif negative_intent:
        agent_decision = {"decision": "agent_exit_or_block", "order_ready": False, "reason": "negative_rating_or_action", "rating": rating, "action": action}
    elif action == "hold" or rating == "hold":
        agent_decision = {"decision": "agent_hold", "order_ready": False, "reason": "hold_rating_or_action", "rating": rating, "action": action}
    elif buy_intent and confidence >= confidence_threshold and validation_ok and technical_ok and evidence_ok and not warnings:
        order_ready = execution_mode == "agent_primary_quant_assisted" or quant_entry_ready
        reason = "agent_buy_confirmed" if order_ready else "agent_buy_without_quant_entry"
        agent_decision = {
            "decision": "agent_primary_buy",
            "order_ready": bool(order_ready),
            "reason": reason,
            "rating": rating,
            "action": action,
            "confidence": confidence,
            "technical_sanity": "ok",
            "validation_grade": validation.get("grade"),
            "analysis_mode": "agent_research",
        }
    elif buy_intent:
        agent_decision = {
            "decision": "agent_buy_watch",
            "order_ready": False,
            "reason": "agent_evidence_or_quality_gate_failed",
            "rating": rating,
            "action": action,
            "confidence": confidence,
            "technical_sanity": "ok" if technical_ok else "failed",
            "validation_grade": validation.get("grade"),
        }
    else:
        agent_decision = {"decision": "agent_neutral", "order_ready": False, "reason": "no_buy_intent", "rating": rating, "action": action}

    if blocked:
        final_action = "blocked"
        decision_reason = "risk_veto"
    elif agent_decision.get("decision") == "agent_exit_or_block":
        final_action = "do_not_touch"
        decision_reason = "agent_negative_rating"
    elif agent_decision.get("order_ready"):
        final_action = "review_for_entry"
        decision_reason = "agent_primary_buy" if not quant_entry_ready else "agent_and_quant_aligned"
    elif buy_intent and agent_decision.get("reason") == "agent_buy_without_quant_entry":
        final_action = "watch_only"
        decision_reason = "agent_buy_without_quant_entry"
    elif quant_decision.get("order_ready"):
        final_action = "review_for_entry"
        decision_reason = str(quant_decision.get("reason"))
    elif quant_decision.get("decision") == "operator_review":
        final_action = "watch_only"
        decision_reason = str(quant_decision.get("reason"))
    elif signal_state == "exit":
        final_action = "do_not_touch"
        decision_reason = "exit_signal"
    elif agent_decision.get("decision") == "agent_hold":
        final_action = "watch_only"
        decision_reason = "agent_hold"
    else:
        final_action = str(quant_decision.get("decision") or "do_not_touch")
        decision_reason = str(quant_decision.get("reason") or "weak_quant")

    return {
        "layer": "E",
        "final_action": final_action,
        "decision_reason": decision_reason,
        "timestamp": timestamp,
        "execution_mode": execution_mode,
        "quant_decision": quant_decision,
        "agent_decision": agent_decision,
        "source_context": source_context,
    }


def build_layer_events(*, layer_a: dict[str, Any], layer_b: dict[str, Any], layer_c: dict[str, Any], layer_d: dict[str, Any], layer_e: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"layer": "A", "status": "ok", "snapshot": layer_a},
        {"layer": "B", "status": "ok", "snapshot": layer_b},
        {"layer": "C", "status": layer_c.get("provider_status") or "healthy", "snapshot": layer_c},
        {"layer": "D", "status": "blocked" if layer_d.get("blocked") else "allowed", "snapshot": layer_d},
        {"layer": "E", "status": layer_e.get("final_action"), "snapshot": layer_e},
    ]
