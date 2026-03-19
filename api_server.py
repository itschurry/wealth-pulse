#!/usr/bin/env python3
"""
실시간 시장 데이터 + AI 분석/추천 캐시 API 서버 (Python 표준 라이브러리만 사용)
GET /api/live-market     → JSON (5분 캐시)
GET /api/analysis        → JSON (파일 mtime 기반 캐시)
GET /api/recommendations → JSON (파일 mtime 기반 캐시)
"""
import datetime
import glob
import json
import os
import re
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer

from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest
from analyzer.today_picks_engine import build_watchlist_actions
from broker.kis_client import KISAPIError, KISClient, KISConfigError

PORT = 8001
CACHE_TTL = 300   # 5분

_market_cache: dict = {"data": None, "ts": 0.0}
_analysis_cache: dict = {"data": None, "mtime": 0.0}
_recommendation_cache: dict = {"data": None, "mtime": 0.0}
_macro_cache: dict = {"data": None, "mtime": 0.0}
_market_context_cache: dict = {"data": None, "mtime": 0.0}
_today_picks_cache: dict = {"data": None, "mtime": 0.0}
_backtest_cache: dict = {"data": None, "mtime": 0.0}
_backtest_run_cache: dict = {}
_technical_cache: dict = {}
_investor_flow_cache: dict = {}
_kis_client: KISClient | None = None
_kis_client_disabled = False

_KST = datetime.timezone(datetime.timedelta(hours=9))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Referer": "https://finance.naver.com/",
}

_ALLOWED_SEARCH_MARKETS = {"KOSPI", "NASDAQ", "코스피", "나스닥 증권거래소"}
TECHNICAL_CACHE_TTL = 900
INVESTOR_FLOW_CACHE_TTL = 900


def _resolve_reports_dir() -> str:
    candidates = [
        os.getenv("REPORT_OUTPUT_DIR"),
        "/reports",
        os.path.join(os.getcwd(), "report"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return candidates[-1]


REPORTS_DIR = _resolve_reports_dir()


# ──────────────────────────────────────────
#  Fetch helpers
# ──────────────────────────────────────────
def _get(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _naver_index(symbol: str):
    url = f"https://m.stock.naver.com/api/index/{symbol}/basic"
    d = json.loads(_get(url, timeout=4))
    price = float(d["closePrice"].replace(",", ""))
    pct = float(d["fluctuationsRatio"])
    code = d.get("compareToPreviousPrice", {}).get("code", "3")
    if code == "5":
        pct = -abs(pct)
    elif code == "2":
        pct = abs(pct)
    return price, pct


def _stooq_daily(symbol: str):
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    text = _get(url, timeout=4)
    rows = [l for l in text.strip().splitlines()
            if l and not l.startswith("Date")]
    if len(rows) < 2:
        return None, None
    last = rows[-1].split(",")
    prev = rows[-2].split(",")
    close = float(last[4])
    prev_close = float(prev[4])
    pct = (close - prev_close) / prev_close * 100
    return close, pct


def _yahoo_chart(symbol: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    payload = json.loads(_get(url, timeout=4))
    result = payload["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    valid = [float(value) for value in closes if value is not None]
    if not valid:
        return None, None
    close = valid[-1]
    prev_close = valid[-2] if len(valid) >= 2 else close
    pct = (close - prev_close) / prev_close * 100 if prev_close else None
    return close, pct


def _stooq_spot(symbol: str):
    url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcvp&h&e=csv"
    text = _get(url, timeout=4)
    rows = [l for l in text.strip().splitlines()
            if l and not l.startswith("Symbol")]
    if not rows:
        return None, None
    parts = rows[-1].split(",")
    if len(parts) < 9:
        return None, None
    try:
        close = float(parts[6])
        prev = float(parts[8])
        pct = (close - prev) / prev * 100 if prev else None
        return close, pct
    except (ValueError, IndexError):
        return None, None


def _usd_krw():
    text = _get("https://finance.naver.com/marketindex/", timeout=4)
    m = re.search(r'class="value"[^>]*>(1[,\d]+\.\d{2})', text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _is_allowed_market_label(*labels: str) -> bool:
    normalized_labels = {label.strip().upper() for label in labels if label and label.strip()}
    return any(label in _ALLOWED_SEARCH_MARKETS for label in normalized_labels)


def _resolve_chart_symbol(code: str, market: str) -> str | None:
    normalized_code = code.strip().upper()
    normalized_market = market.strip().upper()
    if not normalized_code:
        return None
    if normalized_market == "KOSPI" and normalized_code.isdigit():
        return f"{normalized_code}.KS"
    if normalized_market == "NASDAQ":
        return normalized_code
    return None


def _get_kis_client() -> KISClient | None:
    global _kis_client, _kis_client_disabled

    if _kis_client_disabled:
        return None
    if _kis_client is not None:
        return _kis_client
    if not KISClient.is_configured():
        _kis_client_disabled = True
        return None
    try:
        _kis_client = KISClient.from_env(timeout=8.0)
        return _kis_client
    except (KISConfigError, KISAPIError):
        _kis_client_disabled = True
        return None


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(values[:-1], values[1:]):
        delta = current - prev
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for idx in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _fetch_chart_history(symbol: str, range_: str = "6mo", interval: str = "1d") -> dict | None:
    payload = json.loads(_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval={interval}",
        timeout=5,
    ))
    result = payload.get("chart", {}).get("result", [])
    if not result:
        return None
    chart = result[0]
    quote = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    volumes = quote.get("volume", [])

    history = []
    for close, volume in zip(closes, volumes):
        if close is None:
            continue
        history.append({
            "close": float(close),
            "volume": float(volume) if volume is not None else None,
        })
    return {"history": history}


def _fetch_kis_domestic_history(code: str, lookback_days: int = 180) -> dict | None:
    client = _get_kis_client()
    if client is None:
        return None

    end_date = datetime.datetime.now(_KST).strftime("%Y%m%d")
    start_date = (datetime.datetime.now(_KST) - datetime.timedelta(days=lookback_days)).strftime("%Y%m%d")
    try:
        rows = client.get_domestic_daily_history(
            code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        return None

    history = []
    for item in rows:
        close = item.get("close")
        volume = item.get("volume")
        if close is None:
            continue
        history.append({
            "close": float(close),
            "volume": float(volume) if volume is not None else None,
        })
    return {"history": history} if history else None


def _compute_technical_snapshot(code: str, market: str) -> dict | None:
    symbol = _resolve_chart_symbol(code, market)
    if not symbol:
        return None

    cache_key = f"{market}:{code}"
    cached = _technical_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] < TECHNICAL_CACHE_TTL:
        return cached["data"]

    chart = _fetch_kis_domestic_history(code) if market.strip().upper() == "KOSPI" else None
    if not chart:
        chart = _fetch_chart_history(symbol)
    if not chart:
        return None

    history = chart["history"]
    closes = [item["close"] for item in history if item.get("close") is not None]
    volumes = [item["volume"] for item in history if item.get("volume") is not None]
    if len(closes) < 35:
        return None

    current_price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    sma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    volume = volumes[-1] if volumes else None
    volume_avg20 = (sum(volumes[-20:]) / 20) if len(volumes) >= 20 else None
    volume_ratio = (volume / volume_avg20) if volume and volume_avg20 else None

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_series = [fast - slow for fast, slow in zip(ema12[-len(ema26):], ema26)]
    signal_series = _ema(macd_series, 9)
    macd = macd_series[-1] if macd_series else None
    macd_signal = signal_series[-1] if signal_series else None
    macd_hist = (macd - macd_signal) if macd is not None and macd_signal is not None else None
    rsi14 = _rsi(closes, 14)

    trend = "neutral"
    if sma20 is not None and sma60 is not None:
        if current_price > sma20 and sma20 > sma60:
            trend = "bullish"
        elif current_price < sma20 and sma20 < sma60:
            trend = "bearish"

    snapshot = {
        "current_price": round(current_price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "sma20": round(sma20, 2) if sma20 is not None else None,
        "sma60": round(sma60, 2) if sma60 is not None else None,
        "volume": int(volume) if volume is not None else None,
        "volume_avg20": int(volume_avg20) if volume_avg20 is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "rsi14": round(rsi14, 1) if rsi14 is not None else None,
        "macd": round(macd, 3) if macd is not None else None,
        "macd_signal": round(macd_signal, 3) if macd_signal is not None else None,
        "macd_hist": round(macd_hist, 3) if macd_hist is not None else None,
        "trend": trend,
    }
    _technical_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").strip()


def _parse_signed_number(text: str) -> int | None:
    cleaned = text.replace(",", "").replace(" ", "")
    match = re.search(r"([+-]?\d+)", cleaned)
    if not match:
        return None
    return int(match.group(1))


def _fetch_investor_flow_snapshot(code: str, market: str) -> dict | None:
    if market.strip().upper() not in {"KOSPI", "KOSDAQ"} or not code.strip().isdigit():
        return None

    cache_key = f"{market}:{code}"
    cached = _investor_flow_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] < INVESTOR_FLOW_CACHE_TTL:
        return cached["data"]

    req = urllib.request.Request(
        f"https://finance.naver.com/item/frgn.naver?code={code}",
        headers=_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        html = response.read().decode("euc-kr", "replace")

    table_match = re.search(
        r"외국인ㆍ기관.*?순매매 거래량.*?<table[^>]*class=\"type2\"[^>]*>(.*?)</table>",
        html,
        re.S,
    )
    if not table_match:
        return None

    rows = []
    for row_html in re.findall(r"<tr[^>]*onMouseOver=.*?>(.*?)</tr>", table_match.group(1), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
        if len(cells) < 7:
            continue
        date = _strip_html(cells[0])
        institution_net = _parse_signed_number(_strip_html(cells[5]))
        foreign_net = _parse_signed_number(_strip_html(cells[6]))
        if not date:
            continue
        rows.append({
            "date": date,
            "institution_net": institution_net or 0,
            "foreign_net": foreign_net or 0,
        })
        if len(rows) >= 5:
            break

    if not rows:
        return None

    snapshot = {
        "date": rows[0]["date"],
        "foreign_net_1d": rows[0]["foreign_net"],
        "foreign_net_5d": sum(row["foreign_net"] for row in rows[:5]),
        "institution_net_1d": rows[0]["institution_net"],
        "institution_net_5d": sum(row["institution_net"] for row in rows[:5]),
    }
    _investor_flow_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot


# ──────────────────────────────────────────
#  Market snapshot
# ──────────────────────────────────────────
def _build_market() -> dict:
    result: dict = {}

    tasks = {
        "kospi": lambda: _naver_index("KOSPI"),
        "kosdaq": lambda: _naver_index("KOSDAQ"),
        "usd_krw": _usd_krw,
        "sp100": lambda: _yahoo_chart("^OEX"),
        "nasdaq": lambda: _stooq_daily("%5Endx"),
        "wti": lambda: _stooq_spot("cl.f"),
    }

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(task): key for key, task in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                value = future.result()
                if key == "usd_krw":
                    if value:
                        result["usd_krw"] = round(value, 2)
                    continue

                price, change_pct = value
                if price:
                    result[key] = round(price, 2)
                    if change_pct is not None:
                        result[f"{key}_pct"] = round(change_pct, 2)
            except Exception as e:
                result[f"{key}_err"] = str(e)

    result["updated_at"] = datetime.datetime.now(_KST).strftime("%H:%M:%S KST")
    return result


def _list_report_dates() -> list[str]:
    pattern = os.path.join(REPORTS_DIR, "*_analysis.json")
    dates = []
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)
        if base.endswith("_analysis.json"):
            dates.append(base.replace("_analysis.json", ""))
    return sorted(set(dates))


def _pick_date(requested: str | None = None) -> str | None:
    dates = _list_report_dates()
    if not dates:
        return None
    if requested and requested in dates:
        return requested
    return dates[-1]


def _previous_date(current: str | None = None) -> str | None:
    dates = _list_report_dates()
    if len(dates) < 2:
        return None
    if current and current in dates:
        index = dates.index(current)
        if index > 0:
            return dates[index - 1]
    return dates[-2]


def _report_file(date: str, suffix: str) -> str:
    return os.path.join(REPORTS_DIR, f"{date}_{suffix}.json")


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_report_json(suffix: str, date: str | None = None, latest: bool = True) -> dict:
    target_date = _pick_date(date) if latest else date
    if not target_date:
        return {}

    path = _report_file(target_date, suffix)
    if not os.path.exists(path):
        return {}
    return _read_json(path)


def _build_compare_payload(base_date: str | None = None, prev_date: str | None = None) -> dict:
    base_date = _pick_date(base_date)
    if not base_date:
        return {"error": "비교할 리포트가 없습니다."}

    prev_date = _previous_date(base_date) if prev_date is None else prev_date
    if not prev_date:
        return {"error": "전일 비교 데이터가 없습니다.", "base_date": base_date}

    base_analysis = _load_report_json("analysis", base_date, latest=False)
    prev_analysis = _load_report_json("analysis", prev_date, latest=False)
    base_recommendations = _load_report_json("recommendations", base_date, latest=False)
    prev_recommendations = _load_report_json("recommendations", prev_date, latest=False)
    base_context = _load_report_json("market_context", base_date, latest=False)
    prev_context = _load_report_json("market_context", prev_date, latest=False)
    base_today_picks = _load_report_json("today_picks", base_date, latest=False) or _fallback_today_picks(base_date)
    prev_today_picks = _load_report_json("today_picks", prev_date, latest=False) or _fallback_today_picks(prev_date)

    base_rec_map = {}
    prev_rec_map = {}
    for item in base_recommendations.get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        base_rec_map[key] = item
        base_rec_map[item.get("name")] = item
    for item in prev_recommendations.get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        prev_rec_map[key] = item
        prev_rec_map[item.get("name")] = item

    recommendation_changes = []
    for current in base_recommendations.get("recommendations", []):
        key = (current.get("ticker") or "").split(".")[0] or current.get("name")
        previous = prev_rec_map.get(key) or prev_rec_map.get(current.get("name"))
        if not previous:
            continue
        if current.get("signal") != previous.get("signal") or current.get("score") != previous.get("score"):
            recommendation_changes.append({
                "name": current.get("name"),
                "ticker": current.get("ticker", ""),
                "current_signal": current.get("signal"),
                "previous_signal": previous.get("signal"),
                "score_diff": round(float(current.get("score", 0)) - float(previous.get("score", 0)), 1),
            })

    base_pick_map = {item.get("code") or item.get("name"): item for item in base_today_picks.get("picks", [])}
    prev_pick_map = {item.get("code") or item.get("name"): item for item in prev_today_picks.get("picks", [])}
    today_pick_changes = []
    for key, current in base_pick_map.items():
        previous = prev_pick_map.get(key)
        if not previous:
            today_pick_changes.append({
                "name": current.get("name"),
                "status": "new",
                "current_signal": current.get("signal"),
                "score_diff": current.get("score"),
            })
            continue
        if current.get("signal") != previous.get("signal") or current.get("score") != previous.get("score"):
            today_pick_changes.append({
                "name": current.get("name"),
                "status": "changed",
                "current_signal": current.get("signal"),
                "previous_signal": previous.get("signal"),
                "score_diff": round(float(current.get("score", 0)) - float(previous.get("score", 0)), 1),
            })

    base_ctx = base_context.get("context", {})
    prev_ctx = prev_context.get("context", {})
    context_changes = []
    for field in ("regime", "risk_level", "inflation_signal", "labor_signal", "policy_signal", "yield_curve_signal", "dollar_signal"):
        if base_ctx.get(field) != prev_ctx.get(field):
            context_changes.append({
                "field": field,
                "previous": prev_ctx.get(field),
                "current": base_ctx.get(field),
            })

    base_risks = set(base_ctx.get("risks", []))
    prev_risks = set(prev_ctx.get("risks", []))

    return {
        "base_date": base_date,
        "prev_date": prev_date,
        "summary_lines": {
            "base": base_analysis.get("summary_lines", []),
            "prev": prev_analysis.get("summary_lines", []),
        },
        "signal_counts": {
            "base": base_recommendations.get("signal_counts", {}),
            "prev": prev_recommendations.get("signal_counts", {}),
        },
        "recommendation_changes": sorted(recommendation_changes, key=lambda item: abs(item["score_diff"]), reverse=True)[:10],
        "today_pick_changes": sorted(today_pick_changes, key=lambda item: abs(item["score_diff"]), reverse=True)[:10],
        "context_changes": context_changes,
        "new_risks": sorted(base_risks - prev_risks),
        "resolved_risks": sorted(prev_risks - base_risks),
    }


# ──────────────────────────────────────────
#  Analysis cache (reads *_analysis.json)
# ──────────────────────────────────────────
def _get_analysis() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_analysis.json")), reverse=True)
    if not files:
        return {"error": "분석 결과가 없습니다. run_once.py를 먼저 실행하세요."}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    # 파일이 변경된 경우에만 다시 읽기
    if _analysis_cache["data"] is not None and mtime == _analysis_cache["mtime"]:
        return _analysis_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _analysis_cache["data"] = data
    _analysis_cache["mtime"] = mtime
    return data


def _get_recommendations() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_recommendations.json")), reverse=True)
    if not files:
        return {"error": "추천 결과가 없습니다. run_once.py를 먼저 실행하세요.", "recommendations": []}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    if _recommendation_cache["data"] is not None and mtime == _recommendation_cache["mtime"]:
        return _recommendation_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _recommendation_cache["data"] = data
    _recommendation_cache["mtime"] = mtime
    return data


def _get_today_picks() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_today_picks.json")), reverse=True)
    if not files:
        fallback = _fallback_today_picks()
        if fallback.get("picks"):
            return fallback
        return {"error": "오늘의 추천 결과가 없습니다.", "picks": []}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    if _today_picks_cache["data"] is not None and mtime == _today_picks_cache["mtime"]:
        return _today_picks_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _today_picks_cache["data"] = data
    _today_picks_cache["mtime"] = mtime
    return data


def _fallback_today_picks(date: str | None = None) -> dict:
    recommendations = _get_recommendations() if not date else _load_report_json("recommendations", date, latest=False)
    if not recommendations.get("recommendations"):
        return {"picks": []}

    picks = []
    for item in recommendations.get("recommendations", [])[:8]:
        ticker = (item.get("ticker") or "").split(".")[0]
        picks.append({
            "name": item.get("name"),
            "code": ticker,
            "market": "KOSPI" if item.get("ticker", "").endswith(".KS") else "KOSDAQ" if item.get("ticker", "").endswith(".KQ") else "",
            "sector": item.get("sector"),
            "signal": item.get("signal"),
            "score": item.get("score"),
            "confidence": item.get("confidence", 55),
            "reasons": item.get("reasons", []),
            "risks": item.get("risks", []),
            "catalysts": item.get("reasons", [])[:2],
            "related_news": [],
        })

    return {
        "generated_at": recommendations.get("generated_at"),
        "date": recommendations.get("date"),
        "market_tone": "fallback",
        "strategy": "recommendation-fallback",
        "picks": picks,
    }


def _get_macro() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_macro.json")), reverse=True)
    if not files:
        return {"error": "거시 지표 결과가 없습니다."}

    latest = files[0]
    mtime = os.path.getmtime(latest)
    if _macro_cache["data"] is not None and mtime == _macro_cache["mtime"]:
        return _macro_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _macro_cache["data"] = data
    _macro_cache["mtime"] = mtime
    return data


def _get_market_context() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_market_context.json")), reverse=True)
    if not files:
        return {"error": "시장 컨텍스트 결과가 없습니다."}

    latest = files[0]
    mtime = os.path.getmtime(latest)
    if _market_context_cache["data"] is not None and mtime == _market_context_cache["mtime"]:
        return _market_context_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _market_context_cache["data"] = data
    _market_context_cache["mtime"] = mtime
    return data


def _get_market_dashboard() -> dict:
    market = _market_cache["data"]
    now = time.time()
    if market is None or now - _market_cache["ts"] > CACHE_TTL:
        market = _build_market()
        _market_cache["data"] = market
        _market_cache["ts"] = now

    return {
        "market": market,
        "macro": _get_macro(),
        "context": _get_market_context(),
    }


def _get_kospi_backtest() -> dict:
    path = os.path.join(REPORTS_DIR, "kospi_backtest_latest.json")
    if not os.path.exists(path):
        return {"error": "백테스트 결과가 없습니다. scripts/run_kospi_backtest.py를 먼저 실행하세요."}

    mtime = os.path.getmtime(path)
    if _backtest_cache["data"] is not None and mtime == _backtest_cache["mtime"]:
        return _backtest_cache["data"]

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    _backtest_cache["data"] = data
    _backtest_cache["mtime"] = mtime
    return data


def _parse_backtest_config(query: dict[str, list[str]]) -> BacktestConfig:
    market_scope = (query.get("market_scope", ["all"])[0] or "all").strip().lower()
    if market_scope == "kospi":
        markets = ("KOSPI",)
    elif market_scope == "nasdaq":
        markets = ("NASDAQ",)
    else:
        markets = ("KOSPI", "NASDAQ")

    def _parse_int(name: str, default: int, minimum: int, maximum: int) -> int:
        raw = query.get(name, [str(default)])[0]
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _parse_float(name: str, default: float, minimum: float, maximum: float) -> float:
        raw = query.get(name, [str(default)])[0]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _parse_optional_float(name: str, minimum: float, maximum: float) -> float | None:
        raw = (query.get(name, [""])[0] or "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(minimum, min(maximum, value))

    rsi_min = _parse_float("rsi_min", 45.0, 10.0, 90.0)
    rsi_max = _parse_float("rsi_max", 68.0, 10.0, 90.0)
    if rsi_min > rsi_max:
        rsi_min, rsi_max = rsi_max, rsi_min

    return BacktestConfig(
        initial_cash=_parse_float("initial_cash", 10_000_000.0, 1_000_000.0, 500_000_000.0),
        max_positions=_parse_int("max_positions", 5, 1, 20),
        max_holding_days=_parse_int("max_holding_days", 30, 5, 180),
        lookback_days=_parse_int("lookback_days", 1095, 180, 1825),
        markets=markets,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        volume_ratio_min=_parse_float("volume_ratio_min", 1.2, 0.5, 5.0),
        stop_loss_pct=_parse_optional_float("stop_loss_pct", 1.0, 50.0),
        take_profit_pct=_parse_optional_float("take_profit_pct", 1.0, 100.0),
    )


def _config_cache_key(config: BacktestConfig) -> str:
    return json.dumps(
        {
            "initial_cash": config.initial_cash,
            "max_positions": config.max_positions,
            "max_holding_days": config.max_holding_days,
            "lookback_days": config.lookback_days,
            "markets": list(config.markets),
            "rsi_min": config.rsi_min,
            "rsi_max": config.rsi_max,
            "volume_ratio_min": config.volume_ratio_min,
            "stop_loss_pct": config.stop_loss_pct,
            "take_profit_pct": config.take_profit_pct,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _run_backtest(config: BacktestConfig) -> dict:
    cache_key = _config_cache_key(config)
    cached = _backtest_run_cache.get(cache_key)
    if cached:
        return cached

    result = run_kospi_backtest(config)
    _backtest_run_cache[cache_key] = result
    if len(_backtest_run_cache) > 12:
        oldest_key = next(iter(_backtest_run_cache))
        if oldest_key != cache_key:
            _backtest_run_cache.pop(oldest_key, None)
    return result


# ──────────────────────────────────────────
#  HTTP Handler
# ──────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/live-market":
            self._serve_market()
        elif parsed.path == "/api/reports":
            self._serve_reports()
        elif parsed.path == "/api/analysis":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_analysis(date or None)
        elif parsed.path == "/api/recommendations":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_recommendations(date or None)
        elif parsed.path == "/api/today-picks":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_today_picks(date or None)
        elif parsed.path == "/api/compare":
            query = parse_qs(parsed.query)
            self._serve_compare(query.get("base", [""])[0] or None, query.get("prev", [""])[0] or None)
        elif parsed.path == "/api/macro/latest":
            self._serve_macro()
        elif parsed.path == "/api/market-context/latest":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_market_context(date or None)
        elif parsed.path == "/api/market-dashboard":
            self._serve_market_dashboard()
        elif parsed.path == "/api/backtest/run":
            self._serve_backtest_run(parse_qs(parsed.query))
        elif parsed.path == "/api/backtest/kospi":
            self._serve_kospi_backtest()
        elif parsed.path.startswith("/api/stock-search"):
            q = parse_qs(parsed.query).get("q", [""])[0]
            self._serve_stock_search(q)
        elif parsed.path.startswith("/api/stock/"):
            code = parsed.path[len("/api/stock/"):]
            market = parse_qs(parsed.query).get("market", [""])[0]
            self._serve_stock_price(code, market)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/watchlist-actions":
            self._serve_watchlist_actions()
            return
        self.send_response(404)
        self.end_headers()

    def _serve_market(self):
        now = time.time()
        if _market_cache["data"] is None or now - _market_cache["ts"] > CACHE_TTL:
            try:
                _market_cache["data"] = _build_market()
                _market_cache["ts"] = now
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return
        self._json_resp(200, _market_cache["data"])

    def _serve_reports(self):
        self._json_resp(200, {"dates": _list_report_dates()})

    def _serve_analysis(self, date: str | None = None):
        try:
            data = _get_analysis() if not date else _load_report_json("analysis", date, latest=False) or {"error": "해당 날짜 분석이 없습니다."}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_recommendations(self, date: str | None = None):
        try:
            data = _get_recommendations() if not date else _load_report_json("recommendations", date, latest=False) or {"error": "해당 날짜 추천이 없습니다.", "recommendations": []}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "recommendations": []})

    def _serve_today_picks(self, date: str | None = None):
        try:
            if not date:
                data = _get_today_picks()
            else:
                data = _load_report_json("today_picks", date, latest=False) or _fallback_today_picks(date) or {"error": "해당 날짜 오늘의 추천이 없습니다.", "picks": []}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "picks": []})

    def _serve_compare(self, base_date: str | None, prev_date: str | None):
        try:
            self._json_resp(200, _build_compare_payload(base_date, prev_date))
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_macro(self):
        try:
            data = _get_macro()
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_market_context(self, date: str | None = None):
        try:
            data = _get_market_context() if not date else _load_report_json("market_context", date, latest=False) or {"error": "해당 날짜 시장 컨텍스트가 없습니다."}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_market_dashboard(self):
        try:
            self._json_resp(200, _get_market_dashboard())
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_kospi_backtest(self):
        try:
            self._json_resp(200, _get_kospi_backtest())
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_backtest_run(self, query: dict[str, list[str]]):
        try:
            config = _parse_backtest_config(query)
            self._json_resp(200, _run_backtest(config))
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_stock_search(self, query: str):
        if not query:
            self._json_resp(200, {"results": []})
            return
        try:
            url = f"https://ac.stock.naver.com/ac?q={quote(query)}&target=stock,index"
            raw = json.loads(_get(url))
            items = raw.get("items", [])
            results = [
                {
                    "name":   r["name"],
                    "code":   r["code"],
                    "market": r.get("typeCode", r.get("typeName", "")),
                }
                for r in items[:10]
                if _is_allowed_market_label(r.get("typeCode", ""), r.get("typeName", ""))
            ]
            self._json_resp(200, {"results": results})
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_watchlist_actions(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw or "{}")
            items = payload.get("items", [])
            base_date = payload.get("date") or _pick_date()
            prev_date = _previous_date(base_date)
            today_picks = _get_today_picks() if not payload.get("date") else (_load_report_json("today_picks", base_date, latest=False) or _fallback_today_picks(base_date))
            recommendations = _get_recommendations() if not payload.get("date") else _load_report_json("recommendations", base_date, latest=False)
            previous_recommendations = _load_report_json("recommendations", prev_date, latest=False) if prev_date else {}
            previous_today_picks = (_load_report_json("today_picks", prev_date, latest=False) or _fallback_today_picks(prev_date)) if prev_date else {}
            enriched_items = [dict(item) for item in items]
            with ThreadPoolExecutor(max_workers=max(1, min(len(enriched_items), 6))) as executor:
                futures = {
                    executor.submit(_compute_technical_snapshot, item.get("code", ""), item.get("market", "")): idx
                    for idx, item in enumerate(enriched_items)
                    if item.get("code")
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    technicals = future.result()
                    enriched = enriched_items[idx]
                    if technicals:
                        if enriched.get("price") is None and technicals.get("current_price") is not None:
                            enriched["price"] = technicals["current_price"]
                        if enriched.get("change_pct") is None and technicals.get("change_pct") is not None:
                            enriched["change_pct"] = technicals["change_pct"]
                        enriched["technicals"] = technicals
                    flow = _fetch_investor_flow_snapshot(enriched.get("code", ""), enriched.get("market", ""))
                    if flow:
                        enriched["investor_flow"] = flow
            result = build_watchlist_actions(enriched_items, today_picks, recommendations, previous_recommendations, previous_today_picks)
            self._json_resp(200, result)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "actions": []})

    def _serve_stock_price(self, code: str, market: str = ""):
        code = code.split(".")[0].strip()
        if not code:
            self._json_resp(400, {"error": "code required"})
            return
        try:
            if market.upper() == "NASDAQ":
                technicals = _compute_technical_snapshot(code, market)
                if not technicals:
                    raise ValueError("NASDAQ 종목 기술지표를 불러오지 못했습니다.")
                self._json_resp(200, {
                    "code": code,
                    "name": code,
                    "price": technicals.get("current_price"),
                    "change_pct": technicals.get("change_pct"),
                    "market": market,
                })
                return

            if market.upper() == "KOSPI":
                client = _get_kis_client()
                if client is not None:
                    kis_price = client.get_domestic_price(code)
                    self._json_resp(200, {
                        "code": code,
                        "name": kis_price.get("name") or code,
                        "price": kis_price.get("price"),
                        "change_pct": kis_price.get("change_pct"),
                        "market": "KOSPI",
                    })
                    return

            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            d = json.loads(_get(url))
            price = float(d["closePrice"].replace(",", ""))
            pct = float(d["fluctuationsRatio"])
            direction = d.get("compareToPreviousPrice", {}).get("code", "3")
            if direction == "5":
                pct = -abs(pct)
            elif direction == "2":
                pct = abs(pct)
            self._json_resp(200, {
                "code":       code,
                "name":       d.get("stockName", code),
                "price":      price,
                "change_pct": round(pct, 2),
                "market":     d.get("stockExchangeType", {}).get("name", market),
            })
        except Exception as e:
            technicals = _compute_technical_snapshot(code, market) if market else None
            if technicals:
                self._json_resp(200, {
                    "code": code,
                    "name": code,
                    "price": technicals.get("current_price"),
                    "change_pct": technicals.get("change_pct"),
                    "market": market,
                })
                return
            self._json_resp(500, {"error": str(e)})

    def _json_resp(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 관심 있는 API 호출만 로그
        msg = format % args if args else format
        if '/api/' in msg or 'GET' in msg:
            print(f"[{self.client_address[0]}] {msg}", flush=True)


def run(host: str = "127.0.0.1", port: int = PORT):
    server = HTTPServer((host, port), Handler)
    print(f"✅ API server running on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
