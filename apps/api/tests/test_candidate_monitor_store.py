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
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "wealth-pulse-candidate-monitor-tests"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings_stub.REPORT_OUTPUT_DIR = settings_stub.LOGS_DIR

with patch.dict(sys.modules, {"config.settings": settings_stub}):
    from services import candidate_monitor_store as store


class CandidateMonitorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_path = Path(self.tmpdir.name) / "candidate_monitor.db"
        self.path_patch = patch.object(store, "DB_PATH", self.db_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_replace_candidate_pool_and_list_active_slots(self):
        inserted = store.replace_candidate_pool(
            "KOSPI",
            [
                {
                    "code": "005930",
                    "strategy_id": "trend_a",
                    "strategy_name": "Trend A",
                    "candidate_rank": 2,
                    "final_action": "review_for_entry",
                    "signal_state": "entry",
                    "entry_allowed": True,
                    "score": 82.5,
                    "confidence": 77.2,
                    "last_scanned_at": "2026-04-14T09:00:00+09:00",
                    "research_status": "healthy",
                    "snapshot_fresh": True,
                    "snapshot_generated_at": "2026-04-14T08:50:00+09:00",
                },
                {
                    "code": "000660",
                    "strategy_id": "trend_b",
                    "strategy_name": "Trend B",
                    "candidate_rank": 1,
                    "final_action": "watch_only",
                    "signal_state": "watch",
                    "entry_allowed": False,
                    "score": 75.0,
                },
            ],
            updated_at="2026-04-14T09:01:00+09:00",
        )
        self.assertEqual(2, inserted)

        rows = store.list_candidate_pool("KOSPI")
        self.assertEqual(["000660", "005930"], [row["symbol"] for row in rows])
        self.assertFalse(rows[0]["entry_allowed"])
        self.assertTrue(rows[1]["snapshot_fresh"])
        self.assertEqual("trend_a", rows[1]["strategy_id"])

    def test_replace_active_slots_and_market_state_and_events(self):
        store.replace_active_slots(
            "NASDAQ",
            [
                {
                    "symbol": "AAPL",
                    "slot_type": "core",
                    "priority": 100,
                    "reason": "opening_focus",
                    "strategy_id": "us_trend",
                },
                {
                    "symbol": "MSFT",
                    "slot_type": "promotion",
                    "priority": 80,
                    "reason": "intraday_breakout",
                    "strategy_id": "us_trend",
                },
            ],
            selected_at="2026-04-14T22:30:00+09:00",
        )
        store.save_market_state(
            "NASDAQ",
            source="candidate_monitor",
            session_date="2026-04-14",
            core_limit=10,
            promotion_limit=3,
            candidate_pool_count=35,
            active_count=2,
            held_count=1,
            generated_at="2026-04-14T22:30:00+09:00",
            metadata={"notes": ["initial_build"]},
        )
        store.append_promotion_event(
            "NASDAQ",
            "MSFT",
            "promoted",
            "intraday_breakout",
            payload={"from_rank": 18, "to_slot": "promotion"},
            created_at="2026-04-14T22:31:00+09:00",
        )

        active_rows = store.list_active_slots("NASDAQ")
        self.assertEqual(["AAPL", "MSFT"], [row["symbol"] for row in active_rows])
        self.assertEqual("core", active_rows[0]["slot_type"])

        promotion_rows = store.list_active_slots("NASDAQ", slot_type="promotion")
        self.assertEqual(1, len(promotion_rows))
        self.assertEqual("MSFT", promotion_rows[0]["symbol"])

        market_state = store.load_market_state("NASDAQ")
        self.assertIsNotNone(market_state)
        self.assertEqual(35, market_state["candidate_pool_count"])
        self.assertEqual(["initial_build"], market_state["metadata"]["notes"])

        events = store.list_promotion_events("NASDAQ", limit=5)
        self.assertEqual(1, len(events))
        self.assertEqual("MSFT", events[0]["symbol"])
        self.assertEqual("promoted", events[0]["event_type"])
        self.assertEqual(18, events[0]["payload"]["from_rank"])


if __name__ == "__main__":
    unittest.main()
