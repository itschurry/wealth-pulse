from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from scripts.openai_research_runner import _merge_analysis_with_target
from services import research_source_enricher as enricher


class ResearchSourceEnricherTests(unittest.TestCase):
    def test_source_pack_merges_required_entry_technicals(self) -> None:
        original_news = enricher.fetch_google_news_inputs
        original_dart = enricher.fetch_dart_disclosure_evidence
        original_fdr = enricher.fetch_fdr_technical_features
        enricher.fetch_google_news_inputs = lambda **_: []
        enricher.fetch_dart_disclosure_evidence = lambda **_: []
        enricher.fetch_fdr_technical_features = lambda **_: {
            "current_price": 100000,
            "close": 100000,
            "close_vs_sma20": 1.04,
            "close_vs_sma60": 1.08,
            "volume_ratio": 1.35,
            "rsi14": 58.0,
            "source": "finance-datareader",
        }
        try:
            pack = enricher.build_research_source_pack(
                {
                    "symbol": "000660",
                    "market": "KOSPI",
                    "name": "SK하이닉스",
                    "technical_snapshot": {
                        "current_price": 101000,
                        "change_pct": 3.2,
                        "source": "naver_mobile_stock",
                    },
                }
            )
        finally:
            enricher.fetch_google_news_inputs = original_news
            enricher.fetch_dart_disclosure_evidence = original_dart
            enricher.fetch_fdr_technical_features = original_fdr

        technical = pack["technical_features"]
        self.assertEqual(technical["current_price"], 101000)
        self.assertEqual(technical["change_pct"], 3.2)
        self.assertEqual(technical["close_vs_sma20"], 1.04)
        self.assertEqual(technical["close_vs_sma60"], 1.08)
        self.assertEqual(technical["volume_ratio"], 1.35)
        self.assertEqual(technical["source"], "naver_mobile_stock+finance-datareader")

    def test_merge_analysis_preserves_source_pack_technicals(self) -> None:
        merged = _merge_analysis_with_target(
            {
                "rating": "overweight",
                "action": "buy",
                "technical_features": {},
                "data_quality": {},
            },
            {
                "symbol": "000660",
                "market": "KOSPI",
                "technical_snapshot": {"current_price": 101000, "change_pct": 3.2},
                "source_pack": {
                    "technical_features": {
                        "current_price": 100000,
                        "close_vs_sma20": 1.04,
                        "close_vs_sma60": 1.08,
                        "volume_ratio": 1.35,
                        "rsi14": 58.0,
                    }
                },
            },
        )

        technical = merged["technical_features"]
        self.assertEqual(technical["current_price"], 101000)
        self.assertEqual(technical["close_vs_sma20"], 1.04)
        self.assertEqual(technical["close_vs_sma60"], 1.08)
        self.assertEqual(technical["volume_ratio"], 1.35)
        self.assertEqual(technical["rsi14"], 58.0)


if __name__ == "__main__":
    unittest.main()
