from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services import candidate_monitor_service as service
from services.trading_pipeline.ranker import rank_candidates
from services.trading_pipeline.research_queue import build_research_queue
from services.trading_pipeline.scanner import scan_universe
from services.trading_pipeline.universe import build_dynamic_universe


class CandidateMonitorServiceTests(unittest.TestCase):
    def _source_rows(self) -> list[dict]:
        return [
            {"Code": "000660", "Name": "SK하이닉스", "Close": 100000, "Volume": 3000000, "Amount": 300000000000, "ChangesRatio": 3.2, "Marcap": 120000000000000},
            {"Code": "005930", "Name": "삼성전자", "Close": 80000, "Volume": 1000000, "Amount": 80000000000, "ChangesRatio": 0.5, "Marcap": 400000000000000},
            {"Code": "123456", "Name": "저유동성", "Close": 10000, "Volume": 100, "Amount": 1000000, "ChangesRatio": 10.0, "Marcap": 10000000000},
        ]

    def test_dynamic_universe_filters_and_orders_by_liquidity(self) -> None:
        universe = build_dynamic_universe(
            market="KOSPI",
            source_rows=self._source_rows(),
            max_symbols=10,
            min_trading_value_krw=5_000_000_000,
        )

        self.assertEqual(universe["schema_version"], "trading_pipeline.universe.v1")
        self.assertEqual([row["symbol"] for row in universe["symbols"]], ["000660", "005930"])
        self.assertEqual(universe["config"]["min_trading_value_krw"], 5_000_000_000.0)

    def test_scanner_marks_intraday_mover(self) -> None:
        universe = build_dynamic_universe(market="KOSPI", source_rows=self._source_rows())
        scan = scan_universe(universe)
        top = scan["candidates"][0]

        self.assertEqual(top["symbol"], "000660")
        self.assertIn("market_scanner", top["reason_codes"])
        self.assertIn("realtime_mover", top["reason_codes"])
        self.assertEqual(top["technical_snapshot"]["change_pct"], 3.2)

    def test_ranker_keeps_priority_breakdown(self) -> None:
        universe = build_dynamic_universe(market="KOSPI", source_rows=self._source_rows())
        ranked = rank_candidates(scan_universe(universe), active_limit=1)
        top = ranked["active_slots"][0]

        self.assertEqual(top["symbol"], "000660")
        self.assertIn("monitor_priority_breakdown", top)
        self.assertGreater(top["monitor_priority_breakdown"]["realtime_mover"], 0)
        self.assertEqual(top["candidate_source"], "market_scanner")

    def test_build_market_watchlist_preview_does_not_persist(self) -> None:
        original_refresh = service.refresh_market_pipeline

        def fake_refresh(market: str, **kwargs):
            self.assertFalse(kwargs["persist"])
            return {
                "watchlist": {
                    "ok": True,
                    "market": market,
                    "state": {"metadata": {"universe_generation_mode": "dynamic_market_listing"}},
                    "candidate_pool": [],
                    "active_slots": [{"symbol": "000660", "code": "000660", "market": market, "slot_type": "core"}],
                    "events": [],
                    "core_slots": [{"symbol": "000660", "code": "000660", "market": market, "slot_type": "core"}],
                    "promotion_slots": [],
                    "held_slots": [],
                    "persisted": False,
                }
            }

        service.refresh_market_pipeline = fake_refresh
        try:
            result = service.build_market_watchlist("KOSPI", refresh=True, persist=False, core_limit=1, promotion_limit=0)
        finally:
            service.refresh_market_pipeline = original_refresh

        self.assertFalse(result["persisted"])
        self.assertEqual(result["active_slots"][0]["symbol"], "000660")
        self.assertEqual(result["state"]["metadata"]["universe_generation_mode"], "dynamic_market_listing")

    def test_research_queue_marks_missing_snapshot_pending(self) -> None:
        ranked = {
            "market": "KOSPI",
            "active_slots": [{"symbol": "999999", "code": "999999", "market": "KOSPI", "monitor_priority": 80}],
        }
        queue = build_research_queue(ranked, mode="missing_or_stale", limit=5)

        self.assertEqual(queue["pending_count"], 1)
        self.assertEqual(queue["items"][0]["research_status"], "missing")
        self.assertFalse(queue["items"][0]["snapshot_exists"])

    def test_recent_promotion_events_match_web_contract(self) -> None:
        original_read_events = service.read_events

        service.read_events = lambda _kind, _market, limit: [
            {
                "recorded_at": "2026-07-16T06:21:15+00:00",
                "symbol": "010950",
                "event": "entered_watch",
                "payload": {
                    "market": "KOSPI",
                    "name": "S-Oil",
                    "slot_type": "promotion",
                    "selection_reason": "change_rate_top",
                },
            },
            {
                "recorded_at": "2026-07-16T06:20:01+00:00",
                "symbol": "034020",
                "event": "left_watch",
            },
        ]
        try:
            items = service.list_recent_promotion_events(["KOSPI"], limit=20)
        finally:
            service.read_events = original_read_events

        self.assertEqual(items[0]["created_at"], "2026-07-16T06:21:15+00:00")
        self.assertEqual(items[0]["event_type"], "entered_watch")
        self.assertEqual(items[0]["name"], "S-Oil")
        self.assertEqual(items[0]["slot_type"], "promotion")
        self.assertEqual(items[0]["reason"], "change_rate_top")
        self.assertEqual(items[1]["market"], "KOSPI")
        self.assertEqual(items[1]["event_type"], "left_watch")


if __name__ == "__main__":
    unittest.main()
