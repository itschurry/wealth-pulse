from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.execution_service import _live_trading_approved, handle_runtime_engine_start
from services.system_mode_service import get_mode_status


class LiveTradingApprovalTests(unittest.TestCase):
    def test_live_start_requires_explicit_manual_approval(self) -> None:
        with patch.dict(os.environ, {"EXECUTION_MODE": "live", "LIVE_TRADING_APPROVED": "false"}, clear=False):
            status, payload = handle_runtime_engine_start({})

        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "live_trading_manual_approval_required")

    def test_approval_is_true_only_for_explicit_true(self) -> None:
        with patch.dict(os.environ, {"LIVE_TRADING_APPROVED": "true"}, clear=False):
            self.assertTrue(_live_trading_approved())
        with patch.dict(os.environ, {"LIVE_TRADING_APPROVED": "1"}, clear=False):
            self.assertFalse(_live_trading_approved())

    def test_mode_status_exposes_manual_approval_state(self) -> None:
        with patch.dict(os.environ, {"EXECUTION_MODE": "paper", "LIVE_TRADING_APPROVED": "false"}, clear=False):
            status = get_mode_status()

        self.assertEqual(status["current_mode"], "paper")
        self.assertFalse(status["live_trading_approved"])
        self.assertTrue(status["manual_live_approval_required"])


if __name__ == "__main__":
    unittest.main()
