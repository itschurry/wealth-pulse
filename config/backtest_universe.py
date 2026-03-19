"""백테스트 전용 종목 우주."""

from __future__ import annotations

import html
import re
import time
from typing import TypedDict

import requests


class BacktestUniverseEntry(TypedDict):
    name: str
    code: str
    market: str


_KOSPI_CACHE_TTL = 60 * 60 * 12
_kospi_cache: dict[str, object] = {"ts": 0.0, "data": []}

# KRX 전체 상장목록 다운로드는 안정적이지만, KOSPI50 구성종목 자체는 수시로 바뀌고
# 공개 엔드포인트가 일관되지 않아 카테고리 기준으로 유지한다.
_KOSPI50_CATEGORY: tuple[tuple[str, str], ...] = (
    ("LG전자", "066570"),
    ("삼성전기", "009150"),
    ("한화에어로스페이스", "012450"),
    ("HMM", "011200"),
    ("삼성중공업", "010140"),
    ("삼성화재", "000810"),
    ("하나금융지주", "086790"),
    ("현대글로비스", "086280"),
    ("고려아연", "010130"),
    ("현대모비스", "012330"),
    ("현대차", "005380"),
    ("SK이노베이션", "096770"),
    ("KB금융", "105560"),
    ("LG화학", "051910"),
    ("삼성생명", "032830"),
    ("SK하이닉스", "000660"),
    ("삼성전자", "005930"),
    ("한화오션", "042660"),
    ("삼성SDI", "006400"),
    ("신한지주", "055550"),
    ("기아", "000270"),
    ("SK텔레콤", "017670"),
    ("삼성물산", "028260"),
    ("KT&G", "033780"),
    ("NAVER", "035420"),
    ("KT", "030200"),
    ("LG", "003550"),
    ("SK", "034730"),
    ("한국전력", "015760"),
    ("POSCO홀딩스", "005490"),
    ("HD한국조선해양", "009540"),
    ("기업은행", "024110"),
    ("두산에너빌리티", "034020"),
    ("한미반도체", "042700"),
    ("메리츠금융지주", "138040"),
    ("현대로템", "064350"),
    ("삼성SDS", "018260"),
    ("포스코퓨처엠", "003670"),
    ("카카오", "035720"),
    ("셀트리온", "068270"),
    ("삼성바이오로직스", "207940"),
    ("HD현대일렉트릭", "267260"),
    ("우리금융지주", "316140"),
    ("하이브", "352820"),
    ("카카오뱅크", "323410"),
    ("크래프톤", "259960"),
    ("HD현대중공업", "329180"),
    ("SK스퀘어", "402340"),
    ("LG에너지솔루션", "373220"),
    ("포스코인터내셔널", "047050"),
)

_SP50_UNIVERSE: tuple[tuple[str, str, str], ...] = (
    ("NVIDIA", "NVDA", "NASDAQ"),
    ("Apple", "AAPL", "NASDAQ"),
    ("Microsoft", "MSFT", "NASDAQ"),
    ("Amazon", "AMZN", "NASDAQ"),
    ("Alphabet Class A", "GOOGL", "NASDAQ"),
    ("Broadcom", "AVGO", "NASDAQ"),
    ("Alphabet Class C", "GOOG", "NASDAQ"),
    ("Meta Platforms", "META", "NASDAQ"),
    ("Tesla", "TSLA", "NASDAQ"),
    ("Berkshire Hathaway", "BRK.B", "NYSE"),
    ("Eli Lilly", "LLY", "NYSE"),
    ("JPMorgan Chase", "JPM", "NYSE"),
    ("Exxon Mobil", "XOM", "NYSE"),
    ("Johnson & Johnson", "JNJ", "NYSE"),
    ("Walmart", "WMT", "NYSE"),
    ("Visa", "V", "NYSE"),
    ("Costco", "COST", "NASDAQ"),
    ("Mastercard", "MA", "NYSE"),
    ("Netflix", "NFLX", "NASDAQ"),
    ("AbbVie", "ABBV", "NYSE"),
    ("Chevron", "CVX", "NYSE"),
    ("Procter & Gamble", "PG", "NYSE"),
    ("Palantir", "PLTR", "NASDAQ"),
    ("Home Depot", "HD", "NYSE"),
    ("Caterpillar", "CAT", "NYSE"),
    ("GE Aerospace", "GE", "NYSE"),
    ("Advanced Micro Devices", "AMD", "NASDAQ"),
    ("Bank of America", "BAC", "NYSE"),
    ("Cisco", "CSCO", "NASDAQ"),
    ("Coca-Cola", "KO", "NYSE"),
    ("Merck", "MRK", "NYSE"),
    ("Philip Morris", "PM", "NYSE"),
    ("Oracle", "ORCL", "NYSE"),
    ("UnitedHealth", "UNH", "NYSE"),
    ("Goldman Sachs", "GS", "NYSE"),
    ("Wells Fargo", "WFC", "NYSE"),
    ("McDonald's", "MCD", "NYSE"),
    ("IBM", "IBM", "NYSE"),
    ("Linde", "LIN", "NASDAQ"),
    ("PepsiCo", "PEP", "NASDAQ"),
    ("Verizon", "VZ", "NYSE"),
    ("AT&T", "T", "NYSE"),
    ("Salesforce", "CRM", "NYSE"),
    ("Abbott Laboratories", "ABT", "NYSE"),
    ("Walt Disney", "DIS", "NYSE"),
    ("Texas Instruments", "TXN", "NASDAQ"),
    ("Intuitive Surgical", "ISRG", "NASDAQ"),
    ("Accenture", "ACN", "NYSE"),
    ("Intuit", "INTU", "NASDAQ"),
    ("ServiceNow", "NOW", "NYSE"),
)


def _to_entries(pairs: tuple[tuple[str, str], ...]) -> list[BacktestUniverseEntry]:
    return [{"name": name, "code": code, "market": "KOSPI"} for name, code in pairs]


def _download_krx_kospi_listing_map() -> dict[str, BacktestUniverseEntry]:
    response = requests.get(
        "https://kind.krx.co.kr/corpgeneral/corpList.do",
        params={"method": "download", "marketType": "stockMkt"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    text = response.content.decode("euc-kr", "replace")
    rows = re.findall(r"<tr>(.*?)</tr>", text, re.S)
    listing_map: dict[str, BacktestUniverseEntry] = {}
    for row in rows:
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        ]
        if len(cells) < 2:
            continue
        code = cells[1].zfill(6)
        if not code.isdigit():
            continue
        listing_map[code] = {
            "name": cells[0],
            "code": code,
            "market": "KOSPI",
        }
    return listing_map


def get_sp50_universe() -> list[BacktestUniverseEntry]:
    deduped: dict[str, BacktestUniverseEntry] = {}
    for name, code, market in _SP50_UNIVERSE:
        deduped[code] = {"name": name, "code": code, "market": market}
    return list(deduped.values())


def get_kospi50_universe() -> list[BacktestUniverseEntry]:
    now = time.time()
    cached_data = _kospi_cache.get("data")
    if cached_data and now - float(_kospi_cache.get("ts") or 0.0) < _KOSPI_CACHE_TTL:
        return list(cached_data)  # type: ignore[arg-type]

    try:
        listing_map = _download_krx_kospi_listing_map()
        universe = [listing_map.get(code) or {"name": name, "code": code, "market": "KOSPI"} for name, code in _KOSPI50_CATEGORY]
        if universe:
            _kospi_cache["ts"] = now
            _kospi_cache["data"] = universe
            return universe
    except Exception:
        pass

    fallback = _to_entries(_KOSPI50_CATEGORY)
    _kospi_cache["ts"] = now
    _kospi_cache["data"] = fallback
    return fallback


def get_kospi_universe() -> list[BacktestUniverseEntry]:
    return get_kospi50_universe()


def get_sp100_nasdaq_universe() -> list[BacktestUniverseEntry]:
    return get_sp50_universe()
