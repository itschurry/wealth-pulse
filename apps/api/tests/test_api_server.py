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

from server import dispatch_get, dispatch_post


class ApiServerDispatchTests(unittest.TestCase):
    def test_dispatch_get_passes_date_query_to_analysis_handler(self):
        with patch("server.handle_analysis", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_get("/api/analysis", {"date": ["2026-03-20"]})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with("2026-03-20")

    def test_dispatch_get_extracts_stock_code_and_market(self):
        with patch("server.handle_stock_price", return_value=(200, {"price": 1})) as mock_handler:
            result = dispatch_get("/api/stock/005930", {"market": ["KOSPI"]})

        self.assertEqual((200, {"price": 1}), result)
        mock_handler.assert_called_once_with("005930", "KOSPI")

    def test_dispatch_get_normalizes_paper_account_refresh_flag(self):
        with patch("server.handle_paper_account", return_value=(200, {"ok": True})) as mock_handler:
            dispatch_get("/api/paper/account", {"refresh": ["0"]})

        mock_handler.assert_called_once_with(False)

    def test_dispatch_post_calls_handlers_without_payload_when_expected(self):
        with patch("server.handle_paper_engine_stop", return_value=(200, {"stopped": True})) as mock_handler:
            result = dispatch_post("/api/paper/engine/stop", {"ignored": True})

        self.assertEqual((200, {"stopped": True}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_system_mode(self):
        with patch("server.handle_system_mode", return_value=(200, {"ok": True, "current_mode": "paper"})) as mock_handler:
            result = dispatch_get("/api/system/mode", {})

        self.assertEqual((200, {"ok": True, "current_mode": "paper"}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_domain_signals(self):
        with patch("server.handle_signals_rank", return_value=(200, {"ok": True, "count": 1})) as mock_handler:
            result = dispatch_get("/api/signals/rank", {"limit": ["10"]})

        self.assertEqual((200, {"ok": True, "count": 1}), result)
        mock_handler.assert_called_once_with({"limit": ["10"]})

    def test_dispatch_get_routes_signal_snapshots(self):
        with patch("server.handle_signal_snapshots", return_value=(200, {"ok": True, "count": 1})) as mock_handler:
            result = dispatch_get("/api/signals/snapshots", {"limit": ["20"]})

        self.assertEqual((200, {"ok": True, "count": 1}), result)
        mock_handler.assert_called_once_with({"limit": ["20"]})

    def test_dispatch_get_routes_domain_signal_detail(self):
        with patch("server.handle_signal_detail", return_value=(200, {"ok": True, "signal": {}})) as mock_handler:
            result = dispatch_get("/api/signals/005930", {})

        self.assertEqual((200, {"ok": True, "signal": {}}), result)
        mock_handler.assert_called_once_with("/api/signals/005930")

    def test_dispatch_get_routes_domain_portfolio_refresh_flag(self):
        with patch("server.handle_portfolio_state", return_value=(200, {"ok": True})) as mock_handler:
            dispatch_get("/api/portfolio/state", {"refresh": ["0"]})

        mock_handler.assert_called_once_with(False)

    def test_dispatch_get_routes_notifications_status(self):
        with patch("server.handle_notifications_status", return_value=(200, {"ok": True, "channel": "telegram"})) as mock_handler:
            result = dispatch_get("/api/system/notifications/status", {})

        self.assertEqual((200, {"ok": True, "channel": "telegram"}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_validation_diagnostics(self):
        with patch("server.handle_validation_diagnostics", return_value=(200, {"ok": True, "research": {}})) as mock_handler:
            result = dispatch_get("/api/validation/diagnostics", {"lookback_days": ["365"]})

        self.assertEqual((200, {"ok": True, "research": {}}), result)
        mock_handler.assert_called_once_with({"lookback_days": ["365"]})

    def test_dispatch_get_routes_quant_ops_workflow(self):
        with patch("server.handle_get_quant_ops_workflow", return_value=(200, {"ok": True, "stage_status": {}})) as mock_handler:
            result = dispatch_get("/api/quant-ops/workflow", {})

        self.assertEqual((200, {"ok": True, "stage_status": {}}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_post_routes_quant_ops_actions(self):
        with patch("server.handle_quant_ops_revalidate", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_post("/api/quant-ops/revalidate", {"query": {"market_scope": "kospi"}})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with({"query": {"market_scope": "kospi"}})

    def test_dispatch_post_routes_quant_ops_symbol_actions(self):
        with patch("server.handle_quant_ops_set_symbol_approval", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_post("/api/quant-ops/set-symbol-approval", {"symbol": "AAPL", "status": "approved"})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with({"symbol": "AAPL", "status": "approved"})

    def test_dispatch_returns_none_for_unknown_route(self):
        self.assertIsNone(dispatch_get("/api/unknown", {}))
        self.assertIsNone(dispatch_post("/api/unknown", {}))


if __name__ == "__main__":
    unittest.main()
