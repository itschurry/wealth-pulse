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
        },
        "routes.performance": {"handle_performance_summary": lambda: (200, {"ok": True})},
        "routes.optimization": {
            "handle_get_optimization_status": lambda: (200, {"ok": True}),
            "handle_get_optimized_params": lambda: (200, {"ok": True}),
            "handle_run_optimization": lambda payload=None: (200, {"ok": True, "payload": payload}),
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
            "handle_research_scanner_enrich_targets": lambda query: (200, {"query": query}),
            "handle_research_scanner_targets": lambda query: (200, {"query": query}),
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
        },
        "routes.reports_domain": {
            "handle_reports_explain": lambda date=None: (200, {"date": date}),
            "handle_reports_index": lambda: (200, {"ok": True}),
            "handle_reports_operations": lambda limit=500: (200, {"ok": True, "limit": limit}),
        },
        "routes.scanner": {"handle_scanner_status": lambda query: (200, {"query": query})},
        "routes.signals": {
            "handle_signal_detail": lambda path: (200, {"path": path}),
            "handle_signal_snapshots": lambda query: (200, {"query": query}),
            "handle_signals_rank": lambda query: (200, {"query": query}),
        },
        "routes.strategies": {
            "handle_strategy_metadata": lambda: (200, {"ok": True}),
            "handle_strategies_list": lambda query: (200, {"query": query}),
            "handle_strategy_detail": lambda path: (200, {"path": path}),
            "handle_strategy_delete": lambda payload: (200, {"payload": payload}),
            "handle_strategy_toggle": lambda payload: (200, {"payload": payload}),
            "handle_strategy_save": lambda payload: (200, {"payload": payload}),
            "handle_strategy_seed_defaults": lambda: (200, {"ok": True}),
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
            "handle_paper_history_clear": lambda payload: (200, {"payload": payload, "ok": True}),
            "handle_paper_workflow": lambda query: (200, {"query": query}),
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

from server import dispatch_get, dispatch_post

_remove_server_route_stubs(_INSTALLED_ROUTE_STUBS)


class ApiServerDispatchTests(unittest.TestCase):
    def test_dispatch_get_passes_date_query_to_analysis_handler(self):
        with patch("server.handle_analysis", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_get("/api/analysis", {"date": ["2026-03-20"]})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with("2026-03-20")

    def test_dispatch_get_routes_hanna_brief(self):
        with patch("server.handle_hanna_brief", return_value=(200, {"owner": "hanna"})) as mock_handler:
            result = dispatch_get("/api/hanna/brief", {"date": ["2026-04-02"]})

        self.assertEqual((200, {"owner": "hanna"}), result)
        mock_handler.assert_called_once_with("2026-04-02")

    def test_dispatch_get_routes_research_status(self):
        with patch("server.handle_research_status", return_value=(200, {"status": "healthy"})) as mock_handler:
            result = dispatch_get("/api/research/status", {"provider": ["openclaw"]})

        self.assertEqual((200, {"status": "healthy"}), result)
        mock_handler.assert_called_once_with({"provider": ["openclaw"]})

    def test_dispatch_get_routes_research_latest_snapshot(self):
        with patch("server.handle_research_latest_snapshot", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_get("/api/research/snapshots/latest", {"symbol": ["005930"], "market": ["KR"]})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with({"symbol": ["005930"], "market": ["KR"]})

    def test_dispatch_get_routes_research_snapshots(self):
        with patch("server.handle_research_snapshots", return_value=(200, {"ok": True, "snapshots": []})) as mock_handler:
            result = dispatch_get(
                "/api/research/snapshots",
                {
                    "symbol": ["005930"],
                    "market": ["KR"],
                    "provider": ["openclaw"],
                    "bucket_start": ["2026-04-03T09:00:00+09:00"],
                    "bucket_end": ["2026-04-03T10:00:00+09:00"],
                    "limit": ["10"],
                    "descending": ["0"],
                },
            )

        self.assertEqual((200, {"ok": True, "snapshots": []}), result)
        mock_handler.assert_called_once_with({
            "symbol": ["005930"],
            "market": ["KR"],
            "provider": ["openclaw"],
            "bucket_start": ["2026-04-03T09:00:00+09:00"],
            "bucket_end": ["2026-04-03T10:00:00+09:00"],
            "limit": ["10"],
            "descending": ["0"],
        })

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

    def test_dispatch_post_routes_run_optimization_payload(self):
        with patch("server.handle_run_optimization", return_value=(200, {"status": "started"})) as mock_handler:
            payload = {"query": {"market_scope": "nasdaq"}, "settings": {"trainingDays": 180}}
            result = dispatch_post("/api/run-optimization", payload)

        self.assertEqual((200, {"status": "started"}), result)
        mock_handler.assert_called_once_with(payload)

    def test_dispatch_get_routes_strategy_metadata(self):
        with patch("server.handle_strategy_metadata", return_value=(200, {"ok": True, "available_strategies": []})) as mock_handler:
            result = dispatch_get("/api/strategies/metadata", {})

        self.assertEqual((200, {"ok": True, "available_strategies": []}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_post_routes_research_ingest_bulk(self):
        with patch("server.handle_research_ingest_bulk", return_value=(200, {"accepted": 1})) as mock_handler:
            payload = {"provider": "openclaw", "items": []}
            result = dispatch_post("/api/research/ingest/bulk", payload)

        self.assertEqual((200, {"accepted": 1}), result)
        mock_handler.assert_called_once_with(payload)

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

    def test_dispatch_get_routes_strategies(self):
        with patch("server.handle_strategies_list", return_value=(200, {"ok": True, "count": 2})) as mock_handler:
            result = dispatch_get("/api/strategies", {"live_only": ["1"]})

        self.assertEqual((200, {"ok": True, "count": 2}), result)
        mock_handler.assert_called_once_with({"live_only": ["1"]})

    def test_dispatch_get_routes_strategy_detail(self):
        with patch("server.handle_strategy_detail", return_value=(200, {"ok": True, "item": {}})) as mock_handler:
            result = dispatch_get("/api/strategies/kr_momentum_v1", {})

        self.assertEqual((200, {"ok": True, "item": {}}), result)
        mock_handler.assert_called_once_with("/api/strategies/kr_momentum_v1")

    def test_dispatch_get_routes_scanner_status(self):
        with patch("server.handle_scanner_status", return_value=(200, {"ok": True, "count": 1})) as mock_handler:
            result = dispatch_get("/api/scanner/status", {"refresh": ["1"]})

        self.assertEqual((200, {"ok": True, "count": 1}), result)
        mock_handler.assert_called_once_with({"refresh": ["1"]})

    def test_dispatch_get_routes_universe(self):
        with patch("server.handle_universe_list", return_value=(200, {"ok": True, "count": 1})) as mock_handler:
            result = dispatch_get("/api/universe", {"refresh": ["1"]})

        self.assertEqual((200, {"ok": True, "count": 1}), result)
        mock_handler.assert_called_once_with({"refresh": ["1"]})

    def test_dispatch_get_routes_performance_summary(self):
        with patch("server.handle_performance_summary", return_value=(200, {"ok": True, "live": {}})) as mock_handler:
            result = dispatch_get("/api/performance/summary", {})

        self.assertEqual((200, {"ok": True, "live": {}}), result)
        mock_handler.assert_called_once_with()

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

    def test_dispatch_get_routes_validation_diagnostics(self):
        with patch("server.handle_validation_diagnostics", return_value=(200, {"ok": True, "research": {}})) as mock_handler:
            result = dispatch_get("/api/validation/diagnostics", {"lookback_days": ["365"]})

        self.assertEqual((200, {"ok": True, "research": {}}), result)
        mock_handler.assert_called_once_with({"lookback_days": ["365"]})

    def test_dispatch_get_routes_validation_settings(self):
        with patch("server.handle_validation_settings_get", return_value=(200, {"ok": True, "saved_at": "2026-04-01T08:00:00+09:00"})) as mock_handler:
            result = dispatch_get("/api/validation/settings", {})

        self.assertEqual((200, {"ok": True, "saved_at": "2026-04-01T08:00:00+09:00"}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_post_routes_validation_settings_actions(self):
        with patch("server.handle_validation_settings_save", return_value=(200, {"ok": True})) as mock_save, \
             patch("server.handle_validation_settings_reset", return_value=(200, {"ok": True, "saved_at": "2026-04-01T08:00:00+09:00"})) as mock_reset:
            save_result = dispatch_post("/api/validation/settings/save", {"query": {"market_scope": "kospi"}})
            reset_result = dispatch_post("/api/validation/settings/reset", {"ignored": True})

        self.assertEqual((200, {"ok": True}), save_result)
        self.assertEqual((200, {"ok": True, "saved_at": "2026-04-01T08:00:00+09:00"}), reset_result)
        mock_save.assert_called_once_with({"query": {"market_scope": "kospi"}})
        mock_reset.assert_called_once_with()

    def test_dispatch_get_routes_quant_ops_policy(self):
        with patch("server.handle_get_quant_ops_policy", return_value=(200, {"ok": True, "policy": {"version": 1}})) as mock_handler:
            result = dispatch_get("/api/quant-ops/policy", {})

        self.assertEqual((200, {"ok": True, "policy": {"version": 1}}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_quant_ops_workflow(self):
        with patch("server.handle_get_quant_ops_workflow", return_value=(200, {"ok": True, "stage_status": {}})) as mock_handler:
            result = dispatch_get("/api/quant-ops/workflow", {})

        self.assertEqual((200, {"ok": True, "stage_status": {}}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_reports_operations(self):
        with patch("server.handle_reports_operations", return_value=(200, {"ok": True, "report": {}})) as mock_handler:
            result = dispatch_get("/api/reports/operations", {"limit": ["120"]})

        self.assertEqual((200, {"ok": True, "report": {}}), result)
        mock_handler.assert_called_once_with(120)

    def test_dispatch_post_routes_quant_ops_policy_actions(self):
        with patch("server.handle_quant_ops_save_policy", return_value=(200, {"ok": True})) as mock_save, \
             patch("server.handle_quant_ops_reset_policy", return_value=(200, {"ok": True, "policy": {"version": 1}})) as mock_reset:
            save_result = dispatch_post("/api/quant-ops/policy/save", {"policy": {"version": 1}})
            reset_result = dispatch_post("/api/quant-ops/policy/reset", {})

        self.assertEqual((200, {"ok": True}), save_result)
        self.assertEqual((200, {"ok": True, "policy": {"version": 1}}), reset_result)
        mock_save.assert_called_once_with({"policy": {"version": 1}})
        mock_reset.assert_called_once_with()

    def test_dispatch_post_routes_strategy_actions(self):
        with patch("server.handle_strategy_toggle", return_value=(200, {"ok": True})) as mock_toggle, \
             patch("server.handle_strategy_save", return_value=(200, {"ok": True, "item": {"strategy_id": "kr"}})) as mock_save:
            toggle_result = dispatch_post("/api/strategies/toggle", {"strategy_id": "kr", "enabled": False})
            save_result = dispatch_post("/api/strategies/save", {"strategy_id": "kr"})

        self.assertEqual((200, {"ok": True}), toggle_result)
        self.assertEqual((200, {"ok": True, "item": {"strategy_id": "kr"}}), save_result)
        mock_toggle.assert_called_once_with({"strategy_id": "kr", "enabled": False})
        mock_save.assert_called_once_with({"strategy_id": "kr"})

    def test_dispatch_post_routes_paper_history_clear(self):
        with patch("server.handle_paper_history_clear", return_value=(200, {"ok": True, "clear_count": {"order_events": 2}})) as mock_handler:
            payload = {"clear_all": True}
            result = dispatch_post("/api/paper/history/clear", payload)

        self.assertEqual((200, {"ok": True, "clear_count": {"order_events": 2}}), result)
        mock_handler.assert_called_once_with(payload)

    def test_dispatch_post_routes_quant_ops_actions(self):
        with patch("server.handle_quant_ops_revalidate", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_post("/api/quant-ops/revalidate", {"query": {"market_scope": "kospi"}})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with({"query": {"market_scope": "kospi"}})

    def test_dispatch_returns_none_for_unknown_route(self):
        self.assertIsNone(dispatch_get("/api/unknown", {}))
        self.assertIsNone(dispatch_post("/api/unknown", {}))


if __name__ == "__main__":
    unittest.main()
