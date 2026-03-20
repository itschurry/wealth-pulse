from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analyzer.candidate_selector import (
    load_historical_candidates,
    normalize_candidate_selection_config,
    select_market_candidates,
)


class CandidateSelectorTests(unittest.TestCase):
    def test_today_picks_are_ranked_with_theme_bonus(self):
        cfg = normalize_candidate_selection_config({})
        candidates = select_market_candidates(
            market="KOSPI",
            cfg=cfg,
            today_picks={
                "auto_candidates": [
                    {
                        "code": "AAA",
                        "market": "KOSPI",
                        "signal": "추천",
                        "score": 60,
                        "theme_score": 3.0,
                        "related_news": [{"theme_score": 3.0, "matched_themes": ["AI"]}],
                    },
                    {
                        "code": "BBB",
                        "market": "KOSPI",
                        "signal": "추천",
                        "score": 61,
                        "theme_score": 0.0,
                        "related_news": [],
                    },
                ]
            },
        )

        self.assertEqual([item["code"] for item in candidates], ["AAA", "BBB"])
        self.assertEqual(candidates[0]["priority_score"], 62.0)
        self.assertEqual(candidates[1]["priority_score"], 61.0)

    def test_recommendations_are_used_when_today_picks_do_not_match(self):
        cfg = normalize_candidate_selection_config({"include_neutral": False})
        candidates = select_market_candidates(
            market="NASDAQ",
            cfg=cfg,
            today_picks={
                "auto_candidates": [
                    {
                        "code": "005930",
                        "market": "KOSPI",
                        "signal": "추천",
                        "score": 80,
                    }
                ]
            },
            recommendations={
                "recommendations": [
                    {
                        "ticker": "AAPL",
                        "market": "NASDAQ",
                        "signal": "buy",
                        "score": 77,
                        "theme_score": 1.0,
                    }
                ]
            },
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["code"], "AAPL")
        self.assertEqual(candidates[0]["source"], "recommendations")

    def test_historical_loader_reports_actual_source(self):
        cfg = normalize_candidate_selection_config({})
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            (report_dir / "2026-03-20_today_picks.json").write_text(
                json.dumps({"auto_candidates": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (report_dir / "2026-03-20_recommendations.json").write_text(
                json.dumps(
                    {
                        "recommendations": [
                            {
                                "ticker": "MSFT",
                                "market": "NASDAQ",
                                "signal": "buy",
                                "score": 71,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = load_historical_candidates(
                date="2026-03-20",
                market="NASDAQ",
                cfg=cfg,
                report_dir=report_dir,
            )

        self.assertTrue(result["has_report"])
        self.assertEqual(result["source"], "recommendations")
        self.assertEqual(result["codes"], {"MSFT"})


if __name__ == "__main__":
    unittest.main()
