from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import signal_service as svc


class RuntimeCandidateFallbackGuardTests(unittest.TestCase):
    def test_runtime_collection_disables_recommendation_fallback_by_default(self):
        with patch.object(svc, "_get_today_picks", return_value={"auto_candidates": []}), \
             patch.object(
                 svc,
                 "_get_recommendations",
                 return_value={
                     "recommendations": [
                         {
                             "ticker": "AAPL",
                             "market": "NASDAQ",
                             "signal": "buy",
                             "score": 77,
                         }
                     ]
                 },
             ):
            candidates = svc.collect_pick_candidates("NASDAQ", cfg={})

        self.assertEqual([], candidates)

    def test_runtime_collection_can_opt_in_to_recommendation_fallback(self):
        with patch.object(svc, "_get_today_picks", return_value={"auto_candidates": []}), \
             patch.object(
                 svc,
                 "_get_recommendations",
                 return_value={
                     "recommendations": [
                         {
                             "ticker": "AAPL",
                             "market": "NASDAQ",
                             "signal": "buy",
                             "score": 77,
                         }
                     ]
                 },
             ):
            candidates = svc.collect_pick_candidates(
                "NASDAQ",
                cfg={
                    "runtime_candidate_source_mode": "research_only",
                    "allow_recommendation_fallback": True,
                },
            )

        self.assertEqual(1, len(candidates))
        self.assertEqual("AAPL", candidates[0]["code"])
        self.assertEqual("recommendations", candidates[0]["source"])


if __name__ == "__main__":
    unittest.main()
