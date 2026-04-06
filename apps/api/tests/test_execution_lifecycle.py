from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.execution_lifecycle import (
    LIFECYCLE_ACCEPTED,
    LIFECYCLE_FAILED,
    LIFECYCLE_FILLED,
    LIFECYCLE_INTENT,
    LIFECYCLE_SUBMITTED,
    build_execution_events,
    summarize_execution_events,
)


class ExecutionLifecycleTests(unittest.TestCase):
    def test_build_execution_events_for_successful_order(self):
        events = build_execution_events({
            "market": "KOSPI",
            "code": "005930",
            "side": "buy",
            "quantity": 2,
            "order_type": "market",
            "success": True,
            "timestamp": "2026-04-06T09:00:00+09:00",
            "submitted_at": "2026-04-06T09:00:01+09:00",
            "filled_at": "2026-04-06T09:00:03+09:00",
        })

        self.assertEqual(
            [LIFECYCLE_INTENT, LIFECYCLE_SUBMITTED, LIFECYCLE_ACCEPTED, LIFECYCLE_FILLED],
            [item["event_type"] for item in events],
        )
        self.assertTrue(all(item["order_id"] == events[0]["order_id"] for item in events))
        self.assertTrue(all(item["trace_id"] == events[0]["trace_id"] for item in events))

    def test_build_execution_events_for_failed_order(self):
        events = build_execution_events({
            "market": "NASDAQ",
            "code": "NVDA",
            "side": "buy",
            "quantity": 1,
            "order_type": "market",
            "success": False,
            "timestamp": "2026-04-06T09:01:00+09:00",
            "submitted_at": "2026-04-06T09:01:01+09:00",
            "reason_code": "insufficient_cash",
        })

        self.assertEqual(LIFECYCLE_FAILED, events[-1]["event_type"])
        self.assertEqual("insufficient_funds", events[-1]["reason_code"])

    def test_summarize_execution_events_counts_terminal_states(self):
        summary = summarize_execution_events([
            {"order_id": "1", "event_type": LIFECYCLE_INTENT, "timestamp": "2026-04-06T09:00:00+09:00"},
            {"order_id": "1", "event_type": LIFECYCLE_SUBMITTED, "timestamp": "2026-04-06T09:00:01+09:00"},
            {"order_id": "1", "event_type": LIFECYCLE_ACCEPTED, "timestamp": "2026-04-06T09:00:02+09:00"},
            {"order_id": "1", "event_type": LIFECYCLE_FILLED, "timestamp": "2026-04-06T09:00:03+09:00"},
            {"order_id": "2", "event_type": LIFECYCLE_FAILED, "timestamp": "2026-04-06T09:02:00+09:00", "reason_code": "risk_blocked"},
        ])

        self.assertEqual(1, summary["terminal_counts"]["filled"])
        self.assertEqual(1, summary["terminal_counts"]["failed"])
        self.assertEqual(1, summary["reason_counts"]["risk_blocked"])


if __name__ == "__main__":
    unittest.main()
