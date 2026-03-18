"""수집 데이터 모델"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""
    body: str = ""
    lang: str = "ko"
    relevance_score: float = 0.0


@dataclass
class MarketSnapshot:
    timestamp: datetime
    kospi: Optional[float] = None
    kospi_change_pct: Optional[float] = None
    kosdaq: Optional[float] = None
    kosdaq_change_pct: Optional[float] = None
    sp100: Optional[float] = None
    sp100_change_pct: Optional[float] = None
    nasdaq: Optional[float] = None
    nasdaq_change_pct: Optional[float] = None
    usd_krw: Optional[float] = None
    brent_oil: Optional[float] = None
    wti_oil: Optional[float] = None
    gold: Optional[float] = None
    btc_usd: Optional[float] = None
    vix: Optional[float] = None


@dataclass
class MacroIndicator:
    key: str
    label: str
    value: Optional[float] = None
    previous: Optional[float] = None
    unit: str = ""
    as_of: str = ""
    source: str = "FRED"
    series_id: str = ""
    display_value: str = ""
    summary: str = ""


@dataclass
class MarketContext:
    regime: str = "neutral"
    risk_level: str = "중간"
    inflation_signal: str = "중립"
    labor_signal: str = "중립"
    policy_signal: str = "중립"
    yield_curve_signal: str = "중립"
    dollar_signal: str = "중립"
    summary: str = "거시 컨텍스트 데이터 없음"
    risks: list = field(default_factory=list)
    supports: list = field(default_factory=list)


@dataclass
class HoldingPrice:
    name: str
    ticker: str
    current_price: float
    prev_close: float
    change_pct: float
    avg_buy_price: float
    unrealized_return_pct: float


@dataclass
class DailyData:
    """하루치 수집 데이터 전체"""
    collected_at: datetime
    market: MarketSnapshot
    holdings: list = field(default_factory=list)
    news: list = field(default_factory=list)
    macro: list = field(default_factory=list)
    market_context: Optional[MarketContext] = None
