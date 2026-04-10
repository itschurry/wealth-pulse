"""Shared strategy profile helpers and backward-compatible strategy wrappers."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Iterable, Mapping

from schemas.strategy_metadata import strategy_defaults
from services.strategy_selector import get_strategy, resolve_strategy
from strategies.base import StrategyProfile, read_snapshot_value

_US_MARKETS = {"NASDAQ", "NYSE", "AMEX", "US", "USA"}

def normalize_strategy_market(market: str | None) -> str:
    normalized = str(market or "").strip().upper()
    if normalized in {"KOSPI", "KOSDAQ", "KRX", "KR", "KOREA"}:
        return "KOSPI"
    if normalized in _US_MARKETS:
        return "NASDAQ"
    return normalized or "KOSPI"


def default_strategy_profile(
    market: str,
    strategy_kind: str = "trend_following",
    risk_profile: str = "balanced",
    regime_mode: str = "manual",
) -> StrategyProfile:
    normalized_market = normalize_strategy_market(market)
    defaults = strategy_defaults(strategy_kind, market=normalized_market, risk_profile=risk_profile)
    return StrategyProfile(
        market=normalized_market,
        strategy_kind=str(defaults.get("strategy_kind") or strategy_kind),
        risk_profile=str(defaults.get("risk_profile") or risk_profile),
        regime_mode=str(regime_mode or "manual"),
        max_positions=int(defaults.get("max_positions", 5)),
        max_holding_days=int(defaults.get("max_holding_days", 15)),
        rsi_min=float(defaults.get("rsi_min", 38.0)),
        rsi_max=float(defaults.get("rsi_max", 62.0)),
        volume_ratio_min=float(defaults.get("volume_ratio_min", 1.0)),
        stop_loss_pct=defaults.get("stop_loss_pct"),
        take_profit_pct=defaults.get("take_profit_pct"),
        adx_min=defaults.get("adx_min"),
        mfi_min=defaults.get("mfi_min"),
        mfi_max=defaults.get("mfi_max"),
        bb_pct_min=defaults.get("bb_pct_min"),
        bb_pct_max=defaults.get("bb_pct_max"),
        stoch_k_min=defaults.get("stoch_k_min"),
        stoch_k_max=defaults.get("stoch_k_max"),
        trade_suppression_threshold=defaults.get("trade_suppression_threshold"),
        signal_interval="1d",
        signal_range="6mo",
    )


def build_strategy_profile(market: str, **overrides: Any) -> StrategyProfile:
    template = default_strategy_profile(
        market,
        strategy_kind=str(overrides.get("strategy_kind") or "trend_following"),
        risk_profile=str(overrides.get("risk_profile") or "balanced"),
        regime_mode=str(overrides.get("regime_mode") or "manual"),
    )
    data = asdict(template)
    for key, value in overrides.items():
        if key in data:
            data[key] = value
    return normalize_strategy_profile(StrategyProfile(**data))


def normalize_strategy_profile(profile: StrategyProfile) -> StrategyProfile:
    market = normalize_strategy_market(profile.market)
    strategy_kind = str(profile.strategy_kind or "trend_following").strip().lower()
    if strategy_kind not in {"trend_following", "mean_reversion", "defensive"}:
        strategy_kind = "trend_following"
    risk_profile = str(profile.risk_profile or "balanced").strip().lower()
    if risk_profile not in {"conservative", "balanced", "aggressive"}:
        risk_profile = "balanced"
    regime_mode = str(profile.regime_mode or "manual").strip().lower()
    if regime_mode not in {"auto", "manual"}:
        regime_mode = "manual"
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
        strategy_kind=strategy_kind,
        risk_profile=risk_profile,
        regime_mode=regime_mode,
        max_positions=max(1, min(20, int(profile.max_positions))),
        max_holding_days=max(1, min(180, int(profile.max_holding_days))),
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        volume_ratio_min=max(0.2, min(5.0, float(profile.volume_ratio_min))),
        stop_loss_pct=stop_loss,
        take_profit_pct=take_profit,
        signal_interval=_normalize_signal_interval(profile.signal_interval),
        signal_range=_normalize_signal_range(profile.signal_range),

        adx_min=profile.adx_min if profile.adx_min is None else max(
            5.0, min(40.0, float(profile.adx_min))),
        mfi_min=profile.mfi_min if profile.mfi_min is None else max(
            0.0, min(100.0, float(profile.mfi_min))),
        mfi_max=profile.mfi_max if profile.mfi_max is None else max(
            0.0, min(100.0, float(profile.mfi_max))),
        bb_pct_min=profile.bb_pct_min if profile.bb_pct_min is None else max(
            0.0, min(1.0, float(profile.bb_pct_min))),
        bb_pct_max=profile.bb_pct_max if profile.bb_pct_max is None else max(
            0.0, min(1.0, float(profile.bb_pct_max))),
        stoch_k_min=profile.stoch_k_min if profile.stoch_k_min is None else max(
            0.0, min(100.0, float(profile.stoch_k_min))),
        stoch_k_max=profile.stoch_k_max if profile.stoch_k_max is None else max(
            0.0, min(100.0, float(profile.stoch_k_max))),
        trade_suppression_threshold=(
            profile.trade_suppression_threshold if profile.trade_suppression_threshold is None
            else max(0.0, min(10.0, float(profile.trade_suppression_threshold)))
        ),
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
    defaults = default_strategy_profile(
        market,
        strategy_kind=str(raw.get("strategy_kind") or "trend_following"),
        risk_profile=str(raw.get("risk_profile") or "balanced"),
        regime_mode=str(raw.get("regime_mode") or "manual"),
    )
    return build_strategy_profile(
        market,
        strategy_kind=raw.get("strategy_kind", defaults.strategy_kind),
        risk_profile=raw.get("risk_profile", defaults.risk_profile),
        regime_mode=raw.get("regime_mode", defaults.regime_mode),
        max_positions=raw.get("max_positions", defaults.max_positions),
        max_holding_days=raw.get("max_holding_days", defaults.max_holding_days),
        rsi_min=raw.get("rsi_min", defaults.rsi_min),
        rsi_max=raw.get("rsi_max", defaults.rsi_max),
        volume_ratio_min=raw.get("volume_ratio_min", defaults.volume_ratio_min),
        stop_loss_pct=raw.get("stop_loss_pct", defaults.stop_loss_pct),
        take_profit_pct=raw.get("take_profit_pct", defaults.take_profit_pct),
        adx_min=raw.get("adx_min", defaults.adx_min),
        mfi_min=raw.get("mfi_min", defaults.mfi_min),
        mfi_max=raw.get("mfi_max", defaults.mfi_max),
        bb_pct_min=raw.get("bb_pct_min", defaults.bb_pct_min),
        bb_pct_max=raw.get("bb_pct_max", defaults.bb_pct_max),
        stoch_k_min=raw.get("stoch_k_min", defaults.stoch_k_min),
        stoch_k_max=raw.get("stoch_k_max", defaults.stoch_k_max),
        trade_suppression_threshold=raw.get("trade_suppression_threshold", defaults.trade_suppression_threshold),
        signal_interval=raw.get("signal_interval", defaults.signal_interval),
        signal_range=raw.get("signal_range", defaults.signal_range),
    )


def should_enter_from_snapshot(snapshot: Mapping[str, Any] | None, profile: StrategyProfile) -> bool:
    if not snapshot:
        return False
    selection = resolve_strategy(profile, snapshot)
    strategy = selection["strategy"]
    resolved_profile = selection["profile"]
    return bool(strategy.should_enter(snapshot, resolved_profile, {"regime": selection["regime"]}))


def should_exit_from_snapshot(
    snapshot: Mapping[str, Any] | None,
    *,
    entry_price: float | None,
    holding_days: int,
    profile: StrategyProfile,
) -> str | None:
    if not snapshot:
        return None
    strategy = get_strategy(profile.strategy_kind)
    return strategy.should_exit(
        snapshot,
        {"entry_price": entry_price, "holding_days": holding_days},
        profile,
        {},
    )


def entry_score_from_snapshot(snapshot: Mapping[str, Any] | None, profile: StrategyProfile | None = None) -> float:
    if not snapshot:
        return 0.0
    profile = profile or default_strategy_profile(str(snapshot.get("market") or "KOSPI"))
    selection = resolve_strategy(profile, snapshot)
    strategy = selection["strategy"]
    resolved_profile = selection["profile"]
    return round(strategy.score(snapshot, resolved_profile, {"regime": selection["regime"]}), 4)


def _normalize_signal_interval(value: str | None) -> str:
    normalized = str(value or "1d").strip().lower()
    return normalized if normalized in {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1d"} else "1d"


def _normalize_signal_range(value: str | None) -> str:
    normalized = str(value or "6mo").strip().lower()
    return normalized if normalized in {"1d", "5d", "1mo", "3mo", "6mo", "1y"} else "6mo"


def _read_snapshot_value(snapshot: Mapping[str, Any], *keys: str) -> Any:
    return read_snapshot_value(snapshot, *keys)
