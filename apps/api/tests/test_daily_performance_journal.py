from __future__ import annotations

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.daily_performance_journal import _validate_date_key, build_daily_performance_journal


KST = ZoneInfo("Asia/Seoul")


class DailyPerformanceJournalTests(unittest.TestCase):
    def test_rejects_invalid_date_key(self) -> None:
        with self.assertRaises(ValueError):
            _validate_date_key("../../engine_state")

    def test_builds_daily_account_market_and_trade_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cycles_dir = Path(tmpdir) / "engine_cycles"
            cycles_dir.mkdir()
            buy = {
                "ts": "2026-07-16T00:15:00+00:00", "side": "buy", "status": "filled",
                "code": "000020", "market": "KOSPI", "quantity": 10,
                "filled_price_krw": 1000, "fee_krw": 2, "entry_plan_price": 990,
                "stop_loss_price": 950, "take_profit_price": 1100,
            }
            sell = {
                "ts": "2026-07-16T00:45:00+00:00", "side": "sell", "status": "filled",
                "code": "000020", "market": "KOSPI", "quantity": 10,
                "filled_price_krw": 1020, "fee_krw": 3, "realized_pnl_krw": 197,
                "note": "Auto-liquidation (trailing_profit_stop)",
            }
            cycles = [
                {
                    "account": {"mode": "paper", "equity_krw": 5_000_000, "starting_equity_krw": 5_000_000, "orders": []},
                    "executed_buys": [], "skip_reason_counts": {}, "blocked_reason_counts": {},
                },
                {
                    "account": {
                        "mode": "paper", "equity_krw": 5_000_195, "cash_krw": 5_000_195,
                        "market_value_krw": 0, "starting_equity_krw": 5_000_000,
                        "positions": [], "orders": [sell, buy],
                    },
                    "executed_buys": [{"code": "000020", "name": "동화약품", "expected_value": 0.7, "strategy_type": "scanner"}],
                    "skip_reason_counts": {"entry_price_chased": 1},
                    "blocked_reason_counts": {},
                    "rotation_summary": {"attempted_count": 0, "executed_count": 0},
                },
            ]
            path = cycles_dir / "2026-07-16.jsonl"
            path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in cycles), encoding="utf-8")

            with (
                patch("services.daily_performance_journal.ENGINE_CYCLES_DIR", cycles_dir),
                patch("services.daily_performance_journal.load_engine_state", return_value={"current_config": {"markets": ["KOSPI"]}}),
            ):
                result = build_daily_performance_journal(
                    "2026-07-16",
                    market_payload={"kospi_history": [{"date": "2026-07-16", "close": 6820.6, "pct": -6.37}]},
                    generated_at=datetime.datetime(2026, 7, 16, 15, 40, tzinfo=KST),
                )

        self.assertEqual(result["account"]["net_pnl_krw"], 195.0)
        self.assertEqual(result["trading"]["round_trip_count"], 1)
        self.assertEqual(result["trading"]["trades"][0]["name"], "동화약품")
        self.assertEqual(result["trading"]["trades"][0]["holding_seconds"], 1800)
        self.assertEqual(result["market"]["kospi_return_pct"], -6.37)
        self.assertEqual(result["diagnostics"]["skip_reason_counts"], {"entry_price_chased": 1})


if __name__ == "__main__":
    unittest.main()
