from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import signal_service as svc


class RuntimeCandidatePolicyTests(unittest.TestCase):
    def test_runtime_collection_defaults_to_quant_only(self):
        with patch.object(svc, "load_execution_optimized_params", return_value=None), \
             patch.object(svc, "_get_today_picks", return_value={
                 "auto_candidates": [
                     {"code": "005930", "market": "KOSPI", "signal": "추천", "score": 80}
                 ]
             }), \
             patch.object(svc, "_get_recommendations", return_value={
                 "recommendations": [
                     {"ticker": "AAPL", "market": "NASDAQ", "signal": "buy", "score": 77}
                 ]
             }):
            candidates = svc.collect_runtime_candidates("NASDAQ", cfg={})

        self.assertEqual([], candidates)

    def test_runtime_collection_can_use_research_only_mode(self):
        with patch.object(svc, "load_execution_optimized_params", return_value=None), \
             patch.object(svc, "_get_today_picks", return_value={"auto_candidates": []}), \
             patch.object(svc, "_get_recommendations", return_value={
                 "recommendations": [
                     {"ticker": "AAPL", "market": "NASDAQ", "signal": "buy", "score": 77}
                 ]
             }):
            candidates = svc.collect_runtime_candidates(
                "NASDAQ",
                cfg={
                    "runtime_candidate_source_mode": "research_only",
                    "allow_recommendation_fallback": True,
                },
            )

        self.assertEqual(1, len(candidates))
        self.assertEqual("AAPL", candidates[0]["code"])
        self.assertEqual("recommendations", candidates[0]["source"])

    def test_runtime_collection_can_use_quant_only_runtime_overlay(self):
        runtime_payload = {
            "per_symbol": {
                "AAPL": {
                    "market": "NASDAQ",
                    "is_reliable": True,
                    "strategy_reliability": "high",
                    "reliability_reason": "validated_candidate",
                    "trade_count": 18,
                    "validation_trades": 18,
                    "validation_sharpe": 0.93,
                    "composite_score": 64.0,
                }
            }
        }
        with patch.object(svc, "load_execution_optimized_params", return_value=runtime_payload), \
             patch.object(svc, "fetch_technical_snapshot", return_value={
                 "current_price": 201.5,
                 "volume_avg20": 1500000,
                 "volume_ratio": 1.4,
             }):
            candidates = svc.collect_runtime_candidates("NASDAQ", cfg={})

        self.assertEqual(1, len(candidates))
        self.assertEqual("AAPL", candidates[0]["code"])
        self.assertEqual("quant_runtime", candidates[0]["source"])
        self.assertEqual("quant_runtime", candidates[0]["validation_snapshot"]["validation_source"])
        self.assertEqual(201.5, candidates[0]["technical_snapshot"]["current_price"])
        self.assertEqual(201.5, candidates[0]["current_price"])
        self.assertEqual(1500000, candidates[0]["technical_snapshot"]["volume_avg20"])
        self.assertEqual("quant_only", candidates[0]["runtime_candidate_source_mode"])

    def test_runtime_collection_hybrid_merges_only_in_policy_layer(self):
        runtime_payload = {
            "per_symbol": {
                "AAPL": {
                    "market": "NASDAQ",
                    "is_reliable": True,
                    "strategy_reliability": "high",
                    "reliability_reason": "validated_candidate",
                    "trade_count": 18,
                    "validation_trades": 18,
                    "validation_sharpe": 0.93,
                    "composite_score": 64.0,
                }
            }
        }
        with patch.object(svc, "load_execution_optimized_params", return_value=runtime_payload), \
             patch.object(svc, "fetch_technical_snapshot", return_value=None), \
             patch.object(svc, "_get_today_picks", return_value={
                 "auto_candidates": [
                     {
                         "code": "AAPL",
                         "market": "NASDAQ",
                         "signal": "추천",
                         "score": 70,
                         "technical_snapshot": {"current_price": 200.0},
                     }
                 ]
             }), \
             patch.object(svc, "_get_recommendations", return_value={"recommendations": []}):
            candidates = svc.collect_runtime_candidates(
                "NASDAQ",
                cfg={"runtime_candidate_source_mode": "hybrid"},
            )

        self.assertEqual(1, len(candidates))
        self.assertEqual("hybrid", candidates[0]["source"])
        self.assertEqual("today_picks", candidates[0]["research_source"])
        self.assertEqual(200.0, candidates[0]["technical_snapshot"]["current_price"])

    def test_quant_runtime_candidates_ignore_research_min_score(self):
        runtime_payload = {
            "per_symbol": {
                "000810": {
                    "market": "KOSPI",
                    "is_reliable": False,
                    "strategy_reliability": "insufficient",
                    "reliability_reason": "insufficient_validation_signals",
                    "trade_count": 79,
                    "validation_trades": 6,
                    "validation_sharpe": 0.0,
                    "composite_score": 33.02,
                }
            }
        }
        with patch.object(svc, "load_execution_optimized_params", return_value=runtime_payload), \
             patch.object(svc, "fetch_technical_snapshot", return_value=None):
            candidates = svc.collect_runtime_candidates(
                "KOSPI",
                cfg={
                    "runtime_candidate_source_mode": "quant_only",
                    "min_score": 50,
                },
            )

        self.assertEqual(1, len(candidates))
        self.assertEqual("000810", candidates[0]["code"])

    def test_quant_runtime_candidates_can_use_dedicated_quant_min_score(self):
        runtime_payload = {
            "per_symbol": {
                "000810": {
                    "market": "KOSPI",
                    "is_reliable": False,
                    "strategy_reliability": "insufficient",
                    "reliability_reason": "insufficient_validation_signals",
                    "trade_count": 79,
                    "validation_trades": 6,
                    "validation_sharpe": 0.0,
                    "composite_score": 33.02,
                }
            }
        }
        with patch.object(svc, "load_execution_optimized_params", return_value=runtime_payload), \
             patch.object(svc, "fetch_technical_snapshot", return_value=None):
            candidates = svc.collect_runtime_candidates(
                "KOSPI",
                cfg={
                    "runtime_candidate_source_mode": "quant_only",
                    "min_score": 50,
                    "quant_min_score": 34,
                },
            )

        self.assertEqual([], candidates)


if __name__ == "__main__":
    unittest.main()
