from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.portfolio import handle_portfolio_state


class PortfolioRouteTests(unittest.TestCase):
    def test_portfolio_state_propagates_account_failure_instead_of_ok_payload(self):
        service = Mock()
        service.paper_account.return_value = (500, {"ok": False, "error": "KIS balance unavailable"})

        with patch("routes.portfolio.get_execution_service", return_value=service):
            status, payload = handle_portfolio_state(refresh_quotes=False)

        self.assertEqual(500, status)
        self.assertFalse(payload["ok"])
        self.assertEqual("KIS balance unavailable", payload["error"])
        self.assertEqual("KIS balance unavailable", payload["account"]["error"])

    def test_portfolio_state_keeps_common_account_shape_on_success(self):
        service = Mock()
        account = {
            "mode": "real",
            "cash_krw": 1000.0,
            "equity_krw": 1200.0,
            "positions": [],
            "orders": [],
        }
        service.paper_account.return_value = (200, account)

        with (
            patch("routes.portfolio.get_execution_service", return_value=service),
            patch("routes.portfolio._context_snapshot", return_value=("neutral", "low")),
            patch("routes.portfolio.build_risk_guard_state", return_value={"status": "ok"}),
        ):
            status, payload = handle_portfolio_state(refresh_quotes=False)

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(account, payload["account"])
        self.assertEqual({"status": "ok"}, payload["risk_guard_state"])


if __name__ == "__main__":
    unittest.main()
