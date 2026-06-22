from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.execution_service import _allows_rotation_candidate


class ExecutionRotationTests(unittest.TestCase):
    def test_watch_bluechip_high_score_can_rotate_when_position_limit_blocks_entry(self) -> None:
        candidate = {
            "code": "000660",
            "market": "KOSPI",
            "score": 98,
            "bluechip": True,
            "research_score": 0.82,
            "research_status": "healthy",
            "final_action": "watch_only",
            "size_recommendation": {"quantity": 0, "reason": "signal_only"},
            "final_action_snapshot": {
                "agent_decision": {"decision": "agent_buy_watch"},
            },
        }

        allowed = _allows_rotation_candidate(
            candidate,
            signal_state="watch",
            entry_allowed=False,
            order_qty=0,
            position_only_blocked=False,
        )

        self.assertTrue(allowed)

    def test_ordinary_watch_candidate_does_not_rotate(self) -> None:
        candidate = {
            "code": "123456",
            "market": "KOSPI",
            "score": 72,
            "bluechip": False,
            "research_score": 0.4,
            "research_status": "healthy",
            "final_action": "watch_only",
            "size_recommendation": {"quantity": 0, "reason": "signal_only"},
        }

        allowed = _allows_rotation_candidate(
            candidate,
            signal_state="watch",
            entry_allowed=False,
            order_qty=0,
            position_only_blocked=False,
        )

        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
