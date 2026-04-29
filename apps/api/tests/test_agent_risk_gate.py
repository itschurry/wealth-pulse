from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.agent_risk_gate import evaluate_agent_decision_risk


BASE_DECISION = {
    "action": "BUY",
    "symbol": "005930",
    "confidence": 0.72,
    "risk": {
        "entry_price": 81000,
        "stop_loss": 79000,
        "take_profit": 84000,
        "max_position_ratio": 0.05,
    },
}
BASE_ACCOUNT = {
    "cash_krw": 2_000_000,
    "equity_krw": 10_000_000,
    "positions": [],
    "orders": [],
}
BASE_CONFIG = {
    "trading_mode": "paper",
    "enable_live_trading": False,
    "min_confidence": 0.7,
    "min_reward_risk_ratio": 1.3,
    "max_symbol_position_ratio": 0.1,
    "cooldown_minutes": 30,
    "allow_additional_buy": False,
}


class AgentRiskGateTests(unittest.TestCase):
    def test_buy_is_approved_when_all_checks_pass_in_paper_mode(self):
        result = evaluate_agent_decision_risk(
            decision=BASE_DECISION,
            account=BASE_ACCOUNT,
            config=BASE_CONFIG,
            recent_orders=[],
            now=dt.datetime(2026, 4, 29, 10, 0, tzinfo=dt.timezone.utc),
        )

        self.assertTrue(result["approved"])
        self.assertEqual("BUY", result["final_action"])
        self.assertEqual("approved", result["reason_code"])
        self.assertGreater(result["order_intent"]["quantity"], 0)

    def test_live_order_requires_enable_live_trading(self):
        config = {**BASE_CONFIG, "trading_mode": "live", "enable_live_trading": False}

        result = evaluate_agent_decision_risk(decision=BASE_DECISION, account=BASE_ACCOUNT, config=config)

        self.assertFalse(result["approved"])
        self.assertEqual("live_trading_disabled", result["reason_code"])

    def test_low_confidence_is_rejected_as_hold(self):
        decision = {**BASE_DECISION, "confidence": 0.4}

        result = evaluate_agent_decision_risk(decision=decision, account=BASE_ACCOUNT, config=BASE_CONFIG)

        self.assertFalse(result["approved"])
        self.assertEqual("HOLD", result["final_action"])
        self.assertEqual("confidence_below_minimum", result["reason_code"])

    def test_missing_stop_loss_is_rejected(self):
        decision = {**BASE_DECISION, "risk": {**BASE_DECISION["risk"], "stop_loss": 0}}

        result = evaluate_agent_decision_risk(decision=decision, account=BASE_ACCOUNT, config=BASE_CONFIG)

        self.assertFalse(result["approved"])
        self.assertEqual("stop_loss_required", result["reason_code"])

    def test_poor_reward_risk_is_rejected(self):
        decision = {**BASE_DECISION, "risk": {**BASE_DECISION["risk"], "take_profit": 82000}}

        result = evaluate_agent_decision_risk(decision=decision, account=BASE_ACCOUNT, config=BASE_CONFIG)

        self.assertFalse(result["approved"])
        self.assertEqual("reward_risk_below_minimum", result["reason_code"])

    def test_insufficient_cash_is_rejected(self):
        account = {**BASE_ACCOUNT, "cash_krw": 10_000}

        result = evaluate_agent_decision_risk(decision=BASE_DECISION, account=account, config=BASE_CONFIG)

        self.assertFalse(result["approved"])
        self.assertEqual("insufficient_cash", result["reason_code"])

    def test_existing_position_blocks_additional_buy_by_default(self):
        account = {**BASE_ACCOUNT, "positions": [{"code": "005930", "symbol": "005930", "market_value_krw": 400_000}]}

        result = evaluate_agent_decision_risk(decision=BASE_DECISION, account=account, config=BASE_CONFIG)

        self.assertFalse(result["approved"])
        self.assertEqual("additional_buy_blocked", result["reason_code"])

    def test_recent_same_symbol_order_is_rejected_by_cooldown(self):
        now = dt.datetime(2026, 4, 29, 10, 0, tzinfo=dt.timezone.utc)
        recent_orders = [{"symbol": "005930", "action": "BUY", "created_at": (now - dt.timedelta(minutes=10)).isoformat()}]

        result = evaluate_agent_decision_risk(
            decision=BASE_DECISION,
            account=BASE_ACCOUNT,
            config=BASE_CONFIG,
            recent_orders=recent_orders,
            now=now,
        )

        self.assertFalse(result["approved"])
        self.assertEqual("cooldown_active", result["reason_code"])


if __name__ == "__main__":
    unittest.main()
