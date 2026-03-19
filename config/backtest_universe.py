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

_SP100_NASDAQ: tuple[tuple[str, str], ...] = (
    ("Apple", "AAPL"),
    ("Microsoft", "MSFT"),
    ("Amazon", "AMZN"),
    ("Alphabet", "GOOGL"),
    ("Meta Platforms", "META"),
    ("NVIDIA", "NVDA"),
    ("Broadcom", "AVGO"),
    ("Adobe", "ADBE"),
    ("Advanced Micro Devices", "AMD"),
    ("Applied Materials", "AMAT"),
    ("Analog Devices", "ADI"),
    ("Amgen", "AMGN"),
    ("Automatic Data Processing", "ADP"),
    ("Booking Holdings", "BKNG"),
    ("Cisco", "CSCO"),
    ("Comcast", "CMCSA"),
    ("Costco", "COST"),
    ("Gilead Sciences", "GILD"),
    ("Intel", "INTC"),
    ("Intuit", "INTU"),
    ("Intuitive Surgical", "ISRG"),
    ("Micron", "MU"),
    ("Mondelez", "MDLZ"),
    ("Netflix", "NFLX"),
    ("PepsiCo", "PEP"),
    ("QUALCOMM", "QCOM"),
    ("Starbucks", "SBUX"),
    ("T-Mobile US", "TMUS"),
    ("Texas Instruments", "TXN"),
)


def get_sp100_nasdaq_universe() -> list[BacktestUniverseEntry]:
    deduped: dict[str, BacktestUniverseEntry] = {}
    for name, code in _SP100_NASDAQ:
        deduped[code] = {"name": name, "code": code, "market": "NASDAQ"}
    return list(deduped.values())


def get_kospi_universe() -> list[BacktestUniverseEntry]:
    now = time.time()
    cached_data = _kospi_cache.get("data")
    if cached_data and now - float(_kospi_cache.get("ts") or 0.0) < _KOSPI_CACHE_TTL:
        return list(cached_data)  # type: ignore[arg-type]

    try:
        response = requests.get(
            "https://kind.krx.co.kr/corpgeneral/corpList.do",
            params={"method": "download", "marketType": "stockMkt"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
        text = response.content.decode("euc-kr", "replace")
        rows = re.findall(r"<tr>(.*?)</tr>", text, re.S)
        universe: list[BacktestUniverseEntry] = []
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
            universe.append({
                "name": cells[0],
                "code": code,
                "market": "KOSPI",
            })
        if universe:
            _kospi_cache["ts"] = now
            _kospi_cache["data"] = universe
            return universe
    except Exception:
        pass

    fallback = [
        {"name": "삼성전자", "code": "005930", "market": "KOSPI"},
        {"name": "SK하이닉스", "code": "000660", "market": "KOSPI"},
        {"name": "삼성바이오로직스", "code": "207940", "market": "KOSPI"},
        {"name": "삼성SDI", "code": "006400", "market": "KOSPI"},
        {"name": "LG에너지솔루션", "code": "373220", "market": "KOSPI"},
        {"name": "현대차", "code": "005380", "market": "KOSPI"},
        {"name": "기아", "code": "000270", "market": "KOSPI"},
        {"name": "현대모비스", "code": "012330", "market": "KOSPI"},
        {"name": "NAVER", "code": "035420", "market": "KOSPI"},
        {"name": "카카오", "code": "035720", "market": "KOSPI"},
        {"name": "카카오뱅크", "code": "323410", "market": "KOSPI"},
        {"name": "LG화학", "code": "051910", "market": "KOSPI"},
        {"name": "LG전자", "code": "066570", "market": "KOSPI"},
        {"name": "LG이노텍", "code": "011070", "market": "KOSPI"},
        {"name": "SK이노베이션", "code": "096770", "market": "KOSPI"},
        {"name": "POSCO홀딩스", "code": "005490", "market": "KOSPI"},
        {"name": "포스코퓨처엠", "code": "003670", "market": "KOSPI"},
        {"name": "셀트리온", "code": "068270", "market": "KOSPI"},
        {"name": "유한양행", "code": "000100", "market": "KOSPI"},
        {"name": "녹십자", "code": "006280", "market": "KOSPI"},
        {"name": "한미반도체", "code": "042700", "market": "KOSPI"},
        {"name": "한화에어로스페이스", "code": "012450", "market": "KOSPI"},
        {"name": "대한항공", "code": "003490", "market": "KOSPI"},
        {"name": "아시아나항공", "code": "020560", "market": "KOSPI"},
        {"name": "KT", "code": "030200", "market": "KOSPI"},
        {"name": "SK텔레콤", "code": "017670", "market": "KOSPI"},
        {"name": "한국전력", "code": "015760", "market": "KOSPI"},
        {"name": "신한지주", "code": "055550", "market": "KOSPI"},
        {"name": "KB금융", "code": "105560", "market": "KOSPI"},
        {"name": "우리금융지주", "code": "316140", "market": "KOSPI"},
        {"name": "하나금융지주", "code": "086790", "market": "KOSPI"},
        {"name": "메리츠금융지주", "code": "138040", "market": "KOSPI"},
        {"name": "미래에셋증권", "code": "006800", "market": "KOSPI"},
        {"name": "넷마블", "code": "251270", "market": "KOSPI"},
        {"name": "크래프톤", "code": "259960", "market": "KOSPI"},
        {"name": "엔씨소프트", "code": "036570", "market": "KOSPI"},
        {"name": "두산에너빌리티", "code": "034020", "market": "KOSPI"},
    ]
    _kospi_cache["ts"] = now
    _kospi_cache["data"] = fallback
    return fallback
