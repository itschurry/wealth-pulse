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

if "services.backtest_service" not in sys.modules:
    stub = types.ModuleType("services.backtest_service")
    stub.get_backtest_service = lambda: None
    sys.modules["services.backtest_service"] = stub

from services.validation_service import (
    run_backtest_with_extended_metrics,
    run_walk_forward_validation,
)


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

    def run_with_optional_optimization(self, _query: dict[str, list[str]]) -> dict:
        return copy.deepcopy(self._payload_for_optional)

    def parse_config(self, _query: dict[str, list[str]]) -> SimpleNamespace:
        return SimpleNamespace(markets=("KOSPI", "NASDAQ"), lookback_days=365)

    def run(self, _config: SimpleNamespace) -> dict:
        return copy.deepcopy(self._payload_for_run)


class ValidationPipelineRegressionTests(unittest.TestCase):
    def test_extended_backtest_includes_scorecard_tail_risk_and_stats(self):
        payload = _load_validation_payload()
        stub = _StubBacktestService(payload_for_optional=payload, payload_for_run=payload)

        with patch("services.validation_service.get_backtest_service", return_value=stub):
            result = run_backtest_with_extended_metrics({})

        self.assertIn("metrics", result)
        self.assertIn("scorecard", result)
        self.assertEqual(1.23, result["metrics"]["legacy_metric"])
        self.assertIn("exit_reason_stats", result["metrics"])
        self.assertIn("regime_stats", result["metrics"])

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

        summary = result["summary"]
        self.assertIn("oos_reliability", summary)
        self.assertIn("positive_window_ratio", summary)
        self.assertGreaterEqual(summary["positive_window_ratio"], 0.0)
        self.assertLessEqual(summary["positive_window_ratio"], 1.0)
        self.assertEqual(
            result["scorecard"]["composite_score"],
            result["segments"]["oos"]["strategy_scorecard"]["composite_score"],
        )


if __name__ == "__main__":
    unittest.main()
