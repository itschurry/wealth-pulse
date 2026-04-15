from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.engine import handle_engine_summary


class _FakeExecutionService:
    def paper_engine_status(self) -> tuple[int, dict]:
        return 200, {
            "ok": True,
            "state": {
                "engine_state": "running",
                "running": True,
                "started_at": "2026-04-15T01:00:00+00:00",
                "next_run_at": "2026-04-15T01:00:30+00:00",
                "last_error": "",
                "today_order_counts": {"buy": 1, "sell": 0, "failed": 2},
                "order_failure_summary": {"today_failed": 2, "top_reason": "insufficient_cash"},
                "today_realized_pnl": 12345.0,
                "current_equity": 25000000.0,
                "validation_policy": {"validation_gate_enabled": False, "validation_min_trades": 8},
                "optimized_params": {"version": "strategy_registry", "is_stale": False, "effective_source": "strategy_registry"},
                "last_summary": {
                    "cycle_id": "cycle-1",
                    "candidate_counts_by_market": {"KOSPI": 3, "NASDAQ": 0},
                    "blocked_reason_counts": {"market_closed": 1},
                    "rotation_summary": {"attempted_count": 1, "executed_count": 0},
                    "skip_reason_counts": {"market_closed": 1},
                    "market_stats": {
                        "KOSPI": {"candidate_count": 3, "market_closed": False},
                        "NASDAQ": {"candidate_count": 0, "market_closed": True},
                    },
                    "closed_markets": ["NASDAQ"],
                    "risk_guard_state": {"entry_allowed": True, "reasons": []},
                    "validation_gate_summary": {"enabled": False},
                    "pnl_snapshot": {"equity_krw": 25000000.0},
                    "executed_buys": [{"code": "005930"}],
                    "executed_sells": [],
                    "brief_candidates": {"buy": [{"code": "005930"}]},
                    "account": {"positions": [{"code": "005930"}]},
                    "skipped": [{"reason": "market_closed"}, {"reason": "max_positions_reached"}],
                },
            },
            "account": {
                "equity_krw": 25000000.0,
                "positions": [{"code": "005930"}],
            },
        }


class EngineRouteTests(unittest.TestCase):
    def test_handle_engine_summary_returns_compact_payload(self):
        service = _FakeExecutionService()
        scans = [
            {
                "strategy_id": "kr_momentum_v1",
                "top_candidates": [
                    {"entry_allowed": True, "risk_guard_state": {"entry_allowed": True, "reasons": []}},
                    {"entry_allowed": False, "signal_state": "entry"},
                ],
            },
        ]

        with (
            patch("routes.engine.get_execution_service", return_value=service),
            patch("routes.engine.list_strategy_scans", return_value=scans),
            patch("routes.engine.get_mode_status", return_value={"current_mode": "paper"}),
            patch("routes.engine._context_snapshot", return_value=("neutral", "중간")),
        ):
            status, payload = handle_engine_summary()

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual({"current_mode": "paper"}, payload["mode"])
        self.assertNotIn("scanner", payload)
        self.assertNotIn("registry", payload)
        self.assertEqual(1, payload["allocator"]["entry_allowed_count"])
        self.assertEqual(1, payload["allocator"]["blocked_count"])
        self.assertEqual("neutral", payload["allocator"]["regime"])
        self.assertEqual("중간", payload["allocator"]["risk_level"])
        self.assertEqual({"entry_allowed": True, "reasons": []}, payload["risk_guard_state"])
        self.assertEqual(
            {
                "equity_krw": 25000000.0,
                "cash_krw": None,
                "cash_usd": None,
                "positions": [{"code": "005930"}],
            },
            payload["execution"]["account"],
        )
        self.assertEqual("running", payload["execution"]["state"]["engine_state"])
        self.assertEqual({"buy": 1, "sell": 0, "failed": 2}, payload["execution"]["state"]["today_order_counts"])
        self.assertEqual(2, payload["execution"]["state"]["last_summary"]["skipped_count"])
        self.assertNotIn("account", payload["execution"]["state"]["last_summary"])
        self.assertNotIn("executed_buys", payload["execution"]["state"]["last_summary"])
        self.assertNotIn("brief_candidates", payload["execution"]["state"]["last_summary"])


if __name__ == "__main__":
    unittest.main()
