from __future__ import annotations

from typing import Any

from services.risk_guard_service import build_risk_guard_state


_REASON_MESSAGES = {
    "DAILY_LOSS_LIMIT_EXCEEDED": "일일 손실 한도를 넘어 신규 진입을 차단했습니다.",
    "LOSS_STREAK_COOLDOWN": "연속 손실 쿨다운이 끝날 때까지 신규 진입을 차단했습니다.",
    "MAX_POSITIONS_REACHED": "전략별 최대 포지션 수에 도달했습니다.",
    "DUPLICATE_POSITION": "동일 종목 포지션이 이미 존재합니다.",
    "LIQUIDITY_TOO_LOW": "거래량 기준을 충족하지 못해 유동성이 부족합니다.",
    "SPREAD_TOO_WIDE": "현재 스프레드가 허용 범위를 초과했습니다.",
    "POSITION_SIZE_LIMIT_EXCEEDED": "포지션 비중 한도를 초과합니다.",
    "RISK_GUARD_BLOCKED": "포트폴리오 리스크 가드가 신규 진입을 차단했습니다.",
    "SIZE_ZERO": "사이징 결과가 0주여서 주문을 만들지 않았습니다.",
    "OK": "주문 가능",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _risk_cfg(strategy: dict[str, Any]) -> dict[str, Any]:
    risk_limits = strategy.get("risk_limits") if isinstance(strategy.get("risk_limits"), dict) else {}
    position_size_pct = _to_float(risk_limits.get("position_size_pct"), 0.1)
    if position_size_pct <= 1.0:
        position_size_pct *= 100.0
    daily_loss_limit_pct = _to_float(risk_limits.get("daily_loss_limit_pct"), 0.02)
    if daily_loss_limit_pct <= 1.0:
        daily_loss_limit_pct *= 100.0
    return {
        "daily_loss_limit_pct": daily_loss_limit_pct,
        "max_symbol_weight_pct": position_size_pct,
        "max_sector_weight_pct": max(position_size_pct * 2.0, 20.0),
        "max_market_exposure_pct": 70.0,
        "block_buy_in_risk_off": False,
        "block_buy_when_risk_high": False,
    }


def build_strategy_risk_state(*, account: dict[str, Any], strategy: dict[str, Any], regime: str = "neutral", risk_level: str = "중간") -> dict[str, Any]:
    return build_risk_guard_state(account=account, cfg=_risk_cfg(strategy), regime=regime, risk_level=risk_level)


def _guard_reason_code(state: dict[str, Any]) -> str:
    reasons = [str(item or "") for item in state.get("reasons", [])]
    if "daily_loss_limit_reached" in reasons:
        return "DAILY_LOSS_LIMIT_EXCEEDED"
    if "loss_streak_cooldown" in reasons:
        return "LOSS_STREAK_COOLDOWN"
    return "RISK_GUARD_BLOCKED"


def evaluate_entry_risk(
    *,
    account: dict[str, Any],
    strategy: dict[str, Any],
    candidate: dict[str, Any],
    desired_quantity: int | None = None,
    regime: str = "neutral",
    risk_level: str = "중간",
) -> dict[str, Any]:
    risk_limits = strategy.get("risk_limits") if isinstance(strategy.get("risk_limits"), dict) else {}
    state = build_strategy_risk_state(account=account, strategy=strategy, regime=regime, risk_level=risk_level)
    checks: list[dict[str, Any]] = []
    positions = account.get("positions", []) if isinstance(account.get("positions"), list) else []
    market = str(candidate.get("market") or strategy.get("market") or "").upper()
    code = str(candidate.get("code") or "").upper()
    market_positions = [item for item in positions if str(item.get("market") or "").upper() == market]
    duplicate_exists = any(str(item.get("code") or "").upper() == code for item in market_positions)
    max_positions = max(1, int(risk_limits.get("max_positions") or 5))
    technicals = candidate.get("technical_snapshot") if isinstance(candidate.get("technical_snapshot"), dict) else {}
    min_liquidity = max(0.0, _to_float(risk_limits.get("min_liquidity"), 0.0))
    volume_avg20 = _to_float(technicals.get("volume_avg20"), 0.0)
    spread_pct = _to_float(technicals.get("spread_pct"), 0.0)
    max_spread_pct = _to_float(risk_limits.get("max_spread_pct"), 0.0)
    position_size_pct = _to_float(risk_limits.get("position_size_pct"), 0.1)
    if position_size_pct <= 1.0:
        position_size_pct *= 100.0

    checks.append({
        "id": "portfolio_guard",
        "passed": bool(state.get("entry_allowed", True)),
        "reason_code": _guard_reason_code(state) if not bool(state.get("entry_allowed", True)) else "OK",
        "message": _REASON_MESSAGES[_guard_reason_code(state)] if not bool(state.get("entry_allowed", True)) else _REASON_MESSAGES["OK"],
        "details": list(state.get("reasons", [])),
    })
    checks.append({
        "id": "max_positions",
        "passed": len(market_positions) < max_positions,
        "reason_code": "MAX_POSITIONS_REACHED" if len(market_positions) >= max_positions else "OK",
        "message": _REASON_MESSAGES["MAX_POSITIONS_REACHED"] if len(market_positions) >= max_positions else _REASON_MESSAGES["OK"],
        "current": len(market_positions),
        "limit": max_positions,
    })
    checks.append({
        "id": "duplicate_position",
        "passed": not duplicate_exists,
        "reason_code": "DUPLICATE_POSITION" if duplicate_exists else "OK",
        "message": _REASON_MESSAGES["DUPLICATE_POSITION"] if duplicate_exists else _REASON_MESSAGES["OK"],
    })
    checks.append({
        "id": "liquidity",
        "passed": volume_avg20 >= min_liquidity,
        "reason_code": "LIQUIDITY_TOO_LOW" if volume_avg20 < min_liquidity else "OK",
        "message": _REASON_MESSAGES["LIQUIDITY_TOO_LOW"] if volume_avg20 < min_liquidity else _REASON_MESSAGES["OK"],
        "current": volume_avg20,
        "limit": min_liquidity,
    })
    spread_failed = max_spread_pct > 0 and spread_pct > max_spread_pct
    checks.append({
        "id": "spread",
        "passed": not spread_failed,
        "reason_code": "SPREAD_TOO_WIDE" if spread_failed else "OK",
        "message": _REASON_MESSAGES["SPREAD_TOO_WIDE"] if spread_failed else _REASON_MESSAGES["OK"],
        "current": spread_pct,
        "limit": max_spread_pct,
    })

    if desired_quantity is not None and desired_quantity > 0:
        current_price = _to_float(candidate.get("current_price") or candidate.get("price") or technicals.get("current_price"), 0.0)
        fx_rate = 1.0 if market == "KOSPI" else _to_float(account.get("fx_rate"), 1300.0)
        equity_krw = max(_to_float(account.get("equity_krw"), 1.0), 1.0)
        estimated_weight_pct = (current_price * fx_rate * desired_quantity / equity_krw) * 100.0 if current_price > 0 else 0.0
        size_failed = estimated_weight_pct > position_size_pct
        checks.append({
            "id": "position_size",
            "passed": not size_failed,
            "reason_code": "POSITION_SIZE_LIMIT_EXCEEDED" if size_failed else "OK",
            "message": _REASON_MESSAGES["POSITION_SIZE_LIMIT_EXCEEDED"] if size_failed else _REASON_MESSAGES["OK"],
            "current": round(estimated_weight_pct, 4),
            "limit": position_size_pct,
        })
    elif desired_quantity is not None:
        checks.append({
            "id": "position_size",
            "passed": False,
            "reason_code": "SIZE_ZERO",
            "message": _REASON_MESSAGES["SIZE_ZERO"],
            "current": 0,
            "limit": position_size_pct,
        })

    failure = next((item for item in checks if not bool(item.get("passed"))), None)
    return {
        "passed": failure is None,
        "reason_code": str((failure or {}).get("reason_code") or "OK"),
        "message": str((failure or {}).get("message") or _REASON_MESSAGES["OK"]),
        "checks": checks,
        "risk_state": state,
    }
