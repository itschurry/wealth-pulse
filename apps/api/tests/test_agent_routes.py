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

if "loguru" not in sys.modules:
    sys.modules["loguru"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    )

from routes import agent as agent_routes
from services.agent_store import AgentAuditStore


class AgentRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.store = AgentAuditStore(Path(self.tmpdir.name) / "agent_trading.db")
        self.store_patch = patch.object(agent_routes, "default_store", return_value=self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def test_post_agent_run_executes_paper_run_and_returns_run_id(self):
        payload = {
            "trading_mode": "paper",
            "candidates": [{"symbol": "005930", "market": "KOSPI", "name": "삼성전자"}],
            "evidence_by_symbol": {"005930": [{"type": "chart", "payload": {"rsi14": 58}}]},
            "decisions_by_symbol": {
                "005930": {
                    "action": "BUY",
                    "symbol": "005930",
                    "confidence": 0.72,
                    "reason_summary": "테스트",
                    "evidence": ["차트"],
                    "risk": {"entry_price": 81000, "stop_loss": 79000, "take_profit": 84000, "max_position_ratio": 0.05},
                }
            },
            "account": {"cash_krw": 2_000_000, "equity_krw": 10_000_000, "positions": []},
            "risk_config": {"min_confidence": 0.7, "min_reward_risk_ratio": 1.3, "max_symbol_position_ratio": 0.1},
        }

        with patch.object(agent_routes, "_submit_paper_order", return_value={"ok": True, "order_id": "paper-test"}):
            status, result = agent_routes.handle_agent_run(payload)

        self.assertEqual(200, status)
        self.assertTrue(result["ok"])
        self.assertGreater(result["run_id"], 0)
        detail = self.store.get_run_detail(result["run_id"])
        self.assertEqual("BUY", detail["decisions"][0]["action"])
        self.assertEqual("submitted", detail["orders"][0]["status"])

    def test_get_routes_return_runs_decisions_orders_and_evidence(self):
        run_id = self.store.create_run(trigger="manual", trading_mode="paper", status="completed")
        candidate_id = self.store.add_candidate(run_id, symbol="005930", market="KOSPI")
        decision_id = self.store.add_decision(run_id, candidate_id=candidate_id, symbol="005930", action="HOLD", confidence=0.1)
        risk_id = self.store.add_risk_event(run_id, decision_id=decision_id, symbol="005930", approved=False, reason_code="hold_decision")
        self.store.add_evidence(run_id, candidate_id=candidate_id, symbol="005930", evidence_type="news", payload={"title": "뉴스"})
        self.store.add_order(run_id, decision_id=decision_id, risk_event_id=risk_id, symbol="005930", action="HOLD", trading_mode="paper", status="skipped")

        self.assertEqual(200, agent_routes.handle_agent_runs({})[0])
        self.assertEqual(run_id, agent_routes.handle_agent_run_detail(f"/api/agent/runs/{run_id}")[1]["run"]["id"])
        self.assertEqual("HOLD", agent_routes.handle_agent_decisions({})[1]["items"][0]["action"])
        self.assertEqual("skipped", agent_routes.handle_agent_orders({})[1]["items"][0]["status"])
        self.assertEqual("news", agent_routes.handle_agent_evidence("/api/agent/evidence/005930", {})[1]["items"][0]["evidence_type"])

    def test_post_agent_run_can_collect_monitor_candidates(self):
        with patch.object(agent_routes, "handle_candidate_monitor_watchlist", return_value=(200, {
            "ok": True,
            "pending_items": [{"symbol": "005930", "market": "KOSPI", "name": "삼성전자", "source": "monitor"}],
        })) as mock_watchlist:
            status, result = agent_routes.handle_agent_run({
                "trading_mode": "paper",
                "candidate_source": "monitor_watchlist",
                "markets": ["KOSPI"],
                "limit": 1,
            })

        self.assertEqual(200, status)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["summary"]["candidate_count"])
        detail = self.store.get_run_detail(result["run_id"])
        self.assertEqual("005930", detail["candidates"][0]["symbol"])
        mock_watchlist.assert_called_once()

    def test_post_agent_run_can_use_hermes_decision_provider(self):
        with patch.object(agent_routes, "call_hermes_trade_decision", return_value={
            "action": "BUY",
            "symbol": "005930",
            "market": "KOSPI",
            "confidence": 0.75,
            "reason_summary": "Hermes decision",
            "evidence": ["chart"],
            "risk": {"entry_price": 81000, "stop_loss": 79000, "take_profit": 85000, "max_position_ratio": 0.05},
        }) as mock_hermes, patch.object(agent_routes, "_submit_paper_order", return_value={"ok": True, "order_id": "paper-1"}):
            status, result = agent_routes.handle_agent_run({
                "trading_mode": "paper",
                "decision_source": "hermes",
                "candidates": [{"symbol": "005930", "market": "KOSPI"}],
                "account": {"cash_krw": 2_000_000, "equity_krw": 10_000_000, "positions": []},
                "risk_config": {"min_confidence": 0.7, "min_reward_risk_ratio": 1.3},
            })

        self.assertEqual(200, status)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["summary"]["orders_submitted"])
        self.assertTrue(mock_hermes.called)

    def test_paper_executor_uses_execution_service_order_path(self):
        with patch.object(agent_routes, "handle_paper_order", return_value=(200, {"ok": True, "order_id": "paper-1"})) as mock_order:
            result = agent_routes._paper_order_executor({"action": "BUY", "symbol": "005930", "market": "KOSPI", "quantity": 3})

        self.assertTrue(result["ok"])
        mock_order.assert_called_once_with({
            "side": "buy",
            "code": "005930",
            "market": "KOSPI",
            "quantity": 3,
            "order_type": "market",
        })

    def test_research_snapshot_decision_source_maps_latest_snapshot_to_decision(self):
        snapshot = {
            "symbol": "005930",
            "market": "KOSPI",
            "action": "buy_watch",
            "confidence": 0.76,
            "summary": "리서치 스냅샷 기반",
            "trade_plan": {"entry_price": 81000, "stop_loss": 79000, "take_profit": 85000, "size_intent_pct": 5},
            "evidence": [{"title": "근거"}],
        }
        with patch.object(agent_routes, "handle_research_latest_snapshot", return_value=(200, {"snapshot": snapshot})), \
             patch.object(agent_routes, "_submit_paper_order", return_value={"ok": True, "order_id": "paper-2"}):
            status, result = agent_routes.handle_agent_run({
                "trading_mode": "paper",
                "decision_source": "research_snapshot",
                "candidates": [{"symbol": "005930", "market": "KOSPI"}],
                "account": {"cash_krw": 2_000_000, "equity_krw": 10_000_000, "positions": []},
                "risk_config": {"min_confidence": 0.7, "min_reward_risk_ratio": 1.3},
            })

        detail = self.store.get_run_detail(result["run_id"])
        self.assertEqual(200, status)
        self.assertEqual("BUY", detail["decisions"][0]["action"])
        self.assertEqual("submitted", detail["orders"][0]["status"])


if __name__ == "__main__":
    unittest.main()
