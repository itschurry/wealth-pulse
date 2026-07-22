from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routes.engine import handle_engine_summary


class EngineSummaryTests(unittest.TestCase):
    def test_uses_hydrated_runtime_status_for_today_pnl(self) -> None:
        service = Mock()
        service.runtime_engine_status.return_value = (200, {
            "ok": True,
            "execution_mode": "paper",
            "state": {
                "running": True,
                "today_realized_pnl": 5984.76,
                "current_equity": 5_187_051.62,
            },
            "account": {
                "mode": "paper",
                "equity_krw": 5_187_051.62,
                "cash_krw": 5_187_051.62,
                "positions": [],
            },
        })
        with (
            patch("routes.engine.get_execution_service", return_value=service),
            patch("routes.engine.list_strategy_scans", return_value=[]),
            patch("routes.engine._context_snapshot", return_value=("neutral", "normal")),
            patch("routes.engine.get_mode_status", return_value={"current_mode": "paper"}),
        ):
            status, payload = handle_engine_summary()

        self.assertEqual(status, 200)
        self.assertEqual(payload["execution"]["state"]["today_realized_pnl"], 5984.76)
        self.assertEqual(payload["execution"]["account"]["equity_krw"], 5_187_051.62)


if __name__ == "__main__":
    unittest.main()
