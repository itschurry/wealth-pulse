from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.trade_workflow import derive_order_workflow


class TradeWorkflowTests(unittest.TestCase):
    def test_success_without_filled_at_stays_submitted(self) -> None:
        workflow = derive_order_workflow({
            "success": True,
            "side": "sell",
            "code": "001210",
            "market": "KOSPI",
            "submitted_at": "2026-07-10T06:20:57+00:00",
            "filled_at": "",
        })

        self.assertEqual(workflow["workflow_stage"], "order_sent")
        self.assertEqual(workflow["execution_status"], "submitted")
        self.assertEqual(workflow["lifecycle_state"], "submitted")

    def test_success_with_filled_at_is_filled(self) -> None:
        workflow = derive_order_workflow({
            "success": True,
            "side": "sell",
            "code": "001210",
            "market": "KOSPI",
            "submitted_at": "2026-07-10T06:20:57+00:00",
            "filled_at": "2026-07-10T06:20:58+00:00",
        })

        self.assertEqual(workflow["workflow_stage"], "filled")
        self.assertEqual(workflow["execution_status"], "filled")
        self.assertEqual(workflow["lifecycle_state"], "filled")


if __name__ == "__main__":
    unittest.main()
