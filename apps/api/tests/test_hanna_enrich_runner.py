from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import hanna_enrich_runner as runner
from scripts import research_ops


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

    def test_build_ingest_payload_emits_v2_agent_contract_for_scanner_target(self):
        payload = runner._build_ingest_payload([
            {
                "symbol": "005930",
                "market": "KOSPI",
                "name": "삼성전자",
                "candidate_rank": 1,
                "strategy_name": "Momentum Breakout",
                "final_action": "review_for_entry",
                "signal_state": "entry",
                "score": 88,
                "snapshot_exists": False,
                "snapshot_fresh": False,
                "risk_inputs": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0},
            }
        ])

        self.assertEqual("v2", payload["schema_version"])
        self.assertEqual(1, len(payload["items"]))
        item = payload["items"][0]
        self.assertEqual("overweight", item["rating"])
        self.assertEqual("buy_watch", item["action"])
        self.assertGreaterEqual(item["confidence"], 0.65)
        self.assertEqual("candidate_monitor_scanner", item["candidate_source"])
        self.assertEqual("entry", item["technical_features"]["signal_state"])
        self.assertEqual(1, item["technical_features"]["candidate_rank"])
        self.assertTrue(item["data_quality"]["has_technical_features"])
        self.assertFalse(item["data_quality"]["has_news"])
        self.assertTrue(item["evidence"])
        self.assertIn("deterministic_fallback", item["tags"])
        self.assertIn("Hermes/LLM", item["risks"][0])

    def test_build_ingest_payload_keeps_non_entry_scanner_target_neutral(self):
        payload = runner._build_ingest_payload([
            {
                "symbol": "AAPL",
                "market": "NASDAQ",
                "candidate_rank": 12,
                "strategy_name": "Scanner",
                "final_action": "watch_only",
                "signal_state": "watch",
                "score": 61,
                "snapshot_exists": True,
                "snapshot_fresh": False,
            }
        ])

        item = payload["items"][0]
        self.assertEqual("hold", item["rating"])
        self.assertEqual("hold", item["action"])
        self.assertLess(item["confidence"], 0.75)
        self.assertEqual("watch", item["technical_features"]["signal_state"])
        self.assertEqual("stale_recheck", item["data_quality"]["research_context"])

    def test_research_ops_ingest_agent_builds_v2_payload_before_bulk_ingest(self):
        analysis = {
            "symbol": "005930",
            "market": "KOSPI",
            "generated_at": "2026-04-29T10:15:00+09:00",
            "confidence": 0.82,
            "rating": "strong_buy",
            "action": "buy",
            "summary": "Hermes thesis",
            "technical_features": {"close_vs_sma20": 1.03, "volume_ratio": 1.4},
            "news_inputs": [{"title": "AI memory"}],
            "evidence": [{"type": "news", "summary": "AI memory"}],
        }
        with (
            patch.object(research_ops, "_load_json_payload", return_value=analysis),
            patch.object(research_ops, "handle_research_ingest_bulk", return_value=(200, {"ok": True, "accepted": 1})) as mock_ingest,
            patch.object(research_ops, "_print_payload", return_value=0) as mock_print,
        ):
            exit_code = research_ops.cmd_ingest_agent(type("Args", (), {"input": None})())

        self.assertEqual(0, exit_code)
        mock_print.assert_called_once_with(200, {"ok": True, "accepted": 1})
        ingest_payload = mock_ingest.call_args.args[0]
        self.assertEqual("v2", ingest_payload["schema_version"])
        self.assertEqual("default", ingest_payload["provider"])
        self.assertEqual("strong_buy", ingest_payload["items"][0]["rating"])
        self.assertEqual("agent_research", ingest_payload["items"][0]["data_quality"]["analysis_mode"])


if __name__ == "__main__":
    unittest.main()
