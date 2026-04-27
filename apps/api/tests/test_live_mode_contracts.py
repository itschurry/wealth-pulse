from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.execution_lifecycle import build_execution_events
from services.execution_service import _build_status_payload, _start_auto_trader, handle_paper_account
from services.system_mode_service import get_mode_status


class _FakeLiveEngine:
    def get_account(self, *, refresh_quotes: bool = True) -> dict:
        return {
            "mode": "real",
            "account_product_code": "01",
            "positions": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 3,
                    "orderable_quantity": 3,
                    "avg_price": 70000.0,
                    "current_price": 71000.0,
                    "eval_amount": 213000.0,
                    "profit_loss": 3000.0,
                    "profit_loss_rate": 1.43,
                }
            ],
            "summary": {
                "deposit": 2507620.0,
                "buy_amount": 210000.0,
                "eval_amount": 213000.0,
                "eval_profit_loss": 3000.0,
                "total_amount": 2720620.0,
            },
        }


class _FakeMixedLiveEngine:
    def get_account(self, *, refresh_quotes: bool = True) -> dict:
        return {
            "mode": "real",
            "account_product_code": "01",
            "positions": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "market": "KOSPI",
                    "currency": "KRW",
                    "quantity": 3,
                    "orderable_quantity": 3,
                    "avg_price": 70000.0,
                    "current_price": 71000.0,
                    "eval_amount": 213000.0,
                    "profit_loss": 3000.0,
                    "profit_loss_rate": 1.43,
                    "fx_rate": 1.0,
                },
                {
                    "code": "AAPL",
                    "name": "Apple Inc.",
                    "market": "NASDAQ",
                    "currency": "USD",
                    "quantity": 2,
                    "orderable_quantity": 2,
                    "avg_price": 150.5,
                    "current_price": 160.0,
                    "eval_amount": 320.0,
                    "profit_loss": 19.0,
                    "profit_loss_rate": 6.31,
                    "fx_rate": 1450.0,
                },
            ],
            "summary": {
                "cash_krw": 2000000.0,
                "cash_usd": 1000.0,
                "buy_amount_krw": 210000.0,
                "buy_amount_usd": 301.0,
                "eval_amount_krw": 213000.0,
                "eval_amount_usd": 320.0,
                "eval_profit_loss_krw": 3000.0,
                "eval_profit_loss_usd": 19.0,
                "total_amount_krw": 4147000.0,
                "fx_rate": 1450.0,
            },
        }


class _FakeLiveEngineWithRawDomesticFill:
    def get_account(self, *, refresh_quotes: bool = True) -> dict:
        return {
            "mode": "real",
            "account_product_code": "01",
            "positions": [
                {
                    "code": "002700",
                    "name": "신일전자",
                    "market": "KOSPI",
                    "currency": "KRW",
                    "quantity": 128,
                    "orderable_quantity": 128,
                    "avg_price": 1478.0,
                    "current_price": 1472.0,
                    "eval_amount": 188416.0,
                    "profit_loss": -768.0,
                    "profit_loss_rate": -0.4,
                    "fx_rate": 1.0,
                }
            ],
            "summary": {
                "cash_krw": 1546565.0,
                "cash_usd": 0.0,
                "eval_amount_krw": 188416.0,
                "eval_profit_loss_krw": -768.0,
                "total_amount_krw": 1734981.0,
                "fx_rate": 1.0,
            },
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


class _FakePaperEngine:
    def get_account(self, *, refresh_quotes: bool = True) -> dict:
        return {
            "mode": "paper",
            "cash_krw": 111.0,
            "equity_krw": 222.0,
            "market_value_krw": 0.0,
            "positions": [],
            "orders": [],
            "days_left": 30,
        }


class _FakeNotifier:
    def notify_engine_started(self, payload):
        return None


class _FakeThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started


class LiveModeContractTests(unittest.TestCase):
    def test_get_mode_status_falls_back_to_execution_mode_when_auto_mode_missing(self):
        with patch.dict(os.environ, {"EXECUTION_MODE": "live"}, clear=True):
            payload = get_mode_status()

        self.assertTrue(payload["ok"])
        self.assertEqual("live_ready", payload["current_mode"])

    def test_handle_paper_account_normalizes_live_account_shape(self):
        with (
            patch.dict(os.environ, {"EXECUTION_MODE": "live"}, clear=True),
            patch("services.execution_service.get_execution_engine", return_value=_FakeLiveEngine()),
        ):
            status, payload = handle_paper_account(False)

        self.assertEqual(200, status)
        self.assertEqual("real", payload["mode"])
        self.assertEqual(2507620.0, payload["cash_krw"])
        self.assertEqual(2720620.0, payload["equity_krw"])
        self.assertEqual(213000.0, payload["market_value_krw"])
        self.assertEqual(1, len(payload["positions"]))
        self.assertEqual("KOSPI", payload["positions"][0]["market"])
        self.assertEqual("KRW", payload["positions"][0]["currency"])
        self.assertEqual(3, payload["positions"][0]["quantity"])
        self.assertEqual(70000.0, payload["positions"][0]["avg_price_local"])
        self.assertEqual(70000.0, payload["positions"][0]["avg_price_krw"])
        self.assertEqual(71000.0, payload["positions"][0]["last_price_local"])
        self.assertEqual(71000.0, payload["positions"][0]["last_price_krw"])
        self.assertEqual(213000.0, payload["positions"][0]["market_value_krw"])
        self.assertEqual(3000.0, payload["positions"][0]["unrealized_pnl_krw"])
        self.assertEqual(1.43, payload["positions"][0]["unrealized_pnl_pct"])

    def test_build_status_payload_normalizes_live_account_for_engine_status(self):
        payload = _build_status_payload(
            {
                "engine_state": "stopped",
                "current_config": {},
            },
            _FakeLiveEngine().get_account(refresh_quotes=False),
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(2720620.0, payload["state"]["current_equity"])
        self.assertEqual(2507620.0, payload["account"]["cash_krw"])
        self.assertEqual(213000.0, payload["account"]["market_value_krw"])
        self.assertEqual("KOSPI", payload["account"]["positions"][0]["market"])

    def test_live_account_backfills_entry_ts_and_today_fill_counts_from_logs(self):
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
            "order_id": "ord-live-002700",
            "trace_id": "ord-live-002700",
        }
        execution_events = build_execution_events(order_event)

        with (
            patch.dict(os.environ, {"EXECUTION_MODE": "live"}, clear=True),
            patch("services.execution_service.get_execution_engine", return_value=_FakeLiveEngineWithRawDomesticFill()),
            patch("services.execution_service.read_order_events", return_value=[order_event]),
            patch("services.execution_service.read_execution_events", return_value=execution_events),
        ):
            status, payload = handle_paper_account(False)
            status_payload = _build_status_payload(
                {
                    "engine_state": "running",
                    "current_config": {},
                },
                _FakeLiveEngineWithRawDomesticFill().get_account(refresh_quotes=False),
            )

        self.assertEqual(200, status)
        self.assertEqual("2026-04-27T03:48:21+00:00", payload["positions"][0]["entry_ts"])
        self.assertEqual(1, len(payload["orders"]))
        self.assertEqual(128, payload["orders"][0]["quantity"])
        self.assertTrue(str(payload["orders"][0]["filled_at"] or "").strip())
        self.assertEqual(1, status_payload["state"]["today_order_counts"]["buy"])
        self.assertEqual(0, status_payload["state"]["today_order_counts"]["sell"])
        self.assertEqual(0, status_payload["state"]["today_order_counts"]["failed"])

    def test_handle_paper_account_preserves_nasdaq_positions_for_ui_table(self):
        with (
            patch.dict(os.environ, {"EXECUTION_MODE": "live"}, clear=True),
            patch("services.execution_service.get_execution_engine", return_value=_FakeMixedLiveEngine()),
        ):
            status, payload = handle_paper_account(False)

        self.assertEqual(200, status)
        self.assertEqual(2000000.0, payload["cash_krw"])
        self.assertEqual(1000.0, payload["cash_usd"])
        self.assertEqual(677000.0, payload["market_value_krw"])
        self.assertEqual(320.0, payload["market_value_usd"])
        self.assertEqual(4147000.0, payload["equity_krw"])
        nasdaq = next(item for item in payload["positions"] if item["code"] == "AAPL")
        self.assertEqual("NASDAQ", nasdaq["market"])
        self.assertEqual("USD", nasdaq["currency"])
        self.assertEqual(150.5, nasdaq["avg_price_local"])
        self.assertEqual(218225.0, nasdaq["avg_price_krw"])
        self.assertEqual(160.0, nasdaq["last_price_local"])
        self.assertEqual(232000.0, nasdaq["last_price_krw"])
        self.assertEqual(464000.0, nasdaq["market_value_krw"])
        self.assertEqual(27550.0, nasdaq["unrealized_pnl_krw"])

    def test_start_auto_trader_uses_live_account_in_response_payload(self):
        fake_thread = _FakeThread()
        baseline_state = {
            "engine_state": "stopped",
            "running": False,
            "current_config": {},
            "config": {},
            "validation_policy": {},
            "optimized_params": {},
            "last_error": "",
            "last_error_at": "",
            "started_at": "",
            "paused_at": "",
            "stopped_at": "",
            "next_run_at": "",
        }
        with (
            patch.dict(os.environ, {"EXECUTION_MODE": "live"}, clear=True),
            patch("services.execution_service._hydrate_auto_trader_state", return_value=None),
            patch("services.execution_service._persist_auto_trader_state_locked", return_value=None),
            patch("services.execution_service._optimized_params_status", return_value={}),
            patch("services.execution_service.get_execution_engine", return_value=_FakeMixedLiveEngine()),
            patch("services.execution_service._get_paper_engine", return_value=_FakePaperEngine()),
            patch("services.execution_service.get_notification_service", return_value=_FakeNotifier()),
            patch("services.execution_service.threading.Thread", return_value=fake_thread),
            patch.object(sys.modules["services.execution_service"], "_auto_trader_state", dict(baseline_state)),
            patch.object(sys.modules["services.execution_service"], "_auto_trader_thread", None),
            patch.object(sys.modules["services.execution_service"], "_auto_trader_stop_event", None),
        ):
            payload = _start_auto_trader({"markets": ["KOSPI"]})

        self.assertTrue(payload["ok"])
        self.assertEqual("running", payload["state"]["engine_state"])
        self.assertEqual("real", payload["account"]["mode"])
        self.assertEqual(2000000.0, payload["account"]["cash_krw"])
        self.assertEqual(4147000.0, payload["account"]["equity_krw"])


if __name__ == "__main__":
    unittest.main()
