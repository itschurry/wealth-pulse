from __future__ import annotations

from typing import Any

from services.research_scoring import ResearchScoreRequest, get_research_scorer


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
    normalized_quant = float(quant_score or 0.0) / 100.0
    research_score = research.get("research_score")
    warnings = [str(item) for item in (research.get("warnings") or []) if str(item) != "research_unavailable"]
    blocked = bool(risk.get("blocked"))

    if blocked:
        final_action = "blocked"
        decision_reason = "risk_veto"
    elif signal_state == "exit":
        final_action = "do_not_touch"
        decision_reason = "exit_signal"
    elif signal_state != "entry":
        final_action = "do_not_touch" if normalized_quant < 0.45 else "watch_only"
        decision_reason = "non_entry_signal"
    elif normalized_quant >= 0.7 and (research_score is None or float(research_score) >= 0.45) and not warnings:
        final_action = "review_for_entry"
        decision_reason = "quant_confirmed"
    elif normalized_quant >= 0.58:
        final_action = "watch_only"
        decision_reason = "needs_operator_review"
    else:
        final_action = "do_not_touch"
        decision_reason = "weak_quant"

    return {
        "layer": "E",
        "final_action": final_action,
        "decision_reason": decision_reason,
        "timestamp": timestamp,
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
