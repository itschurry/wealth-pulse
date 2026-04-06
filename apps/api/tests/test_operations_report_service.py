from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.operations_report_service import build_operations_report


class OperationsReportServiceTests(unittest.TestCase):
    def test_build_operations_report_counts_blocks_and_execution_results(self):
        signal_rows = [
            {
                "timestamp": "2026-04-06T09:00:00+09:00",
                "entry_allowed": False,
                "reason_codes": ["risk_blocked"],
                "risk_reason_code": "risk_blocked",
            },
            {
                "timestamp": "2026-04-06T09:01:00+09:00",
                "entry_allowed": False,
                "reason_codes": ["data_missing"],
                "risk_reason_code": "data_missing",
            },
        ]
        execution_rows = [
            {
                "timestamp": "2026-04-06T09:02:00+09:00",
                "event_type": "submitted",
                "strategy_id": "kr_momo",
                "strategy_name": "KR Momentum",
            },
            {
                "timestamp": "2026-04-06T09:03:00+09:00",
                "event_type": "filled",
                "strategy_id": "kr_momo",
                "strategy_name": "KR Momentum",
            },
            {
                "timestamp": "2026-04-06T09:04:00+09:00",
                "event_type": "failed",
                "strategy_id": "kr_momo",
                "strategy_name": "KR Momentum",
                "reason_code": "insufficient_funds",
            },
        ]

        with patch("services.operations_report_service._today_str", return_value="2026-04-06"), \
             patch("services.operations_report_service.read_signal_snapshots", return_value=signal_rows), \
             patch("services.operations_report_service.read_execution_events", return_value=execution_rows):
            result = build_operations_report(limit=50)

        self.assertEqual(2, result["report"]["today_signal_count"])
        self.assertEqual(2, result["report"]["blocked_count"])
        self.assertEqual(1, result["report"]["blocked_reason_counts"]["risk_blocked"])
        self.assertEqual(1, result["report"]["execution_counts"]["filled"])
        self.assertEqual(1, result["report"]["execution_counts"]["failed"])
        self.assertEqual("KR Momentum", result["report"]["strategy_performance"][0]["strategy_name"])
        self.assertTrue(any(item["alert_code"] == "data_missing" for item in result["alerts"]))


if __name__ == "__main__":
    unittest.main()
