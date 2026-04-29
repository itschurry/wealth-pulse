from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config.settings import KIS_ACCOUNT_ACNT_PRDT_CD, KIS_ACCOUNT_CANO, KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE_URL, LOGS_DIR

DEFAULT_RISK_CONFIG_PATH = LOGS_DIR / "agent_risk_config.json"

_DEFAULT_CONFIG: dict[str, Any] = {
    "trading_mode": "paper",
    "enable_live_trading": False,
    "min_confidence": 0.7,
    "min_reward_risk_ratio": 1.3,
    "max_symbol_position_ratio": 0.10,
    "allow_additional_buy": False,
    "cooldown_minutes": 30,
    "daily_loss_limit_pct": 3.0,
    "max_daily_orders": 20,
}

_ALLOWED_KEYS = set(_DEFAULT_CONFIG)


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sanitize_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = dict(_DEFAULT_CONFIG)
    for key in _ALLOWED_KEYS:
        if key in raw:
            config[key] = raw[key]
    config["trading_mode"] = "paper" if str(config.get("trading_mode") or "paper").lower() != "live" else "live"
    # Live trading cannot be enabled through this first API. Operators must use
    # explicit env/config rollout in a later phase.
    config["enable_live_trading"] = False
    config["min_confidence"] = max(0.0, min(1.0, _to_float(config.get("min_confidence"), _DEFAULT_CONFIG["min_confidence"])))
    config["min_reward_risk_ratio"] = max(0.0, _to_float(config.get("min_reward_risk_ratio"), _DEFAULT_CONFIG["min_reward_risk_ratio"]))
    config["max_symbol_position_ratio"] = max(0.0, min(0.10, _to_float(config.get("max_symbol_position_ratio"), _DEFAULT_CONFIG["max_symbol_position_ratio"])))
    config["allow_additional_buy"] = _to_bool(config.get("allow_additional_buy"), False)
    config["cooldown_minutes"] = max(0, _to_int(config.get("cooldown_minutes"), _DEFAULT_CONFIG["cooldown_minutes"]))
    config["daily_loss_limit_pct"] = max(0.0, _to_float(config.get("daily_loss_limit_pct"), _DEFAULT_CONFIG["daily_loss_limit_pct"]))
    config["max_daily_orders"] = max(0, _to_int(config.get("max_daily_orders"), _DEFAULT_CONFIG["max_daily_orders"]))
    return config


class AgentRiskConfigStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_RISK_CONFIG_PATH)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(_DEFAULT_CONFIG)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return dict(_DEFAULT_CONFIG)
        return _sanitize_config(raw if isinstance(raw, dict) else {})

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.load(), **(updates if isinstance(updates, dict) else {})}
        config = _sanitize_config(merged)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return config


def default_risk_config_store() -> AgentRiskConfigStore:
    return AgentRiskConfigStore()


def _present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _redacted(value: Any) -> str:
    return "[REDACTED]" if _present(value) else ""


def broker_status() -> dict[str, Any]:
    app_key = os.getenv("KIS_APP_KEY") or KIS_APP_KEY
    app_secret = os.getenv("KIS_APP_SECRET") or KIS_APP_SECRET
    account_cano = os.getenv("KIS_ACCOUNT_CANO") or KIS_ACCOUNT_CANO
    account_product = os.getenv("KIS_ACCOUNT_ACNT_PRDT_CD") or KIS_ACCOUNT_ACNT_PRDT_CD
    base_url = os.getenv("KIS_BASE_URL") or KIS_BASE_URL
    return {
        "ok": True,
        "broker": "kis",
        "configured": _present(app_key) and _present(app_secret),
        "account_configured": _present(account_cano) and _present(account_product),
        "base_url": str(base_url or ""),
        "credentials": {
            "app_key": _redacted(app_key),
            "app_secret": _redacted(app_secret),
            "account_cano": _redacted(account_cano),
            "account_product_code": _redacted(account_product),
        },
        "connectivity_checked": False,
        "live_order_enabled": False,
    }
