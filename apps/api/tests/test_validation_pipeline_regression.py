from __future__ import annotations

import copy
import datetime as dt
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_INSTALLED_STUBS: list[str] = []

if "services.backtest_service" not in sys.modules:
    stub = types.ModuleType("services.backtest_service")
    stub.get_backtest_service = lambda: None
    sys.modules["services.backtest_service"] = stub
    _INSTALLED_STUBS.append("services.backtest_service")

from services.validation_service import (
    _build_exit_reason_analysis,
    run_backtest_with_extended_metrics,
    run_validation_diagnostics,
    run_walk_forward_validation,
)

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_validation_payload() -> dict:
    return json.loads((_FIXTURES_DIR / "validation_backtest_payload.json").read_text(encoding="utf-8"))


def _expand_for_walk_forward(base_payload: dict, repeats: int = 4) -> dict:
    payload = copy.deepcopy(base_payload)
    seed_curve = payload.get("equity_curve") or []
    seed_trades = payload.get("trades") or []

    if not seed_curve:
        return payload

    start_date = dt.date.fromisoformat(seed_curve[0]["date"])
    expanded_curve: list[dict] = []
    expanded_trades: list[dict] = []

    for block in range(repeats):
        date_shift = dt.timedelta(days=35 * block)
        equity_multiplier = 1.0 + (0.005 * block)

        for point in seed_curve:
            shifted_date = dt.date.fromisoformat(point["date"]) - start_date + date_shift + start_date
            expanded_curve.append(
                {
                    "date": shifted_date.isoformat(),
                    "equity": round(float(point["equity"]) * equity_multiplier, 2),
                    "positions": list(point.get("positions") or []),
                }
            )

        for trade in seed_trades:
            entry = dt.date.fromisoformat(trade["entry_date"]) - start_date + date_shift + start_date
            exit_date = dt.date.fromisoformat(trade["exit_date"]) - start_date + date_shift + start_date
            expanded_trades.append(
                {
                    **trade,
                    "entry_date": entry.isoformat(),
                    "exit_date": exit_date.isoformat(),
                }
            )

    payload["equity_curve"] = expanded_curve
    payload["trades"] = expanded_trades
    return payload


class _StubBacktestService:
    def __init__(self, payload_for_optional: dict, payload_for_run: dict):
        self._payload_for_optional = payload_for_optional
        self._payload_for_run = payload_for_run

    def run_with_optional_optimization(self, _query: dict[str, list[str]], auto_optimize: bool = True) -> dict:
        _ = auto_optimize
        return copy.deepcopy(self._payload_for_optional)

    def parse_config(self, _query: dict[str, list[str]]) -> SimpleNamespace:
        return SimpleNamespace(markets=("KOSPI", "NASDAQ"), lookback_days=365)

    def run(self, _config: SimpleNamespace) -> dict:
        return copy.deepcopy(self._payload_for_run)


class ValidationPipelineRegressionTests(unittest.TestCase):
    def test_exit_reason_analysis_normalizes_aliases_and_highlights_loss_drivers(self):
        analysis = _build_exit_reason_analysis(
            [
                {"reason": "손절", "pnl_pct": -2.5, "holding_days": 3},
                {"reason": "stop_loss", "pnl_pct": -1.0, "holding_days": 2},
                {"reason": "MACD 약세 전환", "pnl_pct": -0.8, "holding_days": 6},
                {"reason": "take_profit", "pnl_pct": 1.4, "holding_days": 4},
            ],
            segment_label="OOS",
        )

        reasons = {item["key"]: item for item in analysis["reasons"]}
        self.assertIn("stop_loss", reasons)
        self.assertEqual("손절", reasons["stop_loss"]["label"])
        self.assertEqual(2, reasons["stop_loss"]["count"])
        self.assertAlmostEqual(3.5, reasons["stop_loss"]["gross_loss_pct"])
        self.assertGreater(reasons["stop_loss"]["loss_share_pct"], 70.0)
        self.assertIn("손절", analysis["summary_lines"][0])

    def test_exit_reason_analysis_surfaces_symbol_and_sector_concentration(self):
        analysis = _build_exit_reason_analysis(
            [
                {"code": "AAPL", "name": "Apple", "market": "NASDAQ", "reason": "stop_loss", "pnl_pct": -3.0, "holding_days": 3},
                {"code": "AAPL", "name": "Apple", "market": "NASDAQ", "reason": "손절", "pnl_pct": -2.0, "holding_days": 2},
                {"code": "NVDA", "name": "NVIDIA", "market": "NASDAQ", "reason": "stop_loss", "pnl_pct": -1.0, "holding_days": 4},
                {"code": "TSLA", "name": "Tesla", "market": "NASDAQ", "reason": "timeout", "pnl_pct": -1.4, "holding_days": 15},
                {"code": "AMZN", "name": "Amazon", "market": "NASDAQ", "reason": "take_profit", "pnl_pct": 1.2, "holding_days": 5},
            ],
            segment_label="OOS",
        )

        self.assertEqual("Apple (AAPL)", analysis["symbol_weaknesses"][0]["label"])
        top_sector_label = analysis["sector_weaknesses"][0]["label"]
        self.assertTrue(top_sector_label)
        stop_loss = next(item for item in analysis["concentration_verdicts"] if item.get("key") == "stop_loss")
        self.assertEqual("concentrated", stop_loss["strategy_issue_bias"])
        self.assertEqual("Apple (AAPL)", stop_loss["top_symbols"][0]["label"])
        self.assertEqual(top_sector_label, stop_loss["top_sectors"][0]["label"])
        self.assertIn("쏠림", stop_loss["summary"])

    def test_extended_backtest_includes_scorecard_tail_risk_and_stats(self):
        payload = _load_validation_payload()
        stub = _StubBacktestService(payload_for_optional=payload, payload_for_run=payload)

        with patch("services.validation_service.get_backtest_service", return_value=stub):
            result = run_backtest_with_extended_metrics({})

        self.assertIn("metrics", result)
        self.assertIn("scorecard", result)
        self.assertIn("reliability_diagnostic", result)
        self.assertEqual(1.23, result["metrics"]["legacy_metric"])
        self.assertIn("exit_reason_stats", result["metrics"])
        self.assertIn("exit_reason_analysis", result["metrics"])
        self.assertIn("regime_stats", result["metrics"])
        self.assertIn("reasons", result["metrics"]["exit_reason_analysis"])
        self.assertIn("symbol_weaknesses", result["metrics"]["exit_reason_analysis"])
        self.assertIn("sector_weaknesses", result["metrics"]["exit_reason_analysis"])
        self.assertIn("concentration_verdicts", result["metrics"]["exit_reason_analysis"])
        self.assertIn("focus_items", result["metrics"]["exit_reason_analysis"])

        scorecard = result["scorecard"]
        self.assertIn("composite_score", scorecard)
        self.assertIn("components", scorecard)
        self.assertIn("tail_risk", scorecard)
        self.assertIn("return_p05_pct", scorecard["tail_risk"])
        self.assertIn("expected_shortfall_5_pct", scorecard["tail_risk"])

    def test_walk_forward_structure_contains_segment_scorecards_and_summary(self):
        base_payload = _load_validation_payload()
        walk_payload = _expand_for_walk_forward(base_payload, repeats=4)
        stub = _StubBacktestService(payload_for_optional=base_payload, payload_for_run=walk_payload)

        with patch("services.validation_service.get_backtest_service", return_value=stub):
            result = run_walk_forward_validation({})

        self.assertTrue(result["ok"])
        self.assertIn("segments", result)
        self.assertIn("summary", result)
        self.assertIn("scorecard", result)
        self.assertIn("rolling_windows", result)
        self.assertGreaterEqual(len(result["rolling_windows"]), 1)

        for segment in ("train", "validation", "oos"):
            segment_payload = result["segments"][segment]
            self.assertIn("strategy_scorecard", segment_payload)
            self.assertIn("tail_risk", segment_payload["strategy_scorecard"])
            self.assertIn("exit_reason_analysis", segment_payload)
            self.assertIn("reasons", segment_payload["exit_reason_analysis"])
            self.assertIn("symbol_weaknesses", segment_payload["exit_reason_analysis"])
            self.assertIn("sector_weaknesses", segment_payload["exit_reason_analysis"])
            self.assertIn("concentration_verdicts", segment_payload["exit_reason_analysis"])

        summary = result["summary"]
        self.assertIn("oos_reliability", summary)
        self.assertIn("positive_window_ratio", summary)
        self.assertIn("reliability_diagnostic", summary)
        self.assertIn("blocking_factors", summary["reliability_diagnostic"])
        self.assertIn("uplift_search", summary["reliability_diagnostic"])
        self.assertIn("exit_reason_analysis", summary)
        self.assertIn("weakness_clusters", summary["exit_reason_analysis"])
        self.assertIn("persistent_negative_reasons", summary["exit_reason_analysis"])
        self.assertIn("headlines", summary["exit_reason_analysis"])
        self.assertGreaterEqual(summary["positive_window_ratio"], 0.0)
        self.assertLessEqual(summary["positive_window_ratio"], 1.0)
        self.assertTrue(
            any(
                item.get("segment") == "oos" and item.get("key") == "stop_loss"
                for item in summary["exit_reason_analysis"]["weakness_clusters"]
            )
        )
        self.assertTrue(
            any(
                item.get("key") == "stop_loss"
                for item in summary["exit_reason_analysis"]["persistent_negative_reasons"]
            )
        )
        self.assertEqual(
            result["scorecard"]["composite_score"],
            result["segments"]["oos"]["strategy_scorecard"]["composite_score"],
        )

    def test_walk_forward_config_exposes_requested_and_effective_windows_when_clipped(self):
        base_payload = _load_validation_payload()
        walk_payload = _expand_for_walk_forward(base_payload, repeats=4)
        stub = _StubBacktestService(payload_for_optional=base_payload, payload_for_run=walk_payload)

        with patch("services.validation_service.get_backtest_service", return_value=stub):
            result = run_walk_forward_validation({
                "training_days": ["180"],
                "validation_days": ["60"],
            })

        self.assertTrue(result["ok"])
        self.assertEqual(180, result["config"]["training_days"])
        self.assertEqual(60, result["config"]["validation_days"])
        self.assertIn("effective_window", result["config"])
        self.assertTrue(result["config"]["effective_window"]["clipped"])
        self.assertEqual("insufficient_equity_curve_length", result["config"]["effective_window"]["clipping_reason"])
        self.assertLess(result["config"]["effective_window"]["training_days"], 180)
        self.assertLess(result["config"]["effective_window"]["validation_days"], 60)


    def test_validation_diagnostics_returns_diagnosis_and_local_research(self):
        base_payload = _load_validation_payload()
        walk_payload = _expand_for_walk_forward(base_payload, repeats=4)
        stub = _StubBacktestService(payload_for_optional=base_payload, payload_for_run=walk_payload)

        with patch("services.validation_service.get_backtest_service", return_value=stub):
            result = run_validation_diagnostics({
                "rsi_min": ["45"],
                "rsi_max": ["62"],
                "volume_ratio_min": ["1.0"],
                "max_holding_days": ["15"],
                "adx_min": ["10"],
                "mfi_min": ["20"],
                "mfi_max": ["80"],
            })

        self.assertTrue(result["ok"])
        self.assertIn("validation", result)
        self.assertIn("diagnosis", result)
        self.assertIn("research", result)
        self.assertIn("summary_lines", result["diagnosis"])
        self.assertIn("suggestions", result["research"])
        self.assertGreaterEqual(result["research"]["trial_limit"], 1)

    def test_validation_diagnostics_light_mode_skips_walk_forward_and_local_research(self):
        base_payload = _load_validation_payload()
        walk_payload = _expand_for_walk_forward(base_payload, repeats=4)
        stub = _StubBacktestService(payload_for_optional=base_payload, payload_for_run=walk_payload)

        with patch("services.validation_service.get_backtest_service", return_value=stub):
            result = run_validation_diagnostics({
                "rsi_min": ["45"],
                "rsi_max": ["62"],
            }, mode="light")

        self.assertTrue(result["ok"])
        self.assertEqual("backtest_light", result["validation"]["source"])
        self.assertEqual(False, result["validation"]["config"]["walk_forward"])
        self.assertEqual(0, result["research"]["trial_limit"])
        self.assertEqual([], result["research"]["suggestions"])
        self.assertIn("summary_lines", result["diagnosis"])


if __name__ == "__main__":
    unittest.main()
