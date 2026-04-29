from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import hermes_research_runner as runner


class HermesResearchRunnerTests(unittest.TestCase):
    def test_build_prompt_requires_strict_v2_json_and_forbids_direct_orders(self):
        target = {
            "symbol": "005930",
            "market": "KOSPI",
            "name": "삼성전자",
            "candidate_rank": 1,
            "final_action": "review_for_entry",
            "signal_state": "entry",
            "score": 88,
            "technical_features": {"close_vs_sma20": 1.04, "volume_ratio": 1.6},
        }

        prompt = runner.build_research_prompt(target)

        self.assertIn("Return ONLY one JSON object", prompt)
        self.assertIn("Research Snapshot v2", prompt)
        self.assertIn("005930", prompt)
        self.assertIn("삼성전자", prompt)
        self.assertIn("rating", prompt)
        self.assertIn("action", prompt)
        self.assertIn("technical_features", prompt)
        self.assertIn("news_inputs", prompt)
        self.assertIn("evidence", prompt)
        self.assertIn("Do not place orders", prompt)
        self.assertIn("Do not invent news", prompt)
        self.assertIn("risk guard", prompt)

    def test_parse_agent_json_accepts_fenced_output(self):
        parsed = runner.parse_agent_json("""```json\n{"rating":"hold","action":"hold","confidence":0.51}\n```""")

        self.assertEqual("hold", parsed["rating"])
        self.assertEqual("hold", parsed["action"])
        self.assertEqual(0.51, parsed["confidence"])

    def test_run_dry_run_collects_targets_and_returns_prompts_without_calling_agent(self):
        watchlist = {
            "ok": True,
            "pending_items": [
                {"symbol": "AAPL", "market": "NASDAQ", "name": "Apple", "candidate_rank": 2, "final_action": "watch_only"}
            ],
        }
        with (
            patch.object(runner, "handle_candidate_monitor_watchlist", return_value=(200, watchlist)) as mock_watchlist,
            patch.object(runner, "call_hermes_agent") as mock_agent,
            patch.object(runner, "handle_research_ingest_bulk") as mock_ingest,
        ):
            status, payload = runner.run(markets=["NASDAQ"], limit=3, mode="missing_or_stale", dry_run=True)

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("dry_run", payload["stage"])
        self.assertEqual(1, payload["selected_count"])
        self.assertIn("Return ONLY one JSON object", payload["prompts"][0]["prompt"])
        self.assertEqual(["1"], mock_watchlist.call_args.args[0]["refresh"])
        mock_agent.assert_not_called()
        mock_ingest.assert_not_called()

    def test_run_calls_hermes_agent_normalizes_and_ingests_v2_snapshot(self):
        watchlist = {
            "ok": True,
            "pending_items": [
                {
                    "symbol": "005930",
                    "market": "KOSPI",
                    "name": "삼성전자",
                    "candidate_rank": 1,
                    "final_action": "review_for_entry",
                    "signal_state": "entry",
                }
            ],
        }
        agent_output = """```json
{
  "confidence": 0.84,
  "rating": "strong_buy",
  "action": "buy",
  "summary": "AI 메모리 수요와 차트가 모두 우호적이다.",
  "technical_features": {"close_vs_sma20": 1.04, "volume_ratio": 1.6, "rsi14": 61.0},
  "news_inputs": [{"title": "AI memory demand"}],
  "evidence": [{"type": "news", "summary": "AI memory demand"}],
  "trade_plan": {"entry_style": "staged", "size_intent_pct": 9.0}
}
```"""
        with (
            patch.object(runner, "handle_candidate_monitor_watchlist", return_value=(200, watchlist)),
            patch.object(runner, "call_hermes_agent", return_value=agent_output) as mock_agent,
            patch.object(runner, "handle_research_ingest_bulk", return_value=(200, {"ok": True, "accepted": 1})) as mock_ingest,
        ):
            status, payload = runner.run(markets=["KOSPI"], limit=1, mode="missing_or_stale", dry_run=False, agent_command=["hermes", "chat", "-q"])

        self.assertEqual(200, status)
        self.assertEqual("ingested", payload["stage"])
        mock_agent.assert_called_once()
        ingest_payload = mock_ingest.call_args.args[0]
        self.assertEqual("v2", ingest_payload["schema_version"])
        self.assertEqual("default", ingest_payload["provider"])
        item = ingest_payload["items"][0]
        self.assertEqual("005930", item["symbol"])
        self.assertEqual("KOSPI", item["market"])
        self.assertEqual("strong_buy", item["rating"])
        self.assertEqual("agent_research", item["data_quality"]["analysis_mode"])
        self.assertEqual(5.0, item["trade_plan"]["size_intent_pct"])
    def test_host_side_handlers_prefer_http_surface_by_default(self):
        with patch.object(runner, "_http_json", return_value=(200, {"ok": True, "pending_items": []})) as mock_http:
            status, payload = runner.handle_candidate_monitor_watchlist({"limit": ["1"]}, base_url="http://127.0.0.1:8001")

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        mock_http.assert_called_once_with("GET", "/api/monitor/watchlist", base_url="http://127.0.0.1:8001", query={"limit": ["1"]})

        with patch.object(runner, "_http_json", return_value=(200, {"ok": True, "accepted": 1})) as mock_http:
            status, payload = runner.handle_research_ingest_bulk({"items": []}, base_url="http://127.0.0.1:8001")

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        mock_http.assert_called_once_with("POST", "/api/research/ingest/bulk", base_url="http://127.0.0.1:8001", payload={"items": []})


if __name__ == "__main__":
    unittest.main()
