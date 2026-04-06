"""시장 데이터 수집 모듈

데이터 소스:
- 한국 지수/종목: 네이버 금융 API (m.stock.naver.com)
- 환율 (USD/KRW): 네이버 금융 스크래핑
- 미국 S&P 100, VIX, Brent유가: Yahoo Chart API
- 기타 해외 지수/원자재: stooq.com
"""
from datetime import datetime, timedelta
from typing import Optional, List

import requests
from bs4 import BeautifulSoup
from loguru import logger

from collectors.models import MarketSnapshot, HoldingPrice
from config.portfolio import HOLDINGS

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ──────────────────────────────────────────────
# 네이버 금융 API
# ──────────────────────────────────────────────

def _naver_index(code: str) -> Optional[dict]:
    """네이버 금융 API로 지수(KOSPI/KOSDAQ) 조회."""
    try:
        url = f"https://m.stock.naver.com/api/index/{code}/basic"
        r = requests.get(url, headers=_HEADERS, timeout=8)
        d = r.json()
        close_str = d.get("closePrice", "")
        if not close_str:
            return None
        close = float(close_str.replace(",", ""))
        ratio = d.get("fluctuationsRatio")
        change_pct = float(ratio) if ratio else 0.0
        # compareToPreviousPrice.code: "2"=상승, "5"=하락, "3"=보합
        direction = d.get("compareToPreviousPrice", {}).get("code", "3")
        if direction == "5":
            change_pct = -abs(change_pct)
        return {"current": close, "change_pct": change_pct}
    except Exception as e:
        logger.debug(f"네이버 지수 조회 실패 [{code}]: {e}")
        return None


def _naver_stock(code: str) -> Optional[dict]:
    """네이버 금융 API로 개별 종목 현재가 조회 (6자리 종목코드)."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        r = requests.get(url, headers=_HEADERS, timeout=8)
        d = r.json()
        close_str = d.get("closePrice", "")
        if not close_str:
            return None
        close = float(close_str.replace(",", ""))
        ratio = d.get("fluctuationsRatio")
        change_pct = float(ratio) if ratio else 0.0
        direction = d.get("compareToPreviousPrice", {}).get("code", "3")
        if direction == "5":
            change_pct = -abs(change_pct)
        return {"current": close, "change_pct": change_pct}
    except Exception as e:
        logger.debug(f"네이버 종목 조회 실패 [{code}]: {e}")
        return None


def _naver_usd_krw() -> Optional[float]:
    """네이버 금융 환율 페이지에서 USD/KRW 스크래핑."""
    try:
        url = "https://finance.naver.com/marketindex/"
        r = requests.get(url, headers=_HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        # 첫 번째 li = 미국 USD
        value_span = soup.select_one("#exchangeList .value")
        if value_span:
            return float(value_span.get_text(strip=True).replace(",", ""))
        return None
    except Exception as e:
        logger.debug(f"네이버 환율 조회 실패: {e}")
        return None


# ──────────────────────────────────────────────
# stooq.com (해외 지수 / 원자재)
# ──────────────────────────────────────────────

_STOOQ_SYMBOLS = {
    "nasdaq":  "%5Endx",
    "gold":    "xauusd",
    "btc_usd": "btc.v",
}

# WTI는 단일쿼리 + Prev 필드 방식 사용 (일별 히스토리 미지원)
_STOOQ_SPOT_SYMBOLS = {
    "wti_oil": "cl.f",
}


def _stooq_fetch(symbol: str) -> Optional[dict]:
    """stooq.com 일별 히스토리 API로 최근 2일치 종가 조회."""
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        r = requests.get(url, headers=_HEADERS, timeout=8)
        lines = [l for l in r.text.strip().splitlines()
                 if l and not l.startswith("Date")]
        if not lines:
            return None
        cols = lines[-1].split(",")
        # Date,Open,High,Low,Close,Volume
        if len(cols) < 5 or cols[0] == "N/D":
            return None
        current = float(cols[4])
        prev = float(lines[-2].split(",")[4]) if len(lines) >= 2 else current
        change_pct = (current - prev) / prev * 100 if prev else 0.0
        return {"current": current, "change_pct": change_pct}
    except Exception as e:
        logger.debug(f"stooq 조회 실패 [{symbol}]: {e}")
        return None


def _stooq_spot_fetch(symbol: str) -> Optional[dict]:
    """stooq.com 단일쿼리 + 전일종가(Prev) 방식 (선물 등 일별히스토리 미지원 심볼용)."""
    try:
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcvp&h&e=csv"
        r = requests.get(url, headers=_HEADERS, timeout=8)
        lines = [l for l in r.text.strip().splitlines()
                 if not l.startswith("Symbol")]
        if not lines:
            return None
        cols = lines[-1].split(",")
        # Symbol,Date,Time,Open,High,Low,Close,Volume,Prev
        if len(cols) < 9 or cols[1] == "N/D":
            return None
        current = float(cols[6])
        prev = float(cols[8]) if cols[8] else current
        change_pct = (current - prev) / prev * 100 if prev else 0.0
        return {"current": current, "change_pct": change_pct}
    except Exception as e:
        logger.debug(f"stooq spot 조회 실패 [{symbol}]: {e}")
        return None


# ──────────────────────────────────────────────
# Yahoo Chart (VIX, Brent 등 stooq 미지원)
# ──────────────────────────────────────────────

def _yahoo_chart_fetch(symbol: str) -> Optional[dict]:
    """Yahoo Chart API로 최근 5영업일 종가 조회."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        response = requests.get(
            url,
            params={"range": "5d", "interval": "1d"},
            headers=_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload["chart"]["result"][0]
        closes = [float(value) for value in result["indicators"]
                  ["quote"][0]["close"] if value is not None]
        if not closes:
            return None
        current = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else current
        change_pct = (current - prev) / prev * 100 if prev else 0.0
        return {"current": current, "change_pct": change_pct}
    except Exception as e:
        logger.debug(f"Yahoo Chart 조회 실패 [{symbol}]: {e}")
        return None


# ──────────────────────────────────────────────
# 공개 함수
# ──────────────────────────────────────────────

def collect_market() -> MarketSnapshot:
    """주요 지수, 환율, 원자재 데이터 수집."""
    snap = MarketSnapshot(timestamp=datetime.now())

    # 한국 지수 — 네이버 금융
    kospi = _naver_index("KOSPI")
    if kospi:
        snap.kospi = kospi["current"]
        snap.kospi_change_pct = kospi["change_pct"]

    kosdaq = _naver_index("KOSDAQ")
    if kosdaq:
        snap.kosdaq = kosdaq["current"]
        snap.kosdaq_change_pct = kosdaq["change_pct"]

    # 환율 — 네이버 금융
    snap.usd_krw = _naver_usd_krw()

    # 해외 지수 / 원자재 — stooq.com (일별 히스토리)
    for field, symbol in _STOOQ_SYMBOLS.items():
        data = _stooq_fetch(symbol)
        if data is None:
            continue
        if field == "nasdaq":
            snap.nasdaq = data["current"]
            snap.nasdaq_change_pct = data["change_pct"]
        elif field == "gold":
            snap.gold = data["current"]
        elif field == "btc_usd":
            snap.btc_usd = data["current"]

    sp100 = _yahoo_chart_fetch("^OEX")
    if sp100:
        snap.sp100 = sp100["current"]
        snap.sp100_change_pct = sp100["change_pct"]

    # WTI — stooq 단일쿼리+Prev 방식
    for field, symbol in _STOOQ_SPOT_SYMBOLS.items():
        data = _stooq_spot_fetch(symbol)
        if data and field == "wti_oil":
            snap.wti_oil = data["current"]

    # Brent 유가, VIX — Yahoo Chart API
    for field, ticker in [("brent_oil", "BZ=F"), ("vix", "^VIX")]:
        data = _yahoo_chart_fetch(ticker)
        if data:
            if field == "brent_oil":
                snap.brent_oil = data["current"]
            elif field == "vix":
                snap.vix = data["current"]

    logger.info(
        f"시장 데이터 수집 완료: KOSPI={snap.kospi}, KOSDAQ={snap.kosdaq}, "
        f"S&P100={snap.sp100}, USD/KRW={snap.usd_krw}"
    )
    return snap


def collect_holdings() -> List[HoldingPrice]:
    """보유종목 현재가 및 수익률 계산 (네이버 금융)."""
    results: List[HoldingPrice] = []

    for h in HOLDINGS:
        data = None
        if h.ticker_kr:
            code = h.ticker_kr.split(".")[0]
            data = _naver_stock(code)

        if data is None:
            logger.warning(f"종목 조회 실패: {h.name}")
            continue

        current = data["current"]
        change_pct = data["change_pct"]
        unrealized = (current - h.avg_price) / h.avg_price * 100
        prev_close = current / \
            (1 + change_pct / 100) if change_pct != -100 else current

        results.append(HoldingPrice(
            name=h.name,
            ticker=h.ticker_kr or h.ticker_us,
            current_price=current,
            prev_close=prev_close,
            change_pct=change_pct,
            avg_buy_price=h.avg_price,
            unrealized_return_pct=unrealized,
        ))
        logger.info(f"종목 수집: {h.name} → {current:,.0f}원 ({change_pct:+.2f}%)")

    return results
