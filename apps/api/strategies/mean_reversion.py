from __future__ import annotations

from typing import Any, Mapping

from strategies.base import BaseStrategy, StrategyProfile, pnl_pct_from_snapshot, read_snapshot_value, to_float


class MeanReversionStrategy(BaseStrategy):
    strategy_kind = "mean_reversion"
    strategy_id = "mean_reversion"

    def should_enter(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        close = read_snapshot_value(snapshot, "current_price", "close", "trade_price")
        sma20 = read_snapshot_value(snapshot, "sma20")
        sma60 = read_snapshot_value(snapshot, "sma60")
        volume_ratio = read_snapshot_value(snapshot, "volume_ratio")
        rsi14 = read_snapshot_value(snapshot, "rsi14")
        bb_pct = read_snapshot_value(snapshot, "bb_pct")
        stoch_k = read_snapshot_value(snapshot, "stoch_k")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")
        if None in {close, sma20, sma60, volume_ratio, rsi14, bb_pct, stoch_k, macd_hist}:
            return False
        if to_float(close) < to_float(sma60) * 0.92:
            return False
        if to_float(volume_ratio) < max(0.5, float(profile.volume_ratio_min) * 0.85):
            return False
        if to_float(rsi14) < float(profile.rsi_min) or to_float(rsi14) > float(profile.rsi_max):
            return False
        if profile.bb_pct_max is not None and to_float(bb_pct) > float(profile.bb_pct_max):
            return False
        if profile.stoch_k_max is not None and to_float(stoch_k) > float(profile.stoch_k_max):
            return False
        if to_float(macd_hist) < -0.75:
            return False
        return to_float(close) <= to_float(sma20) * 1.01

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
        bb_pct = read_snapshot_value(snapshot, "bb_pct")

        if holding_days >= profile.max_holding_days:
            return "보유기간 만료"
        if profile.stop_loss_pct is not None and pnl_pct is not None and pnl_pct <= -float(profile.stop_loss_pct):
            return "손절"
        if profile.take_profit_pct is not None and pnl_pct is not None and pnl_pct >= float(profile.take_profit_pct):
            return "익절"
        if close is not None and sma20 is not None and to_float(close) >= to_float(sma20):
            return "20일선 복귀"
        if rsi14 is not None and to_float(rsi14) >= max(55.0, float(profile.rsi_max) + 8.0):
            return "반등 소진"
        if bb_pct is not None and to_float(bb_pct) >= 0.62:
            return "밴드 복귀"
        return None

    def score(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> float:
        close = read_snapshot_value(snapshot, "close", "current_price", "trade_price")
        sma20 = read_snapshot_value(snapshot, "sma20")
        rsi14 = read_snapshot_value(snapshot, "rsi14")
        bb_pct = read_snapshot_value(snapshot, "bb_pct")
        stoch_k = read_snapshot_value(snapshot, "stoch_k")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")
        if None in {close, sma20, rsi14, bb_pct, stoch_k, macd_hist}:
            return 0.0
        distance_score = max(0.0, (to_float(sma20) - to_float(close)) / max(to_float(sma20), 1.0) * 100.0)
        oversold_score = max(0.0, float(profile.rsi_max) - to_float(rsi14))
        band_score = max(0.0, 0.3 - to_float(bb_pct)) * 60.0
        stoch_score = max(0.0, float(profile.stoch_k_max or 30.0) - to_float(stoch_k)) * 0.4
        momentum_penalty = abs(min(0.0, to_float(macd_hist))) * 6.0
        return round(distance_score + oversold_score + band_score + stoch_score - momentum_penalty, 4)
