"""Research snapshot decision adapter for Agent Runs."""

from __future__ import annotations

from typing import Any


_BUY_ACTIONS = {"buy", "buy_watch", "strong_buy", "overweight"}
_SELL_ACTIONS = {"sell", "reduce", "underweight"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("title") or item.get("summary") or item.get("source") or item).strip()
        else:
            text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _risk_value(plan: dict[str, Any], *names: str) -> float:
    for name in names:
        if name in plan:
            value = _to_float(plan.get(name), 0.0)
            if value > 0:
                return value
    return 0.0


def research_analysis_to_trade_decision(analysis: dict[str, Any], candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    candidate = candidate if isinstance(candidate, dict) else {}
    symbol = str(analysis.get("symbol") or candidate.get("symbol") or candidate.get("code") or "").strip().upper()
    market = str(analysis.get("market") or candidate.get("market") or "").strip().upper()
    raw_intent = str(analysis.get("action") or analysis.get("rating") or "hold").strip().lower()
    if raw_intent in _BUY_ACTIONS:
        action = "BUY"
    elif raw_intent in _SELL_ACTIONS:
        action = "SELL"
    else:
        action = "HOLD"

    trade_plan = analysis.get("trade_plan") if isinstance(analysis.get("trade_plan"), dict) else {}
    invalidation = analysis.get("invalidation_trigger") if isinstance(analysis.get("invalidation_trigger"), dict) else {}
    technical = analysis.get("technical_features") if isinstance(analysis.get("technical_features"), dict) else {}
    confidence = _clamp(_to_float(analysis.get("confidence"), 0.0), 0.0, 1.0)
    entry_price = _risk_value(trade_plan, "entry_price", "entry", "target_entry") or _risk_value(technical, "close", "price", "current_price")
    stop_loss = _risk_value(trade_plan, "stop_loss", "stop") or _risk_value(invalidation, "stop_loss", "price")
    take_profit = _risk_value(trade_plan, "take_profit", "target_price", "target")
    size_pct = _to_float(trade_plan.get("size_intent_pct"), 0.0)
    allocation_mode = str(candidate.get("allocation_mode") or analysis.get("allocation_mode") or "concentrated").strip().lower()
    bluechip = bool(candidate.get("bluechip") or analysis.get("bluechip"))
    max_allowed_ratio = 0.40 if allocation_mode == "concentrated" and bluechip else 0.10
    max_position_ratio = _clamp(size_pct / 100.0 if size_pct > 1 else size_pct, 0.0, max_allowed_ratio)

    evidence = [
        *_text_list(analysis.get("evidence")),
        *_text_list(analysis.get("news_inputs")),
    ]
    if not evidence:
        evidence = _text_list(analysis.get("bull_case"))[:3]

    return {
        "action": action,
        "symbol": symbol,
        "market": market,
        "allocation_mode": allocation_mode,
        "bluechip": bluechip,
        "bluechip_reason": str(candidate.get("bluechip_reason") or analysis.get("bluechip_reason") or "").strip(),
        "confidence": confidence,
        "reason_summary": str(analysis.get("summary") or analysis.get("reason_summary") or "").strip(),
        "evidence": evidence,
        "risk": {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "max_position_ratio": max_position_ratio,
        },
    }
