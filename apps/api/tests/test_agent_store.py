from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import agent_store


class AgentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_path = Path(self.tmpdir.name) / "agent_trading.db"
        self.store = agent_store.AgentAuditStore(self.db_path)

    def test_initialize_creates_required_audit_tables(self):
        self.store.initialize()

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "select name from sqlite_master where type='table' order by name"
            ).fetchall()

        table_names = {row[0] for row in rows}
        self.assertTrue({
            "agent_runs",
            "trade_candidates",
            "market_evidence",
            "trade_decisions",
            "risk_events",
            "trade_orders",
        }.issubset(table_names))

    def test_records_full_agent_run_audit_trail(self):
        run_id = self.store.create_run(trigger="manual", trading_mode="paper", status="running")
        candidate_id = self.store.add_candidate(
            run_id,
            symbol="005930",
            market="KOSPI",
            name="삼성전자",
            source="manual",
            payload={"rank": 1},
        )
        evidence_id = self.store.add_evidence(
            run_id,
            candidate_id=candidate_id,
            symbol="005930",
            evidence_type="chart",
            payload={"rsi14": 58.2},
        )
        decision_id = self.store.add_decision(
            run_id,
            candidate_id=candidate_id,
            symbol="005930",
            action="BUY",
            confidence=0.72,
            payload={"reason_summary": "테스트 판단"},
            raw_response="{\"action\":\"BUY\"}",
            schema_valid=True,
        )
        risk_event_id = self.store.add_risk_event(
            run_id,
            decision_id=decision_id,
            symbol="005930",
            approved=True,
            reason_code="approved",
            payload={"checks": []},
        )
        order_id = self.store.add_order(
            run_id,
            decision_id=decision_id,
            risk_event_id=risk_event_id,
            symbol="005930",
            action="BUY",
            trading_mode="paper",
            status="submitted",
            payload={"quantity": 1},
        )
        self.store.finish_run(run_id, status="completed", summary={"orders": 1})

        detail = self.store.get_run_detail(run_id)

        self.assertEqual(run_id, detail["run"]["id"])
        self.assertEqual("completed", detail["run"]["status"])
        self.assertEqual(candidate_id, detail["candidates"][0]["id"])
        self.assertEqual(evidence_id, detail["evidence"][0]["id"])
        self.assertEqual(decision_id, detail["decisions"][0]["id"])
        self.assertEqual(risk_event_id, detail["risk_events"][0]["id"])
        self.assertEqual(order_id, detail["orders"][0]["id"])
        self.assertEqual({"orders": 1}, detail["run"]["summary"])
        self.assertEqual({"quantity": 1}, detail["orders"][0]["payload"])

    def test_lists_recent_runs_and_filters_decisions_orders_evidence(self):
        run_id = self.store.create_run(trigger="manual", trading_mode="paper", status="running")
        candidate_id = self.store.add_candidate(run_id, symbol="005930", market="KOSPI", name="삼성전자", source="manual")
        decision_id = self.store.add_decision(run_id, candidate_id=candidate_id, symbol="005930", action="HOLD", confidence=0.2)
        risk_event_id = self.store.add_risk_event(run_id, decision_id=decision_id, symbol="005930", approved=False, reason_code="confidence_below_minimum")
        self.store.add_evidence(run_id, candidate_id=candidate_id, symbol="005930", evidence_type="news", payload={"title": "뉴스"})
        self.store.add_order(run_id, decision_id=decision_id, risk_event_id=risk_event_id, symbol="005930", action="HOLD", trading_mode="paper", status="skipped")
        self.store.finish_run(run_id, status="completed")

        self.assertEqual([run_id], [row["id"] for row in self.store.list_runs(limit=5)])
        self.assertEqual("HOLD", self.store.list_decisions(limit=5)[0]["action"])
        self.assertEqual("skipped", self.store.list_orders(limit=5)[0]["status"])
        self.assertEqual("news", self.store.list_evidence(symbol="005930", limit=5)[0]["evidence_type"])


if __name__ == "__main__":
    unittest.main()
