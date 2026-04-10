from __future__ import annotations

from copy import deepcopy
from typing import Any


STRATEGY_KINDS = ("trend_following", "mean_reversion", "defensive")
REGIME_MODES = ("auto", "manual")
RISK_PROFILES = ("conservative", "balanced", "aggressive")

STRATEGY_LABELS = {
    "trend_following": "Trend Following",
    "mean_reversion": "Mean Reversion",
    "defensive": "Defensive",
}

STRATEGY_DESCRIPTIONS = {
    "trend_following": "상승장과 강세 구간에서 추세 정렬, 거래량, 모멘텀을 확인해 진입합니다.",
    "mean_reversion": "횡보장과 반등 초입에서 과매도와 밴드 하단 복귀를 이용해 진입합니다.",
    "defensive": "약세장과 고위험 구간에서 진입을 줄이고 짧은 보유와 엄격한 리스크 관리에 집중합니다.",
}

_PORTFOLIO_DEFAULTS = {
    "kospi": {
        "market_scope": "kospi",
        "initial_cash": 10_000_000,
        "max_positions": 5,
        "max_holding_days": 15,
    },
    "nasdaq": {
        "market_scope": "nasdaq",
        "initial_cash": 10_000,
        "max_positions": 5,
        "max_holding_days": 30,
    },
    "all": {
        "market_scope": "all",
        "initial_cash": 10_000_000,
        "max_positions": 6,
        "max_holding_days": 20,
    },
}

_STRATEGY_MARKET_DEFAULTS: dict[str, dict[str, dict[str, Any]]] = {
    "trend_following": {
        "KOSPI": {
            "max_positions": 5,
            "max_holding_days": 18,
            "rsi_min": 45.0,
            "rsi_max": 72.0,
            "volume_ratio_min": 1.05,
            "adx_min": 18.0,
            "mfi_min": 25.0,
            "mfi_max": 82.0,
            "bb_pct_min": 0.15,
            "bb_pct_max": 0.98,
            "stoch_k_min": 18.0,
            "stoch_k_max": 95.0,
            "stop_loss_pct": 5.0,
            "take_profit_pct": None,
            "trade_suppression_threshold": None,
        },
        "NASDAQ": {
            "max_positions": 5,
            "max_holding_days": 30,
            "rsi_min": 45.0,
            "rsi_max": 74.0,
            "volume_ratio_min": 1.15,
            "adx_min": 18.0,
            "mfi_min": 25.0,
            "mfi_max": 84.0,
            "bb_pct_min": 0.18,
            "bb_pct_max": 0.99,
            "stoch_k_min": 20.0,
            "stoch_k_max": 95.0,
            "stop_loss_pct": 6.0,
            "take_profit_pct": None,
            "trade_suppression_threshold": None,
        },
    },
    "mean_reversion": {
        "KOSPI": {
            "max_positions": 4,
            "max_holding_days": 9,
            "rsi_min": 18.0,
            "rsi_max": 42.0,
            "volume_ratio_min": 0.85,
            "adx_min": 8.0,
            "mfi_min": 0.0,
            "mfi_max": 45.0,
            "bb_pct_min": 0.0,
            "bb_pct_max": 0.18,
            "stoch_k_min": 0.0,
            "stoch_k_max": 24.0,
            "stop_loss_pct": 4.0,
            "take_profit_pct": 9.0,
            "trade_suppression_threshold": None,
        },
        "NASDAQ": {
            "max_positions": 4,
            "max_holding_days": 12,
            "rsi_min": 20.0,
            "rsi_max": 44.0,
            "volume_ratio_min": 0.9,
            "adx_min": 8.0,
            "mfi_min": 0.0,
            "mfi_max": 48.0,
            "bb_pct_min": 0.0,
            "bb_pct_max": 0.2,
            "stoch_k_min": 0.0,
            "stoch_k_max": 28.0,
            "stop_loss_pct": 4.5,
            "take_profit_pct": 10.0,
            "trade_suppression_threshold": None,
        },
    },
    "defensive": {
        "KOSPI": {
            "max_positions": 3,
            "max_holding_days": 7,
            "rsi_min": 45.0,
            "rsi_max": 63.0,
            "volume_ratio_min": 1.2,
            "adx_min": 16.0,
            "mfi_min": 30.0,
            "mfi_max": 72.0,
            "bb_pct_min": 0.1,
            "bb_pct_max": 0.8,
            "stoch_k_min": 18.0,
            "stoch_k_max": 78.0,
            "stop_loss_pct": 3.0,
            "take_profit_pct": 6.0,
            "trade_suppression_threshold": 5.5,
        },
        "NASDAQ": {
            "max_positions": 3,
            "max_holding_days": 9,
            "rsi_min": 46.0,
            "rsi_max": 64.0,
            "volume_ratio_min": 1.25,
            "adx_min": 16.0,
            "mfi_min": 32.0,
            "mfi_max": 74.0,
            "bb_pct_min": 0.1,
            "bb_pct_max": 0.82,
            "stoch_k_min": 20.0,
            "stoch_k_max": 80.0,
            "stop_loss_pct": 3.5,
            "take_profit_pct": 7.0,
            "trade_suppression_threshold": 6.0,
        },
    },
}

_RISK_ADJUSTMENTS = {
    "conservative": {
        "max_positions_delta": -1,
        "max_holding_multiplier": 0.8,
        "stop_loss_multiplier": 0.85,
        "take_profit_multiplier": 0.9,
        "volume_ratio_bonus": 0.1,
    },
    "balanced": {
        "max_positions_delta": 0,
        "max_holding_multiplier": 1.0,
        "stop_loss_multiplier": 1.0,
        "take_profit_multiplier": 1.0,
        "volume_ratio_bonus": 0.0,
    },
    "aggressive": {
        "max_positions_delta": 1,
        "max_holding_multiplier": 1.15,
        "stop_loss_multiplier": 1.15,
        "take_profit_multiplier": 1.15,
        "volume_ratio_bonus": -0.05,
    },
}

_STRATEGY_FIELDS = {
    "trend_following": [
        {"name": "volume_ratio_min", "label": "거래량 비율 최소", "type": "number", "min": 0.2, "max": 3.0, "step": 0.05},
        {"name": "adx_min", "label": "ADX 최소", "type": "number", "min": 5.0, "max": 40.0, "step": 0.5},
        {"name": "rsi_min", "label": "RSI 하한", "type": "number", "min": 10.0, "max": 60.0, "step": 1},
        {"name": "rsi_max", "label": "RSI 상한", "type": "number", "min": 50.0, "max": 90.0, "step": 1},
        {"name": "take_profit_pct", "label": "익절", "type": "number", "min": 2.0, "max": 30.0, "step": 0.5},
        {"name": "stop_loss_pct", "label": "손절", "type": "number", "min": 1.0, "max": 20.0, "step": 0.5},
    ],
    "mean_reversion": [
        {"name": "rsi_min", "label": "RSI 과매도 기준", "type": "number", "min": 5.0, "max": 40.0, "step": 1},
        {"name": "rsi_max", "label": "RSI 반등 마감선", "type": "number", "min": 20.0, "max": 55.0, "step": 1},
        {"name": "bb_pct_max", "label": "밴드 하단 비율", "type": "number", "min": 0.0, "max": 0.5, "step": 0.01},
        {"name": "stoch_k_max", "label": "Stoch K 상한", "type": "number", "min": 5.0, "max": 50.0, "step": 1},
        {"name": "take_profit_pct", "label": "익절", "type": "number", "min": 2.0, "max": 20.0, "step": 0.5},
        {"name": "stop_loss_pct", "label": "손절", "type": "number", "min": 1.0, "max": 12.0, "step": 0.5},
    ],
    "defensive": [
        {"name": "volume_ratio_min", "label": "거래량 비율 최소", "type": "number", "min": 0.2, "max": 3.0, "step": 0.05},
        {"name": "trade_suppression_threshold", "label": "리스크 차단선", "type": "number", "min": 1.0, "max": 10.0, "step": 0.1},
        {"name": "stop_loss_pct", "label": "손절", "type": "number", "min": 1.0, "max": 10.0, "step": 0.5},
        {"name": "take_profit_pct", "label": "익절", "type": "number", "min": 2.0, "max": 15.0, "step": 0.5},
        {"name": "rsi_min", "label": "RSI 하한", "type": "number", "min": 20.0, "max": 60.0, "step": 1},
        {"name": "rsi_max", "label": "RSI 상한", "type": "number", "min": 40.0, "max": 80.0, "step": 1},
    ],
}


def _normalize_market_scope(market: str | None) -> str:
    normalized = str(market or "KOSPI").strip().upper()
    if normalized in {"NASDAQ", "NYSE", "US", "USA", "AMEX"}:
        return "NASDAQ"
    return "KOSPI"


def portfolio_defaults(market_scope: str | None = None) -> dict[str, Any]:
    key = str(market_scope or "kospi").strip().lower()
    return deepcopy(_PORTFOLIO_DEFAULTS.get(key, _PORTFOLIO_DEFAULTS["kospi"]))


def strategy_defaults(
    strategy_kind: str | None = None,
    *,
    market: str | None = None,
    risk_profile: str | None = None,
) -> dict[str, Any]:
    kind = str(strategy_kind or "trend_following").strip().lower()
    if kind not in STRATEGY_KINDS:
        kind = "trend_following"
    market_key = _normalize_market_scope(market)
    defaults = deepcopy(_STRATEGY_MARKET_DEFAULTS[kind][market_key])
    risk_key = str(risk_profile or "balanced").strip().lower()
    if risk_key not in _RISK_ADJUSTMENTS:
        risk_key = "balanced"
    adjustment = _RISK_ADJUSTMENTS[risk_key]
    defaults["max_positions"] = max(1, int(round(float(defaults["max_positions"]) + float(adjustment["max_positions_delta"]))))
    defaults["max_holding_days"] = max(1, int(round(float(defaults["max_holding_days"]) * float(adjustment["max_holding_multiplier"]))))
    if defaults.get("stop_loss_pct") is not None:
        defaults["stop_loss_pct"] = round(float(defaults["stop_loss_pct"]) * float(adjustment["stop_loss_multiplier"]), 2)
    if defaults.get("take_profit_pct") is not None:
        defaults["take_profit_pct"] = round(float(defaults["take_profit_pct"]) * float(adjustment["take_profit_multiplier"]), 2)
    defaults["volume_ratio_min"] = round(max(0.5, float(defaults["volume_ratio_min"]) + float(adjustment["volume_ratio_bonus"])), 2)
    defaults["strategy_kind"] = kind
    defaults["risk_profile"] = risk_key
    return defaults


def editable_fields(strategy_kind: str | None) -> list[dict[str, Any]]:
    kind = str(strategy_kind or "trend_following").strip().lower()
    return deepcopy(_STRATEGY_FIELDS.get(kind, _STRATEGY_FIELDS["trend_following"]))


def build_strategy_metadata_payload() -> dict[str, Any]:
    available = []
    for strategy_kind in STRATEGY_KINDS:
        available.append(
            {
                "strategy_kind": strategy_kind,
                "label": STRATEGY_LABELS[strategy_kind],
                "description": STRATEGY_DESCRIPTIONS[strategy_kind],
                "regimes": (
                    ["bull"] if strategy_kind == "trend_following"
                    else ["sideways"] if strategy_kind == "mean_reversion"
                    else ["bear", "risk_off"]
                ),
                "editable_fields": editable_fields(strategy_kind),
                "defaults_by_market": {
                    "KOSPI": strategy_defaults(strategy_kind, market="KOSPI"),
                    "NASDAQ": strategy_defaults(strategy_kind, market="NASDAQ"),
                },
                "defaults_by_market_and_risk": {
                    "KOSPI": {
                        risk_profile: strategy_defaults(strategy_kind, market="KOSPI", risk_profile=risk_profile)
                        for risk_profile in RISK_PROFILES
                    },
                    "NASDAQ": {
                        risk_profile: strategy_defaults(strategy_kind, market="NASDAQ", risk_profile=risk_profile)
                        for risk_profile in RISK_PROFILES
                    },
                },
                "hidden_params": [],
                "deprecated_params": [],
            }
        )
    return {
        "ok": True,
        "regime_modes": [
            {"value": "auto", "label": "자동", "description": "시장 상태를 보고 전략을 자동 선택합니다."},
            {"value": "manual", "label": "수동", "description": "선택한 전략만 고정해서 실행합니다."},
        ],
        "risk_profiles": [
            {"value": "conservative", "label": "보수적", "description": "포지션과 손절 폭을 줄입니다."},
            {"value": "balanced", "label": "균형", "description": "기본 추천 설정입니다."},
            {"value": "aggressive", "label": "공격적", "description": "보유와 손절 폭을 다소 넓힙니다."},
        ],
        "portfolio_defaults": {
            key: portfolio_defaults(key) for key in _PORTFOLIO_DEFAULTS
        },
        "portfolio_fields": [
            {"name": "market_scope", "label": "시장", "type": "select", "options": ["kospi", "nasdaq", "all"]},
            {"name": "initial_cash", "label": "초기 자금", "type": "number", "min": 1, "step": 1000},
            {"name": "max_positions", "label": "최대 포지션", "type": "number", "min": 1, "max": 20, "step": 1},
            {"name": "max_holding_days", "label": "최대 보유일", "type": "number", "min": 1, "max": 180, "step": 1},
            {"name": "lookback_days", "label": "백테스트 기간", "type": "number", "min": 180, "max": 1825, "step": 30},
        ],
        "available_strategies": available,
        "default_request": {
            "strategy_kind": "trend_following",
            "regime_mode": "auto",
            "risk_profile": "balanced",
            "lookback_days": 1095,
            "portfolio_constraints": portfolio_defaults("kospi"),
            "strategy_params": strategy_defaults("trend_following", market="KOSPI"),
        },
    }
