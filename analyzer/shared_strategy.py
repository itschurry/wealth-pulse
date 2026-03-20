"""Shared market-specific strategy profiles and signal evaluators."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping

_US_MARKETS = {"NASDAQ", "NYSE", "AMEX", "US", "USA"}


@dataclass(frozen=True)
class StrategyProfile:
    market: str
    max_positions: int
    max_holding_days: int
    rsi_min: float
    rsi_max: float
    volume_ratio_min: float
    stop_loss_pct: float | None
    take_profit_pct: float | None
    signal_interval: str = "1d"
    signal_range: str = "6mo"


_DEFAULT_PROFILES: dict[str, StrategyProfile] = {
    "KOSPI": StrategyProfile(
        market="KOSPI",
        max_positions=5,
        max_holding_days=15,
        rsi_min=45.0,
        rsi_max=62.0,
        volume_ratio_min=1.0,
        stop_loss_pct=5.0,
        take_profit_pct=None,
        signal_interval="1d",
        signal_range="6mo",
    ),
    "NASDAQ": StrategyProfile(
        market="NASDAQ",
        max_positions=5,
        max_holding_days=30,
        rsi_min=45.0,
        rsi_max=68.0,
        volume_ratio_min=1.2,
        stop_loss_pct=None,
        take_profit_pct=None,
        signal_interval="1d",
        signal_range="6mo",
    ),
}


def normalize_strategy_market(market: str | None) -> str:
    normalized = str(market or "").strip().upper()
    if normalized in {"KOSPI", "KOSDAQ", "KRX", "KR", "KOREA"}:
        return "KOSPI"
    if normalized in _US_MARKETS:
        return "NASDAQ"
    return normalized or "KOSPI"


def default_strategy_profile(market: str) -> StrategyProfile:
    normalized_market = normalize_strategy_market(market)
    template = _DEFAULT_PROFILES["NASDAQ" if normalized_market in _US_MARKETS else normalized_market]
    return replace(template, market=normalized_market)


def build_strategy_profile(market: str, **overrides: Any) -> StrategyProfile:
    template = default_strategy_profile(market)
    data = asdict(template)
    for key, value in overrides.items():
        if key in data:
            data[key] = value
    return normalize_strategy_profile(StrategyProfile(**data))


def normalize_strategy_profile(profile: StrategyProfile) -> StrategyProfile:
    market = normalize_strategy_market(profile.market)
    rsi_min = max(10.0, min(90.0, float(profile.rsi_min)))
    rsi_max = max(10.0, min(90.0, float(profile.rsi_max)))
    if rsi_min > rsi_max:
        rsi_min, rsi_max = rsi_max, rsi_min
    stop_loss = profile.stop_loss_pct
    if stop_loss is not None:
        stop_loss = max(1.0, min(50.0, float(stop_loss)))
    take_profit = profile.take_profit_pct
    if take_profit is not None:
        take_profit = max(1.0, min(100.0, float(take_profit)))
    return StrategyProfile(
        market=market,
        max_positions=max(1, min(20, int(profile.max_positions))),
        max_holding_days=max(1, min(180, int(profile.max_holding_days))),
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        volume_ratio_min=max(0.5, min(5.0, float(profile.volume_ratio_min))),
        stop_loss_pct=stop_loss,
        take_profit_pct=take_profit,
        signal_interval=_normalize_signal_interval(profile.signal_interval),
        signal_range=_normalize_signal_range(profile.signal_range),
    )


def default_strategy_profiles(markets: Iterable[str]) -> tuple[StrategyProfile, ...]:
    ordered: list[StrategyProfile] = []
    seen: set[str] = set()
    for market in markets:
        normalized = normalize_strategy_market(market)
        if normalized in seen:
            continue
        ordered.append(default_strategy_profile(normalized))
        seen.add(normalized)
    return tuple(ordered)


def profiles_by_market(profiles: Iterable[StrategyProfile] | None, markets: Iterable[str] | None = None) -> dict[str, StrategyProfile]:
    result: dict[str, StrategyProfile] = {}
    if profiles:
        for profile in profiles:
            normalized = normalize_strategy_market(profile.market)
            result[normalized] = normalize_strategy_profile(profile)
    if markets:
        for market in markets:
            normalized = normalize_strategy_market(market)
            result.setdefault(normalized, default_strategy_profile(normalized))
    return result


def serialize_strategy_profile(profile: StrategyProfile) -> dict[str, Any]:
    return asdict(normalize_strategy_profile(profile))


def serialize_strategy_profiles(profiles: Iterable[StrategyProfile] | Mapping[str, StrategyProfile]) -> dict[str, dict[str, Any]]:
    if isinstance(profiles, Mapping):
        items = profiles.items()
    else:
        items = ((profile.market, profile) for profile in profiles)
    return {
        normalize_strategy_market(market): serialize_strategy_profile(profile)
        for market, profile in items
    }


def profile_from_mapping(market: str, payload: Mapping[str, Any] | None) -> StrategyProfile:
    raw = payload or {}
    return build_strategy_profile(
        market,
        max_positions=raw.get("max_positions", default_strategy_profile(market).max_positions),
        max_holding_days=raw.get("max_holding_days", default_strategy_profile(market).max_holding_days),
        rsi_min=raw.get("rsi_min", default_strategy_profile(market).rsi_min),
        rsi_max=raw.get("rsi_max", default_strategy_profile(market).rsi_max),
        volume_ratio_min=raw.get("volume_ratio_min", default_strategy_profile(market).volume_ratio_min),
        stop_loss_pct=raw.get("stop_loss_pct", default_strategy_profile(market).stop_loss_pct),
        take_profit_pct=raw.get("take_profit_pct", default_strategy_profile(market).take_profit_pct),
        signal_interval=raw.get("signal_interval", default_strategy_profile(market).signal_interval),
        signal_range=raw.get("signal_range", default_strategy_profile(market).signal_range),
    )


def should_enter_from_snapshot(snapshot: Mapping[str, Any] | None, profile: StrategyProfile) -> bool:
    if not snapshot:
        return False
    close = _read_snapshot_value(snapshot, "current_price", "close", "trade_price")
    sma20 = snapshot.get("sma20")
    sma60 = snapshot.get("sma60")
    volume_ratio = snapshot.get("volume_ratio")
    rsi14 = snapshot.get("rsi14")
    macd = snapshot.get("macd")
    macd_signal = snapshot.get("macd_signal")
    macd_hist = snapshot.get("macd_hist")

    return bool(
        close is not None
        and sma20 is not None
        and sma60 is not None
        and volume_ratio is not None
        and rsi14 is not None
        and macd is not None
        and macd_signal is not None
        and macd_hist is not None
        and float(close) > float(sma20) > float(sma60)
        and float(volume_ratio) >= profile.volume_ratio_min
        and profile.rsi_min <= float(rsi14) <= profile.rsi_max
        and float(macd_hist) > 0
        and float(macd) > float(macd_signal)
    )


def should_exit_from_snapshot(
    snapshot: Mapping[str, Any] | None,
    *,
    entry_price: float | None,
    holding_days: int,
    profile: StrategyProfile,
) -> str | None:
    if not snapshot:
        return None
    price = _read_snapshot_value(snapshot, "trade_price", "current_price", "close")
    close = _read_snapshot_value(snapshot, "close", "current_price", "trade_price")
    sma20 = snapshot.get("sma20")
    rsi14 = snapshot.get("rsi14")
    macd = snapshot.get("macd")
    macd_signal = snapshot.get("macd_signal")
    macd_hist = snapshot.get("macd_hist")

    if holding_days >= profile.max_holding_days:
        return "보유기간 만료"
    if (
        profile.stop_loss_pct is not None
        and price is not None
        and entry_price
        and ((float(price) / float(entry_price)) - 1) * 100 <= -profile.stop_loss_pct
    ):
        return "손절"
    if (
        profile.take_profit_pct is not None
        and price is not None
        and entry_price
        and ((float(price) / float(entry_price)) - 1) * 100 >= profile.take_profit_pct
    ):
        return "익절"
    if close is not None and sma20 is not None and float(close) < float(sma20):
        return "20일선 이탈"
    if macd is not None and macd_signal is not None and macd_hist is not None:
        if float(macd) < float(macd_signal) and float(macd_hist) < 0:
            return "MACD 약세 전환"
    if rsi14 is not None and float(rsi14) >= 75:
        return "RSI 과열"
    return None


def entry_score_from_snapshot(snapshot: Mapping[str, Any] | None, profile: StrategyProfile | None = None) -> float:
    if not snapshot:
        return 0.0
    close = _read_snapshot_value(snapshot, "close", "current_price", "trade_price")
    sma20 = snapshot.get("sma20")
    sma60 = snapshot.get("sma60")
    volume_ratio = snapshot.get("volume_ratio")
    rsi14 = snapshot.get("rsi14")
    macd_hist = snapshot.get("macd_hist")
    if None in {close, sma20, sma60, volume_ratio, rsi14, macd_hist}:
        return 0.0
    trend_score = ((float(close) / float(sma20)) - 1) * 100 + ((float(sma20) / float(sma60)) - 1) * 100
    rsi_score = max(0.0, 70 - abs(57.0 - float(rsi14)))
    return round(trend_score + float(volume_ratio) * 2.5 + float(macd_hist) * 12 + rsi_score * 0.1, 4)


def _normalize_signal_interval(value: str | None) -> str:
    normalized = str(value or "1d").strip().lower()
    return normalized if normalized in {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1d"} else "1d"


def _normalize_signal_range(value: str | None) -> str:
    normalized = str(value or "6mo").strip().lower()
    return normalized if normalized in {"1d", "5d", "1mo", "3mo", "6mo", "1y"} else "6mo"


def _read_snapshot_value(snapshot: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = snapshot.get(key)
        if value is not None:
            return value
    return None
