from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.trade_workflow import (
    build_workflow_summary,
    derive_order_workflow,
    derive_signal_workflow,
    enrich_order_payload,
    enrich_signal_payload,
)


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
        self.assertEqual("filled", result["lifecycle_state"])

    @patch("services.trade_workflow.lookup_company_listing")
    def test_enrich_signal_payload_uses_company_lookup_when_name_is_code(self, mock_lookup):
        mock_lookup.return_value = {
            "name": "삼성전자",
            "market": "KOSPI",
            "code": "005930",
        }
        result = enrich_signal_payload({
            "market": "",
            "code": "005930",
            "name": "005930",
            "signal_state": "entry",
            "entry_allowed": True,
            "final_action": "review_for_entry",
            "size_recommendation": {"quantity": 1},
        })

        self.assertEqual("order_ready", result["workflow_stage"])
        self.assertEqual("삼성전자", result["name"])
        self.assertEqual("KOSPI", result["market"])
        mock_lookup.assert_called_once_with(code="005930", market="")

    @patch("services.trade_workflow.lookup_company_listing")
    def test_enrich_signal_payload_keeps_existing_name(self, mock_lookup):
        result = enrich_signal_payload({
            "market": "KOSPI",
            "code": "005930",
            "name": "SK 하이닉스",
            "signal_state": "entry",
            "entry_allowed": False,
            "final_action": "blocked",
            "risk_check": {"reason_code": "DAILY_LOSS_LIMIT"},
        })

        self.assertEqual("SK 하이닉스", result["name"])
        self.assertEqual("KOSPI", result["market"])
        mock_lookup.assert_not_called()

    @patch("services.trade_workflow.lookup_company_listing")
    def test_enrich_order_payload_uses_company_lookup_when_name_missing(self, mock_lookup):
        mock_lookup.return_value = {
            "name": "엔비디아",
            "market": "NASDAQ",
            "code": "NVDA",
        }
        result = enrich_order_payload({
            "market": "",
            "code": "NVDA",
            "success": False,
            "reason_code": "insufficient_cash",
        })

        self.assertEqual("rejected", result["workflow_stage"])
        self.assertEqual("엔비디아", result["name"])
        self.assertEqual("NASDAQ", result["market"])
        self.assertEqual("insufficient_cash", result["execution_status"])
        self.assertEqual("failed", result["lifecycle_state"])

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
        self.assertEqual(1, summary["lifecycle_counts"]["filled"])


if __name__ == "__main__":
    unittest.main()
