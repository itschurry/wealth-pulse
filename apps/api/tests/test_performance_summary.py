from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routes.performance import _account_equity_krw, _read_json_file, _resolve_live_performance_baseline


class PerformanceSummaryTests(unittest.TestCase):
    def test_paper_equity_uses_cash_and_market_value(self) -> None:
        equity = _account_equity_krw("paper", 0.0, 4_700_000.0, 487_051.62)

        self.assertEqual(equity, 5_187_051.62)

    def test_configured_live_starting_equity_overrides_stale_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_path = Path(tmpdir) / "live_performance_baseline.json"
            baseline_path.write_text(
                '{"account_key":"real:01","starting_equity_krw":2500000,"initial_cash_krw":124407}',
                encoding="utf-8",
            )

            with (
                patch("routes.performance._LIVE_PERFORMANCE_BASELINE_PATH", baseline_path),
                patch("routes.performance.LIVE_PERFORMANCE_STARTING_EQUITY_KRW", 5_000_000.0),
            ):
                baseline = _resolve_live_performance_baseline(
                    {"mode": "real", "account_product_code": "01"},
                    cash_krw=124_407.0,
                    equity_krw=4_950_000.0,
                    realized_pnl_krw=0.0,
                    unrealized_pnl_krw=-50_000.0,
                )

            self.assertEqual(baseline["starting_equity_krw"], 5_000_000.0)
            self.assertEqual(baseline["initial_cash_krw"], 5_000_000.0)
            persisted = _read_json_file(baseline_path)
            self.assertEqual(persisted["starting_equity_krw"], 5_000_000.0)
            self.assertEqual(persisted["initial_cash_krw"], 5_000_000.0)

    def test_new_live_baseline_uses_starting_equity_as_initial_cash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_path = Path(tmpdir) / "live_performance_baseline.json"

            with (
                patch("routes.performance._LIVE_PERFORMANCE_BASELINE_PATH", baseline_path),
                patch("routes.performance.LIVE_PERFORMANCE_STARTING_EQUITY_KRW", 0.0),
            ):
                baseline = _resolve_live_performance_baseline(
                    {"mode": "real", "account_product_code": "01"},
                    cash_krw=124_407.0,
                    equity_krw=4_950_000.0,
                    realized_pnl_krw=0.0,
                    unrealized_pnl_krw=-50_000.0,
                )

            self.assertEqual(baseline["starting_equity_krw"], 5_000_000.0)
            self.assertEqual(baseline["initial_cash_krw"], 5_000_000.0)


if __name__ == "__main__":
    unittest.main()
