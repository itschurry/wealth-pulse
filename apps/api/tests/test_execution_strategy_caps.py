from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

if "holidays" not in sys.modules:
    sys.modules["holidays"] = types.SimpleNamespace(KR=lambda *args, **kwargs: set(), US=lambda *args, **kwargs: set())

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import execution_service as execution_svc


class _FakeNotifier:
    def notify_order_failure(self, payload):
        return None


class _FakeEngine:
    def __init__(self):
        self.account = {
            "days_left": 30,
            "positions": [
                {"code": "AAA", "market": "KOSPI", "quantity": 1, "avg_price_local": 1000, "avg_price_krw": 1000},
                {"code": "BBB", "market": "KOSPI", "quantity": 1, "avg_price_local": 1000, "avg_price_krw": 1000},
            ],
            "orders": [],
            "equity_krw": 1000000,
        }
        self.placed_orders: list[dict] = []

    def get_account(self, refresh_quotes: bool = True):
        return self.account

    def place_order(self, **kwargs):
        self.placed_orders.append(dict(kwargs))
        code = str(kwargs.get("code") or "").upper()
        market = str(kwargs.get("market") or "").upper()
        quantity = int(kwargs.get("quantity") or 0)
        event = {
            "ts": "2026-04-10T09:10:00+09:00",
            "quantity": quantity,
            "filled_price_local": 1000.0,
            "filled_price_krw": 1000.0,
            "notional_krw": 1000.0 * quantity,
        }
        self.account["orders"].append({
            "ts": event["ts"],
            "market": market,
            "code": code,
            "side": kwargs.get("side"),
        })
        if kwargs.get("side") == "buy":
            self.account["positions"].append({
                "code": code,
                "market": market,
                "quantity": quantity,
                "avg_price_local": 1000.0,
                "avg_price_krw": 1000.0,
            })
        return {"ok": True, "event": event, "account": self.account}


class ExecutionStrategyCapTests(unittest.TestCase):
    def test_handle_paper_order_forwards_stop_loss_and_take_profit(self):
        engine = _FakeEngine()

        with patch.object(execution_svc, "get_execution_engine", return_value=engine), \
             patch.object(execution_svc, "_hydrate_auto_trader_state", return_value=None), \
             patch.object(execution_svc, "_record_execution_order", side_effect=lambda payload: payload), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None):
            status, payload = execution_svc.handle_paper_order({
                "side": "buy",
                "code": "AAPL",
                "market": "NASDAQ",
                "quantity": 3,
                "order_type": "market",
                "stop_loss_pct": 4.5,
                "take_profit_pct": 11.0,
            })

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(1, len(engine.placed_orders))
        self.assertEqual(4.5, engine.placed_orders[0]["stop_loss_pct"])
        self.assertEqual(11.0, engine.placed_orders[0]["take_profit_pct"])

    def test_infer_strategy_position_counts_reads_full_order_history(self):
        account = {
            "positions": [
                {"code": "AAA", "market": "KOSPI"},
                {"code": "BBB", "market": "KOSPI"},
            ]
        }
        older_buy = {"success": True, "side": "buy", "market": "KOSPI", "code": "AAA", "strategy_id": "alpha"}
        filler = [
            {"success": True, "side": "buy", "market": "KOSPI", "code": f"ZZ{i:03d}", "strategy_id": "beta"}
            for i in range(600)
        ]
        recent_buy = {"success": True, "side": "buy", "market": "KOSPI", "code": "BBB", "strategy_id": "alpha"}
        history = [older_buy, *filler, recent_buy]

        def _read_events(limit=100):
            if limit is None:
                return history
            return history[-int(limit):]

        with patch.object(execution_svc, "read_order_events", side_effect=_read_events):
            counts = execution_svc._infer_strategy_position_counts(account, "KOSPI")

        self.assertEqual({"alpha": 2}, counts)

    def test_strategy_position_cap_map_uses_more_conservative_of_params_and_risk_limits(self):
        with patch.object(execution_svc, "list_strategies", return_value=[
            {
                "strategy_id": "alpha",
                "market": "KOSPI",
                "enabled": True,
                "params": {"max_positions": 5},
                "risk_limits": {"max_positions": 2},
            },
            {
                "strategy_id": "beta",
                "market": "KOSPI",
                "enabled": True,
                "params": {"max_positions": 3},
                "risk_limits": {},
            },
        ]):
            caps = execution_svc._strategy_position_cap_map("KOSPI")

        self.assertEqual({"alpha": 2, "beta": 3}, caps)

    def test_run_auto_trader_cycle_keeps_market_slot_but_blocks_strategy_at_its_own_cap(self):
        engine = _FakeEngine()
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI"]
        cfg["daily_buy_limit"] = 10
        cfg["daily_sell_limit"] = 10
        cfg["max_orders_per_symbol_per_day"] = 3
        cfg["market_profiles"]["KOSPI"]["max_positions"] = 3
        cfg = execution_svc._sync_primary_strategy_fields(cfg)

        signals = [
            {
                "code": "CCC",
                "name": "Alpha Candidate",
                "market": "KOSPI",
                "strategy_id": "alpha",
                "strategy_name": "Alpha",
                "signal_state": "entry",
                "size_recommendation": {"quantity": 1, "reason": "ok"},
                "risk_inputs": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0},
                "ev_metrics": {},
                "risk_check": {"reason_code": "ok", "message": ""},
                "reason_codes": [],
                "layer_events": [],
            },
            {
                "code": "DDD",
                "name": "Beta Candidate",
                "market": "KOSPI",
                "strategy_id": "beta",
                "strategy_name": "Beta",
                "signal_state": "entry",
                "size_recommendation": {"quantity": 1, "reason": "ok"},
                "risk_inputs": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0},
                "ev_metrics": {},
                "risk_check": {"reason_code": "ok", "message": ""},
                "reason_codes": [],
                "layer_events": [],
            },
        ]

        with patch.object(execution_svc, "get_execution_engine", return_value=engine), \
             patch.object(execution_svc, "get_notification_service", return_value=_FakeNotifier()), \
             patch.object(execution_svc, "is_market_open", return_value=True), \
             patch.object(execution_svc, "_compute_technical_snapshot", return_value={"close": 1000.0}), \
             patch.object(execution_svc, "_should_exit_by_indicators", return_value=None), \
             patch.object(execution_svc, "build_signal_book", return_value={"signals": signals, "generated_at": "2026-04-10T09:00:00+09:00", "risk_guard_state": {}}), \
             patch.object(execution_svc, "summarize_order_decision", return_value={"orderable": True, "reason_code": "", "action": "allow", "order_quantity": 1}), \
             patch.object(execution_svc, "list_strategies", return_value=[
                 {"strategy_id": "alpha", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
                 {"strategy_id": "beta", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
             ]), \
             patch.object(execution_svc, "read_order_events", return_value=[
                 {"success": True, "side": "buy", "market": "KOSPI", "code": "BBB", "strategy_id": "alpha"},
                 {"success": True, "side": "buy", "market": "KOSPI", "code": "AAA", "strategy_id": "alpha"},
             ]), \
             patch.object(execution_svc, "_record_execution_order", side_effect=lambda payload: payload), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        self.assertEqual(1, summary["executed_buy_count"])
        self.assertEqual(["DDD"], [item["code"] for item in summary["executed_buys"]])
        self.assertIn("strategy_max_positions_reached", summary["skip_reason_counts"])
        self.assertEqual(1, summary["skip_reason_counts"]["strategy_max_positions_reached"])
        self.assertEqual(["DDD"], [item["code"] for item in engine.placed_orders])


if __name__ == "__main__":
    unittest.main()
