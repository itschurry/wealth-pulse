from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import signals as signals_route


class SignalsRouteTests(unittest.TestCase):
    def test_handle_signals_rank_uses_runtime_account_context(self):
        execution_service = SimpleNamespace(
            paper_engine_status=lambda: (200, {"account": {"cash_krw": 12_500_000, "positions": [{"code": "005930"}]}})
        )

        with patch.object(signals_route, "get_execution_service", return_value=execution_service), \
             patch.object(signals_route, "build_signal_book", return_value={"signals": [{"code": "005930"}], "generated_at": "2026-04-02T18:00:00+09:00"}) as mock_build:
            status, payload = signals_route.handle_signals_rank({"limit": ["10"], "market": ["KOSPI"]})

        self.assertEqual(200, status)
        self.assertTrue(payload["signals"])
        mock_build.assert_called_once_with(
            markets=["KOSPI"],
            cfg={},
            account={"cash_krw": 12_500_000, "positions": [{"code": "005930"}]},
        )

    def test_handle_signal_detail_uses_runtime_account_context(self):
        execution_service = SimpleNamespace(
            paper_engine_status=lambda: (200, {"account": {"cash_krw": 7_500_000, "positions": []}})
        )
        signal_payload = {
            "generated_at": "2026-04-02T18:05:00+09:00",
            "signals": [
                {"code": "005930", "final_action": "review_for_entry"},
                {"code": "000660", "final_action": "watch_only"},
            ],
        }

        with patch.object(signals_route, "get_execution_service", return_value=execution_service), \
             patch.object(signals_route, "build_signal_book", return_value=signal_payload) as mock_build:
            status, payload = signals_route.handle_signal_detail("/api/signals/005930")

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("005930", payload["signal"]["code"])
        mock_build.assert_called_once_with(
            markets=["KOSPI", "NASDAQ"],
            cfg={},
            account={"cash_krw": 7_500_000, "positions": []},
        )


if __name__ == "__main__":
    unittest.main()
