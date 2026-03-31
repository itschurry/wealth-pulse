from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_server_route_stubs() -> None:
    modules: dict[str, dict[str, object]] = {
        "routes.backtest": {
            "handle_backtest_run": lambda query: (200, {"ok": True, "query": query}),
            "handle_kospi_backtest": lambda: (200, {"ok": True}),
        },
        "routes.engine": {"handle_engine_status": lambda: (200, {"ok": True})},
        "routes.market": {
            "handle_live_market": lambda: (200, {"ok": True}),
            "handle_stock_price": lambda code, market: (200, {"code": code, "market": market}),
            "handle_stock_search": lambda query: (200, {"q": query}),
        },
        "routes.optimization": {
            "handle_get_optimization_status": lambda: (200, {"ok": True}),
            "handle_get_optimized_params": lambda: (200, {"ok": True}),
            "handle_run_optimization": lambda: (200, {"ok": True}),
        },
        "routes.portfolio": {"handle_portfolio_state": lambda refresh=True: (200, {"refresh": refresh})},
        "routes.quant_ops": {
            "handle_get_quant_ops_workflow": lambda: (200, {"ok": True}),
            "handle_quant_ops_apply_runtime": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_revalidate": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_revalidate_symbol": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_set_symbol_approval": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_save_symbol_candidate": lambda payload: (200, {"payload": payload}),
            "handle_quant_ops_save_candidate": lambda payload: (200, {"payload": payload}),
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
        },
        "routes.reports_domain": {
            "handle_reports_explain": lambda date=None: (200, {"date": date}),
            "handle_reports_index": lambda: (200, {"ok": True}),
        },
        "routes.signals": {
            "handle_signal_detail": lambda path: (200, {"path": path}),
            "handle_signal_snapshots": lambda query: (200, {"query": query}),
            "handle_signals_rank": lambda query: (200, {"query": query}),
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
            "handle_notifications_status": lambda: (200, {"ok": True}),
            "handle_system_mode": lambda: (200, {"ok": True}),
        },
        "routes.validation": {
            "handle_validation_backtest": lambda query: (200, {"query": query}),
            "handle_validation_diagnostics": lambda query: (200, {"query": query}),
            "handle_validation_walk_forward": lambda query: (200, {"query": query}),
        },
        "routes.watchlist": {
            "handle_watchlist_actions": lambda payload: (200, {"payload": payload}),
            "handle_watchlist_get": lambda: (200, {"ok": True}),
            "handle_watchlist_save": lambda payload: (200, {"payload": payload}),
        },
    }
    for module_name, attrs in modules.items():
        module = types.ModuleType(module_name)
        for attr_name, value in attrs.items():
            setattr(module, attr_name, value)
        sys.modules[module_name] = module


_install_server_route_stubs()

from fastapi.testclient import TestClient

from api_server import app


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
