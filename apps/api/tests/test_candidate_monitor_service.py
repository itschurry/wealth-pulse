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

    def test_candidate_priority_breakdown_is_stored_on_annotated_rows(self) -> None:
        rows = service._annotate_standard_sources(
            [
                {
                    "code": "000660",
                    "market": "KOSPI",
                    "candidate_sources": ["realtime_mover"],
                    "candidate_source": "realtime_mover",
                    "score": 80,
                    "change_pct": 3.4,
                    "trading_value": 8000000000.0,
                }
            ],
            held_symbols=set(),
            interest_symbols=set(),
        )

        row = rows[0]
        self.assertIn("monitor_priority_breakdown", row)
        self.assertEqual(row["monitor_priority"], row["monitor_priority_breakdown"]["total"])
        self.assertIn("realtime_mover", row["monitor_priority_breakdown"]["components"])
        self.assertIn("market_scanner", row["candidate_sources"])

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

    def test_build_market_watchlist_preview_does_not_persist(self) -> None:
        original_dedupe = service._dedupe_market_candidates
        original_list_active = service.store.list_active_slots
        original_list_events = service.store.list_promotion_events
        original_replace_pool = service.store.replace_candidate_pool
        original_replace_slots = service.store.replace_active_slots
        original_save_state = service.store.save_market_state
        original_append_event = service.store.append_promotion_event

        def fail_if_persisted(*_args, **_kwargs):
            raise AssertionError("preview refresh must not persist")

        service._dedupe_market_candidates = lambda *_args, **_kwargs: [
            {
                "code": "000660",
                "symbol": "000660",
                "market": "KOSPI",
                "name": "SK하이닉스",
                "candidate_sources": ["market_scanner"],
                "candidate_source": "market_scanner",
                "monitor_priority": 1234.0,
                "monitor_priority_breakdown": {
                    "total": 1234.0,
                    "components": {"market_scanner": 900.0},
                    "inputs": {},
                },
                "candidate_rank": 1,
                "score": 90,
            }
        ]
        service.store.list_active_slots = lambda *_args, **_kwargs: []
        service.store.list_promotion_events = lambda *_args, **_kwargs: []
        service.store.replace_candidate_pool = fail_if_persisted
        service.store.replace_active_slots = fail_if_persisted
        service.store.save_market_state = fail_if_persisted
        service.store.append_promotion_event = fail_if_persisted
        try:
            result = service.build_market_watchlist("KOSPI", persist=False, core_limit=1, promotion_limit=0)
        finally:
            service._dedupe_market_candidates = original_dedupe
            service.store.list_active_slots = original_list_active
            service.store.list_promotion_events = original_list_events
            service.store.replace_candidate_pool = original_replace_pool
            service.store.replace_active_slots = original_replace_slots
            service.store.save_market_state = original_save_state
            service.store.append_promotion_event = original_append_event

        self.assertFalse(result["persisted"])
        self.assertEqual(result["active_slots"][0]["symbol"], "000660")
        self.assertEqual(result["state"]["metadata"]["universe_generation_mode"], "static_config")


if __name__ == "__main__":
    unittest.main()
