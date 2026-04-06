from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR


QUANT_GUARDRAIL_POLICY_PATH = LOGS_DIR / "quant_guardrail_policy.json"
_DEFAULT_POLICY_VERSION = 1

_DEFAULT_POLICY: dict[str, Any] = {
    "version": _DEFAULT_POLICY_VERSION,
    "thresholds": {
        "reject": {
            "blocked_reliability_levels": ["insufficient", "low"],
            "min_profit_factor": 0.95,
            "min_oos_return_pct": -2.0,
            "max_drawdown_pct": 30.0,
            "min_expected_shortfall_5_pct": -20.0,
        },
        "adopt": {
            "required_reliability": "high",
            "min_oos_return_pct": 0.0,
            "min_profit_factor": 1.08,
            "max_drawdown_pct": 22.0,
            "min_positive_window_ratio": 0.5,
            "min_expected_shortfall_5_pct": -15.0,
        },
        "limited_adopt": {
            "allowed_reliability_levels": ["high", "medium"],
            "min_oos_return_pct": 0.0,
            "min_profit_factor": 1.0,
            "max_drawdown_pct": 25.0,
            "min_positive_window_ratio": 0.45,
            "min_expected_shortfall_5_pct": -16.0,
            "min_near_miss_count": 1,
            "max_near_miss_count": 2,
        },
        "limited_adopt_runtime": {
            "risk_per_trade_pct_multiplier": 0.5,
            "risk_per_trade_pct_cap": 0.2,
            "max_positions_per_market_cap": 2,
            "max_symbol_weight_pct_cap": 10.0,
            "max_market_exposure_pct_cap": 35.0,
        },
    },
}

_ALLOWED_RELIABILITY_LEVELS = {"high", "medium", "low", "insufficient"}


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


def _to_float(value: Any, fallback: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(fallback)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return round(parsed, 4)


def _to_int(value: Any, fallback: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = int(fallback)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _normalize_reliability_list(value: Any, fallback: list[str]) -> list[str]:
    items = value if isinstance(value, (list, tuple, set)) else fallback
    normalized: list[str] = []
    for item in items:
        level = str(item or "").strip().lower()
        if level in _ALLOWED_RELIABILITY_LEVELS and level not in normalized:
            normalized.append(level)
    return normalized or list(fallback)


def default_quant_guardrail_policy() -> dict[str, Any]:
    return copy.deepcopy(_DEFAULT_POLICY)


def normalize_quant_guardrail_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    raw_thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
    reject_raw = raw_thresholds.get("reject") if isinstance(raw_thresholds.get("reject"), dict) else {}
    adopt_raw = raw_thresholds.get("adopt") if isinstance(raw_thresholds.get("adopt"), dict) else {}
    limited_raw = raw_thresholds.get("limited_adopt") if isinstance(raw_thresholds.get("limited_adopt"), dict) else {}
    runtime_raw = raw_thresholds.get("limited_adopt_runtime") if isinstance(raw_thresholds.get("limited_adopt_runtime"), dict) else {}

    default_thresholds = _DEFAULT_POLICY["thresholds"]
    default_reject = default_thresholds["reject"]
    default_adopt = default_thresholds["adopt"]
    default_limited = default_thresholds["limited_adopt"]
    default_runtime = default_thresholds["limited_adopt_runtime"]

    required_reliability = str(adopt_raw.get("required_reliability") or default_adopt["required_reliability"]).strip().lower()
    if required_reliability not in _ALLOWED_RELIABILITY_LEVELS:
        required_reliability = str(default_adopt["required_reliability"])

    policy = {
        "version": _to_int(raw.get("version"), _DEFAULT_POLICY_VERSION, minimum=1),
        "thresholds": {
            "reject": {
                "blocked_reliability_levels": _normalize_reliability_list(reject_raw.get("blocked_reliability_levels"), list(default_reject["blocked_reliability_levels"])),
                "min_profit_factor": _to_float(reject_raw.get("min_profit_factor"), float(default_reject["min_profit_factor"]), minimum=0.0),
                "min_oos_return_pct": _to_float(reject_raw.get("min_oos_return_pct"), float(default_reject["min_oos_return_pct"])),
                "max_drawdown_pct": _to_float(reject_raw.get("max_drawdown_pct"), float(default_reject["max_drawdown_pct"]), minimum=0.0),
                "min_expected_shortfall_5_pct": _to_float(reject_raw.get("min_expected_shortfall_5_pct"), float(default_reject["min_expected_shortfall_5_pct"])),
            },
            "adopt": {
                "required_reliability": required_reliability,
                "min_oos_return_pct": _to_float(adopt_raw.get("min_oos_return_pct"), float(default_adopt["min_oos_return_pct"])),
                "min_profit_factor": _to_float(adopt_raw.get("min_profit_factor"), float(default_adopt["min_profit_factor"]), minimum=0.0),
                "max_drawdown_pct": _to_float(adopt_raw.get("max_drawdown_pct"), float(default_adopt["max_drawdown_pct"]), minimum=0.0),
                "min_positive_window_ratio": _to_float(adopt_raw.get("min_positive_window_ratio"), float(default_adopt["min_positive_window_ratio"]), minimum=0.0, maximum=1.0),
                "min_expected_shortfall_5_pct": _to_float(adopt_raw.get("min_expected_shortfall_5_pct"), float(default_adopt["min_expected_shortfall_5_pct"])),
            },
            "limited_adopt": {
                "allowed_reliability_levels": _normalize_reliability_list(limited_raw.get("allowed_reliability_levels"), list(default_limited["allowed_reliability_levels"])),
                "min_oos_return_pct": _to_float(limited_raw.get("min_oos_return_pct"), float(default_limited["min_oos_return_pct"])),
                "min_profit_factor": _to_float(limited_raw.get("min_profit_factor"), float(default_limited["min_profit_factor"]), minimum=0.0),
                "max_drawdown_pct": _to_float(limited_raw.get("max_drawdown_pct"), float(default_limited["max_drawdown_pct"]), minimum=0.0),
                "min_positive_window_ratio": _to_float(limited_raw.get("min_positive_window_ratio"), float(default_limited["min_positive_window_ratio"]), minimum=0.0, maximum=1.0),
                "min_expected_shortfall_5_pct": _to_float(limited_raw.get("min_expected_shortfall_5_pct"), float(default_limited["min_expected_shortfall_5_pct"])),
                "min_near_miss_count": _to_int(limited_raw.get("min_near_miss_count"), int(default_limited["min_near_miss_count"]), minimum=0, maximum=4),
                "max_near_miss_count": _to_int(limited_raw.get("max_near_miss_count"), int(default_limited["max_near_miss_count"]), minimum=0, maximum=4),
            },
            "limited_adopt_runtime": {
                "risk_per_trade_pct_multiplier": _to_float(runtime_raw.get("risk_per_trade_pct_multiplier"), float(default_runtime["risk_per_trade_pct_multiplier"]), minimum=0.0, maximum=1.0),
                "risk_per_trade_pct_cap": _to_float(runtime_raw.get("risk_per_trade_pct_cap"), float(default_runtime["risk_per_trade_pct_cap"]), minimum=0.0),
                "max_positions_per_market_cap": _to_int(runtime_raw.get("max_positions_per_market_cap"), int(default_runtime["max_positions_per_market_cap"]), minimum=1),
                "max_symbol_weight_pct_cap": _to_float(runtime_raw.get("max_symbol_weight_pct_cap"), float(default_runtime["max_symbol_weight_pct_cap"]), minimum=0.0, maximum=100.0),
                "max_market_exposure_pct_cap": _to_float(runtime_raw.get("max_market_exposure_pct_cap"), float(default_runtime["max_market_exposure_pct_cap"]), minimum=0.0, maximum=100.0),
            },
        },
    }
    if policy["thresholds"]["limited_adopt"]["max_near_miss_count"] < policy["thresholds"]["limited_adopt"]["min_near_miss_count"]:
        policy["thresholds"]["limited_adopt"]["max_near_miss_count"] = policy["thresholds"]["limited_adopt"]["min_near_miss_count"]
    return policy


def build_quant_guardrail_policy_response(policy: dict[str, Any], *, saved_at: str) -> dict[str, Any]:
    normalized = normalize_quant_guardrail_policy(policy)
    return {
        "ok": True,
        "policy": normalized,
        "saved_at": saved_at,
        "source": str(QUANT_GUARDRAIL_POLICY_PATH),
    }


def load_quant_guardrail_policy() -> dict[str, Any]:
    payload = _read_json(QUANT_GUARDRAIL_POLICY_PATH) or {}
    saved_at = str(payload.get("saved_at") or "")
    policy = normalize_quant_guardrail_policy(payload.get("policy") if isinstance(payload.get("policy"), dict) else payload)
    if not saved_at and QUANT_GUARDRAIL_POLICY_PATH.exists():
        saved_at = _now_iso()
    return build_quant_guardrail_policy_response(policy, saved_at=saved_at)


def save_quant_guardrail_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw_policy = payload.get("policy") if isinstance(payload, dict) and isinstance(payload.get("policy"), dict) else payload
    policy = normalize_quant_guardrail_policy(raw_policy if isinstance(raw_policy, dict) else None)
    saved_at = _now_iso()
    _write_json(QUANT_GUARDRAIL_POLICY_PATH, {"policy": policy, "saved_at": saved_at})
    return build_quant_guardrail_policy_response(policy, saved_at=saved_at)


def reset_quant_guardrail_policy() -> dict[str, Any]:
    return save_quant_guardrail_policy(default_quant_guardrail_policy())
