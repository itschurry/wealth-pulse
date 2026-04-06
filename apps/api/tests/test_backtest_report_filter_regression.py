from __future__ import annotations

import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_INSTALLED_STUBS: list[str] = []

if "broker.kis_client" not in sys.modules:
    stub = types.ModuleType("broker.kis_client")

    class _StubKISClient:
        @staticmethod
        def is_configured() -> bool:
            return False

    stub.KISClient = _StubKISClient
    sys.modules["broker.kis_client"] = stub
    _INSTALLED_STUBS.append("broker.kis_client")

from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


class BacktestReportFilterRegressionTests(unittest.TestCase):
    def _history_rows(self) -> dict[str, list[dict]]:
        rows: list[dict] = []
        start = date(2026, 1, 1)
        for offset in range(85):
            trade_price = 105.0 + offset * 0.2
            rows.append(
                {
                    "date": start + timedelta(days=offset),
                    "code": "AAA",
                    "name": "Alpha",
                    "market": "KOSPI",
                    "close": trade_price,
                    "current_price": trade_price,
                    "trade_price": trade_price,
                    "sma20": trade_price - 5.0,
                    "sma60": trade_price - 10.0,
                    "volume_ratio": 1.6,
                    "rsi14": 50.0,
                    "macd": 1.2,
                    "macd_signal": 0.6,
                    "macd_hist": 0.6,
                }
            )
        return {"KOSPI:AAA": rows}

    def test_backtest_defaults_to_indicator_only_and_skips_historical_report_loader(self):
        with patch("analyzer.kospi_backtest._get_backtest_universe", return_value=[("AAA", "Alpha", "KOSPI")]), patch(
            "analyzer.kospi_backtest._load_histories",
            return_value=self._history_rows(),
        ), patch("analyzer.kospi_backtest.load_historical_candidates") as loader:
            result = run_kospi_backtest(BacktestConfig(markets=("KOSPI",)))

        loader.assert_not_called()
        self.assertFalse(result["config"]["candidate_selection"]["enabled"])
        self.assertEqual(result["config"]["candidate_selection"]["fallback_mode"], "indicator_only")
        self.assertNotIn("theme_min_score", result["config"]["candidate_selection"])
        self.assertTrue(any(point["positions"] for point in result["equity_curve"]))

    def test_explicit_historical_report_filter_still_applies_when_opted_in(self):
        filtered_payload = {
            "date": "2026-01-01",
            "market": "KOSPI",
            "source": "today_picks",
            "codes": {"BBB"},
            "candidates": [{"code": "BBB"}],
            "has_report": True,
        }
        with patch("analyzer.kospi_backtest._get_backtest_universe", return_value=[("AAA", "Alpha", "KOSPI")]), patch(
            "analyzer.kospi_backtest._load_histories",
            return_value=self._history_rows(),
        ), patch(
            "analyzer.kospi_backtest.load_historical_candidates",
            return_value=filtered_payload,
        ) as loader:
            result = run_kospi_backtest(
                BacktestConfig(
                    markets=("KOSPI",),
                    candidate_selection_enabled=True,
                )
            )

        loader.assert_called()
        self.assertTrue(result["config"]["candidate_selection"]["enabled"])
        self.assertIn("theme_min_score", result["config"]["candidate_selection"])
        self.assertEqual(result["config"]["candidate_selection"]["source_counts"], {"today_picks": 85})
        self.assertFalse(any(point["positions"] for point in result["equity_curve"]))
        self.assertEqual(result["metrics"]["final_equity"], result["config"]["initial_cash"])


if __name__ == "__main__":
    unittest.main()
