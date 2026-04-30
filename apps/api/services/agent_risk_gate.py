"""Deterministic Risk Gate for Hermes Agent trade decisions.

This module never calls a broker. It turns a validated Hermes BUY/SELL/HOLD
proposal into either an approved order intent or a rejected/skipped decision.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _parse_ts(value: Any) -> _dt.datetime | None:
    try:
        parsed = _dt.datetime.fromisoformat(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _cash_krw(account: dict[str, Any]) -> float:
    if "cash_krw" in account:
        return _to_float(account.get("cash_krw"))
    summary = account.get("summary") if isinstance(account.get("summary"), dict) else {}
    return _to_float(summary.get("deposit") or summary.get("cash_krw"))


def _equity_krw(account: dict[str, Any]) -> float:
    if "equity_krw" in account:
        return max(1.0, _to_float(account.get("equity_krw"), 1.0))
    summary = account.get("summary") if isinstance(account.get("summary"), dict) else {}
    return max(1.0, _to_float(summary.get("total_amount") or summary.get("eval_amount") or account.get("total_amount"), 1.0))


def _position_matches(position: dict[str, Any], symbol: str) -> bool:
    keys = ("symbol", "code", "pdno")
    return any(str(position.get(key) or "").strip().upper() == symbol for key in keys)


def _same_symbol_recent_order(order: dict[str, Any], symbol: str, now: _dt.datetime, cooldown_minutes: int) -> bool:
    order_symbol = str(order.get("symbol") or order.get("code") or "").strip().upper()
    if order_symbol != symbol:
        return False
    ts = _parse_ts(order.get("created_at") or order.get("logged_at") or order.get("ts"))
    if ts is None:
        return False
    return (now - ts).total_seconds() < max(0, cooldown_minutes) * 60


def _reject(reason_code: str, *, final_action: str = "HOLD", checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "approved": False,
        "final_action": final_action,
        "reason_code": reason_code,
        "checks": checks or [],
        "order_intent": None,
    }


def evaluate_agent_decision_risk(
    *,
    decision: dict[str, Any],
    account: dict[str, Any] | None,
    config: dict[str, Any] | None,
    recent_orders: list[dict[str, Any]] | None = None,
    now: _dt.datetime | None = None,
) -> dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    config = config if isinstance(config, dict) else {}
    recent_orders = recent_orders if isinstance(recent_orders, list) else []
    now = (now or _now_utc()).astimezone(_dt.timezone.utc)

    action = str(decision.get("action") or "HOLD").strip().upper()
    symbol = str(decision.get("symbol") or "").strip().upper()
    risk = decision.get("risk") if isinstance(decision.get("risk"), dict) else {}
    checks: list[dict[str, Any]] = []

    if action == "HOLD":
        return _reject("hold_decision", final_action="HOLD", checks=checks)

    confidence = _to_float(decision.get("confidence"), 0.0)
    min_confidence = _to_float(config.get("min_confidence"), 0.7)
    checks.append({"id": "confidence", "passed": confidence >= min_confidence, "current": confidence, "limit": min_confidence})
    if confidence < min_confidence:
        return _reject("confidence_below_minimum", checks=checks)

    positions = account.get("positions") if isinstance(account.get("positions"), list) else []

    if action == "BUY":
        entry_price = _to_float(risk.get("entry_price"))
        stop_loss = _to_float(risk.get("stop_loss"))
        take_profit = _to_float(risk.get("take_profit"))
        if stop_loss <= 0:
            checks.append({"id": "stop_loss", "passed": False, "current": stop_loss})
            return _reject("stop_loss_required", final_action=action, checks=checks)

        downside = max(0.0, entry_price - stop_loss)
        upside = max(0.0, take_profit - entry_price)
        reward_risk = (upside / downside) if downside > 0 else 0.0
        min_rr = _to_float(config.get("min_reward_risk_ratio"), 1.3)
        checks.append({"id": "reward_risk", "passed": reward_risk >= min_rr, "current": round(reward_risk, 4), "limit": min_rr})
        if reward_risk < min_rr:
            return _reject("reward_risk_below_minimum", final_action=action, checks=checks)

        existing_position = next((p for p in positions if isinstance(p, dict) and _position_matches(p, symbol)), None)
        if existing_position and not bool(config.get("allow_additional_buy", False)):
            checks.append({"id": "additional_buy", "passed": False})
            return _reject("additional_buy_blocked", final_action=action, checks=checks)

        cooldown_minutes = int(config.get("cooldown_minutes") or 0)
        if any(_same_symbol_recent_order(order, symbol, now, cooldown_minutes) for order in recent_orders if isinstance(order, dict)):
            checks.append({"id": "cooldown", "passed": False, "limit_minutes": cooldown_minutes})
            return _reject("cooldown_active", final_action=action, checks=checks)

        equity = _equity_krw(account)
        cash = _cash_krw(account)
        requested_ratio = _to_float(risk.get("max_position_ratio"), 0.0)
        max_ratio = _to_float(config.get("max_symbol_position_ratio"), 0.1)
        target_ratio = requested_ratio if requested_ratio > 0 else max_ratio
        target_ratio = min(target_ratio, max_ratio)
        budget = max(0.0, equity * target_ratio)
        if cash < min(entry_price, budget):
            checks.append({"id": "cash", "passed": False, "current": cash, "required": min(entry_price, budget)})
            return _reject("insufficient_cash", final_action=action, checks=checks)
        quantity = int(min(cash, budget) // max(entry_price, 1.0))
        if quantity <= 0:
            return _reject("size_zero", final_action=action, checks=checks)
        return {
            "approved": True,
            "final_action": "BUY",
            "reason_code": "approved",
            "checks": checks,
            "order_intent": {
                "symbol": symbol,
                "market": str(decision.get("market") or "").strip().upper(),
                "action": "BUY",
                "quantity": quantity,
                "estimated_price": entry_price,
                "estimated_amount_krw": quantity * entry_price,
                "reward_risk_ratio": round(reward_risk, 4),
            },
        }

    if action == "SELL":
        existing_position = next((p for p in positions if isinstance(p, dict) and _position_matches(p, symbol)), None)
        if not existing_position:
            checks.append({"id": "position", "passed": False})
            return _reject("sell_position_not_found", final_action=action, checks=checks)
        held_quantity = int(_to_float(existing_position.get("quantity") or existing_position.get("hldg_qty"), 0.0))
        orderable_quantity = int(_to_float(existing_position.get("orderable_quantity"), held_quantity))
        quantity = max(0, min(held_quantity, orderable_quantity))
        if quantity <= 0:
            checks.append({"id": "sell_quantity", "passed": False, "held": held_quantity, "orderable": orderable_quantity})
            return _reject("sell_quantity_unavailable", final_action=action, checks=checks)
        return {
            "approved": True,
            "final_action": "SELL",
            "reason_code": "approved",
            "checks": checks,
            "order_intent": {
                "symbol": symbol,
                "market": str(decision.get("market") or existing_position.get("market") or "").strip().upper(),
                "action": "SELL",
                "quantity": quantity,
            },
        }

    return {
        "approved": True,
        "final_action": action,
        "reason_code": "approved",
        "checks": checks,
        "order_intent": {"symbol": symbol, "market": str(decision.get("market") or "").strip().upper(), "action": action, "quantity": 0},
    }
