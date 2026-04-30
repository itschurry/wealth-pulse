"""Hermes trade-decision provider for Agent Runs.

This module bridges existing Hermes research-analysis utilities into the new
Agent Run BUY/SELL/HOLD contract. It never places orders; it only returns a
candidate decision dictionary that must still pass schema validation and the
server-side Risk Gate.
"""

from __future__ import annotations

import json
from typing import Any

try:  # Reuse the host-side Hermes runner helpers when available.
    from scripts.hermes_research_runner import call_hermes_agent, parse_agent_json  # type: ignore
except Exception:  # pragma: no cover - defensive fallback for unusual import paths
    call_hermes_agent = None  # type: ignore

    def parse_agent_json(output: str) -> dict[str, Any]:  # type: ignore
        parsed = json.loads(str(output or "{}"))
        if not isinstance(parsed, dict):
            raise ValueError("agent_output_must_be_object")
        return parsed


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
    max_position_ratio = _clamp(size_pct / 100.0 if size_pct > 1 else size_pct, 0.0, 0.10)

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


def build_trade_decision_prompt(candidate: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    feature_pack = {
        "candidate": candidate,
        "evidence": evidence,
        "contract": {
            "schema": {
                "action": "BUY | SELL | HOLD",
                "symbol": "string",
                "market": "string",
                "confidence": "number 0..1",
                "reason_summary": "short Korean explanation",
                "evidence": ["cited evidence strings"],
                "risk": {
                    "entry_price": "number; required for BUY/SELL",
                    "stop_loss": "number; required for BUY/SELL",
                    "take_profit": "number; required for BUY",
                    "max_position_ratio": "number 0..0.10; intent only",
                },
            },
            "safety": {
                "do_not_place_orders": True,
                "risk_gate_owner": "WealthPulse deterministic server Risk Gate",
            },
        },
    }
    return (
        "You are Hermes, the WealthPulse investment decision proposer.\n"
        "Return ONLY one JSON object, no markdown and no commentary.\n"
        "Allowed action values are BUY, SELL, HOLD.\n"
        "Do not place orders, do not call brokers, and do not claim execution.\n"
        "Risk Gate and Executor decide whether any simulated/live order is sent.\n"
        "If evidence is weak, stale, or risk fields are missing, choose HOLD.\n\n"
        f"Feature pack:\n{json.dumps(feature_pack, ensure_ascii=False, indent=2, sort_keys=True)}"
    )


def call_hermes_trade_decision(
    candidate: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    agent_command: list[str] | str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    if call_hermes_agent is None:
        raise RuntimeError("hermes_agent_helper_unavailable")
    prompt = build_trade_decision_prompt(candidate, evidence)
    raw = call_hermes_agent(prompt, agent_command=agent_command, timeout=timeout)
    parsed = parse_agent_json(raw)
    parsed.setdefault("symbol", candidate.get("symbol") or candidate.get("code"))
    parsed.setdefault("market", candidate.get("market"))
    return parsed
