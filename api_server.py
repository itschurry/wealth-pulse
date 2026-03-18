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
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8001
REPORTS_DIR = "/reports"
CACHE_TTL = 300   # 5분

_market_cache: dict = {"data": None, "ts": 0.0}
_analysis_cache: dict = {"data": None, "mtime": 0.0}
_recommendation_cache: dict = {"data": None, "mtime": 0.0}
_macro_cache: dict = {"data": None, "mtime": 0.0}
_market_context_cache: dict = {"data": None, "mtime": 0.0}

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


# ──────────────────────────────────────────
#  Fetch helpers
# ──────────────────────────────────────────
def _get(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _naver_index(symbol: str):
    url = f"https://m.stock.naver.com/api/index/{symbol}/basic"
    d = json.loads(_get(url))
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
    text = _get(url)
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
    payload = json.loads(_get(url))
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
    text = _get(url)
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
    text = _get("https://finance.naver.com/marketindex/")
    m = re.search(r'class="value"[^>]*>(1[,\d]+\.\d{2})', text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


# ──────────────────────────────────────────
#  Market snapshot
# ──────────────────────────────────────────
def _build_market() -> dict:
    result: dict = {}

    try:
        p, c = _naver_index("KOSPI")
        result["kospi"] = p
        result["kospi_pct"] = round(c, 2)
    except Exception as e:
        result["kospi_err"] = str(e)

    try:
        p, c = _naver_index("KOSDAQ")
        result["kosdaq"] = p
        result["kosdaq_pct"] = round(c, 2)
    except Exception as e:
        result["kosdaq_err"] = str(e)

    try:
        v = _usd_krw()
        if v:
            result["usd_krw"] = round(v, 2)
    except Exception as e:
        result["usd_krw_err"] = str(e)

    try:
        p, c = _yahoo_chart("^OEX")
        if p:
            result["sp100"] = round(p, 2)
            if c is not None:
                result["sp100_pct"] = round(c, 2)
    except Exception as e:
        result["sp100_err"] = str(e)

    try:
        p, c = _stooq_daily("%5Endx")
        if p:
            result["nasdaq"] = round(p, 2)
            if c is not None:
                result["nasdaq_pct"] = round(c, 2)
    except Exception as e:
        result["nasdaq_err"] = str(e)

    try:
        p, c = _stooq_spot("cl.f")
        if p:
            result["wti"] = round(p, 2)
            if c is not None:
                result["wti_pct"] = round(c, 2)
    except Exception as e:
        result["wti_err"] = str(e)

    try:
        p, c = _stooq_daily("xauusd")
        if p:
            result["gold"] = round(p, 2)
            if c is not None:
                result["gold_pct"] = round(c, 2)
    except Exception as e:
        result["gold_err"] = str(e)

    try:
        p, c = _stooq_daily("btc.v")
        if p:
            result["btc"] = round(p, 2)
            if c is not None:
                result["btc_pct"] = round(c, 2)
    except Exception as e:
        result["btc_err"] = str(e)

    result["updated_at"] = datetime.datetime.now(_KST).strftime("%H:%M:%S KST")
    return result


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


# ──────────────────────────────────────────
#  HTTP Handler
# ──────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/live-market":
            self._serve_market()
        elif self.path == "/api/analysis":
            self._serve_analysis()
        elif self.path == "/api/recommendations":
            self._serve_recommendations()
        elif self.path == "/api/macro/latest":
            self._serve_macro()
        elif self.path == "/api/market-context/latest":
            self._serve_market_context()
        elif self.path.startswith("/api/stock-search"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._serve_stock_search(q)
        elif self.path.startswith("/api/stock/"):
            code = self.path[len("/api/stock/"):]
            self._serve_stock_price(code)
        else:
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

    def _serve_analysis(self):
        try:
            data = _get_analysis()
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_recommendations(self):
        try:
            data = _get_recommendations()
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "recommendations": []})

    def _serve_macro(self):
        try:
            data = _get_macro()
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_market_context(self):
        try:
            data = _get_market_context()
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_stock_search(self, query: str):
        if not query:
            self._json_resp(200, {"results": []})
            return
        try:
            from urllib.parse import quote
            url = f"https://ac.stock.naver.com/ac?q={quote(query)}&target=stock,index"
            raw = json.loads(_get(url))
            items = raw.get("items", [])
            results = [
                {
                    "name":   r["name"],
                    "code":   r["code"],
                    "market": r.get("typeName", r.get("typeCode", "")),
                }
                for r in items[:10]
            ]
            self._json_resp(200, {"results": results})
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_stock_price(self, code: str):
        code = code.split(".")[0].strip()
        if not code:
            self._json_resp(400, {"error": "code required"})
            return
        try:
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
                "market":     d.get("stockExchangeType", {}).get("name", ""),
            })
        except Exception as e:
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
