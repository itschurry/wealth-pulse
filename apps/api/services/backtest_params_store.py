from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from schemas.strategy_metadata import portfolio_defaults, strategy_defaults
from services.signal_service import normalize_runtime_candidate_source_mode


BACKTEST_VALIDATION_SETTINGS_PATH = LOGS_DIR / "backtest_validation_settings.json"

_DEFAULT_QUERY: dict[str, Any] = {
    "market_scope": "kospi",
    "lookback_days": 1095,
    "strategy_kind": "trend_following",
    "regime_mode": "auto",
    "risk_profile": "balanced",
    "initial_cash": 10_000_000,
    "max_positions": 5,
    "max_holding_days": 15,
    "portfolio_constraints": portfolio_defaults("kospi"),
    "strategy_params": strategy_defaults("trend_following", market="KOSPI"),
    "rsi_min": 45,
    "rsi_max": 62,
    "volume_ratio_min": 1.0,
    "stop_loss_pct": 5.0,
    "take_profit_pct": None,
    "adx_min": 10.0,
    "mfi_min": 20.0,
    "mfi_max": 80.0,
    "bb_pct_min": 0.05,
    "bb_pct_max": 0.95,
    "stoch_k_min": 10.0,
    "stoch_k_max": 90.0,
}

_DEFAULT_SETTINGS: dict[str, Any] = {
    "strategy": "퀀트 전략 엔진",
    "trainingDays": 180,
    "validationDays": 60,
    "walkForward": True,
    "minTrades": 20,
    "objective": "수익 우선",
    "runtime_candidate_source_mode": "quant_only",
}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _to_int(value: Any, fallback: int, minimum: int | None = None) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = int(fallback)
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def _to_float(value: Any, fallback: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(fallback)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _to_nullable_float(value: Any, fallback: float | None, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if value in (None, ""):
        return None if fallback is None else _to_float(fallback, float(fallback), minimum=minimum, maximum=maximum)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None if fallback is None else _to_float(fallback, float(fallback), minimum=minimum, maximum=maximum)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def default_validation_query() -> dict[str, Any]:
    return dict(_DEFAULT_QUERY)


def default_validation_settings() -> dict[str, Any]:
    return dict(_DEFAULT_SETTINGS)


def _normalize_query(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    market_scope = str(raw.get("market_scope") or _DEFAULT_QUERY["market_scope"]).lower()
    if market_scope not in {"kospi", "nasdaq", "all"}:
        market_scope = str(_DEFAULT_QUERY["market_scope"])
    strategy_kind = str(raw.get("strategy_kind") or _DEFAULT_QUERY["strategy_kind"]).lower()
    if strategy_kind not in {"trend_following", "mean_reversion", "defensive"}:
        strategy_kind = str(_DEFAULT_QUERY["strategy_kind"])
    regime_mode = str(raw.get("regime_mode") or _DEFAULT_QUERY["regime_mode"]).lower()
    if regime_mode not in {"auto", "manual"}:
        regime_mode = str(_DEFAULT_QUERY["regime_mode"])
    risk_profile = str(raw.get("risk_profile") or _DEFAULT_QUERY["risk_profile"]).lower()
    if risk_profile not in {"conservative", "balanced", "aggressive"}:
        risk_profile = str(_DEFAULT_QUERY["risk_profile"])
    portfolio_raw = raw.get("portfolio_constraints") if isinstance(raw.get("portfolio_constraints"), dict) else {}
    strategy_params_raw = raw.get("strategy_params") if isinstance(raw.get("strategy_params"), dict) else {}
    default_portfolio = portfolio_defaults(market_scope)
    default_params = strategy_defaults(strategy_kind, market="NASDAQ" if market_scope == "nasdaq" else "KOSPI", risk_profile=risk_profile)
    return {
        "market_scope": market_scope,
        "strategy_kind": strategy_kind,
        "regime_mode": regime_mode,
        "risk_profile": risk_profile,
        "lookback_days": _to_int(raw.get("lookback_days"), int(_DEFAULT_QUERY["lookback_days"]), minimum=180),
        "initial_cash": _to_int(raw.get("initial_cash"), int(_DEFAULT_QUERY["initial_cash"]), minimum=1),
        "max_positions": _to_int(raw.get("max_positions"), int(_DEFAULT_QUERY["max_positions"]), minimum=1),
        "max_holding_days": _to_int(raw.get("max_holding_days"), int(_DEFAULT_QUERY["max_holding_days"]), minimum=1),
        "portfolio_constraints": {
            "market_scope": market_scope,
            "initial_cash": _to_int(portfolio_raw.get("initial_cash"), int(default_portfolio["initial_cash"]), minimum=1),
            "max_positions": _to_int(portfolio_raw.get("max_positions"), int(default_portfolio["max_positions"]), minimum=1),
            "max_holding_days": _to_int(portfolio_raw.get("max_holding_days"), int(default_portfolio["max_holding_days"]), minimum=1),
        },
        "strategy_params": {
            "rsi_min": _to_float(strategy_params_raw.get("rsi_min"), float(default_params["rsi_min"])),
            "rsi_max": _to_float(strategy_params_raw.get("rsi_max"), float(default_params["rsi_max"])),
            "volume_ratio_min": _to_float(strategy_params_raw.get("volume_ratio_min"), float(default_params["volume_ratio_min"]), minimum=0.0),
            "stop_loss_pct": _to_nullable_float(strategy_params_raw.get("stop_loss_pct"), default_params.get("stop_loss_pct"), minimum=0.0),
            "take_profit_pct": _to_nullable_float(strategy_params_raw.get("take_profit_pct"), default_params.get("take_profit_pct"), minimum=0.0),
            "adx_min": _to_nullable_float(strategy_params_raw.get("adx_min"), default_params.get("adx_min"), minimum=0.0),
            "mfi_min": _to_nullable_float(strategy_params_raw.get("mfi_min"), default_params.get("mfi_min")),
            "mfi_max": _to_nullable_float(strategy_params_raw.get("mfi_max"), default_params.get("mfi_max")),
            "bb_pct_min": _to_nullable_float(strategy_params_raw.get("bb_pct_min"), default_params.get("bb_pct_min"), minimum=0.0, maximum=1.0),
            "bb_pct_max": _to_nullable_float(strategy_params_raw.get("bb_pct_max"), default_params.get("bb_pct_max"), minimum=0.0, maximum=1.0),
            "stoch_k_min": _to_nullable_float(strategy_params_raw.get("stoch_k_min"), default_params.get("stoch_k_min")),
            "stoch_k_max": _to_nullable_float(strategy_params_raw.get("stoch_k_max"), default_params.get("stoch_k_max")),
            "trade_suppression_threshold": _to_nullable_float(strategy_params_raw.get("trade_suppression_threshold"), default_params.get("trade_suppression_threshold"), minimum=0.0),
        },
        "rsi_min": _to_int(raw.get("rsi_min"), int(_DEFAULT_QUERY["rsi_min"])),
        "rsi_max": _to_int(raw.get("rsi_max"), int(_DEFAULT_QUERY["rsi_max"])),
        "volume_ratio_min": _to_float(raw.get("volume_ratio_min"), float(_DEFAULT_QUERY["volume_ratio_min"]), minimum=0.0),
        "stop_loss_pct": _to_nullable_float(raw.get("stop_loss_pct"), _DEFAULT_QUERY["stop_loss_pct"], minimum=0.0),
        "take_profit_pct": _to_nullable_float(raw.get("take_profit_pct"), _DEFAULT_QUERY["take_profit_pct"], minimum=0.0),
        "adx_min": _to_nullable_float(raw.get("adx_min"), _DEFAULT_QUERY["adx_min"], minimum=0.0),
        "mfi_min": _to_nullable_float(raw.get("mfi_min"), _DEFAULT_QUERY["mfi_min"]),
        "mfi_max": _to_nullable_float(raw.get("mfi_max"), _DEFAULT_QUERY["mfi_max"]),
        "bb_pct_min": _to_nullable_float(raw.get("bb_pct_min"), _DEFAULT_QUERY["bb_pct_min"], minimum=0.0, maximum=1.0),
        "bb_pct_max": _to_nullable_float(raw.get("bb_pct_max"), _DEFAULT_QUERY["bb_pct_max"], minimum=0.0, maximum=1.0),
        "stoch_k_min": _to_nullable_float(raw.get("stoch_k_min"), _DEFAULT_QUERY["stoch_k_min"]),
        "stoch_k_max": _to_nullable_float(raw.get("stoch_k_max"), _DEFAULT_QUERY["stoch_k_max"]),
    }


def _normalize_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "strategy": str(raw.get("strategy") or _DEFAULT_SETTINGS["strategy"]),
        "trainingDays": _to_int(raw.get("trainingDays"), int(_DEFAULT_SETTINGS["trainingDays"]), minimum=30),
        "validationDays": _to_int(raw.get("validationDays"), int(_DEFAULT_SETTINGS["validationDays"]), minimum=20),
        "walkForward": bool(raw.get("walkForward")) if "walkForward" in raw else bool(_DEFAULT_SETTINGS["walkForward"]),
        "minTrades": _to_int(raw.get("minTrades"), int(_DEFAULT_SETTINGS["minTrades"]), minimum=1),
        "objective": str(raw.get("objective") or _DEFAULT_SETTINGS["objective"]),
        "runtime_candidate_source_mode": normalize_runtime_candidate_source_mode(
            raw.get("runtime_candidate_source_mode")
        ),
    }


def _build_response(query: dict[str, Any], settings: dict[str, Any], saved_at: str) -> dict[str, Any]:
    return {
        "ok": True,
        "query": query,
        "settings": settings,
        "saved_at": saved_at,
        "source": str(BACKTEST_VALIDATION_SETTINGS_PATH),
    }


def load_persisted_validation_settings() -> dict[str, Any]:
    payload = _read_json(BACKTEST_VALIDATION_SETTINGS_PATH) or {}
    query = _normalize_query(payload.get("query") if isinstance(payload.get("query"), dict) else None)
    settings = _normalize_settings(payload.get("settings") if isinstance(payload.get("settings"), dict) else None)
    saved_at = str(payload.get("saved_at") or "")
    return _build_response(query, settings, saved_at)


def save_persisted_validation_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    query = _normalize_query(payload.get("query") if isinstance(payload, dict) and isinstance(payload.get("query"), dict) else None)
    settings = _normalize_settings(payload.get("settings") if isinstance(payload, dict) and isinstance(payload.get("settings"), dict) else None)
    saved_at = _now_iso()
    _write_json(
        BACKTEST_VALIDATION_SETTINGS_PATH,
        {
            "query": query,
            "settings": settings,
            "saved_at": saved_at,
        },
    )
    return _build_response(query, settings, saved_at)


def reset_persisted_validation_settings() -> dict[str, Any]:
    return save_persisted_validation_settings({
        "query": default_validation_query(),
        "settings": default_validation_settings(),
    })
