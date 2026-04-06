from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class StrategyProfile:
    market: str
    strategy_kind: str = "trend_following"
    risk_profile: str = "balanced"
    regime_mode: str = "manual"
    max_positions: int = 5
    max_holding_days: int = 15
    rsi_min: float = 38.0
    rsi_max: float = 62.0
    volume_ratio_min: float = 1.0
    stop_loss_pct: float | None = 5.0
    take_profit_pct: float | None = None
    signal_interval: str = "1d"
    signal_range: str = "6mo"
    adx_min: float | None = None
    mfi_min: float | None = None
    mfi_max: float | None = None
    bb_pct_min: float | None = None
    bb_pct_max: float | None = None
    stoch_k_min: float | None = None
    stoch_k_max: float | None = None
    trade_suppression_threshold: float | None = None


class BaseStrategy:
    strategy_kind = "trend_following"
    strategy_id = "trend_following"

    def should_enter(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        raise NotImplementedError

    def should_exit(
        self,
        snapshot: Mapping[str, Any] | None,
        position: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> str | None:
        raise NotImplementedError

    def score(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> float:
        raise NotImplementedError


def read_snapshot_value(snapshot: Mapping[str, Any] | None, *keys: str) -> Any:
    if not snapshot:
        return None
    for key in keys:
        value = snapshot.get(key)
        if value is not None:
            return value
    return None


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pnl_pct_from_snapshot(snapshot: Mapping[str, Any] | None, entry_price: float | None) -> float | None:
    price = read_snapshot_value(snapshot, "trade_price", "current_price", "close")
    if price is None or not entry_price:
        return None
    try:
        return ((float(price) / float(entry_price)) - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None

