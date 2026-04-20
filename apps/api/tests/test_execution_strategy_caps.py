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
    def __init__(self):
        self.market_open_briefs: list[dict] = []

    def notify_order_failure(self, payload):
        return None

    def notify_market_open_brief(self, payload):
        self.market_open_briefs.append(payload)
        return None

    def notify_daily_loss_limit(self, payload):
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
        self.get_account_calls: list[bool] = []

    def get_account(self, refresh_quotes: bool = True):
        self.get_account_calls.append(bool(refresh_quotes))
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
                "entry_ts": event["ts"],
            })
        elif kwargs.get("side") == "sell":
            self.account["positions"] = [
                position
                for position in self.account["positions"]
                if not (
                    str(position.get("code") or "").upper() == code
                    and str(position.get("market") or "").upper() == market
                )
            ]
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

    def test_default_auto_trader_config_enables_conservative_rotation_defaults(self):
        cfg = execution_svc._default_auto_trader_config()

        self.assertEqual({
            "enabled": True,
            "min_score_gap": 8.0,
            "daily_limit": 1,
            "min_holding_days": 2,
        }, cfg["rotation"])

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

    def test_run_auto_trader_cycle_skips_quote_refresh_when_all_markets_closed(self):
        engine = _FakeEngine()
        notifier = _FakeNotifier()
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI", "NASDAQ"]
        cfg = execution_svc._sync_primary_strategy_fields(cfg)

        with patch.object(execution_svc, "get_execution_engine", return_value=engine), \
             patch.object(execution_svc, "get_notification_service", return_value=notifier), \
             patch.object(execution_svc, "is_market_open", return_value=False), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None), \
             patch.object(execution_svc, "_should_send_market_open_brief", return_value=(False, "2026-04-19")):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        self.assertEqual({"market_closed": 2}, summary["skip_reason_counts"])
        self.assertEqual([], engine.placed_orders)
        self.assertEqual([False], engine.get_account_calls)
        self.assertEqual([], notifier.market_open_briefs)

    def test_run_auto_trader_cycle_ignores_paper_days_for_live_account(self):
        engine = _FakeEngine()
        engine.account = {
            "mode": "real",
            "positions": [],
            "orders": [],
            "equity_krw": 1000000.0,
        }
        notifier = _FakeNotifier()
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI"]
        cfg = execution_svc._sync_primary_strategy_fields(cfg)

        with patch.dict(execution_svc.os.environ, {"EXECUTION_MODE": "live"}, clear=False), \
             patch.object(execution_svc, "get_execution_engine", return_value=engine), \
             patch.object(execution_svc, "get_notification_service", return_value=notifier), \
             patch.object(execution_svc, "_auto_refresh_research_snapshots", return_value={"ok": True, "stage": "noop", "selected_count": 0}), \
             patch.object(execution_svc, "is_market_open", return_value=False), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None), \
             patch.object(execution_svc, "_should_send_market_open_brief", return_value=(False, "2026-04-19")):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        self.assertEqual({"market_closed": 1}, summary["skip_reason_counts"])
        self.assertEqual([], engine.placed_orders)
        self.assertEqual([False], engine.get_account_calls)
        self.assertEqual([], notifier.market_open_briefs)

    def test_run_auto_trader_cycle_triggers_live_research_auto_refresh(self):
        engine = _FakeEngine()
        engine.account = {
            "mode": "real",
            "positions": [],
            "orders": [],
            "equity_krw": 1000000.0,
        }
        notifier = _FakeNotifier()
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI"]
        cfg = execution_svc._sync_primary_strategy_fields(cfg)
        refresh_result = {
            "ok": True,
            "stage": "ingested",
            "selected_count": 3,
        }

        with patch.dict(execution_svc.os.environ, {"EXECUTION_MODE": "live"}, clear=False), \
             patch.object(execution_svc, "get_execution_engine", return_value=engine), \
             patch.object(execution_svc, "get_notification_service", return_value=notifier), \
             patch.object(execution_svc, "_auto_refresh_research_snapshots", return_value=refresh_result) as mock_refresh, \
             patch.object(execution_svc, "is_market_open", return_value=False), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None), \
             patch.object(execution_svc, "_should_send_market_open_brief", return_value=(False, "2026-04-19")):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        mock_refresh.assert_called_once_with(markets=["KOSPI"], limit=30, mode="missing_or_stale")
        self.assertEqual(refresh_result, summary["research_refresh"])
        self.assertEqual({"market_closed": 1}, summary["skip_reason_counts"])

    def test_run_auto_trader_cycle_builds_market_open_brief_candidates(self):
        engine = _FakeEngine()
        notifier = _FakeNotifier()
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI"]
        cfg = execution_svc._sync_primary_strategy_fields(cfg)

        signals = [
            {
                "code": "BUY1",
                "name": "Buy One",
                "market": "KOSPI",
                "strategy_id": "alpha",
                "strategy_name": "Alpha",
                "signal_state": "entry",
                "final_action": "review_for_entry",
                "size_recommendation": {"quantity": 1, "reason": "ok"},
                "risk_inputs": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0},
                "ev_metrics": {},
                "risk_check": {"reason_code": "ok", "message": ""},
                "reason_codes": ["momentum_ok"],
                "reasons": ["모멘텀 유지"],
                "layer_events": [],
            },
            {
                "code": "HOLD1",
                "name": "Hold One",
                "market": "KOSPI",
                "strategy_id": "alpha",
                "strategy_name": "Alpha",
                "signal_state": "entry",
                "final_action": "watch_only",
                "size_recommendation": {"quantity": 0, "reason": "size_zero"},
                "risk_inputs": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0},
                "ev_metrics": {},
                "risk_check": {"reason_code": "watch", "message": ""},
                "reason_codes": ["needs_review"],
                "reasons": ["장 확인 필요"],
                "layer_events": [],
            },
            {
                "code": "BLOCK1",
                "name": "Block One",
                "market": "KOSPI",
                "strategy_id": "alpha",
                "strategy_name": "Alpha",
                "signal_state": "entry",
                "final_action": "blocked",
                "size_recommendation": {"quantity": 1, "reason": "ok"},
                "risk_inputs": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0},
                "ev_metrics": {},
                "risk_check": {"reason_code": "blocked", "message": ""},
                "reason_codes": ["risk_blocked"],
                "reasons": ["리스크 가드 차단"],
                "layer_events": [],
            },
        ]

        with patch.object(execution_svc, "get_execution_engine", return_value=engine), \
             patch.object(execution_svc, "get_notification_service", return_value=notifier), \
             patch.object(execution_svc, "is_market_open", return_value=True), \
             patch.object(execution_svc, "_compute_technical_snapshot", return_value={"close": 1000.0}), \
             patch.object(execution_svc, "_should_exit_by_indicators", return_value="모멘텀 약화"), \
             patch.object(execution_svc, "build_signal_book", return_value={"signals": signals, "generated_at": "2026-04-10T09:00:00+09:00", "risk_guard_state": {}, "regime": "risk_off", "risk_level": "높음"}), \
             patch.object(execution_svc, "summarize_order_decision", side_effect=[
                 {"orderable": True, "reason_code": "momentum_ok", "action": "allow", "order_quantity": 1},
                 {"orderable": False, "reason_code": "needs_review", "action": "hold", "order_quantity": 0},
                 {"orderable": False, "reason_code": "risk_blocked", "action": "block", "order_quantity": 0},
             ]), \
             patch.object(execution_svc, "list_strategies", return_value=[
                 {"strategy_id": "alpha", "market": "KOSPI", "enabled": True, "params": {"max_positions": 5}, "risk_limits": {"max_positions": 5}},
             ]), \
             patch.object(execution_svc, "read_order_events", return_value=[]), \
             patch.object(execution_svc, "_record_execution_order", side_effect=lambda payload: payload), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None), \
             patch.object(execution_svc, "_should_send_market_open_brief", return_value=(True, "2026-04-10")), \
             patch.object(execution_svc, "_build_market_open_brief_payload", side_effect=lambda **kwargs: kwargs["summary"]):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        self.assertEqual(["BUY1"], [item["code"] for item in summary["brief_candidates"]["buy"]])
        self.assertEqual(["AAA", "BBB"], [item["code"] for item in summary["brief_candidates"]["sell"]])
        self.assertEqual(["HOLD1"], [item["code"] for item in summary["brief_candidates"]["hold"]])
        self.assertEqual(["BLOCK1"], [item["code"] for item in summary["brief_candidates"]["blocked"]])
        self.assertEqual(1, len(notifier.market_open_briefs))

    def test_run_auto_trader_cycle_rotates_when_full_and_better_candidate_exists(self):
        engine = _FakeEngine()
        engine.account["positions"] = [
            {"code": "AAA", "name": "Weak Hold", "market": "KOSPI", "quantity": 1, "avg_price_local": 1000, "avg_price_krw": 1000, "entry_ts": "2026-04-01T09:00:00+09:00"},
            {"code": "BBB", "name": "Strong Hold", "market": "KOSPI", "quantity": 1, "avg_price_local": 1000, "avg_price_krw": 1000, "entry_ts": "2026-04-01T09:00:00+09:00"},
        ]
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI"]
        cfg["daily_buy_limit"] = 10
        cfg["daily_sell_limit"] = 10
        cfg["max_orders_per_symbol_per_day"] = 3
        cfg["market_profiles"]["KOSPI"]["max_positions"] = 2
        cfg["rotation"] = {
            "enabled": True,
            "min_score_gap": 8.0,
            "daily_limit": 1,
            "min_holding_days": 2,
        }
        cfg = execution_svc._sync_primary_strategy_fields(cfg)

        signals = [
            {
                "code": "AAA",
                "name": "Weak Hold",
                "market": "KOSPI",
                "strategy_id": "alpha",
                "strategy_name": "Alpha",
                "signal_state": "hold",
                "score": 55.0,
                "size_recommendation": {"quantity": 0, "reason": "held"},
                "risk_inputs": {},
                "ev_metrics": {},
                "risk_check": {"reason_code": "held", "message": ""},
                "reason_codes": [],
                "layer_events": [],
            },
            {
                "code": "BBB",
                "name": "Strong Hold",
                "market": "KOSPI",
                "strategy_id": "beta",
                "strategy_name": "Beta",
                "signal_state": "hold",
                "score": 72.0,
                "size_recommendation": {"quantity": 0, "reason": "held"},
                "risk_inputs": {},
                "ev_metrics": {},
                "risk_check": {"reason_code": "held", "message": ""},
                "reason_codes": [],
                "layer_events": [],
            },
            {
                "code": "CCC",
                "name": "Rotation Buy",
                "market": "KOSPI",
                "strategy_id": "gamma",
                "strategy_name": "Gamma",
                "signal_state": "entry",
                "score": 70.0,
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
             patch.object(execution_svc, "summarize_order_decision", side_effect=[
                 {"orderable": False, "reason_code": "held", "action": "hold", "order_quantity": 0},
                 {"orderable": False, "reason_code": "held", "action": "hold", "order_quantity": 0},
                 {"orderable": True, "reason_code": "ok", "action": "allow", "order_quantity": 1},
             ]), \
             patch.object(execution_svc, "list_strategies", return_value=[
                 {"strategy_id": "alpha", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
                 {"strategy_id": "beta", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
                 {"strategy_id": "gamma", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
             ]), \
             patch.object(execution_svc, "read_order_events", return_value=[]), \
             patch.object(execution_svc, "_record_execution_order", side_effect=lambda payload: payload), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        self.assertEqual(["sell", "buy"], [item["side"] for item in engine.placed_orders])
        self.assertEqual(["AAA", "CCC"], [item["code"] for item in engine.placed_orders])
        self.assertEqual(1, summary["rotation_summary"]["executed_count"])
        self.assertEqual("AAA", summary["rotation_summary"]["executed"][0]["sell_code"])
        self.assertEqual("CCC", summary["rotation_summary"]["executed"][0]["buy_code"])

    def test_run_auto_trader_cycle_skips_rotation_when_score_gap_is_too_small(self):
        engine = _FakeEngine()
        engine.account["positions"] = [
            {"code": "AAA", "name": "Weak Hold", "market": "KOSPI", "quantity": 1, "avg_price_local": 1000, "avg_price_krw": 1000, "entry_ts": "2026-04-01T09:00:00+09:00"},
            {"code": "BBB", "name": "Strong Hold", "market": "KOSPI", "quantity": 1, "avg_price_local": 1000, "avg_price_krw": 1000, "entry_ts": "2026-04-01T09:00:00+09:00"},
        ]
        cfg = execution_svc._default_auto_trader_config()
        cfg["markets"] = ["KOSPI"]
        cfg["daily_buy_limit"] = 10
        cfg["daily_sell_limit"] = 10
        cfg["max_orders_per_symbol_per_day"] = 3
        cfg["market_profiles"]["KOSPI"]["max_positions"] = 2
        cfg["rotation"] = {
            "enabled": True,
            "min_score_gap": 8.0,
            "daily_limit": 1,
            "min_holding_days": 2,
        }
        cfg = execution_svc._sync_primary_strategy_fields(cfg)

        signals = [
            {
                "code": "AAA",
                "name": "Weak Hold",
                "market": "KOSPI",
                "strategy_id": "alpha",
                "strategy_name": "Alpha",
                "signal_state": "hold",
                "score": 55.0,
                "size_recommendation": {"quantity": 0, "reason": "held"},
                "risk_inputs": {},
                "ev_metrics": {},
                "risk_check": {"reason_code": "held", "message": ""},
                "reason_codes": [],
                "layer_events": [],
            },
            {
                "code": "BBB",
                "name": "Strong Hold",
                "market": "KOSPI",
                "strategy_id": "beta",
                "strategy_name": "Beta",
                "signal_state": "hold",
                "score": 72.0,
                "size_recommendation": {"quantity": 0, "reason": "held"},
                "risk_inputs": {},
                "ev_metrics": {},
                "risk_check": {"reason_code": "held", "message": ""},
                "reason_codes": [],
                "layer_events": [],
            },
            {
                "code": "CCC",
                "name": "Rotation Buy",
                "market": "KOSPI",
                "strategy_id": "gamma",
                "strategy_name": "Gamma",
                "signal_state": "entry",
                "score": 60.0,
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
             patch.object(execution_svc, "summarize_order_decision", side_effect=[
                 {"orderable": False, "reason_code": "held", "action": "hold", "order_quantity": 0},
                 {"orderable": False, "reason_code": "held", "action": "hold", "order_quantity": 0},
                 {"orderable": True, "reason_code": "ok", "action": "allow", "order_quantity": 1},
             ]), \
             patch.object(execution_svc, "list_strategies", return_value=[
                 {"strategy_id": "alpha", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
                 {"strategy_id": "beta", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
                 {"strategy_id": "gamma", "market": "KOSPI", "enabled": True, "params": {"max_positions": 2}, "risk_limits": {"max_positions": 2}},
             ]), \
             patch.object(execution_svc, "read_order_events", return_value=[]), \
             patch.object(execution_svc, "_record_execution_order", side_effect=lambda payload: payload), \
             patch.object(execution_svc, "append_signal_snapshots", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_engine_cycle", side_effect=lambda payload: None), \
             patch.object(execution_svc, "append_account_snapshot", side_effect=lambda payload: None):
            summary = execution_svc._run_auto_trader_cycle(cfg)

        self.assertEqual([], engine.placed_orders)
        self.assertEqual(0, summary["rotation_summary"]["executed_count"])
        self.assertIn("rotation_score_gap_too_small", summary["skip_reason_counts"])
        self.assertIn("max_positions_reached", summary["skip_reason_counts"])


if __name__ == "__main__":
    unittest.main()
