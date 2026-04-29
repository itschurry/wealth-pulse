from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.agent_schemas import parse_hermes_decision


class AgentSchemasTests(unittest.TestCase):
    def test_valid_buy_decision_is_normalized(self):
        result = parse_hermes_decision('''{
          "action": "buy",
          "symbol": "005930",
          "confidence": 0.72,
          "reason_summary": "삼성전자 단기 수급 개선",
          "evidence": ["20일선 위", "거래량 증가"],
          "risk": {
            "entry_price": 81000,
            "stop_loss": 79000,
            "take_profit": 84000,
            "max_position_ratio": 0.05
          }
        }''')

        self.assertTrue(result["valid"])
        self.assertEqual([], result["errors"])
        self.assertEqual("BUY", result["decision"]["action"])
        self.assertEqual("005930", result["decision"]["symbol"])
        self.assertEqual(0.72, result["decision"]["confidence"])
        self.assertEqual(79000.0, result["decision"]["risk"]["stop_loss"])

    def test_invalid_json_becomes_hold_with_parse_error(self):
        result = parse_hermes_decision("삼성전자 BUY, 신뢰도 0.72")

        self.assertFalse(result["valid"])
        self.assertIn("parse_error", result["errors"])
        self.assertEqual("HOLD", result["decision"]["action"])
        self.assertEqual(0.0, result["decision"]["confidence"])

    def test_invalid_action_becomes_hold_and_records_error(self):
        result = parse_hermes_decision({"action": "STRONG_BUY", "symbol": "005930", "confidence": 0.8})

        self.assertFalse(result["valid"])
        self.assertIn("invalid_action", result["errors"])
        self.assertEqual("HOLD", result["decision"]["action"])
        self.assertEqual("005930", result["decision"]["symbol"])

    def test_confidence_is_clamped_and_risk_defaults_to_zero(self):
        result = parse_hermes_decision({"action": "SELL", "symbol": "abc", "confidence": 1.7, "risk": {}})

        self.assertTrue(result["valid"])
        self.assertEqual("SELL", result["decision"]["action"])
        self.assertEqual("ABC", result["decision"]["symbol"])
        self.assertEqual(1.0, result["decision"]["confidence"])
        self.assertEqual(0.0, result["decision"]["risk"]["stop_loss"])


if __name__ == "__main__":
    unittest.main()
