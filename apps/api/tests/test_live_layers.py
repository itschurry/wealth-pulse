from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.live_layers import build_layer_e_snapshot


def _base_research(**overrides: object) -> dict:
    payload = {
        "research_score": 0.82,
        "freshness": "fresh",
        "research_unavailable": False,
        "warnings": [],
        "rating": "overweight",
        "action": "buy",
        "confidence": 0.72,
        "validation": {"grade": "B"},
        "technical_features": {
            "close_vs_sma20": 1.04,
            "close_vs_sma60": 1.06,
            "volume_ratio": 1.2,
            "rsi14": 55,
        },
        "research_quality": {
            "source_quality_score": 0.8,
            "fresh_news_count": 1,
            "trusted_news_count": 1,
            "trusted_evidence_count": 1,
        },
        "data_quality": {
            "has_news": True,
            "has_recent_price": True,
            "has_technical_features": True,
        },
    }
    payload.update(overrides)
    return payload


class LiveLayerDecisionTests(unittest.TestCase):
    def test_hold_research_overrides_quant_entry(self) -> None:
        layer = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=91,
            research=_base_research(rating="hold", action="hold", research_score=0.62),
            risk={"blocked": False},
            timestamp="2026-06-22T04:25:00+00:00",
            source_context={"execution_mode": "agent_primary_quant_assisted"},
        )

        self.assertEqual(layer["final_action"], "watch_only")
        self.assertEqual(layer["decision_reason"], "agent_hold")
        self.assertFalse(layer["quant_decision"]["order_ready"])

    def test_weak_trend_blocks_quant_entry(self) -> None:
        layer = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=91,
            research=_base_research(
                technical_features={
                    "close_vs_sma20": 0.95,
                    "close_vs_sma60": 0.88,
                    "volume_ratio": 0.42,
                    "rsi14": 42,
                }
            ),
            risk={"blocked": False},
            timestamp="2026-06-22T04:25:00+00:00",
            source_context={"execution_mode": "agent_primary_quant_assisted"},
        )

        self.assertEqual(layer["final_action"], "watch_only")
        self.assertFalse(layer["quant_decision"]["order_ready"])
        self.assertEqual(layer["agent_decision"]["quality_gate"], "weak_trend_or_volume")

    def test_buy_watch_with_healthy_research_can_become_order_ready(self) -> None:
        layer = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=91,
            research=_base_research(
                action="buy_watch",
                confidence=0.9,
                technical_features={
                    "close_vs_sma20": 1.04,
                    "close_vs_sma60": 0.97,
                    "volume_ratio": 0.42,
                    "rsi14": 55,
                },
            ),
            risk={"blocked": False},
            timestamp="2026-07-01T02:25:00+00:00",
            source_context={"execution_mode": "agent_primary_quant_assisted"},
        )

        self.assertEqual(layer["final_action"], "review_for_entry")
        self.assertTrue(layer["agent_decision"]["order_ready"])

    def test_buy_watch_with_weak_trend_stays_watch_only(self) -> None:
        layer = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=91,
            research=_base_research(
                action="buy_watch",
                confidence=0.9,
                technical_features={
                    "close_vs_sma20": 0.98,
                    "close_vs_sma60": 0.97,
                    "volume_ratio": 0.42,
                    "rsi14": 55,
                },
            ),
            risk={"blocked": False},
            timestamp="2026-07-01T02:25:00+00:00",
            source_context={"execution_mode": "agent_primary_quant_assisted"},
        )

        self.assertEqual(layer["final_action"], "watch_only")
        self.assertFalse(layer["agent_decision"]["order_ready"])
        self.assertEqual(layer["agent_decision"]["quality_gate"], "weak_trend_or_volume")


if __name__ == "__main__":
    unittest.main()
