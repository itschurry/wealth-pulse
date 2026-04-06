from __future__ import annotations

from typing import Any, Mapping

from strategies.base import BaseStrategy, StrategyProfile, pnl_pct_from_snapshot, read_snapshot_value, to_float


class DefensiveStrategy(BaseStrategy):
    strategy_kind = "defensive"
    strategy_id = "defensive"

    def should_enter(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        close = read_snapshot_value(snapshot, "current_price", "close", "trade_price")
        sma20 = read_snapshot_value(snapshot, "sma20")
        volume_ratio = read_snapshot_value(snapshot, "volume_ratio")
        rsi14 = read_snapshot_value(snapshot, "rsi14")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")
        atr14_pct = read_snapshot_value(snapshot, "atr14_pct")
        if None in {close, sma20, volume_ratio, rsi14, macd_hist}:
            return False
        if to_float(close) < to_float(sma20) * 0.99:
            return False
        if to_float(volume_ratio) < float(profile.volume_ratio_min):
            return False
        if not (float(profile.rsi_min) <= to_float(rsi14) <= float(profile.rsi_max)):
            return False
        if to_float(macd_hist) <= 0:
            return False
        threshold = profile.trade_suppression_threshold
        if threshold is not None and atr14_pct is not None and to_float(atr14_pct) > float(threshold):
            return False
        return True

    def should_exit(
        self,
        snapshot: Mapping[str, Any] | None,
        position: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> str | None:
        holding_days = int((position or {}).get("holding_days") or 0)
        pnl_pct = pnl_pct_from_snapshot(snapshot, (position or {}).get("entry_price"))
        close = read_snapshot_value(snapshot, "close", "current_price", "trade_price")
        sma20 = read_snapshot_value(snapshot, "sma20")
        rsi14 = read_snapshot_value(snapshot, "rsi14")
        if holding_days >= profile.max_holding_days:
            return "보유기간 만료"
        if profile.stop_loss_pct is not None and pnl_pct is not None and pnl_pct <= -float(profile.stop_loss_pct):
            return "손절"
        if profile.take_profit_pct is not None and pnl_pct is not None and pnl_pct >= float(profile.take_profit_pct):
            return "익절"
        if close is not None and sma20 is not None and to_float(close) < to_float(sma20):
            return "방어 실패"
        if rsi14 is not None and to_float(rsi14) >= 70.0:
            return "과열 회피"
        return None

    def score(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> float:
        close = read_snapshot_value(snapshot, "close", "current_price", "trade_price")
        sma20 = read_snapshot_value(snapshot, "sma20")
        volume_ratio = read_snapshot_value(snapshot, "volume_ratio")
        rsi14 = read_snapshot_value(snapshot, "rsi14")
        atr14_pct = read_snapshot_value(snapshot, "atr14_pct")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")
        if None in {close, sma20, volume_ratio, rsi14, macd_hist}:
            return 0.0
        stability = max(0.0, 7.0 - to_float(atr14_pct, 0.0)) if atr14_pct is not None else 3.0
        structure = max(0.0, ((to_float(close) / to_float(sma20)) - 1.0) * 100.0)
        volume = max(0.0, to_float(volume_ratio) - float(profile.volume_ratio_min) + 0.2) * 10.0
        discipline = max(0.0, 20.0 - abs(55.0 - to_float(rsi14)))
        return round(stability + structure + volume + discipline + max(0.0, to_float(macd_hist)) * 10.0, 4)
