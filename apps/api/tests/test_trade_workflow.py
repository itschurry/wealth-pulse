from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.trade_workflow import build_workflow_summary, derive_order_workflow, derive_signal_workflow


class TradeWorkflowTests(unittest.TestCase):
    def test_entry_signal_becomes_order_ready_when_review_and_size_exist(self):
        result = derive_signal_workflow({
            "market": "KOSPI",
            "code": "005930",
            "signal_state": "entry",
            "entry_allowed": True,
            "final_action": "review_for_entry",
            "size_recommendation": {"quantity": 3},
        })
        self.assertEqual("order_ready", result["workflow_stage"])
        self.assertTrue(result["orderable"])
        self.assertEqual("ready_for_order", result["execution_status"])

    def test_blocked_signal_stays_blocked(self):
        result = derive_signal_workflow({
            "market": "KOSPI",
            "code": "000660",
            "signal_state": "entry",
            "entry_allowed": False,
            "final_action": "blocked",
            "risk_check": {"reason_code": "DAILY_LOSS_LIMIT"},
        })
        self.assertEqual("blocked", result["workflow_stage"])
        self.assertEqual("DAILY_LOSS_LIMIT", result["blocked_reason"])

    def test_order_workflow_marks_success_as_filled(self):
        result = derive_order_workflow({
            "market": "NASDAQ",
            "code": "NVDA",
            "success": True,
            "filled_at": "2026-04-06T09:10:00+09:00",
        })
        self.assertEqual("filled", result["workflow_stage"])
        self.assertEqual("filled", result["execution_status"])

    def test_workflow_summary_promotes_recent_order_state(self):
        summary = build_workflow_summary(
            signals=[{
                "market": "KOSPI",
                "code": "005930",
                "signal_state": "entry",
                "entry_allowed": True,
                "final_action": "review_for_entry",
                "size_recommendation": {"quantity": 2},
                "fetched_at": "2026-04-06T09:00:00+09:00",
            }],
            orders=[{
                "market": "KOSPI",
                "code": "005930",
                "success": True,
                "side": "buy",
                "filled_at": "2026-04-06T09:05:00+09:00",
                "submitted_at": "2026-04-06T09:04:00+09:00",
            }],
        )
        self.assertEqual(1, summary["counts"]["filled"])
        self.assertEqual("filled", summary["items"][0]["workflow_stage"])


if __name__ == "__main__":
    unittest.main()
