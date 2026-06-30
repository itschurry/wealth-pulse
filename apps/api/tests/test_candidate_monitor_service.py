from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services import candidate_monitor_service as service


class CandidateMonitorServiceTests(unittest.TestCase):
    def test_realtime_market_evidence_marks_intraday_mover(self) -> None:
        original = service.resolve_stock_quote
        service.resolve_stock_quote = lambda code, market: {
            "code": code,
            "market": market,
            "price": 10000,
            "change_pct": 3.2,
            "volume": 2000000,
            "trading_value": 20000000000.0,
            "source": "KIS",
            "fetched_at": "2026-06-30T00:00:00+09:00",
            "is_stale": False,
        }
        try:
            rows = service._with_realtime_market_evidence([
                {"code": "000660", "market": "KOSPI", "candidate_sources": ["config_universe"]}
            ])
        finally:
            service.resolve_stock_quote = original

        row = rows[0]
        self.assertEqual(row["change_pct"], 3.2)
        self.assertEqual(row["volume"], 2000000)
        self.assertEqual(row["trading_value"], 20000000000.0)
        self.assertIn("realtime_mover", row["candidate_sources"])
        self.assertEqual(row["technical_snapshot"]["quote_source"], "KIS")

    def test_market_evidence_beats_marketless_news_in_priority(self) -> None:
        marketless_news = {
            "code": "005930",
            "market": "KOSPI",
            "candidate_sources": ["news_surge"],
            "candidate_source": "news_surge",
            "news_surge_score": 95,
            "score": 99,
        }
        realtime_mover = {
            "code": "000660",
            "market": "KOSPI",
            "candidate_sources": ["news_surge", "realtime_mover", "change_rate_top"],
            "candidate_source": "news_surge",
            "news_surge_score": 80,
            "score": 80,
            "change_pct": 3.4,
            "trading_value": 8000000000.0,
        }

        self.assertGreater(
            service._candidate_priority(realtime_mover, held_symbols=set(), interest_symbols=set()),
            service._candidate_priority(marketless_news, held_symbols=set(), interest_symbols=set()),
        )

    def test_promotion_candidates_prioritize_realtime_movers(self) -> None:
        marketless_news = {
            "code": "005930",
            "market": "KOSPI",
            "candidate_sources": ["news_surge"],
            "news_surge_score": 95,
            "score": 99,
        }
        realtime_mover = {
            "code": "000660",
            "market": "KOSPI",
            "candidate_sources": ["realtime_mover", "news_surge"],
            "change_pct": 3.4,
            "trading_value": 8000000000.0,
            "news_surge_score": 80,
            "score": 80,
        }

        selected = service._select_promotion_candidates(
            [marketless_news, realtime_mover],
            used_symbols=set(),
            limit=1,
        )

        self.assertEqual(selected[0]["code"], "000660")


if __name__ == "__main__":
    unittest.main()
