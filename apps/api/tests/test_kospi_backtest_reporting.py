from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest


class KospiBacktestReportingTests(unittest.TestCase):
    def test_backtest_result_exposes_position_sizing_comparison_basis(self):
        start = date(2025, 1, 1)
        rows = []
        for idx in range(90):
            current = start + timedelta(days=idx)
            close = 1000.0 + idx
            rows.append({
                "date": current,
                "code": "000001",
                "name": "테스트종목",
                "market": "KOSPI",
                "close": close,
                "trade_price": close,
                "current_price": close,
                "sma20": close * 0.99,
                "sma60": close * 0.97,
                "volume_ratio": 1.0,
                "rsi14": 50.0,
                "atr14_pct": 2.0,
            })

        with patch("analyzer.kospi_backtest._get_backtest_universe", return_value=[("000001", "테스트종목", "KOSPI")]), \
             patch("analyzer.kospi_backtest._load_histories", return_value={"000001": rows}):
            result = run_kospi_backtest(BacktestConfig(
                lookback_days=90,
                position_sizing="risk_based",
                risk_per_trade_pct=0.35,
                markets=("KOSPI",),
            ))

        sizing = result["position_sizing_meta"]
        self.assertEqual("risk_based", sizing["mode"])
        self.assertEqual(0.35, sizing["risk_per_trade_pct"])
        self.assertEqual("equal_weight", sizing["previous_default"])
        self.assertTrue(sizing["changes_comparison_baseline"])
        self.assertIn("risk_based", sizing["comparison_note"])
        self.assertEqual(sizing, result["config"]["position_sizing_meta"])
        self.assertEqual(sizing, result["execution_summary"]["position_sizing_meta"])
        self.assertEqual("risk_based", result["execution_summary"]["position_sizing"])
        self.assertEqual(0.35, result["execution_summary"]["risk_per_trade_pct"])


if __name__ == "__main__":
    unittest.main()
