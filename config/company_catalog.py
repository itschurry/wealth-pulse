"""추천 및 뉴스 매핑에 사용하는 공통 종목 카탈로그."""
from dataclasses import dataclass

from config.portfolio import HOLDINGS


@dataclass(frozen=True)
class CompanyCatalogEntry:
    name: str
    code: str
    market: str
    sector: str
    aliases: tuple[str, ...]


_BASE_ENTRIES = [
    CompanyCatalogEntry("삼성전자", "005930", "KOSPI", "반도체", ("삼성전자", "삼성 전자", "20만전자")),
    CompanyCatalogEntry("SK하이닉스", "000660", "KOSPI", "반도체", ("sk하이닉스", "sk 하이닉스", "하이닉스")),
    CompanyCatalogEntry("현대차", "005380", "KOSPI", "자동차", ("현대차", "현대 자동차", "현대차그룹")),
    CompanyCatalogEntry("기아", "000270", "KOSPI", "자동차", ("기아", "기아차")),
    CompanyCatalogEntry("현대모비스", "012330", "KOSPI", "자동차부품", ("현대모비스", "현대 모비스")),
    CompanyCatalogEntry("LG에너지솔루션", "373220", "KOSPI", "2차전지", ("lg에너지솔루션", "lg 에너지솔루션")),
    CompanyCatalogEntry("LG화학", "051910", "KOSPI", "화학", ("lg화학", "lg 화학")),
    CompanyCatalogEntry("NAVER", "035420", "KOSPI", "플랫폼", ("naver", "네이버")),
    CompanyCatalogEntry("카카오", "035720", "KOSPI", "플랫폼", ("카카오",)),
    CompanyCatalogEntry("한미반도체", "042700", "KOSPI", "반도체", ("한미반도체", "한미 반도체")),
    CompanyCatalogEntry("한화에어로스페이스", "012450", "KOSPI", "방산", ("한화에어로스페이스", "한화 에어로스페이스")),
    CompanyCatalogEntry("대한항공", "003490", "KOSPI", "항공", ("대한항공", "대한 항공")),
    CompanyCatalogEntry("아시아나항공", "020560", "KOSPI", "항공", ("아시아나항공", "아시아나 항공")),
    CompanyCatalogEntry("KB금융", "105560", "KOSPI", "금융", ("kb금융", "kb 금융", "국민은행")),
    CompanyCatalogEntry("신한지주", "055550", "KOSPI", "금융", ("신한지주", "신한금융", "신한 금융")),
    CompanyCatalogEntry("셀트리온", "068270", "KOSPI", "바이오", ("셀트리온",)),
    CompanyCatalogEntry("에코프로", "086520", "KOSDAQ", "2차전지", ("에코프로",)),
    CompanyCatalogEntry("에코프로비엠", "247540", "KOSDAQ", "2차전지", ("에코프로비엠", "에코프로 비엠")),
    CompanyCatalogEntry("알테오젠", "196170", "KOSDAQ", "바이오", ("알테오젠",)),
    CompanyCatalogEntry("미래에셋증권", "006800", "KOSPI", "금융", ("미래에셋증권", "미래에셋 증권")),
    CompanyCatalogEntry("한국전력", "015760", "KOSPI", "유틸리티", ("한전", "한국전력")),
    CompanyCatalogEntry("삼성바이오로직스", "207940", "KOSPI", "바이오", ("삼성바이오로직스", "삼성 바이오로직스")),
    CompanyCatalogEntry("LG전자", "066570", "KOSPI", "가전", ("lg전자", "lg 전자")),
    CompanyCatalogEntry("NVIDIA", "NVDA", "NASDAQ", "반도체", ("nvidia", "nvda", "엔비디아")),
    CompanyCatalogEntry("Tesla", "TSLA", "NASDAQ", "자동차", ("tesla", "tsla", "테슬라")),
]

_ALLOWED_MARKETS = {"KOSPI", "NASDAQ"}


def get_company_catalog() -> list[CompanyCatalogEntry]:
    """프론트/포트폴리오와 겹치는 종목을 합쳐서 반환한다."""
    seen_codes = {entry.code for entry in _BASE_ENTRIES if entry.code}
    merged = list(_BASE_ENTRIES)

    for holding in HOLDINGS:
        code = (holding.ticker_kr or holding.ticker_us or "").split(".")[0]
        if not code or code in seen_codes:
            continue
        merged.append(
            CompanyCatalogEntry(
                name=holding.name,
                code=code,
                market="KOSPI" if holding.ticker_kr else "NASDAQ",
                sector=holding.sector,
                aliases=(holding.name.lower(), holding.name),
            )
        )
        seen_codes.add(code)

    return [entry for entry in merged if entry.market in _ALLOWED_MARKETS]
