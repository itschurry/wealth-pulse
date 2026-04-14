from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

settings_stub = types.ModuleType("config.settings")
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "wealth-pulse-candidate-monitor-service-tests"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings_stub.REPORT_OUTPUT_DIR = settings_stub.LOGS_DIR

with patch.dict(sys.modules, {"config.settings": settings_stub}):
    from services import candidate_monitor_service as svc
    from services import candidate_monitor_store as store


class CandidateMonitorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_path = Path(self.tmpdir.name) / "candidate_monitor.db"
        self.path_patch = patch.object(store, "DB_PATH", self.db_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_build_market_watchlist_creates_core_promotion_and_held_slots(self):
        scans = [
            {
                "strategy_id": "s1",
                "strategy_name": "S1",
                "market": "KOSPI",
                "last_scan_at": "2026-04-14T09:01:00+09:00",
                "top_candidates": [
                    {"code": "005930", "market": "KOSPI", "candidate_rank": 1, "final_action": "review_for_entry", "signal_state": "entry", "score": 88, "research_status": "fresh"},
                    {"code": "000660", "market": "KOSPI", "candidate_rank": 2, "final_action": "watch_only", "signal_state": "watch", "score": 72, "research_status": "stale_ingest"},
                    {"code": "035420", "market": "KOSPI", "candidate_rank": 3, "final_action": "watch_only", "signal_state": "watch", "score": 70, "research_status": "fresh"},
                    {"code": "051910", "market": "KOSPI", "candidate_rank": 4, "final_action": "do_not_touch", "signal_state": "watch", "score": 65, "research_status": "fresh"},
                ],
            }
        ]
        account = {"positions": [{"code": "000660", "market": "KOSPI"}]}

        with patch.object(svc, "list_strategy_scans", return_value=scans):
            payload = svc.build_market_watchlist("KOSPI", account=account, pool_limit=4, core_limit=2, promotion_limit=1)

        self.assertTrue(payload["ok"])
        self.assertEqual(4, len(payload["candidate_pool"]))
        self.assertEqual(["000660"], [row["symbol"] for row in payload["held_slots"]])
        self.assertEqual(2, len(payload["core_slots"]))
        self.assertEqual(1, len(payload["promotion_slots"]))
        active_symbols = [row["symbol"] for row in payload["active_slots"]]
        self.assertEqual(["000660", "005930", "035420", "051910"], active_symbols)

    def test_build_market_watchlist_logs_enter_and_leave_events(self):
        first_scans = [{
            "strategy_id": "s1",
            "strategy_name": "S1",
            "market": "NASDAQ",
            "last_scan_at": "2026-04-14T22:30:00+09:00",
            "top_candidates": [
                {"code": "AAPL", "market": "NASDAQ", "candidate_rank": 1, "final_action": "review_for_entry", "signal_state": "entry", "score": 90, "research_status": "fresh"},
                {"code": "MSFT", "market": "NASDAQ", "candidate_rank": 2, "final_action": "watch_only", "signal_state": "watch", "score": 80, "research_status": "fresh"},
            ],
        }]
        second_scans = [{
            "strategy_id": "s1",
            "strategy_name": "S1",
            "market": "NASDAQ",
            "last_scan_at": "2026-04-14T22:35:00+09:00",
            "top_candidates": [
                {"code": "NVDA", "market": "NASDAQ", "candidate_rank": 1, "final_action": "review_for_entry", "signal_state": "entry", "score": 95, "research_status": "fresh"},
                {"code": "AAPL", "market": "NASDAQ", "candidate_rank": 2, "final_action": "watch_only", "signal_state": "watch", "score": 85, "research_status": "fresh"},
            ],
        }]

        with patch.object(svc, "list_strategy_scans", return_value=first_scans):
            svc.build_market_watchlist("NASDAQ", account={}, pool_limit=4, core_limit=1, promotion_limit=1)
        with patch.object(svc, "list_strategy_scans", return_value=second_scans):
            payload = svc.build_market_watchlist("NASDAQ", account={}, pool_limit=4, core_limit=1, promotion_limit=1)

        events = payload["events"]
        event_types = {(row["symbol"], row["event_type"]) for row in events}
        self.assertIn(("NVDA", "entered_watch"), event_types)
        self.assertIn(("MSFT", "left_watch"), event_types)

    def test_pending_research_targets_filter_active_slots_only(self):
        scans = [{
            "strategy_id": "s1",
            "strategy_name": "S1",
            "market": "KOSPI",
            "last_scan_at": "2026-04-14T09:01:00+09:00",
            "top_candidates": [
                {"code": "005930", "market": "KOSPI", "candidate_rank": 1, "final_action": "review_for_entry", "signal_state": "entry", "score": 88, "research_status": "fresh", "layer_c": {"freshness": "fresh", "generated_at": "2026-04-14T08:58:00+09:00", "research_score": 0.91, "validation": {"grade": "A"}}},
                {"code": "000660", "market": "KOSPI", "candidate_rank": 2, "final_action": "watch_only", "signal_state": "watch", "score": 72, "research_status": "stale_ingest", "layer_c": {"freshness": "stale", "generated_at": "2026-04-14T05:40:00+09:00", "research_score": 0.55, "validation": {"grade": "C"}}},
                {"code": "035420", "market": "KOSPI", "candidate_rank": 3, "final_action": "watch_only", "signal_state": "watch", "score": 70, "research_status": "research_unavailable"},
            ],
        }]

        with patch.object(svc, "list_strategy_scans", return_value=scans):
            watchlist = svc.build_market_watchlist("KOSPI", account={}, pool_limit=4, core_limit=2, promotion_limit=1)

        pending = svc.list_pending_research_targets([watchlist], mode="missing_or_stale", limit=10)
        self.assertEqual(["000660", "035420"], [row["symbol"] for row in pending])
        self.assertTrue(watchlist["active_slots"][0]["snapshot_exists"])
        self.assertTrue(watchlist["active_slots"][0]["snapshot_fresh"])
        self.assertEqual("A", watchlist["active_slots"][0]["validation_grade"])


if __name__ == "__main__":
    unittest.main()
