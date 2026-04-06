from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_server_route_stubs() -> list[str]:
    modules: dict[str, dict[str, object]] = {
        "config.market_calendar": {
            "is_market_open": lambda market=None, now=None: True,
        },
        "routes.backtest": {
            "handle_backtest_run": lambda query: (200, {"ok": True, "query": query}),
            "handle_kospi_backtest": lambda: (200, {"ok": True}),
        },
        "routes.engine": {"handle_engine_status": lambda: (200, {"ok": True})},
        "routes.hanna": {"handle_hanna_brief": lambda date=None: (200, {"date": date, "owner": "hanna"})},
        "routes.market": {
            "handle_live_market": lambda: (200, {"ok": True}),
            "handle_stock_price": lambda code, market: (200, {"code": code, "market": market}),
            "handle_stock_search": lambda query: (200, {"q": query}),
            "_paper_fx_rate": lambda market: 1300.0,
            "_resolve_stock_quote": lambda *args, **kwargs: {},
        },
        "routes.optimization": {
            "handle_get_optimization_status": lambda: (200, {"ok": True}),
            "handle_get_optimized_params": lambda: (200, {"ok": True}),
            "handle_run_optimization": lambda payload=None: (200, {"ok": True}),
        },
        "routes.portfolio": {"handle_portfolio_state": lambda refresh=True: (200, {"refresh": refresh})},
        "routes.quant_ops": {
            "handle_get_quant_ops_policy": lambda: (200, {"ok": True}),
            "handle_get_quant_ops_workflow": lambda: (200, {"ok": True}),
            "handle_quant_ops_apply_runtime": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_revalidate": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_reset_workflow": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_reset_policy": lambda: (200, {"ok": True}),
            "handle_quant_ops_save_policy": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_save_candidate": lambda payload: (200, {"payload": payload}),
        },
        "routes.research": {
            "handle_research_ingest_bulk": lambda payload: (200, {"payload": payload}),
            "handle_research_latest_snapshot": lambda query: (200, {"query": query}),
            "handle_research_status": lambda query: (200, {"query": query}),
            "handle_research_snapshots": lambda query: (200, {"query": query}),
        },
        "routes.reports": {
            "handle_analysis": lambda date=None: (200, {"date": date}),
            "handle_compare": lambda base=None, prev=None: (200, {"base": base, "prev": prev}),
            "handle_macro": lambda: (200, {"ok": True}),
            "handle_market_context": lambda date=None: (200, {"date": date}),
            "handle_market_dashboard": lambda: (200, {"ok": True}),
            "handle_recommendations": lambda date=None: (200, {"date": date}),
            "handle_reports": lambda: (200, {"ok": True}),
            "handle_today_picks": lambda date=None: (200, {"date": date}),
            "_get_recommendations": lambda: [],
            "_get_today_picks": lambda: [],
            "_get_market_context": lambda market=None: {"market": market},
        },
        "routes.reports_domain": {
            "handle_reports_explain": lambda date=None: (200, {"date": date}),
            "handle_reports_index": lambda: (200, {"ok": True}),
        },
        "routes.scanner": {"handle_scanner_status": lambda query: (200, {"query": query})},
        "routes.signals": {
            "handle_signal_detail": lambda path: (200, {"path": path}),
            "handle_signal_snapshots": lambda query: (200, {"query": query}),
            "handle_signals_rank": lambda query: (200, {"query": query}),
        },
        "routes.strategies": {
            "handle_strategies_list": lambda query: (200, {"query": query}),
            "handle_strategy_detail": lambda path: (200, {"path": path}),
            "handle_strategy_toggle": lambda payload: (200, {"payload": payload}),
            "handle_strategy_save": lambda payload: (200, {"payload": payload}),
        },
        "routes.trading": {
            "handle_paper_account": lambda refresh=True: (200, {"refresh": refresh}),
            "handle_paper_account_history": lambda query: (200, {"query": query}),
            "handle_paper_auto_invest": lambda payload: (200, {"payload": payload}),
            "handle_paper_engine_cycles": lambda query: (200, {"query": query}),
            "handle_paper_engine_pause": lambda: (200, {"ok": True}),
            "handle_paper_engine_resume": lambda: (200, {"ok": True}),
            "handle_paper_engine_start": lambda payload: (200, {"payload": payload}),
            "handle_paper_engine_status": lambda: (200, {"ok": True}),
            "handle_paper_engine_stop": lambda: (200, {"ok": True}),
            "handle_paper_orders": lambda query: (200, {"query": query}),
            "handle_paper_order": lambda payload: (200, {"payload": payload}),
            "handle_paper_reset": lambda payload: (200, {"payload": payload}),
        },
        "routes.system": {
            "handle_system_mode": lambda: (200, {"ok": True}),
        },
        "routes.universe": {"handle_universe_list": lambda query: (200, {"query": query})},
        "routes.validation": {
            "handle_validation_backtest": lambda query: (200, {"query": query}),
            "handle_validation_diagnostics": lambda query: (200, {"query": query}),
            "handle_validation_settings_get": lambda: (200, {"ok": True}),
            "handle_validation_settings_reset": lambda: (200, {"ok": True}),
            "handle_validation_settings_save": lambda payload: (200, {"payload": payload}),
            "handle_validation_walk_forward": lambda query: (200, {"query": query}),
        },
        "routes.watchlist": {
            "handle_watchlist_actions": lambda payload: (200, {"payload": payload}),
            "handle_watchlist_get": lambda: (200, {"ok": True}),
            "handle_watchlist_save": lambda payload: (200, {"payload": payload}),
            "_compute_technical_snapshot": lambda *args, **kwargs: {},
        },
    }
    installed: list[str] = []
    for module_name, attrs in modules.items():
        module = types.ModuleType(module_name)
        for attr_name, value in attrs.items():
            setattr(module, attr_name, value)
        sys.modules[module_name] = module
        installed.append(module_name)
    return installed


def _remove_server_route_stubs(module_names: list[str]) -> None:
    for module_name in module_names:
        sys.modules.pop(module_name, None)


_INSTALLED_ROUTE_STUBS = _install_server_route_stubs()

from fastapi.testclient import TestClient

from api_server import app

_remove_server_route_stubs(_INSTALLED_ROUTE_STUBS)


class FastApiAppTests(unittest.TestCase):
    def test_health_endpoint_returns_ok(self):
        client = TestClient(app)

        response = client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_legacy_api_route_uses_dispatcher(self):
        client = TestClient(app)

        with patch("api_server.dispatch_get", return_value=(200, {"ok": True})) as mock_dispatch:
            response = client.get("/api/system/mode")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True}, response.json())
        mock_dispatch.assert_called_once_with("/api/system/mode", {})

    def test_legacy_api_post_route_uses_dispatcher(self):
        client = TestClient(app)

        with patch("api_server.dispatch_post", return_value=(200, {"ok": True, "saved_at": "2026-04-01T08:00:00+09:00"})) as mock_dispatch:
            response = client.post("/api/validation/settings/save", json={"query": {"market_scope": "kospi"}})

        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True, "saved_at": "2026-04-01T08:00:00+09:00"}, response.json())
        mock_dispatch.assert_called_once_with("/api/validation/settings/save", {"query": {"market_scope": "kospi"}})
