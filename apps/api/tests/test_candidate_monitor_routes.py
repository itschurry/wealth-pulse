from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import candidate_monitor as route_mod


class CandidateMonitorRouteTests(unittest.TestCase):
    def test_watchlist_refresh_builds_each_market(self):
        watchlists = [
            {"ok": True, "market": "KOSPI", "candidate_pool": [], "active_slots": [], "core_slots": [], "promotion_slots": [], "held_slots": [], "events": [], "state": {}},
            {"ok": True, "market": "NASDAQ", "candidate_pool": [], "active_slots": [], "core_slots": [], "promotion_slots": [], "held_slots": [], "events": [], "state": {}},
        ]
        pending_items = [{"symbol": "AAPL", "market": "NASDAQ"}]
        with (
            patch.object(route_mod, "get_execution_service") as mock_exec,
            patch.object(route_mod, "list_market_watchlists", return_value=watchlists) as mock_watchlists,
            patch.object(route_mod, "list_pending_research_targets", return_value=pending_items) as mock_pending,
        ):
            mock_exec.return_value.paper_account.return_value = (200, {"account": {"positions": []}})
            status, payload = route_mod.handle_candidate_monitor_watchlist({"refresh": ["1"]})

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(["KOSPI", "NASDAQ"], payload["markets"])
        self.assertEqual(2, payload["count"])
        self.assertEqual(1, payload["pending_count"])
        mock_watchlists.assert_called_once_with(["KOSPI", "NASDAQ"], refresh=True, account={"positions": []})
        mock_pending.assert_called_once_with(watchlists, mode="missing_or_stale", limit=30)

    def test_status_without_refresh_reads_cached_watchlists(self):
        watchlists = [
            {"market": "KOSPI", "candidate_pool": [{}, {}], "active_slots": [{}, {}], "core_slots": [{}], "promotion_slots": [{}], "held_slots": [], "state": {"generated_at": "a", "session_date": "2026-04-14", "source": "candidate_monitor", "metadata": {}}},
            {"market": "NASDAQ", "candidate_pool": [{}], "active_slots": [{}], "core_slots": [{}], "promotion_slots": [], "held_slots": [], "state": {"generated_at": "b", "session_date": "2026-04-14", "source": "candidate_monitor", "metadata": {}}},
        ]
        summary = [
            {"market": "KOSPI", "candidate_pool_count": 2, "active_count": 2, "core_count": 1, "promotion_count": 1, "held_count": 0},
            {"market": "NASDAQ", "candidate_pool_count": 1, "active_count": 1, "core_count": 1, "promotion_count": 0, "held_count": 0},
        ]
        with (
            patch.object(route_mod, "get_execution_service") as mock_exec,
            patch.object(route_mod, "list_market_watchlists", return_value=watchlists) as mock_watchlists,
            patch.object(route_mod, "summarize_market_watchlists", return_value=summary) as mock_summary,
        ):
            mock_exec.return_value.paper_account.return_value = (200, {"account": {"positions": []}})
            status, payload = route_mod.handle_candidate_monitor_status({})

        self.assertEqual(200, status)
        self.assertEqual(summary, payload["items"])
        mock_watchlists.assert_called_once_with(["KOSPI", "NASDAQ"], refresh=False, account={"positions": []})
        mock_summary.assert_called_once_with(watchlists)

    def test_promotions_route_optionally_refreshes_before_listing_events(self):
        events = [{"market": "NASDAQ", "symbol": "NVDA", "event_type": "entered_watch", "created_at": "2026-04-14T22:35:00+09:00"}]
        with (
            patch.object(route_mod, "get_execution_service") as mock_exec,
            patch.object(route_mod, "list_market_watchlists", return_value=[]) as mock_watchlists,
            patch.object(route_mod, "list_recent_promotion_events", return_value=events) as mock_events,
        ):
            mock_exec.return_value.paper_account.return_value = (200, {"account": {"positions": []}})
            status, payload = route_mod.handle_candidate_monitor_promotions({"refresh": ["1"], "limit": ["20"]})

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(events, payload["items"])
        mock_watchlists.assert_called_once_with(["KOSPI", "NASDAQ"], refresh=True, account={"positions": []})
        mock_events.assert_called_once_with(["KOSPI", "NASDAQ"], limit=20)


if __name__ == "__main__":
    unittest.main()
