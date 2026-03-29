from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from api.routes.backtest import handle_backtest_run, handle_kospi_backtest
from api.routes.engine import handle_engine_status
from api.routes.market import handle_live_market, handle_stock_price, handle_stock_search
from api.routes.optimization import (
    handle_get_optimization_status,
    handle_get_optimized_params,
    handle_run_optimization,
)
from api.routes.portfolio import handle_portfolio_state
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
from api.routes.reports_domain import handle_reports_explain, handle_reports_index
from api.routes.signals import handle_signal_detail, handle_signals_rank
from api.routes.trading import (
    handle_paper_account,
    handle_paper_auto_invest,
    handle_paper_engine_start,
    handle_paper_engine_status,
    handle_paper_engine_stop,
    handle_paper_order,
    handle_paper_reset,
)
from api.routes.system import handle_system_mode
from api.routes.validation import handle_validation_backtest, handle_validation_walk_forward
from api.routes.watchlist import (
    handle_watchlist_actions,
    handle_watchlist_get,
    handle_watchlist_save,
)

PORT = 8001

QueryParams = dict[str, list[str]]
JsonHandlerResult = tuple[int, dict]
GetRouteHandler = Callable[[str, QueryParams], JsonHandlerResult]
PostRouteHandler = Callable[[str, dict], JsonHandlerResult]


@dataclass(frozen=True)
class Route:
    path: str
    handler: GetRouteHandler | PostRouteHandler
    prefix: bool = False

    def matches(self, path: str) -> bool:
        return path.startswith(self.path) if self.prefix else path == self.path


def _query_value(query: QueryParams, name: str, default: str = "") -> str:
    return query.get(name, [default])[0] or default


GET_ROUTES: tuple[Route, ...] = (
    Route("/api/engine/status", lambda _path, _query: handle_engine_status()),
    Route("/api/signals/rank", lambda _path, query: handle_signals_rank(query)),
    Route("/api/signals/", lambda path, _query: handle_signal_detail(path), prefix=True),
    Route(
        "/api/portfolio/state",
        lambda _path, query: handle_portfolio_state(_query_value(query, "refresh", "1").strip() != "0"),
    ),
    Route("/api/validation/backtest", lambda _path, query: handle_validation_backtest(query)),
    Route("/api/validation/walk-forward", lambda _path, query: handle_validation_walk_forward(query)),
    Route("/api/reports/explain", lambda _path, query: handle_reports_explain(_query_value(query, "date") or None)),
    Route("/api/reports/index", lambda _path, _query: handle_reports_index()),
    Route("/api/live-market", lambda _path, _query: handle_live_market()),
    Route("/api/reports", lambda _path, _query: handle_reports()),
    Route("/api/analysis", lambda _path, query: handle_analysis(_query_value(query, "date") or None)),
    Route("/api/recommendations", lambda _path, query: handle_recommendations(_query_value(query, "date") or None)),
    Route("/api/today-picks", lambda _path, query: handle_today_picks(_query_value(query, "date") or None)),
    Route(
        "/api/compare",
        lambda _path, query: handle_compare(
            _query_value(query, "base") or None,
            _query_value(query, "prev") or None,
        ),
    ),
    Route("/api/macro/latest", lambda _path, _query: handle_macro()),
    Route("/api/market-context/latest", lambda _path, query: handle_market_context(_query_value(query, "date") or None)),
    Route("/api/market-dashboard", lambda _path, _query: handle_market_dashboard()),
    Route("/api/backtest/run", lambda _path, query: handle_backtest_run(query)),
    Route("/api/backtest/kospi", lambda _path, _query: handle_kospi_backtest()),
    Route("/api/stock-search", lambda _path, query: handle_stock_search(_query_value(query, "q")), prefix=True),
    Route(
        "/api/stock/",
        lambda path, query: handle_stock_price(path[len("/api/stock/"):], _query_value(query, "market")),
        prefix=True,
    ),
    Route("/api/watchlist", lambda _path, _query: handle_watchlist_get()),
    Route(
        "/api/paper/account",
        lambda _path, query: handle_paper_account(_query_value(query, "refresh", "1").strip() != "0"),
    ),
    Route("/api/paper/engine/status", lambda _path, _query: handle_paper_engine_status()),
    Route("/api/system/mode", lambda _path, _query: handle_system_mode()),
    Route("/api/optimized-params", lambda _path, _query: handle_get_optimized_params()),
    Route("/api/optimization-status", lambda _path, _query: handle_get_optimization_status()),
)

POST_ROUTES: tuple[Route, ...] = (
    Route("/api/watchlist-actions", lambda _path, payload: handle_watchlist_actions(payload)),
    Route("/api/watchlist/save", lambda _path, payload: handle_watchlist_save(payload)),
    Route("/api/paper/order", lambda _path, payload: handle_paper_order(payload)),
    Route("/api/paper/reset", lambda _path, payload: handle_paper_reset(payload)),
    Route("/api/paper/auto-invest", lambda _path, payload: handle_paper_auto_invest(payload)),
    Route("/api/paper/engine/start", lambda _path, payload: handle_paper_engine_start(payload)),
    Route("/api/paper/engine/stop", lambda _path, _payload: handle_paper_engine_stop()),
    Route("/api/run-optimization", lambda _path, _payload: handle_run_optimization()),
)


def dispatch_get(path: str, query: QueryParams) -> JsonHandlerResult | None:
    for route in GET_ROUTES:
        if route.matches(path):
            return route.handler(path, query)
    return None


def dispatch_post(path: str, payload: dict) -> JsonHandlerResult | None:
    for route in POST_ROUTES:
        if route.matches(path):
            return route.handler(path, payload)
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        result = dispatch_get(parsed.path, parse_qs(parsed.query))
        if result is None:
            self._json_resp(404, {})
            return
        status, body = result
        self._json_resp(status, body)

    def do_POST(self):
        parsed = urlparse(self.path)
        result = dispatch_post(parsed.path, self._read_json_body())
        if result is None:
            self._json_resp(404, {})
            return
        status, body = result
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
        if "/api/" in msg or "GET" in msg:
            print(f"[{self.client_address[0]}] {msg}", flush=True)


def run(host: str = "127.0.0.1", port: int = PORT):
    server = HTTPServer((host, port), Handler)
    print(f"API server running on {host}:{port}", flush=True)
    server.serve_forever()
