"""Unified deterministic strategy engine for ranking and execution decisions."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from api.helpers import _KST
from api.routes.reports import _get_market_context
from services.ev_calibration_service import compute_ev_metrics
from services.risk_guard_service import build_risk_guard_state
from services.signal_service import collect_pick_candidates
from services.sizing_service import recommend_position_size
from services.strategy_allocator_service import allocator_weight, determine_strategy_type

_OPTIMIZED_PARAMS_PATH = Path(__file__).resolve().parent.parent / "config" / "optimized_params.json"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_optimized_params() -> dict[str, Any]:
    try:
        if not _OPTIMIZED_PARAMS_PATH.exists():
            return {}
        payload = json.loads(_OPTIMIZED_PARAMS_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _context_snapshot() -> tuple[str, str]:
    payload = _get_market_context()
    context = payload.get("context") if isinstance(payload, dict) else {}
    context = context if isinstance(context, dict) else {}
    regime = str(context.get("regime") or "neutral").lower()
    risk_level = str(context.get("risk_level") or "중간")
    return regime, risk_level


def _default_signal_cfg() -> dict[str, Any]:
    return {
        "min_score": 0.0,
        "include_neutral": True,
        "theme_gate_enabled": True,
        "theme_min_score": 2.5,
        "theme_min_news": 1,
        "theme_priority_bonus": 2.0,
        "theme_focus": ["automotive", "robotics", "physical_ai"],
        "risk_per_trade_pct": 0.35,
        "daily_loss_limit_pct": 2.0,
        "max_consecutive_loss": 3,
        "cooldown_minutes": 120,
        "max_symbol_weight_pct": 20.0,
        "max_sector_weight_pct": 35.0,
        "max_market_exposure_pct": 70.0,
        "block_buy_in_risk_off": True,
        "block_buy_when_risk_high": True,
        "min_avg_volume": 100000,
        "min_avg_notional_krw": 50000000,
        "slippage_bps_base": 8.0,
        "stop_loss_pct": 5.0,
    }


def _estimate_slippage_bps(signal: dict[str, Any], cfg: dict[str, Any], risk_level: str) -> float:
    technicals = signal.get("technical_snapshot") if isinstance(signal.get("technical_snapshot"), dict) else {}
    volume_ratio = _to_float(technicals.get("volume_ratio"), 1.0)
    atr_pct = _to_float(technicals.get("atr14_pct"), 0.0)

    slippage = _to_float(cfg.get("slippage_bps_base"), 8.0)
    if str(risk_level) == "높음":
        slippage += 6.0
    elif str(risk_level) == "중간":
        slippage += 2.0

    if volume_ratio > 0 and volume_ratio < 1.0:
        slippage += (1.0 - volume_ratio) * 12.0
    if atr_pct > 2.5:
        slippage += min(12.0, atr_pct * 1.5)

    strategy_type = str(signal.get("strategy_type") or "")
    if strategy_type == "event-driven":
        slippage += 4.0

    return round(max(1.0, min(60.0, slippage)), 2)


def _liquidity_gate(signal: dict[str, Any], cfg: dict[str, Any], market: str, price_local: float, fx_rate: float) -> tuple[bool, str]:
    technicals = signal.get("technical_snapshot") if isinstance(signal.get("technical_snapshot"), dict) else {}
    avg_volume = _to_float(technicals.get("volume_avg20"), 0.0)
    if avg_volume <= 0.0:
        return False, "liquidity_unknown"

    min_avg_volume = max(0.0, _to_float(cfg.get("min_avg_volume"), 100000.0))
    if avg_volume < min_avg_volume:
        return False, "liquidity_low_volume"

    notional_krw = avg_volume * price_local * (fx_rate if market == "NASDAQ" else 1.0)
    min_notional = max(0.0, _to_float(cfg.get("min_avg_notional_krw"), 50000000.0))
    if notional_krw < min_notional:
        return False, "liquidity_low_notional"

    return True, "ok"


def build_signal_book(
    *,
    markets: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_cfg = _default_signal_cfg()
    merged_cfg.update(cfg or {})

    target_markets = [str(m).upper() for m in (markets or ["KOSPI", "NASDAQ"]) if str(m).upper() in {"KOSPI", "NASDAQ"}]
    if not target_markets:
        target_markets = ["KOSPI", "NASDAQ"]

    regime, risk_level = _context_snapshot()
    optimized_params = _load_optimized_params()
    per_symbol = optimized_params.get("per_symbol", {}) if isinstance(optimized_params, dict) else {}

    risk_guard_state = build_risk_guard_state(
        account=account or {"positions": [], "orders": [], "equity_krw": 0.0},
        cfg=merged_cfg,
        regime=regime,
        risk_level=risk_level,
    )

    signals: list[dict[str, Any]] = []
    blocked = 0

    for market in target_markets:
        candidates = collect_pick_candidates(market=market, cfg=merged_cfg)
        for candidate in candidates:
            code = str(candidate.get("code") or "").upper()
            if not code:
                continue
            name = str(candidate.get("name") or code)
            sector = str(candidate.get("sector") or "미분류")
            score = _to_float(candidate.get("score"), 50.0)
            confidence = _to_float(candidate.get("confidence"), max(45.0, min(90.0, score)))

            strategy_type = determine_strategy_type(candidate)
            allocation = allocator_weight(
                strategy_type=strategy_type,
                regime=regime,
                market=market,
                sector=sector,
            )

            validation_payload = per_symbol.get(code, {}) if isinstance(per_symbol, dict) else {}
            validation_trades = int(validation_payload.get("validation_trades") or 0)
            validation_sharpe = _to_float(validation_payload.get("validation_sharpe"), 0.0)

            ev = compute_ev_metrics(
                strategy_type=strategy_type,
                regime=regime,
                score=score,
                confidence=confidence,
                validation_trades=validation_trades,
                validation_sharpe=validation_sharpe,
                market=market,
                sector=sector,
            )

            entry_allowed = bool(allocation.get("enabled")) and float(ev.get("expected_value") or 0.0) > 0.0
            reason_codes: list[str] = []
            if not bool(allocation.get("enabled")):
                reason_codes.append("allocator_block")
            if float(ev.get("expected_value") or 0.0) <= 0.0:
                reason_codes.append("ev_non_positive")

            if not risk_guard_state.get("entry_allowed", True):
                entry_allowed = False
                reason_codes.extend(str(item) for item in risk_guard_state.get("reasons", []))

            price_local = _to_float(candidate.get("price") or candidate.get("current_price") or candidate.get("last_price_local"), 0.0)
            if price_local <= 0.0:
                technicals = candidate.get("technical_snapshot") if isinstance(candidate.get("technical_snapshot"), dict) else {}
                price_local = _to_float(technicals.get("current_price"), 0.0)

            fx_rate = _to_float((account or {}).get("fx_rate"), 1300.0)
            liquidity_pass, liquidity_status = _liquidity_gate(
                {
                    "technical_snapshot": candidate.get("technical_snapshot"),
                    "strategy_type": strategy_type,
                },
                merged_cfg,
                market,
                price_local,
                fx_rate,
            )
            if not liquidity_pass:
                entry_allowed = False
                reason_codes.append(liquidity_status)

            stop_loss_pct = _to_float(validation_payload.get("stop_loss_pct"), _to_float(merged_cfg.get("stop_loss_pct"), 5.0))

            size_recommendation = {
                "quantity": 0,
                "reason": "account_unavailable",
            }
            if account and price_local > 0:
                size_recommendation = recommend_position_size(
                    account=account,
                    market=market,
                    unit_price_local=price_local,
                    stop_loss_pct=stop_loss_pct,
                    expected_value=_to_float(ev.get("expected_value")),
                    reliability=str(ev.get("reliability") or "insufficient"),
                    risk_guard_state=risk_guard_state,
                    cfg=merged_cfg,
                    symbol_key=f"{market}:{code}",
                    sector=sector,
                )
                if int(size_recommendation.get("quantity") or 0) <= 0:
                    entry_allowed = False
                    reason_codes.append(str(size_recommendation.get("reason") or "size_zero"))

            signal = {
                "code": code,
                "name": name,
                "market": market,
                "sector": sector,
                "score": round(score, 2),
                "strategy_type": strategy_type,
                "entry_allowed": entry_allowed,
                "reason_codes": list(dict.fromkeys(reason_codes)),
                "ev_metrics": ev,
                "risk_inputs": {
                    "stop_loss_pct": stop_loss_pct,
                    "risk_budget_pct": _to_float(merged_cfg.get("risk_per_trade_pct"), 0.35),
                    "risk_guard_state": risk_guard_state,
                },
                "size_recommendation": size_recommendation,
                "execution_realism": {
                    "slippage_model_version": "intraday_v1",
                    "liquidity_gate_status": liquidity_status,
                    "slippage_bps": _estimate_slippage_bps(
                        {
                            "strategy_type": strategy_type,
                            "technical_snapshot": candidate.get("technical_snapshot"),
                        },
                        merged_cfg,
                        risk_level,
                    ),
                },
                "signal_reasoning": {
                    "allocator": allocation,
                    "calibration": ev.get("calibration", {}),
                    "candidate_reasons": candidate.get("reasons", []),
                    "candidate_risks": candidate.get("risks", []),
                },
                "report_reasoning": {
                    "summary": candidate.get("ai_thesis") or candidate.get("summary") or "",
                    "gate_status": candidate.get("gate_status"),
                    "gate_reasons": candidate.get("gate_reasons") or [],
                },
            }
            if not entry_allowed:
                blocked += 1
            signals.append(signal)

    signals.sort(key=lambda item: float((item.get("ev_metrics") or {}).get("expected_value") or -9999.0), reverse=True)

    return {
        "generated_at": datetime.datetime.now(_KST).isoformat(timespec="seconds"),
        "regime": regime,
        "risk_level": risk_level,
        "risk_guard_state": risk_guard_state,
        "signals": signals,
        "count": len(signals),
        "blocked_count": blocked,
        "entry_allowed_count": max(0, len(signals) - blocked),
    }


def select_entry_candidates(
    *,
    market: str,
    cfg: dict[str, Any],
    account: dict[str, Any],
    max_count: int,
) -> list[dict[str, Any]]:
    book = build_signal_book(markets=[market], cfg=cfg, account=account)
    allowed = [
        item for item in book.get("signals", [])
        if bool(item.get("entry_allowed")) and str(item.get("market") or "").upper() == market.upper()
    ]
    return allowed[: max(0, int(max_count))]
