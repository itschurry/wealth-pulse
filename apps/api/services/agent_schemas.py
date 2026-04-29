"""Hermes trade decision schema helpers.

Hermes is allowed to propose BUY/SELL/HOLD only. This module validates and
normalizes the model output before any risk or execution code sees it.
"""

from __future__ import annotations

import json
from typing import Any

_ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _default_decision(*, symbol: str = "", reason_summary: str = "") -> dict[str, Any]:
    return {
        "action": "HOLD",
        "symbol": str(symbol or "").strip().upper(),
        "market": "",
        "confidence": 0.0,
        "reason_summary": reason_summary,
        "evidence": [],
        "risk": {
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "max_position_ratio": 0.0,
        },
    }


def _parse_raw(raw: str | dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if isinstance(raw, dict):
        return raw, json.dumps(raw, ensure_ascii=False)
    raw_text = str(raw or "")
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None, raw_text
    return (parsed if isinstance(parsed, dict) else None), raw_text


def parse_hermes_decision(raw: str | dict[str, Any]) -> dict[str, Any]:
    parsed, raw_text = _parse_raw(raw)
    errors: list[str] = []
    if parsed is None:
        return {
            "valid": False,
            "decision": _default_decision(reason_summary="Hermes JSON parse failed; treated as HOLD."),
            "errors": ["parse_error"],
            "raw_text": raw_text,
        }

    symbol = str(parsed.get("symbol") or "").strip().upper()
    market = str(parsed.get("market") or "").strip().upper()
    action = str(parsed.get("action") or "HOLD").strip().upper()
    if action not in _ALLOWED_ACTIONS:
        errors.append("invalid_action")
        action = "HOLD"

    evidence_raw = parsed.get("evidence")
    evidence = [str(item).strip() for item in evidence_raw if str(item).strip()] if isinstance(evidence_raw, list) else []
    risk_raw = parsed.get("risk") if isinstance(parsed.get("risk"), dict) else {}
    confidence = _clamp(_to_float(parsed.get("confidence"), 0.0), 0.0, 1.0)

    decision = {
        "action": action,
        "symbol": symbol,
        "market": market,
        "confidence": confidence,
        "reason_summary": str(parsed.get("reason_summary") or "").strip(),
        "evidence": evidence,
        "risk": {
            "entry_price": max(0.0, _to_float(risk_raw.get("entry_price"))),
            "stop_loss": max(0.0, _to_float(risk_raw.get("stop_loss"))),
            "take_profit": max(0.0, _to_float(risk_raw.get("take_profit"))),
            "max_position_ratio": max(0.0, _to_float(risk_raw.get("max_position_ratio"))),
        },
    }

    if not symbol:
        errors.append("missing_symbol")
    return {
        "valid": not errors,
        "decision": decision,
        "errors": errors,
        "raw_text": raw_text,
    }
