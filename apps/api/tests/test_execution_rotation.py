from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.execution_service import (
    _allows_rotation_candidate,
    _candidate_unit_price_local,
    _promote_priority_candidate_for_entry,
    _should_attempt_rotation,
)


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

    def test_watch_bluechip_is_promoted_to_entry_when_slot_and_cash_exist(self) -> None:
        candidate = {
            "code": "000660",
            "market": "KOSPI",
            "score": 98,
            "bluechip": True,
            "research_score": 0.82,
            "research_status": "healthy",
            "final_action": "watch_only",
            "size_recommendation": {"quantity": 0, "reason": "signal_only"},
            "technical_snapshot": {"current_price": 100000},
            "risk_inputs": {"stop_loss_pct": 5},
            "ev_metrics": {"expected_value": 6.0, "reliability": "high"},
            "final_action_snapshot": {
                "agent_decision": {"decision": "agent_buy_watch"},
            },
        }
        account = {
            "cash_krw": 10000000,
            "equity_krw": 10000000,
            "positions": [],
        }
        cfg = {
            "allocation_mode": "concentrated",
            "risk_per_trade_pct": 0.8,
            "bluechip_risk_per_trade_pct": 1.5,
            "max_symbol_weight_pct": 30.0,
            "max_sector_weight_pct": 50.0,
            "max_market_exposure_pct": 95.0,
        }

        promoted = _promote_priority_candidate_for_entry(candidate, account, cfg)

        self.assertTrue(promoted["entry_allowed"])
        self.assertEqual(promoted["active_entry_reason"], "priority_bluechip_entry")
        self.assertGreater(promoted["size_recommendation"]["quantity"], 0)

    def test_rotation_runs_when_slots_remain_but_priority_candidate_needs_cash(self) -> None:
        candidate = {
            "code": "000660",
            "market": "KOSPI",
            "score": 98,
            "bluechip": True,
            "research_score": 0.82,
            "research_status": "healthy",
            "final_action": "review_for_entry",
            "size_recommendation": {"quantity": 0, "reason": "exposure_or_cash_limit"},
            "final_action_snapshot": {
                "agent_decision": {"decision": "agent_buy_watch"},
            },
        }

        self.assertTrue(_should_attempt_rotation(1, [candidate]))

    def test_unit_price_uses_research_technical_features_when_quote_missing(self) -> None:
        candidate = {
            "code": "000660",
            "market": "KOSPI",
            "technical_snapshot": {"quote_error": "token_limited"},
            "layer_c": {
                "technical_features": {"current_price": 289000},
            },
        }

        self.assertEqual(_candidate_unit_price_local(candidate), 289000)

    def test_blocked_priority_candidate_can_rotate_when_block_is_size_related(self) -> None:
        candidate = {
            "code": "000660",
            "market": "KOSPI",
            "score": 98,
            "bluechip": True,
            "research_score": 0.82,
            "research_status": "healthy",
            "final_action": "blocked",
            "size_recommendation": {"quantity": 0, "reason": "invalid_unit_price"},
            "final_action_snapshot": {
                "agent_decision": {"decision": "agent_primary_buy"},
            },
        }

        self.assertTrue(_should_attempt_rotation(1, [candidate]))


if __name__ == "__main__":
    unittest.main()
