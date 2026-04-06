"""시장 정규장 및 휴장일 판정 유틸."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays

KST_ZONE = ZoneInfo("Asia/Seoul")
ET_ZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketSessionWindow:
    market: str
    time_zone: ZoneInfo
    open_minutes: int
    close_minutes: int


SESSION_WINDOWS: dict[str, MarketSessionWindow] = {
    "KR": MarketSessionWindow(
        market="KR",
        time_zone=KST_ZONE,
        open_minutes=9 * 60,
        close_minutes=15 * 60 + 30,
    ),
    "US": MarketSessionWindow(
        market="US",
        time_zone=ET_ZONE,
        open_minutes=9 * 60 + 30,
        close_minutes=16 * 60,
    ),
}


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized in {"KR", "KOR", "KOREA", "KOSPI", "KRX"}:
        return "KR"
    if normalized in {"US", "USA", "NASDAQ", "NYSE"}:
        return "US"
    raise ValueError(f"unsupported market: {market}")


@lru_cache(maxsize=16)
def _country_holidays(country: str, years: tuple[int, ...]):
    return holidays.country_holidays(country, years=years)


@lru_cache(maxsize=16)
def _us_market_holidays(years: tuple[int, ...]):
    if hasattr(holidays, "financial_holidays"):
        try:
            return holidays.financial_holidays("NYSE", years=years)
        except Exception:
            pass
    return holidays.country_holidays("US", years=years)


def _holiday_calendar(market: str, years: tuple[int, ...]):
    normalized = _normalize_market(market)
    if normalized == "KR":
        return _country_holidays("KR", years)
    return _us_market_holidays(years)


def get_market_local_dt(market: str, now: datetime | None = None) -> datetime:
    normalized = _normalize_market(market)
    source = now or datetime.now(tz=KST_ZONE)
    return source.astimezone(SESSION_WINDOWS[normalized].time_zone)


def is_market_trading_day(market: str, now: datetime | None = None) -> bool:
    local_dt = get_market_local_dt(market, now)
    if local_dt.weekday() >= 5:
        return False

    years = tuple(sorted({local_dt.year - 1, local_dt.year, local_dt.year + 1}))
    calendar = _holiday_calendar(market, years)
    return local_dt.date() not in calendar


def is_market_open(market: str, now: datetime | None = None) -> bool:
    """현재 시각이 정규장(개장~폐장) 내인지 판정."""
    normalized = _normalize_market(market)
    if not is_market_trading_day(normalized, now):
        return False
    local_dt = get_market_local_dt(normalized, now)
    minutes = local_dt.hour * 60 + local_dt.minute
    window = SESSION_WINDOWS[normalized]
    return window.open_minutes <= minutes < window.close_minutes


def is_market_half_hour_slot(market: str, now: datetime | None = None) -> bool:
    normalized = _normalize_market(market)
    if not is_market_trading_day(normalized, now):
        return False

    local_dt = get_market_local_dt(normalized, now)
    minutes = local_dt.hour * 60 + local_dt.minute
    window = SESSION_WINDOWS[normalized]

    return (
        window.open_minutes <= minutes <= window.close_minutes
        and (minutes - window.open_minutes) % 30 == 0
    )
