from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from schemas.strategy_metadata import strategy_defaults
from services.regime_service import detect_market_regime
from strategies.base import BaseStrategy, StrategyProfile
from strategies.defensive import DefensiveStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.trend_following import TrendFollowingStrategy


_STRATEGIES: dict[str, BaseStrategy] = {
    "trend_following": TrendFollowingStrategy(),
    "mean_reversion": MeanReversionStrategy(),
    "defensive": DefensiveStrategy(),
}

_REGIME_TO_STRATEGY = {
    "bull": "trend_following",
    "sideways": "mean_reversion",
    "bear": "defensive",
    "risk_off": "defensive",
}


def get_strategy(strategy_kind: str | None) -> BaseStrategy:
    kind = str(strategy_kind or "trend_following").strip().lower()
    return _STRATEGIES.get(kind, _STRATEGIES["trend_following"])


def _resolved_strategy_kind(profile: StrategyProfile, snapshot: Mapping[str, Any] | None) -> tuple[str, str]:
    if str(profile.regime_mode or "manual").strip().lower() != "auto":
        return profile.strategy_kind, "manual"
    regime_payload = detect_market_regime(snapshot)
    regime = str(regime_payload.get("regime") or "sideways")
    return _REGIME_TO_STRATEGY.get(regime, profile.strategy_kind), regime


def resolve_strategy(profile: StrategyProfile, snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    resolved_kind, regime = _resolved_strategy_kind(profile, snapshot)
    defaults = strategy_defaults(resolved_kind, market=profile.market, risk_profile=profile.risk_profile)
    runtime_profile = replace(
        profile,
        strategy_kind=resolved_kind,
        regime_mode="manual",
        rsi_min=float(defaults.get("rsi_min", profile.rsi_min)),
        rsi_max=float(defaults.get("rsi_max", profile.rsi_max)),
        volume_ratio_min=float(defaults.get("volume_ratio_min", profile.volume_ratio_min)),
        adx_min=defaults.get("adx_min"),
        mfi_min=defaults.get("mfi_min"),
        mfi_max=defaults.get("mfi_max"),
        bb_pct_min=defaults.get("bb_pct_min"),
        bb_pct_max=defaults.get("bb_pct_max"),
        stoch_k_min=defaults.get("stoch_k_min"),
        stoch_k_max=defaults.get("stoch_k_max"),
        trade_suppression_threshold=defaults.get("trade_suppression_threshold"),
    )
    return {
        "strategy_kind": resolved_kind,
        "regime": regime,
        "strategy": get_strategy(resolved_kind),
        "profile": runtime_profile,
    }
