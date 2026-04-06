"""Risk guard calculations for paper/live execution gating."""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any

from helpers import _KST
from market_utils import lookup_company_listing


def _today_kst() -> str:
    return datetime.datetime.now(_KST).date().isoformat()


def _order_day(ts: str) -> str:
    try:
        return datetime.datetime.fromisoformat(ts).astimezone(_KST).date().isoformat()
    except Exception:
        return ""


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_exposure(account: dict[str, Any]) -> dict[str, Any]:
    equity = max(_to_float(account.get("equity_krw")), 1.0)
    by_market: dict[str, float] = defaultdict(float)
    by_symbol: dict[str, float] = defaultdict(float)
    by_sector: dict[str, float] = defaultdict(float)

    for position in account.get("positions", []):
        market = str(position.get("market") or "UNKNOWN").upper()
        code = str(position.get("code") or "").upper()
        value = _to_float(position.get("market_value_krw"))
        by_market[market] += value
        if code:
            by_symbol[f"{market}:{code}"] += value

            listing = lookup_company_listing(code=code, scope="core") or lookup_company_listing(code=code, scope="live")
            sector = str((listing or {}).get("sector") or position.get("sector") or "unknown")
            by_sector[sector] += value

    market_pct = {k: round(v / equity * 100.0, 4) for k, v in by_market.items()}
    symbol_pct = {k: round(v / equity * 100.0, 4) for k, v in by_symbol.items()}
    sector_pct = {k: round(v / equity * 100.0, 4) for k, v in by_sector.items()}

    return {
        "equity_krw": round(equity, 2),
        "market_pct": market_pct,
        "symbol_pct": symbol_pct,
        "sector_pct": sector_pct,
    }


def _daily_realized_loss(account: dict[str, Any]) -> float:
    today = _today_kst()
    loss = 0.0
    for order in account.get("orders", []):
        if _order_day(str(order.get("ts") or "")) != today:
            continue
        if str(order.get("side") or "").lower() != "sell":
            continue
        pnl = _to_float(order.get("realized_pnl_krw"))
        if pnl < 0:
            loss += abs(pnl)
    return loss


def _consecutive_loss_count(account: dict[str, Any]) -> int:
    count = 0
    for order in account.get("orders", []):
        if str(order.get("side") or "").lower() != "sell":
            continue
        pnl = _to_float(order.get("realized_pnl_krw"))
        if pnl < 0:
            count += 1
            continue
        break
    return count


def build_risk_guard_state(
    *,
    account: dict[str, Any],
    cfg: dict[str, Any],
    regime: str,
    risk_level: str,
) -> dict[str, Any]:
    exposure = _compute_exposure(account)
    equity = exposure["equity_krw"]

    daily_loss_limit_pct = _to_float(cfg.get("daily_loss_limit_pct"), 2.0)
    daily_loss_limit_krw = equity * max(0.1, daily_loss_limit_pct) / 100.0
    consumed_loss = _daily_realized_loss(account)
    daily_loss_left = max(0.0, daily_loss_limit_krw - consumed_loss)

    max_loss_streak = max(1, int(cfg.get("max_consecutive_loss", 3) or 3))
    cooldown_minutes = max(5, int(cfg.get("cooldown_minutes", 120) or 120))
    loss_streak = _consecutive_loss_count(account)

    cooldown_active = False
    cooldown_until = ""
    if loss_streak >= max_loss_streak:
        latest_sell_ts = ""
        for order in account.get("orders", []):
            if str(order.get("side") or "").lower() == "sell":
                latest_sell_ts = str(order.get("ts") or "")
                break
        if latest_sell_ts:
            try:
                base_ts = datetime.datetime.fromisoformat(latest_sell_ts).astimezone(_KST)
                until = base_ts + datetime.timedelta(minutes=cooldown_minutes)
                cooldown_until = until.isoformat(timespec="seconds")
                cooldown_active = until > datetime.datetime.now(_KST)
            except Exception:
                cooldown_active = True

    reasons: list[str] = []
    entry_allowed = True

    if daily_loss_left <= 0.0:
        entry_allowed = False
        reasons.append("daily_loss_limit_reached")
    if cooldown_active:
        entry_allowed = False
        reasons.append("loss_streak_cooldown")

    if str(regime or "").lower() == "risk_off" and bool(cfg.get("block_buy_in_risk_off", True)):
        entry_allowed = False
        reasons.append("regime_risk_off")

    if str(risk_level or "") == "높음" and bool(cfg.get("block_buy_when_risk_high", True)):
        entry_allowed = False
        reasons.append("risk_level_high")

    return {
        "entry_allowed": entry_allowed,
        "reasons": reasons,
        "daily_loss_left": round(daily_loss_left, 2),
        "daily_loss_limit": round(daily_loss_limit_krw, 2),
        "loss_streak": loss_streak,
        "cooldown_until": cooldown_until,
        "cooldown_active": cooldown_active,
        "exposure_caps": {
            "max_symbol_weight_pct": _to_float(cfg.get("max_symbol_weight_pct"), 20.0),
            "max_sector_weight_pct": _to_float(cfg.get("max_sector_weight_pct"), 35.0),
            "max_market_exposure_pct": _to_float(cfg.get("max_market_exposure_pct"), 70.0),
        },
        "exposure": exposure,
        "regime": regime,
        "risk_level": risk_level,
    }
