from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.research_agent_payload import build_agent_research_ingest_payload


class ResearchAgentPayloadTests(unittest.TestCase):
    def test_build_agent_payload_wraps_single_hermes_analysis_as_v2_snapshot(self):
        payload = build_agent_research_ingest_payload({
            "symbol": "005930",
            "market": "KOSPI",
            "generated_at": "2026-04-29T10:15:00+09:00",
            "confidence": 0.83,
            "rating": "strong_buy",
            "action": "buy",
            "summary": "뉴스와 차트가 모두 우호적인 고확신 매수 후보.",
            "bull_case": ["AI 메모리 수요", "20일선 위 추세 유지"],
            "bear_case": ["환율 변동성"],
            "technical_features": {"close_vs_sma20": 1.04, "volume_ratio": 1.6, "rsi14": 61.0},
            "news_inputs": [{"title": "AI memory demand", "url": "https://example.com/news"}],
            "evidence": [{"type": "news", "summary": "AI memory demand cited"}],
            "trade_plan": {"entry_style": "staged", "size_intent_pct": 12.5},
        })

        self.assertEqual("default", payload["provider"])
        self.assertEqual("v2", payload["schema_version"])
        self.assertEqual("hermes-agent", payload["source"])
        self.assertEqual(1, len(payload["items"]))
        item = payload["items"][0]
        self.assertEqual("005930", item["symbol"])
        self.assertEqual("KOSPI", item["market"])
        self.assertEqual("strong_buy", item["rating"])
        self.assertEqual("buy", item["action"])
        self.assertEqual(0.83, item["research_score"])
        self.assertEqual(0.83, item["confidence"])
        self.assertEqual("hermes_agent", item["candidate_source"])
        self.assertTrue(item["data_quality"]["has_news"])
        self.assertTrue(item["data_quality"]["has_technical_features"])
        self.assertEqual("agent_research", item["data_quality"]["analysis_mode"])
        self.assertIn("agent_research", item["tags"])
        self.assertEqual(5.0, item["trade_plan"]["size_intent_pct"])
        self.assertEqual("risk_guard_clamped", item["trade_plan"]["sizing"])

    def test_build_agent_payload_rejects_buy_without_evidence(self):
        with self.assertRaisesRegex(ValueError, "evidence_required_for_buy_intent"):
            build_agent_research_ingest_payload({
                "symbol": "AAPL",
                "market": "NASDAQ",
                "generated_at": "2026-04-29T10:15:00+09:00",
                "confidence": 0.88,
                "rating": "strong_buy",
                "action": "buy",
                "summary": "high conviction but no evidence",
                "technical_features": {"close_vs_sma20": 1.02},
                "evidence": [],
            })

    def test_build_agent_payload_rejects_buy_without_technical_features(self):
        with self.assertRaisesRegex(ValueError, "technical_features_required_for_buy_intent"):
            build_agent_research_ingest_payload({
                "symbol": "MSFT",
                "market": "NASDAQ",
                "generated_at": "2026-04-29T10:15:00+09:00",
                "confidence": 0.8,
                "rating": "overweight",
                "action": "buy_watch",
                "summary": "news only, no chart pack",
                "news_inputs": [{"title": "product launch"}],
                "evidence": [{"type": "news", "summary": "launch"}],
            })


if __name__ == "__main__":
    unittest.main()
