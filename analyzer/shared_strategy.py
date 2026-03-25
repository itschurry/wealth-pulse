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

    adx_min: float | None = None
    mfi_min: float | None = None
    mfi_max: float | None = None
    bb_pct_min: float | None = None
    bb_pct_max: float | None = None
    stoch_k_min: float | None = None
    stoch_k_max: float | None = None


_DEFAULT_PROFILES: dict[str, StrategyProfile] = {
    "KOSPI": StrategyProfile(
        market="KOSPI",
        max_positions=5,
        max_holding_days=25,
        rsi_min=38.0,
        rsi_max=72.0,
        volume_ratio_min=0.8,
        adx_min=10.0,
        mfi_min=20.0,
        mfi_max=80.0,
        bb_pct_min=0.05,
        bb_pct_max=0.95,
        stoch_k_min=10.0,
        stoch_k_max=90.0,
        stop_loss_pct=7.0,
        take_profit_pct=15.0,
        signal_interval="1d",
        signal_range="6mo",
    ),
    "NASDAQ": StrategyProfile(
        market="NASDAQ",
        max_positions=5,
        max_holding_days=40,
        rsi_min=38.0,
        rsi_max=75.0,
        volume_ratio_min=1.0,
        adx_min=10.0,
        mfi_min=20.0,
        mfi_max=80.0,
        bb_pct_min=0.05,
        bb_pct_max=0.95,
        stoch_k_min=10.0,
        stoch_k_max=90.0,
        stop_loss_pct=8.0,
        take_profit_pct=20.0,
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
        max_positions=raw.get(
            "max_positions", default_strategy_profile(market).max_positions),
        max_holding_days=raw.get(
            "max_holding_days", default_strategy_profile(market).max_holding_days),
        rsi_min=raw.get("rsi_min", default_strategy_profile(market).rsi_min),
        rsi_max=raw.get("rsi_max", default_strategy_profile(market).rsi_max),
        volume_ratio_min=raw.get(
            "volume_ratio_min", default_strategy_profile(market).volume_ratio_min),
        stop_loss_pct=raw.get(
            "stop_loss_pct", default_strategy_profile(market).stop_loss_pct),
        take_profit_pct=raw.get(
            "take_profit_pct", default_strategy_profile(market).take_profit_pct),
        adx_min=raw.get("adx_min", default_strategy_profile(market).adx_min),
        mfi_min=raw.get("mfi_min", default_strategy_profile(market).mfi_min),
        mfi_max=raw.get("mfi_max", default_strategy_profile(market).mfi_max),
        bb_pct_min=raw.get(
            "bb_pct_min", default_strategy_profile(market).bb_pct_min),
        bb_pct_max=raw.get(
            "bb_pct_max", default_strategy_profile(market).bb_pct_max),
        stoch_k_min=raw.get(
            "stoch_k_min", default_strategy_profile(market).stoch_k_min),
        stoch_k_max=raw.get(
            "stoch_k_max", default_strategy_profile(market).stoch_k_max),
        signal_interval=raw.get(
            "signal_interval", default_strategy_profile(market).signal_interval),
        signal_range=raw.get(
            "signal_range", default_strategy_profile(market).signal_range),
    )


def should_enter_from_snapshot(snapshot: Mapping[str, Any] | None, profile: StrategyProfile) -> bool:
    """
    진입 조건 판단 (최적화 파라미터 명시적 참조)

    최적화 파라미터 의존성:
    - profile.rsi_min / profile.rsi_max (몬테카를로 최적화 후보)
    - profile.volume_ratio_min (몬테카를로 최적화 후보)

    필수 필터 조건:
    - 가격 > SMA20 > SMA60 (추세 정렬)
    - 거래량 >= 최소 기준 (유동성)
    - RSI 범위 내 (과매도/과매수 회피)
    - MACD 양성 (모멘텀)

    선택 필터(옵션):
    - adx_min, mfi_min/mfi_max, bb_pct_min/bb_pct_max, stoch_k_min/stoch_k_max
    - 값이 설정된 경우에만 필터로 동작
    """
    if not snapshot:
        return False
    close = _read_snapshot_value(
        snapshot, "current_price", "close", "trade_price")
    sma20 = snapshot.get("sma20")
    sma60 = snapshot.get("sma60")
    volume_ratio = snapshot.get("volume_ratio")
    rsi14 = snapshot.get("rsi14")
    macd = snapshot.get("macd")
    macd_signal = snapshot.get("macd_signal")
    macd_hist = snapshot.get("macd_hist")
    # 선택 필터 지표
    adx14 = snapshot.get("adx14")
    mfi14 = snapshot.get("mfi14")
    bb_pct = snapshot.get("bb_pct")
    stoch_k = snapshot.get("stoch_k")

    # profile 기반 선택 필터
    # 신규 지표는 데이터 결측 시 기존 핵심 필터만으로도 진입 가능하게 허용한다.
    adx_ok = profile.adx_min is None or adx14 is None or float(
        adx14) >= float(profile.adx_min)
    mfi_lower_ok = profile.mfi_min is None or mfi14 is None or float(
        mfi14) >= float(profile.mfi_min)
    mfi_upper_ok = profile.mfi_max is None or mfi14 is None or float(
        mfi14) <= float(profile.mfi_max)
    bb_lower_ok = profile.bb_pct_min is None or bb_pct is None or float(
        bb_pct) >= float(profile.bb_pct_min)
    bb_upper_ok = profile.bb_pct_max is None or bb_pct is None or float(
        bb_pct) <= float(profile.bb_pct_max)
    stoch_lower_ok = profile.stoch_k_min is None or stoch_k is None or float(
        stoch_k) >= float(profile.stoch_k_min)
    stoch_upper_ok = profile.stoch_k_max is None or stoch_k is None or float(
        stoch_k) <= float(profile.stoch_k_max)

    return bool(
        close is not None
        and sma20 is not None
        and sma60 is not None
        and volume_ratio is not None
        and rsi14 is not None
        and macd is not None
        and macd_signal is not None
        and macd_hist is not None
        and float(close) > float(sma20) > float(sma60)  # 추세 정렬 (필수 필터)
        and float(volume_ratio) >= profile.volume_ratio_min  # 유동성 (최적화 파라미터)
        # 모멘텀 범위 (최적화 파라미터)
        and profile.rsi_min <= float(rsi14) <= profile.rsi_max
        and (float(macd_hist) > 0 or float(macd) > float(macd_signal))  # MACD 양성 (필수)
        and adx_ok
        and mfi_lower_ok
        and mfi_upper_ok
        and bb_lower_ok
        and bb_upper_ok
        and stoch_lower_ok
        and stoch_upper_ok
    )


def should_exit_from_snapshot(
    snapshot: Mapping[str, Any] | None,
    *,
    entry_price: float | None,
    holding_days: int,
    profile: StrategyProfile,
) -> str | None:
    """
    청산 조건 판단 (최적화 파라미터 명시적 참조)

    최적화 파라미터 의존성:
    - profile.max_holding_days (몬테카를로 최적화 후보) → 보유기간 제한
    - profile.stop_loss_pct (몬테카를로 최적화 후보) → 손절가 설정
    - profile.take_profit_pct (몬테카를로 최적화 후보) → 익절가 설정

    청산 우선순위 (먼저 충족되는 조건):
    1. 보유기간 만료 (profile.max_holding_days)
    2. 손절 (profile.stop_loss_pct)
    3. 익절 (profile.take_profit_pct)
    4. 기술적 약세 신호 (SMA, MACD, RSI)

    주의: 최적화된 파라미터가 None이 아닐 때만 해당 조건 활성화됨.
    """
    if not snapshot:
        return None
    price = _read_snapshot_value(
        snapshot, "trade_price", "current_price", "close")
    close = _read_snapshot_value(
        snapshot, "close", "current_price", "trade_price")
    sma20 = snapshot.get("sma20")
    rsi14 = snapshot.get("rsi14")
    macd = snapshot.get("macd")
    macd_signal = snapshot.get("macd_signal")
    macd_hist = snapshot.get("macd_hist")

    # 1. 보유기간 만료 (최적화 파라미터)
    if holding_days >= profile.max_holding_days:
        return "보유기간 만료"
    # 2. 손절 (최적화 파라미터)
    if (
        profile.stop_loss_pct is not None
        and price is not None
        and entry_price
        and ((float(price) / float(entry_price)) - 1) * 100 <= -profile.stop_loss_pct
    ):
        return "손절"
    # 3. 익절 (최적화 파라미터)
    if (
        profile.take_profit_pct is not None
        and price is not None
        and entry_price
        and ((float(price) / float(entry_price)) - 1) * 100 >= profile.take_profit_pct
    ):
        return "익절"
    # 4. 기술적 약세 신호 (Phase 3-3: 초기 1~2일 잡음 차단)
    # 진입 후 1~2일 내 기술 신호는 무시 (익절과 손절은 항상 유효)
    if holding_days > 2:  # 3일 이상 보유한 경우만 기술 신호 적용
        if close is not None and sma20 is not None and float(close) < float(sma20) * 0.99:
            return "20일선 이탈"
        if (price is not None and entry_price and macd is not None and macd_signal is not None and macd_hist is not None):
            pnl_pct = ((float(price) / float(entry_price)) - 1) * 100
            if float(macd) < float(macd_signal) and float(macd_hist) < 0 and pnl_pct < -2.0:
                return "MACD 약세 전환"
        if rsi14 is not None and float(rsi14) >= 82:
            return "RSI 과열"
    return None


def entry_score_from_snapshot(snapshot: Mapping[str, Any] | None, profile: StrategyProfile | None = None) -> float:
    if not snapshot:
        return 0.0
    close = _read_snapshot_value(
        snapshot, "close", "current_price", "trade_price")
    sma20 = snapshot.get("sma20")
    sma60 = snapshot.get("sma60")
    volume_ratio = snapshot.get("volume_ratio")
    rsi14 = snapshot.get("rsi14")
    macd_hist = snapshot.get("macd_hist")
    if None in {close, sma20, sma60, volume_ratio, rsi14, macd_hist}:
        return 0.0

    trend_score = ((float(close) / float(sma20)) - 1) * 100 + \
        ((float(sma20) / float(sma60)) - 1) * 100
    rsi_score = max(0.0, 70 - abs(57.0 - float(rsi14)))
    base_score = trend_score + \
        float(volume_ratio) * 2.5 + float(macd_hist) * 12 + rsi_score * 0.1

    # Phase 3: 새 지표 점수 추가
    new_indicator_score = 0.0

    adx14 = snapshot.get("adx14")
    if adx14 is not None:
        if float(adx14) >= 25:
            new_indicator_score += 2.0
        elif float(adx14) < 15:
            new_indicator_score -= 2.0

    bb_pct = snapshot.get("bb_pct")
    if bb_pct is not None and float(bb_pct) < 0.2:
        new_indicator_score += 1.5

    obv_trend = snapshot.get("obv_trend")
    if obv_trend == "up":
        new_indicator_score += 1.0
    elif obv_trend == "down":
        new_indicator_score -= 1.5

    stoch_k = snapshot.get("stoch_k")
    stoch_d = snapshot.get("stoch_d")
    if stoch_k is not None and stoch_d is not None:
        if float(stoch_k) < 25 and float(stoch_d) < 25:
            new_indicator_score += 1.0

    # Phase 3-1: MFI 점수 반영 추가
    mfi14 = snapshot.get("mfi14")
    if mfi14 is not None:
        if float(mfi14) < 25:
            new_indicator_score += 1.0  # 과매도
        elif float(mfi14) > 75:
            new_indicator_score -= 1.0  # 과매수

    return round(base_score + new_indicator_score, 4)


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
