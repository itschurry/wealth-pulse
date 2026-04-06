from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.candidate_selector import normalize_candidate_selection_config, select_market_candidates


class CandidateSelectorRuntimeFieldsTests(unittest.TestCase):
    def test_today_picks_preserve_runtime_fields_needed_by_strategy_engine(self):
        cfg = normalize_candidate_selection_config({})
        candidates = select_market_candidates(
            market="KOSPI",
            cfg=cfg,
            today_picks={
                "auto_candidates": [
                    {
                        "code": "005930",
                        "name": "삼성전자",
                        "market": "KOSPI",
                        "sector": "반도체",
                        "signal": "추천",
                        "score": 77.0,
                        "confidence": 81.0,
                        "gate_status": "passed",
                        "reasons": ["volume_breakout"],
                        "risks": ["earnings_week"],
                        "ai_thesis": "거래량이 붙는 박스권 상단 돌파",
                        "technical_snapshot": {
                            "current_price": 71200,
                            "volume_avg20": 2500000,
                            "volume_ratio": 1.6,
                        },
                    }
                ]
            },
            recommendations={},
        )

        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertEqual("반도체", candidate["sector"])
        self.assertEqual(81.0, candidate["confidence"])
        self.assertEqual(71200, candidate["technical_snapshot"]["current_price"])
        self.assertEqual(2500000, candidate["technical_snapshot"]["volume_avg20"])
        self.assertEqual(["volume_breakout"], candidate["reasons"])
        self.assertEqual(["earnings_week"], candidate["risks"])
        self.assertEqual("거래량이 붙는 박스권 상단 돌파", candidate["ai_thesis"])


if __name__ == "__main__":
    unittest.main()
