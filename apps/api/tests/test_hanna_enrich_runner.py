from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import hanna_enrich_runner as runner


class HannaEnrichRunnerTests(unittest.TestCase):
    def test_run_requests_fresh_candidate_monitor_watchlist(self):
        with (
            patch.object(runner, "handle_candidate_monitor_watchlist", return_value=(200, {"ok": True, "pending_items": []})) as mock_watchlist,
            patch.object(runner, "handle_research_status", return_value=(200, {"ok": True, "status": "healthy", "freshness": "fresh"})),
        ):
            status_code, payload = runner.run(markets=["KOSPI", "NASDAQ"], limit=12, mode="missing_or_stale")

        self.assertEqual(200, status_code)
        self.assertTrue(payload["ok"])
        called_query = mock_watchlist.call_args.args[0]
        self.assertEqual(["1"], called_query["refresh"])
        self.assertEqual(["12"], called_query["limit"])
        self.assertEqual(["missing_or_stale"], called_query["mode"])
        self.assertEqual(["KOSPI", "NASDAQ"], called_query["market"])


if __name__ == "__main__":
    unittest.main()
