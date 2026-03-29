from __future__ import annotations

import unittest
from unittest.mock import patch

from api.server import dispatch_get, dispatch_post


class ApiServerDispatchTests(unittest.TestCase):
    def test_dispatch_get_passes_date_query_to_analysis_handler(self):
        with patch("api.server.handle_analysis", return_value=(200, {"ok": True})) as mock_handler:
            result = dispatch_get("/api/analysis", {"date": ["2026-03-20"]})

        self.assertEqual((200, {"ok": True}), result)
        mock_handler.assert_called_once_with("2026-03-20")

    def test_dispatch_get_extracts_stock_code_and_market(self):
        with patch("api.server.handle_stock_price", return_value=(200, {"price": 1})) as mock_handler:
            result = dispatch_get("/api/stock/005930", {"market": ["KOSPI"]})

        self.assertEqual((200, {"price": 1}), result)
        mock_handler.assert_called_once_with("005930", "KOSPI")

    def test_dispatch_get_normalizes_paper_account_refresh_flag(self):
        with patch("api.server.handle_paper_account", return_value=(200, {"ok": True})) as mock_handler:
            dispatch_get("/api/paper/account", {"refresh": ["0"]})

        mock_handler.assert_called_once_with(False)

    def test_dispatch_post_calls_handlers_without_payload_when_expected(self):
        with patch("api.server.handle_paper_engine_stop", return_value=(200, {"stopped": True})) as mock_handler:
            result = dispatch_post("/api/paper/engine/stop", {"ignored": True})

        self.assertEqual((200, {"stopped": True}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_system_mode(self):
        with patch("api.server.handle_system_mode", return_value=(200, {"ok": True, "current_mode": "paper"})) as mock_handler:
            result = dispatch_get("/api/system/mode", {})

        self.assertEqual((200, {"ok": True, "current_mode": "paper"}), result)
        mock_handler.assert_called_once_with()

    def test_dispatch_get_routes_domain_signals(self):
        with patch("api.server.handle_signals_rank", return_value=(200, {"ok": True, "count": 1})) as mock_handler:
            result = dispatch_get("/api/signals/rank", {"limit": ["10"]})

        self.assertEqual((200, {"ok": True, "count": 1}), result)
        mock_handler.assert_called_once_with({"limit": ["10"]})

    def test_dispatch_get_routes_domain_signal_detail(self):
        with patch("api.server.handle_signal_detail", return_value=(200, {"ok": True, "signal": {}})) as mock_handler:
            result = dispatch_get("/api/signals/005930", {})

        self.assertEqual((200, {"ok": True, "signal": {}}), result)
        mock_handler.assert_called_once_with("/api/signals/005930")

    def test_dispatch_get_routes_domain_portfolio_refresh_flag(self):
        with patch("api.server.handle_portfolio_state", return_value=(200, {"ok": True})) as mock_handler:
            dispatch_get("/api/portfolio/state", {"refresh": ["0"]})

        mock_handler.assert_called_once_with(False)

    def test_dispatch_returns_none_for_unknown_route(self):
        self.assertIsNone(dispatch_get("/api/unknown", {}))
        self.assertIsNone(dispatch_post("/api/unknown", {}))


if __name__ == "__main__":
    unittest.main()
