"""보유 종목 정보"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Holding:
    name: str
    ticker_kr: Optional[str]
    ticker_us: Optional[str]
    avg_price: float
    weight_pct: float
    sector: str


HOLDINGS = [
    Holding(
        name="TIGER 반도체TOP10",
        ticker_kr="396500.KS",
        ticker_us=None,
        avg_price=31697,
        weight_pct=51.06,
        sector="반도체",
    ),
    Holding(
        name="SK하이닉스",
        ticker_kr="000660.KS",
        ticker_us=None,
        avg_price=873000,
        weight_pct=20.27,
        sector="반도체",
    ),
    Holding(
        name="삼성전자",
        ticker_kr="005930.KS",
        ticker_us=None,
        avg_price=182450,
        weight_pct=11.01,
        sector="반도체",
    ),
    Holding(
        name="현대차",
        ticker_kr="005380.KS",
        ticker_us=None,
        avg_price=535000,
        weight_pct=4.97,
        sector="자동차",
    ),
    Holding(
        name="미래에셋벤처투자",
        ticker_kr="100790.KQ",
        ticker_us=None,
        avg_price=22134,
        weight_pct=4.73,
        sector="금융/벤처캐피탈",
    ),
    Holding(
        name="KoACT 코스닥액티브",
        ticker_kr="",  # ⚠️ 459580은 KODEX CD금리액티브(오류). 네이버 금융에서 정확한 코드 확인 후 입력하세요.
        ticker_us=None,
        avg_price=13410,
        weight_pct=4.11,
        sector="코스닥 지수",
    ),
    Holding(
        name="현대모비스",
        ticker_kr="012330.KS",
        ticker_us=None,
        avg_price=415000,
        weight_pct=3.85,
        sector="자동차부품",
    ),
]

INVESTMENT_PROFILE = {
    "style": "장기 투자 (3개월 이상)",
    "risk_preference": "리스크가 크지 않은 종목 선호",
    "markets": ["한국 KOSPI/KOSDAQ", "미국 NYSE/NASDAQ"],
    "sectors": "전 섹터 (반도체/AI, 2차전지/에너지, 바이오/헬스케어 등)",
    "total_return_pct": 6.18,
    "start_date": "2026-03",
    "notes": "반도체 비중 82%로 편중 상태. 분산 필요성 인지."
}
