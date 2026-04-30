from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

from config.settings import CONFIG_STATE_DIR, RUNTIME_DIR
from schemas.strategy_metadata import portfolio_defaults, strategy_defaults
BACKTEST_VALIDATION_SETTINGS_PATH = CONFIG_STATE_DIR / "backtest_validation_settings.json"
STATE_SCHEMA_VERSION = 1

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
    "trainingDays": 180,
    "validationDays": 60,
    "walkForward": True,
    "minTrades": 20,
    "objective": "수익 우선",
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
    return copy.deepcopy(_DEFAULT_QUERY)


def default_validation_settings() -> dict[str, Any]:
    return copy.deepcopy(_DEFAULT_SETTINGS)


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

    def _pval(key: str) -> Any:
        """nested 우선, flat 폴백으로 단일 원천에서 포트폴리오 값을 읽는다."""
        v = portfolio_raw.get(key)
        return v if v is not None else raw.get(key)

    def _sval(key: str) -> Any:
        """nested 우선, flat 폴백으로 단일 원천에서 전략 파라미터 값을 읽는다."""
        v = strategy_params_raw.get(key)
        return v if v is not None else raw.get(key)

    # 정규화된 nested dict를 먼저 계산한 뒤 flat 필드를 그것으로부터 파생시킨다.
    # 이렇게 하면 flat 필드와 nested 필드가 항상 동일한 값을 갖고 중복 계산이 없다.
    portfolio_constraints = {
        "market_scope": market_scope,
        "initial_cash": _to_int(_pval("initial_cash"), int(default_portfolio["initial_cash"]), minimum=1),
        "max_positions": _to_int(_pval("max_positions"), int(default_portfolio["max_positions"]), minimum=1),
        "max_holding_days": _to_int(_pval("max_holding_days"), int(default_portfolio["max_holding_days"]), minimum=1),
    }
    strategy_params = {
        "rsi_min": _to_float(_sval("rsi_min"), float(default_params["rsi_min"])),
        "rsi_max": _to_float(_sval("rsi_max"), float(default_params["rsi_max"])),
        "volume_ratio_min": _to_float(_sval("volume_ratio_min"), float(default_params["volume_ratio_min"]), minimum=0.0),
        "stop_loss_pct": _to_nullable_float(_sval("stop_loss_pct"), default_params.get("stop_loss_pct"), minimum=0.0),
        "take_profit_pct": _to_nullable_float(_sval("take_profit_pct"), default_params.get("take_profit_pct"), minimum=0.0),
        "adx_min": _to_nullable_float(_sval("adx_min"), default_params.get("adx_min"), minimum=0.0),
        "mfi_min": _to_nullable_float(_sval("mfi_min"), default_params.get("mfi_min")),
        "mfi_max": _to_nullable_float(_sval("mfi_max"), default_params.get("mfi_max")),
        "bb_pct_min": _to_nullable_float(_sval("bb_pct_min"), default_params.get("bb_pct_min"), minimum=0.0, maximum=1.0),
        "bb_pct_max": _to_nullable_float(_sval("bb_pct_max"), default_params.get("bb_pct_max"), minimum=0.0, maximum=1.0),
        "stoch_k_min": _to_nullable_float(_sval("stoch_k_min"), default_params.get("stoch_k_min")),
        "stoch_k_max": _to_nullable_float(_sval("stoch_k_max"), default_params.get("stoch_k_max")),
        "trade_suppression_threshold": _to_nullable_float(_sval("trade_suppression_threshold"), default_params.get("trade_suppression_threshold"), minimum=0.0),
    }
    return {
        "market_scope": market_scope,
        "strategy_kind": strategy_kind,
        "regime_mode": regime_mode,
        "risk_profile": risk_profile,
        "lookback_days": _to_int(raw.get("lookback_days"), int(_DEFAULT_QUERY["lookback_days"]), minimum=180),
        "portfolio_constraints": portfolio_constraints,
        "strategy_params": strategy_params,
        # flat 필드는 nested canonical 값에서 파생 (하위호환 유지, 별도 계산 없음)
        "initial_cash": portfolio_constraints["initial_cash"],
        "max_positions": portfolio_constraints["max_positions"],
        "max_holding_days": portfolio_constraints["max_holding_days"],
        "rsi_min": strategy_params["rsi_min"],
        "rsi_max": strategy_params["rsi_max"],
        "volume_ratio_min": strategy_params["volume_ratio_min"],
        "stop_loss_pct": strategy_params["stop_loss_pct"],
        "take_profit_pct": strategy_params["take_profit_pct"],
        "adx_min": strategy_params["adx_min"],
        "mfi_min": strategy_params["mfi_min"],
        "mfi_max": strategy_params["mfi_max"],
        "bb_pct_min": strategy_params["bb_pct_min"],
        "bb_pct_max": strategy_params["bb_pct_max"],
        "stoch_k_min": strategy_params["stoch_k_min"],
        "stoch_k_max": strategy_params["stoch_k_max"],
    }


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return default



def _normalize_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "trainingDays": _to_int(raw.get("trainingDays"), int(_DEFAULT_SETTINGS["trainingDays"]), minimum=30),
        "validationDays": _to_int(raw.get("validationDays"), int(_DEFAULT_SETTINGS["validationDays"]), minimum=20),
        "walkForward": _to_bool(raw.get("walkForward"), bool(_DEFAULT_SETTINGS["walkForward"])),
        "minTrades": _to_int(raw.get("minTrades"), int(_DEFAULT_SETTINGS["minTrades"]), minimum=1),
        "objective": str(raw.get("objective") or _DEFAULT_SETTINGS["objective"]),
    }


def _build_state_snapshot(
    *,
    query: dict[str, Any],
    settings: dict[str, Any],
    status: str,
    updated_at: str,
    source: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "query": query,
        "settings": settings,
        "version": STATE_SCHEMA_VERSION,
        "updated_at": updated_at,
        "source": source,
    }


def _load_runtime_apply_meta() -> dict[str, Any] | None:
    """quant_ops_state.json 의 runtime_apply 메타만 읽는다. 없으면 None."""
    path = RUNTIME_DIR / "quant_ops_state.json"
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        ra = payload.get("runtime_apply") if isinstance(payload, dict) else None
        return ra if isinstance(ra, dict) and ra.get("applied_at") else None
    except Exception:
        return None


def _build_response(query: dict[str, Any], settings: dict[str, Any], saved_at: str) -> dict[str, Any]:
    source = str(BACKTEST_VALIDATION_SETTINGS_PATH)
    updated_at = saved_at or ""
    ra = _load_runtime_apply_meta()
    approved_snapshot: dict[str, Any] | None = None
    applied_snapshot: dict[str, Any] | None = None
    if ra:
        ra_source = str(RUNTIME_DIR / "quant_ops_state.json")
        if ra.get("approved_at"):
            approved_snapshot = {
                "status": "approved",
                "candidate_id": ra.get("candidate_id"),
                "updated_at": str(ra.get("approved_at")),
                "version": STATE_SCHEMA_VERSION,
                "source": ra_source,
            }
        applied_snapshot = {
            "status": "applied",
            "candidate_id": ra.get("candidate_id"),
            "updated_at": str(ra.get("applied_at")),
            "version": STATE_SCHEMA_VERSION,
            "source": ra_source,
        }
    return {
        "ok": True,
        "query": query,
        "settings": settings,
        "saved_at": saved_at,
        "source": source,
        "version": STATE_SCHEMA_VERSION,
        "updated_at": updated_at,
        "state": {
            "saved": _build_state_snapshot(
                query=query,
                settings=settings,
                status="saved",
                updated_at=updated_at,
                source=source,
            ),
            "approved": approved_snapshot,
            "applied": applied_snapshot,
            "displayed": _build_state_snapshot(
                query=query,
                settings=settings,
                status="displayed",
                updated_at=updated_at,
                source=source,
            ),
        },
    }


def load_persisted_validation_settings() -> dict[str, Any]:
    payload = _read_json(BACKTEST_VALIDATION_SETTINGS_PATH) or {}
    query = _normalize_query(payload.get("query") if isinstance(payload.get("query"), dict) else None)
    settings = _normalize_settings(payload.get("settings") if isinstance(payload.get("settings"), dict) else None)
    saved_at = str(payload.get("saved_at") or "")
    normalized_payload = {
        "query": query,
        "settings": settings,
        "saved_at": saved_at,
    }
    if payload and payload != normalized_payload:
        _write_json(BACKTEST_VALIDATION_SETTINGS_PATH, normalized_payload)
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
