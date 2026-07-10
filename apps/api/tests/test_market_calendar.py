from datetime import datetime

from zoneinfo import ZoneInfo

from config.market_calendar import is_market_open


KST = ZoneInfo("Asia/Seoul")


def _kst(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 10, hour, minute, tzinfo=KST)


def test_regular_market_open_excludes_after_hours_by_default():
    assert not is_market_open("KOSPI", _kst(8, 59))
    assert is_market_open("KOSPI", _kst(9, 0))
    assert is_market_open("KOSPI", _kst(15, 29))
    assert not is_market_open("KOSPI", _kst(15, 30))
    assert not is_market_open("KOSPI", _kst(15, 40))


def test_auto_trade_session_excludes_pre_market_and_includes_after_hours():
    assert not is_market_open("KOSPI", _kst(8, 59), include_after_hours=True)
    assert is_market_open("KOSPI", _kst(9, 0), include_after_hours=True)
    assert not is_market_open("KOSPI", _kst(15, 39), include_after_hours=True)
    assert is_market_open("KOSPI", _kst(15, 40), include_after_hours=True)
    assert is_market_open("KOSPI", _kst(17, 59), include_after_hours=True)
    assert not is_market_open("KOSPI", _kst(18, 0), include_after_hours=True)
