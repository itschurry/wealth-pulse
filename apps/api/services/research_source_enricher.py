from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
import html
import io
import json
import zipfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

import FinanceDataReader as fdr

from config.settings import CACHE_DIR, DART_API_KEY


GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
OPENDART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
OPENDART_DISCLOSURE_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DEFAULT_NEWS_LIMIT = 5
DEFAULT_DART_LIMIT = 5
DART_CORP_CODE_CACHE = CACHE_DIR / "opendart" / "corp_codes_by_stock.json"
ENTRY_TECHNICAL_FIELDS = ("close_vs_sma20", "close_vs_sma60", "volume_ratio")


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


def _recent_date(days: int) -> str:
    return (dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date() - dt.timedelta(days=max(1, int(days)))).strftime("%Y%m%d")


def _today_date() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().strftime("%Y%m%d")


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(values[:-1], values[1:]):
        change = current - prev
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for idx in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_fdr_technical_features(*, symbol: str, market: str) -> dict[str, Any]:
    if _market(market) not in {"KOSPI", "KOSDAQ"}:
        return {}
    end = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    start = end - dt.timedelta(days=130)
    frame = fdr.DataReader(_text(symbol).upper(), start.isoformat(), end.isoformat())
    if frame is None or len(frame) < 35:
        return {}
    close = [float(value) for value in frame["Close"].dropna().tolist()]
    volume = [float(value) for value in frame["Volume"].dropna().tolist()] if "Volume" in frame else []
    if len(close) < 35:
        return {}
    current = close[-1]
    sma20 = sum(close[-20:]) / 20
    sma60 = sum(close[-60:]) / 60 if len(close) >= 60 else sma20
    avg_volume20 = sum(volume[-20:]) / 20 if len(volume) >= 20 else 0.0
    current_volume = volume[-1] if volume else 0.0
    return {
        "current_price": round(current, 4),
        "close": round(current, 4),
        "close_vs_sma20": round(current / sma20, 4) if sma20 > 0 else None,
        "close_vs_sma60": round(current / sma60, 4) if sma60 > 0 else None,
        "volume_ratio": round(current_volume / avg_volume20, 4) if avg_volume20 > 0 else None,
        "rsi14": round(_rsi(close) or 0.0, 4),
        "source": "finance-datareader",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def _load_dart_corp_codes() -> dict[str, dict[str, str]]:
    if DART_CORP_CODE_CACHE.exists():
        payload = json.loads(DART_CORP_CODE_CACHE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    if not DART_API_KEY:
        return {}

    url = f"{OPENDART_CORP_CODE_URL}?{urllib.parse.urlencode({'crtfc_key': DART_API_KEY})}"
    req = urllib.request.Request(url, headers={"User-Agent": "WealthPulse research source collector"})
    with urllib.request.urlopen(req, timeout=15) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    xml_name = archive.namelist()[0]
    root = ET.fromstring(archive.read(xml_name))
    rows: dict[str, dict[str, str]] = {}
    for item in root.findall("list"):
        stock_code = _text(item.findtext("stock_code")).upper()
        corp_code = _text(item.findtext("corp_code"))
        corp_name = _text(item.findtext("corp_name"))
        if stock_code and corp_code:
            rows[stock_code] = {"corp_code": corp_code, "corp_name": corp_name, "stock_code": stock_code}
    DART_CORP_CODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DART_CORP_CODE_CACHE.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return rows


def fetch_dart_disclosure_evidence(*, symbol: str, market: str, limit: int = DEFAULT_DART_LIMIT, timeout: int = 10) -> list[dict[str, Any]]:
    if _market(market) not in {"KOSPI", "KOSDAQ"} or not DART_API_KEY:
        return []
    corp = _load_dart_corp_codes().get(_text(symbol).upper())
    if not corp:
        return []
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp["corp_code"],
        "bgn_de": _recent_date(30),
        "end_de": _today_date(),
        "page_count": str(max(1, min(100, int(limit)))),
    }
    url = f"{OPENDART_DISCLOSURE_LIST_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "WealthPulse research source collector", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if str(payload.get("status") or "") not in {"000", "013"}:
        raise RuntimeError(f"opendart_list_failed:{payload.get('status')}:{payload.get('message')}")
    rows: list[dict[str, Any]] = []
    for item in payload.get("list") or []:
        if not isinstance(item, dict):
            continue
        receipt_no = _text(item.get("rcept_no"))
        report_name = _text(item.get("report_nm"))
        receipt_date = _text(item.get("rcept_dt"))
        if not receipt_no or not report_name:
            continue
        rows.append(
            {
                "type": "official_disclosure",
                "source": "opendart",
                "title": report_name,
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={urllib.parse.quote(receipt_no)}",
                "published_at": f"{receipt_date[:4]}-{receipt_date[4:6]}-{receipt_date[6:8]}T00:00:00+09:00" if len(receipt_date) == 8 else "",
                "summary": f"{corp.get('corp_name') or symbol} 공시: {report_name}",
                "receipt_no": receipt_no,
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
    dart_evidence = fetch_dart_disclosure_evidence(symbol=symbol, market=market)
    evidence = [*dart_evidence, *build_official_evidence(symbol=symbol, market=market, name=name)]
    target_technical = target.get("technical_snapshot") if isinstance(target.get("technical_snapshot"), dict) else {}
    fdr_technical = fetch_fdr_technical_features(symbol=symbol, market=market)
    technical_features: dict[str, Any] = {}
    for source in (fdr_technical, target_technical):
        for key, value in source.items():
            if value not in (None, "", [], {}):
                technical_features[key] = value
    for field in ENTRY_TECHNICAL_FIELDS:
        if technical_features.get(field) in (None, "") and fdr_technical.get(field) not in (None, ""):
            technical_features[field] = fdr_technical.get(field)
    if target_technical.get("source") and fdr_technical:
        technical_features["source"] = f"{target_technical['source']}+{fdr_technical.get('source', 'finance-datareader')}"
    return {
        "news_inputs": news_inputs,
        "evidence": evidence,
        "technical_features": technical_features,
        "source_summary": {
            "news_source": "google-news-rss",
            "official_sources": sorted({str(item.get("source") or "") for item in evidence if item.get("source")}),
            "news_count": len(news_inputs),
            "dart_disclosure_count": len(dart_evidence),
            "evidence_count": len(evidence),
            "technical_source": str(technical_features.get("source") or "target_snapshot") if technical_features else "",
        },
    }
