from __future__ import annotations

from typing import Any, Mapping

from strategies.base import BaseStrategy, StrategyProfile, pnl_pct_from_snapshot, read_snapshot_value, to_float


class TrendFollowingStrategy(BaseStrategy):
    strategy_kind = "trend_following"
    strategy_id = "trend_following"

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
        macd = read_snapshot_value(snapshot, "macd")
        macd_signal = read_snapshot_value(snapshot, "macd_signal")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")
        adx14 = read_snapshot_value(snapshot, "adx14")
        mfi14 = read_snapshot_value(snapshot, "mfi14")
        bb_pct = read_snapshot_value(snapshot, "bb_pct")
        stoch_k = read_snapshot_value(snapshot, "stoch_k")

        if None in {close, sma20, sma60, volume_ratio, rsi14, macd, macd_signal, macd_hist}:
            return False
        if not (to_float(close) > to_float(sma20) > to_float(sma60)):
            return False
        if to_float(volume_ratio) < float(profile.volume_ratio_min):
            return False
        if not (float(profile.rsi_min) <= to_float(rsi14) <= float(profile.rsi_max)):
            return False
        if not (to_float(macd_hist) > 0 or to_float(macd) > to_float(macd_signal)):
            return False
        if profile.adx_min is not None and adx14 is not None and to_float(adx14) < float(profile.adx_min):
            return False
        if profile.mfi_min is not None and mfi14 is not None and to_float(mfi14) < float(profile.mfi_min):
            return False
        if profile.mfi_max is not None and mfi14 is not None and to_float(mfi14) > float(profile.mfi_max):
            return False
        if profile.bb_pct_min is not None and bb_pct is not None and to_float(bb_pct) < float(profile.bb_pct_min):
            return False
        if profile.bb_pct_max is not None and bb_pct is not None and to_float(bb_pct) > float(profile.bb_pct_max):
            return False
        if profile.stoch_k_min is not None and stoch_k is not None and to_float(stoch_k) < float(profile.stoch_k_min):
            return False
        if profile.stoch_k_max is not None and stoch_k is not None and to_float(stoch_k) > float(profile.stoch_k_max):
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
        macd = read_snapshot_value(snapshot, "macd")
        macd_signal = read_snapshot_value(snapshot, "macd_signal")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")

        if holding_days >= profile.max_holding_days:
            return "보유기간 만료"
        if profile.stop_loss_pct is not None and pnl_pct is not None and pnl_pct <= -float(profile.stop_loss_pct):
            return "손절"
        if profile.take_profit_pct is not None and pnl_pct is not None and pnl_pct >= float(profile.take_profit_pct):
            return "익절"
        if holding_days <= 2:
            return None
        if close is not None and sma20 is not None and to_float(close) < to_float(sma20) * 0.99:
            return "20일선 이탈"
        if macd is not None and macd_signal is not None and macd_hist is not None and pnl_pct is not None:
            if to_float(macd) < to_float(macd_signal) and to_float(macd_hist) < 0 and pnl_pct < -2.0:
                return "MACD 약세 전환"
        if rsi14 is not None and to_float(rsi14) >= 82.0:
            return "RSI 과열"
        return None

    def score(
        self,
        snapshot: Mapping[str, Any] | None,
        profile: StrategyProfile,
        context: Mapping[str, Any] | None = None,
    ) -> float:
        close = read_snapshot_value(snapshot, "close", "current_price", "trade_price")
        sma20 = read_snapshot_value(snapshot, "sma20")
        sma60 = read_snapshot_value(snapshot, "sma60")
        volume_ratio = read_snapshot_value(snapshot, "volume_ratio")
        rsi14 = read_snapshot_value(snapshot, "rsi14")
        macd_hist = read_snapshot_value(snapshot, "macd_hist")
        if None in {close, sma20, sma60, volume_ratio, rsi14, macd_hist}:
            return 0.0

        trend_score = ((to_float(close) / to_float(sma20)) - 1.0) * 100.0
        structure_score = ((to_float(sma20) / to_float(sma60)) - 1.0) * 100.0
        volume_score = max(0.0, to_float(volume_ratio) - float(profile.volume_ratio_min)) * 12.0
        momentum_score = max(0.0, to_float(macd_hist)) * 14.0
        rsi_balance = max(0.0, 18.0 - abs(((profile.rsi_min + profile.rsi_max) / 2.0) - to_float(rsi14)))
        return round(trend_score + structure_score + volume_score + momentum_score + rsi_balance, 4)
