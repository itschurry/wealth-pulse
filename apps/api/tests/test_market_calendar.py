from datetime import datetime
from pathlib import Path
import sys

from zoneinfo import ZoneInfo

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from broker.execution_engine import _domestic_after_hours_order_division
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


def test_after_hours_order_division_matches_kis_session():
    assert _domestic_after_hours_order_division("KOSPI", _kst(15, 39)) is None
    assert _domestic_after_hours_order_division("KOSPI", _kst(15, 40)) == "06"
    assert _domestic_after_hours_order_division("KOSPI", _kst(15, 59)) == "06"
    assert _domestic_after_hours_order_division("KOSPI", _kst(16, 0)) == "07"
    assert _domestic_after_hours_order_division("KOSPI", _kst(17, 59)) == "07"
    assert _domestic_after_hours_order_division("KOSPI", _kst(18, 0)) is None
