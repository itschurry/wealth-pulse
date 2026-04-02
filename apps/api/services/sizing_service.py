"""Risk-based position sizing service."""

from __future__ import annotations

from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _reliability_scale(reliability: str) -> float:
    normalized = str(reliability or "").lower()
    if normalized == "high":
        return 1.15
    if normalized == "medium":
        return 1.0
    if normalized == "low":
        return 0.78
    return 0.55


def recommend_position_size(
    *,
    account: dict[str, Any],
    market: str,
    unit_price_local: float,
    stop_loss_pct: float,
    expected_value: float,
    reliability: str,
    risk_guard_state: dict[str, Any],
    cfg: dict[str, Any],
    symbol_key: str,
    sector: str,
) -> dict[str, Any]:
    if unit_price_local <= 0:
        return {"quantity": 0, "reason": "invalid_unit_price"}

    market_upper = str(market or "").upper()
    fx_rate = 1.0
    if market_upper == "NASDAQ":
        fx_rate = _to_float(account.get("fx_rate"), 1300.0)

    unit_price_krw = unit_price_local * fx_rate
    equity_krw = max(_to_float(account.get("equity_krw")), 1.0)

    risk_per_trade_pct = max(0.05, _to_float(cfg.get("risk_per_trade_pct"), 0.35))
    risk_budget_krw = equity_krw * (risk_per_trade_pct / 100.0)

    ev_scale = max(0.35, min(1.9, 1.0 + (expected_value / 9.0)))
    reliability_scale = _reliability_scale(reliability)
    effective_risk_budget = risk_budget_krw * ev_scale * reliability_scale

    stop_pct = max(0.2, float(stop_loss_pct or 5.0))
    stop_distance_krw = unit_price_krw * (stop_pct / 100.0)
    qty_by_risk = int(effective_risk_budget / max(stop_distance_krw, 1e-6))

    available_cash_krw = _to_float(account.get("cash_krw"))
    if market_upper == "NASDAQ":
        available_cash_krw = _to_float(account.get("cash_usd")) * fx_rate
    qty_by_cash = int((available_cash_krw * 0.995) // max(unit_price_krw, 1.0))

    caps = risk_guard_state.get("exposure_caps", {}) if isinstance(risk_guard_state, dict) else {}
    exposure = risk_guard_state.get("exposure", {}) if isinstance(risk_guard_state, dict) else {}
    symbol_pct = (exposure.get("symbol_pct") or {}).get(symbol_key, 0.0)
    sector_pct = (exposure.get("sector_pct") or {}).get(sector, 0.0)
    market_pct = (exposure.get("market_pct") or {}).get(market_upper, 0.0)

    max_symbol_weight_pct = _to_float(caps.get("max_symbol_weight_pct"), 20.0)
    max_sector_weight_pct = _to_float(caps.get("max_sector_weight_pct"), 35.0)
    max_market_exposure_pct = _to_float(caps.get("max_market_exposure_pct"), 70.0)

    symbol_room_krw = max(0.0, equity_krw * (max_symbol_weight_pct - symbol_pct) / 100.0)
    sector_room_krw = max(0.0, equity_krw * (max_sector_weight_pct - sector_pct) / 100.0)
    market_room_krw = max(0.0, equity_krw * (max_market_exposure_pct - market_pct) / 100.0)

    qty_by_caps = int(min(symbol_room_krw, sector_room_krw, market_room_krw) // max(unit_price_krw, 1.0))

    quantity = max(0, min(qty_by_risk, qty_by_cash, qty_by_caps))
    if quantity <= 0:
        zero_limits: list[str] = []
        if qty_by_risk <= 0:
            zero_limits.append("risk_budget_limit")
        if qty_by_cash <= 0:
            zero_limits.append("cash_limit")
        if qty_by_caps <= 0:
            zero_limits.append("exposure_limit")
        reason = zero_limits[0] if len(zero_limits) == 1 else "exposure_or_cash_limit"
        return {
            "quantity": 0,
            "reason": reason,
            "qty_by_risk": qty_by_risk,
            "qty_by_cash": qty_by_cash,
            "qty_by_caps": qty_by_caps,
        }

    return {
        "quantity": quantity,
        "risk_budget_krw": round(effective_risk_budget, 2),
        "qty_by_risk": qty_by_risk,
        "qty_by_cash": qty_by_cash,
        "qty_by_caps": qty_by_caps,
        "unit_price_krw": round(unit_price_krw, 2),
        "stop_distance_krw": round(stop_distance_krw, 2),
    }
