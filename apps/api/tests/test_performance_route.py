from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.performance import handle_performance_summary
from services.execution_lifecycle import build_execution_events


class _FakeExecutionService:
    def __init__(self, account: dict) -> None:
        self.account = account

    def paper_engine_status(self) -> tuple[int, dict]:
        return 200, {
            "ok": True,
            "state": {
                "last_summary": {
                    "candidate_counts_by_market": {"KOSPI": 0, "NASDAQ": 0},
                }
            },
            "account": self.account,
        }

    def paper_account(self, _refresh_quotes: bool) -> tuple[int, dict]:
        return 200, self.account


class PerformanceRouteTests(unittest.TestCase):
    def test_handle_performance_summary_excludes_submitted_live_orders_from_filled_history(self):
        account = {
            "mode": "real",
            "account_product_code": "01",
            "cash_krw": 700000.0,
            "cash_usd": 0.0,
            "equity_krw": 1000000.0,
            "fx_rate": 1450.0,
            "positions": [],
            "summary": {"total_amount": 1000000.0},
        }
        order_event = {
            "logged_at": "2026-04-25T00:00:05+00:00",
            "timestamp": "2026-04-25T00:00:05+00:00",
            "submitted_at": "2026-04-25T00:00:03+00:00",
            "success": True,
            "side": "buy",
            "code": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "currency": "KRW",
            "quantity": None,
            "order_type": "market",
            "filled_at": "",
            "filled_price_local": None,
            "filled_price_krw": None,
            "notional_local": None,
            "notional_krw": None,
            "order_id": "ord-accepted-1",
            "trace_id": "ord-accepted-1",
        }
        execution_events = build_execution_events(order_event)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("routes.performance.get_execution_service", return_value=_FakeExecutionService(account)),
                patch("routes.performance._read_account_state", return_value={}),
                patch("routes.performance.read_order_events", return_value=[order_event]),
                patch("routes.performance.read_execution_events", return_value=execution_events),
                patch("services.execution_service.read_order_events", return_value=[order_event]),
                patch("services.execution_service.read_execution_events", return_value=execution_events),
                patch("routes.performance.build_operations_report", return_value={"report": {}, "alerts": []}),
                patch("routes.performance._LIVE_PERFORMANCE_BASELINE_PATH", Path(tmpdir) / "live_baseline.json"),
            ):
                status, payload = handle_performance_summary()

        self.assertEqual(200, status)
        self.assertEqual(0, payload["live"]["total_filled_count"])
        self.assertEqual(1, payload["live"]["total_order_count"])
        self.assertEqual([], payload["live"]["filled_history"])
        self.assertEqual(1, len(payload["live"]["order_history"]))
        self.assertEqual("accepted", payload["live"]["order_history"][0]["status"])

    def test_handle_performance_summary_keeps_filled_orders_in_filled_history(self):
        account = {
            "mode": "real",
            "account_product_code": "01",
            "cash_krw": 700000.0,
            "cash_usd": 0.0,
            "equity_krw": 1000000.0,
            "fx_rate": 1450.0,
            "positions": [],
            "summary": {"total_amount": 1000000.0},
        }
        order_event = {
            "logged_at": "2026-04-25T00:01:05+00:00",
            "timestamp": "2026-04-25T00:01:05+00:00",
            "submitted_at": "2026-04-25T00:01:03+00:00",
            "success": True,
            "side": "buy",
            "code": "000660",
            "name": "SK하이닉스",
            "market": "KOSPI",
            "currency": "KRW",
            "quantity": 3,
            "order_type": "market",
            "filled_at": "2026-04-25T00:01:07+00:00",
            "filled_price_local": 1000.0,
            "filled_price_krw": 1000.0,
            "notional_local": 3000.0,
            "notional_krw": 3000.0,
            "order_id": "ord-filled-1",
            "trace_id": "ord-filled-1",
        }
        execution_events = build_execution_events(order_event)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("routes.performance.get_execution_service", return_value=_FakeExecutionService(account)),
                patch("routes.performance._read_account_state", return_value={}),
                patch("routes.performance.read_order_events", return_value=[order_event]),
                patch("routes.performance.read_execution_events", return_value=execution_events),
                patch("services.execution_service.read_order_events", return_value=[order_event]),
                patch("services.execution_service.read_execution_events", return_value=execution_events),
                patch("routes.performance.build_operations_report", return_value={"report": {}, "alerts": []}),
                patch("routes.performance._LIVE_PERFORMANCE_BASELINE_PATH", Path(tmpdir) / "live_baseline.json"),
            ):
                status, payload = handle_performance_summary()

        self.assertEqual(200, status)
        self.assertEqual(1, payload["live"]["total_filled_count"])
        self.assertEqual(1, len(payload["live"]["filled_history"]))
        self.assertEqual("filled", payload["live"]["filled_history"][0]["status"])
        self.assertEqual(3, payload["live"]["filled_history"][0]["quantity"])

    def test_handle_performance_summary_persists_live_starting_equity_baseline(self):
        account_first = {
            "mode": "real",
            "account_product_code": "01",
            "cash_krw": 1000.0,
            "cash_usd": 0.0,
            "equity_krw": 1000.0,
            "fx_rate": 1450.0,
            "positions": [],
            "summary": {"total_amount": 1000.0},
        }
        account_second = {
            "mode": "real",
            "account_product_code": "01",
            "cash_krw": 1100.0,
            "cash_usd": 0.0,
            "equity_krw": 1100.0,
            "fx_rate": 1450.0,
            "positions": [],
            "summary": {"total_amount": 1100.0},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_path = Path(tmpdir) / "live_baseline.json"
            common_patches = (
                patch("routes.performance._read_account_state", return_value={}),
                patch("routes.performance.read_order_events", return_value=[]),
                patch("routes.performance.read_execution_events", return_value=[]),
                patch("services.execution_service.read_order_events", return_value=[]),
                patch("services.execution_service.read_execution_events", return_value=[]),
                patch("routes.performance.build_operations_report", return_value={"report": {}, "alerts": []}),
                patch("routes.performance._LIVE_PERFORMANCE_BASELINE_PATH", baseline_path),
            )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], common_patches[6], patch(
                "routes.performance.get_execution_service", return_value=_FakeExecutionService(account_first)
            ):
                first_status, first_payload = handle_performance_summary()

            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], common_patches[6], patch(
                "routes.performance.get_execution_service", return_value=_FakeExecutionService(account_second)
            ):
                second_status, second_payload = handle_performance_summary()

        self.assertEqual(200, first_status)
        self.assertEqual(1000.0, first_payload["live"]["starting_equity_krw"])
        self.assertEqual(0.0, first_payload["live"]["total_return_pct"])
        self.assertEqual(200, second_status)
        self.assertEqual(1000.0, second_payload["live"]["starting_equity_krw"])
        self.assertEqual(10.0, second_payload["live"]["total_return_pct"])

    def test_handle_performance_summary_reconciles_live_balance_fill_evidence(self):
        account = {
            "mode": "real",
            "account_product_code": "01",
            "cash_krw": 1546565.0,
            "cash_usd": 0.0,
            "equity_krw": 1734981.0,
            "fx_rate": 1.0,
            "positions": [
                {
                    "code": "002700",
                    "name": "신일전자",
                    "market": "KOSPI",
                    "currency": "KRW",
                    "quantity": 128,
                    "avg_price_local": 1478.0,
                    "avg_price_krw": 1478.0,
                    "last_price_local": 1472.0,
                    "last_price_krw": 1472.0,
                    "market_value_krw": 188416.0,
                    "market_value_usd": 0.0,
                    "unrealized_pnl_krw": -768.0,
                    "unrealized_pnl_local": -768.0,
                    "unrealized_pnl_pct": -0.4,
                }
            ],
            "summary": {"total_amount": 1734981.0},
            "raw": {
                "positions": [
                    {
                        "pdno": "002700",
                        "prdt_name": "신일전자",
                        "hldg_qty": "128",
                        "ord_psbl_qty": "128",
                        "thdt_buyqty": "128",
                        "thdt_sll_qty": "0",
                        "pchs_avg_pric": "1478.0000",
                        "prpr": "1472",
                        "evlu_amt": "188416",
                        "evlu_pfls_amt": "-768",
                        "evlu_pfls_rt": "-0.40"
                    }
                ],
                "summary": [{}],
                "overseas_positions": [],
                "overseas_summaries": {},
            },
        }
        order_event = {
            "logged_at": "2026-04-27T03:48:23+00:00",
            "timestamp": "2026-04-27T03:48:23+00:00",
            "submitted_at": "2026-04-27T03:48:21+00:00",
            "success": True,
            "side": "buy",
            "code": "002700",
            "name": "신일전자",
            "market": "KOSPI",
            "currency": "KRW",
            "quantity": 128,
            "order_type": "market",
            "filled_at": "",
            "filled_price_local": None,
            "filled_price_krw": None,
            "notional_local": None,
            "notional_krw": None,
            "order_id": "ord-live-fill-1",
            "trace_id": "ord-live-fill-1",
        }
        execution_events = build_execution_events(order_event)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("routes.performance.get_execution_service", return_value=_FakeExecutionService(account)),
                patch("routes.performance._read_account_state", return_value={}),
                patch("routes.performance.read_order_events", return_value=[order_event]),
                patch("routes.performance.read_execution_events", return_value=execution_events),
                patch("services.execution_service.read_order_events", return_value=[order_event]),
                patch("services.execution_service.read_execution_events", return_value=execution_events),
                patch("routes.performance.build_operations_report", return_value={"report": {}, "alerts": []}),
                patch("routes.performance._LIVE_PERFORMANCE_BASELINE_PATH", Path(tmpdir) / "live_baseline.json"),
            ):
                status, payload = handle_performance_summary()

        self.assertEqual(200, status)
        self.assertEqual(1, payload["live"]["total_order_count"])
        self.assertEqual(1, payload["live"]["total_filled_count"])
        self.assertEqual(1, len(payload["live"]["filled_history"]))
        self.assertEqual("filled", payload["live"]["filled_history"][0]["status"])
        self.assertEqual(128, payload["live"]["filled_history"][0]["quantity"])


if __name__ == "__main__":
    unittest.main()
