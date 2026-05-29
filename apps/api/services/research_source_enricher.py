from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
DEFAULT_NEWS_LIMIT = 5


def _text(value: Any) -> str:
    return str(value or "").strip()


def _market(value: Any) -> str:
    return _text(value).upper()


def _published_at(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _strip_html(value: Any) -> str:
    text = html.unescape(_text(value))
    parts: list[str] = []
    in_tag = False
    for char in text:
        if char == "<":
            in_tag = True
            continue
        if char == ">":
            in_tag = False
            continue
        if not in_tag:
            parts.append(char)
    return " ".join("".join(parts).split())


def _google_news_query(name: str, symbol: str, market: str) -> str:
    if market in {"KOSPI", "KOSDAQ"}:
        return f'"{name or symbol}" 주가 OR 실적 OR 수주 OR 공시 when:3d'
    return f'"{name or symbol}" stock OR earnings OR guidance OR SEC when:3d'


def fetch_google_news_inputs(*, symbol: str, market: str, name: str = "", limit: int = DEFAULT_NEWS_LIMIT, timeout: int = 8) -> list[dict[str, Any]]:
    normalized_market = _market(market)
    query = _google_news_query(_text(name), _text(symbol), normalized_market)
    params = {
        "q": query,
        "hl": "ko",
        "gl": "KR" if normalized_market in {"KOSPI", "KOSDAQ"} else "US",
        "ceid": "KR:ko" if normalized_market in {"KOSPI", "KOSDAQ"} else "US:en",
    }
    url = f"{GOOGLE_NEWS_RSS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 WealthPulse research source collector",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as response:
        body = response.read()

    root = ET.fromstring(body)
    rows: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        title = _strip_html(item.findtext("title"))
        link = _text(item.findtext("link"))
        published = _published_at(item.findtext("pubDate"))
        if not title or not link or not published:
            continue
        source_node = item.find("source")
        publisher = _text(source_node.text if source_node is not None else "")
        rows.append(
            {
                "title": title,
                "source": "google-news-rss",
                "publisher": publisher,
                "url": link,
                "published_at": published,
                "summary": title,
            }
        )
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def build_official_evidence(*, symbol: str, market: str, name: str = "") -> list[dict[str, Any]]:
    normalized_market = _market(market)
    normalized_symbol = _text(symbol).upper()
    company_name = _text(name) or normalized_symbol
    if normalized_market in {"KOSPI", "KOSDAQ"}:
        return [
            {
                "type": "official_disclosure_search",
                "source": "kind",
                "title": f"{company_name} KRX KIND 공시 검색",
                "url": f"https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain&searchCodeType=char&searchCorpName={urllib.parse.quote(company_name)}",
                "summary": "KRX KIND 공식 공시 검색 링크",
            },
            {
                "type": "official_market_data",
                "source": "krx",
                "title": f"{company_name} KRX 종목 정보",
                "url": f"https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?isuCd={urllib.parse.quote(normalized_symbol)}",
                "summary": "KRX 공식 종목 데이터 링크",
            },
        ]
    return [
        {
            "type": "official_company_quote",
            "source": "nasdaq",
            "title": f"{company_name} Nasdaq quote",
            "url": f"https://www.nasdaq.com/market-activity/stocks/{urllib.parse.quote(normalized_symbol.lower())}",
            "summary": "Nasdaq 공식 종목 정보 링크",
        },
        {
            "type": "official_sec_search",
            "source": "sec",
            "title": f"{company_name} SEC filings search",
            "url": f"https://www.sec.gov/edgar/search/#/q={urllib.parse.quote(normalized_symbol)}",
            "summary": "SEC EDGAR 공식 공시 검색 링크",
        },
    ]


def build_research_source_pack(target: dict[str, Any]) -> dict[str, Any]:
    symbol = _text(target.get("symbol") or target.get("code")).upper()
    market = _market(target.get("market"))
    name = _text(target.get("name") or symbol)
    if not symbol or not market:
        raise ValueError("research_source_target_required")
    news_inputs = fetch_google_news_inputs(symbol=symbol, market=market, name=name)
    evidence = build_official_evidence(symbol=symbol, market=market, name=name)
    return {
        "news_inputs": news_inputs,
        "evidence": evidence,
        "source_summary": {
            "news_source": "google-news-rss",
            "official_sources": sorted({str(item.get("source") or "") for item in evidence if item.get("source")}),
            "news_count": len(news_inputs),
            "evidence_count": len(evidence),
        },
    }
