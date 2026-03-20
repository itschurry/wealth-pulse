#!/usr/bin/env python3
"""
실시간 시장 데이터 + AI 분석/추천 캐시 API 서버 (Python 표준 라이브러리만 사용)
GET /api/live-market     → JSON (5분 캐시)
GET /api/analysis        → JSON (SQLite 기반 캐시)
GET /api/recommendations → JSON (SQLite 기반 캐시)
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from api.routes.backtest import handle_backtest_run, handle_kospi_backtest
from api.routes.market import handle_live_market, handle_stock_price, handle_stock_search
from api.routes.reports import (
    handle_analysis,
    handle_compare,
    handle_macro,
    handle_market_context,
    handle_market_dashboard,
    handle_recommendations,
    handle_reports,
    handle_today_picks,
)
from api.routes.trading import (
    handle_paper_account,
    handle_paper_auto_invest,
    handle_paper_engine_start,
    handle_paper_engine_stop,
    handle_paper_engine_status,
    handle_paper_order,
    handle_paper_reset,
)
from api.routes.watchlist import (
    handle_watchlist_actions,
    handle_watchlist_get,
    handle_watchlist_save,
)

PORT = 8001


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/live-market":
            status, body = handle_live_market()
        elif path == "/api/reports":
            status, body = handle_reports()
        elif path == "/api/analysis":
            status, body = handle_analysis(query.get("date", [""])[0] or None)
        elif path == "/api/recommendations":
            status, body = handle_recommendations(query.get("date", [""])[0] or None)
        elif path == "/api/today-picks":
            status, body = handle_today_picks(query.get("date", [""])[0] or None)
        elif path == "/api/compare":
            status, body = handle_compare(
                query.get("base", [""])[0] or None,
                query.get("prev", [""])[0] or None,
            )
        elif path == "/api/macro/latest":
            status, body = handle_macro()
        elif path == "/api/market-context/latest":
            status, body = handle_market_context(query.get("date", [""])[0] or None)
        elif path == "/api/market-dashboard":
            status, body = handle_market_dashboard()
        elif path == "/api/backtest/run":
            status, body = handle_backtest_run(query)
        elif path == "/api/backtest/kospi":
            status, body = handle_kospi_backtest()
        elif path.startswith("/api/stock-search"):
            status, body = handle_stock_search(query.get("q", [""])[0])
        elif path.startswith("/api/stock/"):
            code = path[len("/api/stock/"):]
            market = query.get("market", [""])[0]
            status, body = handle_stock_price(code, market)
        elif path == "/api/watchlist":
            status, body = handle_watchlist_get()
        elif path == "/api/paper/account":
            refresh = (query.get("refresh", ["1"])[0] or "1").strip() != "0"
            status, body = handle_paper_account(refresh)
        elif path == "/api/paper/engine/status":
            status, body = handle_paper_engine_status()
        else:
            self._json_resp(404, {})
            return
        self._json_resp(status, body)

    def do_POST(self):
        payload = self._read_json_body()
        path = self.path

        if path == "/api/watchlist-actions":
            status, body = handle_watchlist_actions(payload)
        elif path == "/api/watchlist/save":
            status, body = handle_watchlist_save(payload)
        elif path == "/api/paper/order":
            status, body = handle_paper_order(payload)
        elif path == "/api/paper/reset":
            status, body = handle_paper_reset(payload)
        elif path == "/api/paper/auto-invest":
            status, body = handle_paper_auto_invest(payload)
        elif path == "/api/paper/engine/start":
            status, body = handle_paper_engine_start(payload)
        elif path == "/api/paper/engine/stop":
            status, body = handle_paper_engine_stop()
        else:
            self._json_resp(404, {})
            return
        self._json_resp(status, body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}

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
        msg = format % args if args else format
        if '/api/' in msg or 'GET' in msg:
            print(f"[{self.client_address[0]}] {msg}", flush=True)


def run(host: str = "127.0.0.1", port: int = PORT):
    server = HTTPServer((host, port), Handler)
    print(f"✅ API server running on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
