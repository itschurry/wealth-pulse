from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.agent_decision_provider import build_trade_decision_prompt, call_hermes_trade_decision, research_analysis_to_trade_decision


class AgentDecisionProviderTests(unittest.TestCase):
    def test_research_analysis_buy_maps_to_trade_decision_schema(self):
        decision = research_analysis_to_trade_decision(
            {
                "symbol": "005930",
                "market": "KOSPI",
                "action": "buy_watch",
                "confidence": 0.76,
                "summary": "실적 개선 기대",
                "evidence": [{"title": "뉴스"}],
                "trade_plan": {
                    "entry_price": 81000,
                    "stop_loss": 79000,
                    "take_profit": 85000,
                    "size_intent_pct": 4.5,
                },
            },
            {"symbol": "005930", "market": "KOSPI"},
        )

        self.assertEqual("BUY", decision["action"])
        self.assertEqual("005930", decision["symbol"])
        self.assertEqual("KOSPI", decision["market"])
        self.assertEqual(0.76, decision["confidence"])
        self.assertEqual(0.045, decision["risk"]["max_position_ratio"])
        self.assertIn("뉴스", decision["evidence"])

    def test_research_analysis_block_maps_to_hold(self):
        decision = research_analysis_to_trade_decision(
            {"symbol": "005930", "action": "block", "confidence": 0.8, "summary": "리스크 큼"},
            {"symbol": "005930", "market": "KOSPI"},
        )

        self.assertEqual("HOLD", decision["action"])
        self.assertEqual("리스크 큼", decision["reason_summary"])

    def test_trade_decision_prompt_enforces_no_orders(self):
        prompt = build_trade_decision_prompt({"symbol": "005930", "market": "KOSPI"}, [])

        self.assertIn("Return ONLY one JSON object", prompt)
        self.assertIn("Do not place orders", prompt)
        self.assertIn("BUY", prompt)
        self.assertIn("SELL", prompt)
        self.assertIn("HOLD", prompt)

    def test_call_hermes_trade_decision_parses_agent_output(self):
        raw = '{"action":"BUY","symbol":"005930","market":"KOSPI","confidence":0.8,"reason_summary":"ok","evidence":["chart"],"risk":{"entry_price":81000,"stop_loss":79000,"take_profit":85000,"max_position_ratio":0.05}}'
        with patch("services.agent_decision_provider.call_hermes_agent", return_value=raw) as mock_call:
            parsed = call_hermes_trade_decision({"symbol": "005930", "market": "KOSPI"}, [], timeout=5)

        self.assertEqual("BUY", parsed["action"])
        self.assertEqual("KOSPI", parsed["market"])
        self.assertTrue(mock_call.called)


if __name__ == "__main__":
    unittest.main()
