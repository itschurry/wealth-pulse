from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.agent_runner import run_agent_once
from services.agent_store import AgentAuditStore


class AgentRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.store = AgentAuditStore(Path(self.tmpdir.name) / "agent_trading.db")
        self.candidate = {"symbol": "005930", "market": "KOSPI", "name": "삼성전자", "source": "manual"}
        self.evidence = [{"type": "chart", "payload": {"rsi14": 58.0}}]
        self.account = {"cash_krw": 2_000_000, "equity_krw": 10_000_000, "positions": []}
        self.config = {"trading_mode": "paper", "min_confidence": 0.7, "min_reward_risk_ratio": 1.3, "max_symbol_position_ratio": 0.1}

    def test_approved_buy_records_audit_and_paper_order(self):
        decision_json = '{"action":"BUY","symbol":"005930","confidence":0.72,"reason_summary":"테스트","evidence":["차트"],"risk":{"entry_price":81000,"stop_loss":79000,"take_profit":84000,"max_position_ratio":0.05}}'
        submitted = []

        result = run_agent_once(
            candidates=[self.candidate],
            evidence_by_symbol={"005930": self.evidence},
            decision_provider=lambda _candidate, _evidence: decision_json,
            account_provider=lambda: self.account,
            order_executor=lambda intent: submitted.append(intent) or {"ok": True, "broker_order_id": "paper-1"},
            config=self.config,
            store=self.store,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(1, result["summary"]["orders_submitted"])
        self.assertEqual("005930", submitted[0]["symbol"])
        detail = self.store.get_run_detail(result["run_id"])
        self.assertEqual("completed", detail["run"]["status"])
        self.assertEqual("BUY", detail["decisions"][0]["action"])
        self.assertTrue(detail["risk_events"][0]["approved"])
        self.assertEqual("submitted", detail["orders"][0]["status"])

    def test_rejected_decision_records_skip_without_calling_executor(self):
        decision_json = '{"action":"BUY","symbol":"005930","confidence":0.4,"reason_summary":"약함","evidence":[],"risk":{"entry_price":81000,"stop_loss":79000,"take_profit":84000,"max_position_ratio":0.05}}'

        result = run_agent_once(
            candidates=[self.candidate],
            evidence_by_symbol={"005930": self.evidence},
            decision_provider=lambda _candidate, _evidence: decision_json,
            account_provider=lambda: self.account,
            order_executor=lambda _intent: self.fail("executor must not be called"),
            config=self.config,
            store=self.store,
        )

        detail = self.store.get_run_detail(result["run_id"])
        self.assertEqual(0, result["summary"]["orders_submitted"])
        self.assertEqual("confidence_below_minimum", detail["risk_events"][0]["reason_code"])
        self.assertEqual("skipped", detail["orders"][0]["status"])

    def test_invalid_json_becomes_hold_and_is_recorded(self):
        result = run_agent_once(
            candidates=[self.candidate],
            evidence_by_symbol={"005930": self.evidence},
            decision_provider=lambda _candidate, _evidence: "삼성전자 BUY",
            account_provider=lambda: self.account,
            order_executor=lambda _intent: self.fail("executor must not be called"),
            config=self.config,
            store=self.store,
        )

        detail = self.store.get_run_detail(result["run_id"])
        self.assertFalse(detail["decisions"][0]["schema_valid"])
        self.assertEqual("HOLD", detail["decisions"][0]["action"])
        self.assertIn("parse_error", detail["decisions"][0]["payload"]["schema_errors"])
        self.assertEqual("hold_decision", detail["risk_events"][0]["reason_code"])


    def test_invalid_decision_falls_back_to_candidate_symbol_and_skips_order(self):
        result = run_agent_once(
            candidates=[{"symbol": "005930", "market": "KOSPI"}],
            decision_provider=lambda _candidate, _evidence: {"action": "BUY", "confidence": 0.8},
            store=self.store,
            config={"trading_mode": "paper"},
        )

        detail = self.store.get_run_detail(result["run_id"])
        self.assertEqual("005930", detail["decisions"][0]["symbol"])
        self.assertFalse(detail["decisions"][0]["schema_valid"])
        self.assertEqual("skipped", detail["orders"][0]["status"])


if __name__ == "__main__":
    unittest.main()
