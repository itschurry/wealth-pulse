from __future__ import annotations

import unittest
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import types

if "loguru" not in sys.modules:
    sys.modules["loguru"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None)
    )

_INSTALLED_STUBS: list[str] = []

if "services.backtest_service" not in sys.modules:
    stub = types.ModuleType("services.backtest_service")
    stub.get_backtest_service = lambda: None
    sys.modules["services.backtest_service"] = stub
    _INSTALLED_STUBS.append("services.backtest_service")

import numpy as np

from analyzer.monte_carlo import (
    OptimizationResult,
    _classify_reliability,
    _compute_composite_score,
    _compute_score_components,
    _safe_pct,
    _should_use_result,
    simulate_strategy,
)
from services.ev_calibration_service import compute_ev_metrics
from services.reliability_policy import (
    overlay_policy_metadata,
    select_global_overlay_candidates,
    should_apply_symbol_overlay,
)
from services.reliability_service import (
    assess_validation_reliability,
    build_reliability_diagnostic,
    find_minimal_reliability_uplift,
)
from services.validation_service import _classify_walk_forward_reliability

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


class MonteCarloReliabilityTests(unittest.TestCase):
    def test_safe_pct_normalizes_ratio_and_percent_inputs(self):
        self.assertEqual(_safe_pct(0.54), 54.0)
        self.assertEqual(_safe_pct(54.0), 54.0)

    def test_composite_score_penalizes_small_trade_samples(self):
        small_sample = _compute_composite_score(
            {
                "sharpe_ratio": 1.0,
                "avg_return_pct": 4.0,
                "max_drawdown_pct": -10.0,
                "win_rate": 0.55,
                "trade_count": 18,
                "return_p05_pct": -4.0,
                "expected_shortfall_5_pct": -6.0,
            }
        )
        solid_sample = _compute_composite_score(
            {
                "sharpe_ratio": 1.0,
                "avg_return_pct": 4.0,
                "max_drawdown_pct": -10.0,
                "win_rate": 0.55,
                "trade_count": 36,
                "return_p05_pct": -4.0,
                "expected_shortfall_5_pct": -6.0,
            }
        )

        self.assertLess(small_sample, solid_sample)

    def test_score_components_penalize_tail_risk_separately(self):
        safer = _compute_score_components(
            {
                "sharpe_ratio": 1.1,
                "avg_return_pct": 5.0,
                "max_drawdown_pct": -11.0,
                "win_rate": 0.56,
                "trade_count": 32,
                "return_p05_pct": -4.0,
                "expected_shortfall_5_pct": -6.0,
            }
        )
        riskier = _compute_score_components(
            {
                "sharpe_ratio": 1.1,
                "avg_return_pct": 5.0,
                "max_drawdown_pct": -11.0,
                "win_rate": 0.56,
                "trade_count": 32,
                "return_p05_pct": -12.0,
                "expected_shortfall_5_pct": -16.0,
            }
        )

        self.assertGreater(safer["tail_component"], riskier["tail_component"])
        self.assertGreater(safer["total_score"], riskier["total_score"])

    def test_classify_reliability_distinguishes_borderline_from_reliable(self):
        self.assertEqual(
            _classify_reliability(
                trade_count=24,
                validation_signals=10,
                validation_sharpe=0.42,
                max_drawdown_pct=-18.0,
            ),
            (False, "borderline_train_trades"),
        )
        self.assertEqual(
            _classify_reliability(
                trade_count=35,
                validation_signals=10,
                validation_sharpe=0.42,
                max_drawdown_pct=-18.0,
            ),
            (True, "passed"),
        )

    def test_simulate_strategy_exposes_tail_risk_metrics(self):
        paths = np.array(
            [
                [1.0, 0.85, 0.82],
                [1.0, 0.97, 1.03],
                [1.0, 1.05, 1.08],
                [1.0, 0.91, 0.89],
                [1.0, 1.02, 1.01],
            ],
            dtype=float,
        )

        metrics = simulate_strategy(paths, stop_loss_pct=50.0, take_profit_pct=50.0, max_holding_days=3)

        self.assertIn("return_p05_pct", metrics)
        self.assertIn("expected_shortfall_5_pct", metrics)
        self.assertIn("worst_case_return_pct", metrics)
        self.assertIn("loss_rate_pct", metrics)
        self.assertLessEqual(metrics["return_p01_pct"], metrics["return_p05_pct"])
        self.assertLessEqual(metrics["expected_shortfall_5_pct"], metrics["return_p05_pct"])

    def test_should_use_result_rejects_weak_validation_and_keeps_borderline(self):
        weak_validation = OptimizationResult(
            symbol="AAA",
            market="KOSPI",
            best_params={},
            sharpe_ratio=1.2,
            win_rate=0.56,
            avg_return_pct=7.0,
            max_drawdown_pct=-12.0,
            avg_holding_days=9.0,
            trade_count=40,
            validation_sharpe=0.15,
            validation_trades=12,
            is_reliable=False,
            reliability_reason="weak_validation_sharpe",
        )
        borderline = OptimizationResult(
            symbol="BBB",
            market="KOSPI",
            best_params={},
            sharpe_ratio=1.1,
            win_rate=0.54,
            avg_return_pct=6.0,
            max_drawdown_pct=-22.0,
            avg_holding_days=10.0,
            trade_count=24,
            validation_sharpe=0.4,
            validation_trades=10,
            is_reliable=False,
            reliability_reason="borderline_train_trades",
        )

        self.assertFalse(_should_use_result(weak_validation))
        self.assertTrue(_should_use_result(borderline))


class SharedReliabilityServiceTests(unittest.TestCase):
    def test_assess_validation_reliability_matches_step1_thresholds(self):
        medium = assess_validation_reliability(
            trade_count=24,
            validation_signals=9,
            validation_sharpe=0.28,
            max_drawdown_pct=-22.0,
        )
        low = assess_validation_reliability(
            trade_count=24,
            validation_signals=9,
            validation_sharpe=0.18,
            max_drawdown_pct=-22.0,
        )

        self.assertEqual(medium.label, "medium")
        self.assertTrue(medium.passes_minimum_gate)
        self.assertEqual(low.label, "low")
        self.assertFalse(low.passes_minimum_gate)

    def test_ev_calibration_uses_shared_reliability_labels(self):
        payload = compute_ev_metrics(
            strategy_type="pullback",
            regime="risk_on",
            score=62.0,
            confidence=64.0,
            trade_count=24,
            validation_trades=9,
            validation_sharpe=0.28,
            max_drawdown_pct=-22.0,
            market="KOSPI",
            sector="반도체",
        )

        self.assertEqual(payload["reliability"], "medium")
        self.assertEqual(payload["reliability_detail"]["reason"], "borderline_train_trades")
        self.assertTrue(payload["calibration"]["passes_minimum_gate"])

    def test_reliability_diagnostic_reports_blocking_gaps_for_low_candidate(self):
        diagnostic = build_reliability_diagnostic(
            trade_count=17,
            validation_signals=7,
            validation_sharpe=0.12,
            max_drawdown_pct=-32.4,
            target_label="medium",
        )

        self.assertFalse(diagnostic["target_reached"])
        blocking_metrics = {item["metric"] for item in diagnostic["blocking_factors"]}
        self.assertEqual(
            blocking_metrics,
            {"trade_count", "validation_signals", "validation_sharpe", "max_drawdown_pct"},
        )
        self.assertTrue(diagnostic["uplift_search"]["feasible"])
        self.assertIsNotNone(diagnostic["uplift_search"]["recommended_path"])

    def test_uplift_search_finds_single_metric_change_when_only_sharpe_is_low(self):
        uplift = find_minimal_reliability_uplift(
            trade_count=26,
            validation_signals=12,
            validation_sharpe=0.18,
            max_drawdown_pct=-20.0,
            target_label="medium",
            max_adjusted_metrics=2,
            max_trials=1200,
        )

        self.assertTrue(uplift["feasible"])
        recommended = uplift["recommended_path"]
        self.assertIsNotNone(recommended)
        changes = recommended["changes"]
        self.assertEqual(1, len(changes))
        self.assertEqual("validation_sharpe", changes[0]["metric"])
        self.assertIn(recommended["label"], {"medium", "high"})

    def test_fixture_low_candidate_has_uplift_path_to_medium(self):
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        payload = json.loads((fixtures_dir / "optimizer_results_high_medium_low.json").read_text(encoding="utf-8"))
        low = next(item for item in payload if item.get("symbol") == "CCC")
        uplift = find_minimal_reliability_uplift(
            trade_count=int(low.get("trade_count", 0)),
            validation_signals=int(low.get("validation_trades", 0)),
            validation_sharpe=float(low.get("validation_sharpe", 0.0)),
            max_drawdown_pct=float(low.get("max_drawdown_pct", 0.0)),
            target_label="medium",
            max_adjusted_metrics=4,
            max_trials=8000,
        )

        self.assertTrue(uplift["feasible"])
        self.assertIsNotNone(uplift["recommended_path"])
        self.assertIn(uplift["recommended_path"]["label"], {"medium", "high"})


class OverlayPolicyTests(unittest.TestCase):
    def test_symbol_overlay_requires_high_reliability(self):
        self.assertTrue(
            should_apply_symbol_overlay(is_reliable=True, reliability_reason="passed")
        )
        self.assertFalse(
            should_apply_symbol_overlay(is_reliable=False, reliability_reason="borderline_train_trades")
        )

    def test_global_overlay_prefers_high_then_medium_then_all(self):
        high = OptimizationResult(symbol="H", market="KOSPI", best_params={}, sharpe_ratio=0.0, win_rate=0.0, avg_return_pct=0.0, max_drawdown_pct=0.0, avg_holding_days=0.0, is_reliable=True, reliability_reason="passed")
        medium = OptimizationResult(symbol="M", market="KOSPI", best_params={}, sharpe_ratio=0.0, win_rate=0.0, avg_return_pct=0.0, max_drawdown_pct=0.0, avg_holding_days=0.0, is_reliable=False, reliability_reason="borderline_drawdown")
        low = OptimizationResult(symbol="L", market="KOSPI", best_params={}, sharpe_ratio=0.0, win_rate=0.0, avg_return_pct=0.0, max_drawdown_pct=0.0, avg_holding_days=0.0, is_reliable=False, reliability_reason="weak_validation_sharpe")

        selected, source = select_global_overlay_candidates(
            [high, medium, low],
            is_reliable_getter=lambda r: bool(r.is_reliable),
            reliability_reason_getter=lambda r: str(r.reliability_reason),
        )
        self.assertEqual(source, "high_only")
        self.assertEqual([r.symbol for r in selected], ["H"])

        selected, source = select_global_overlay_candidates(
            [medium, low],
            is_reliable_getter=lambda r: bool(r.is_reliable),
            reliability_reason_getter=lambda r: str(r.reliability_reason),
        )
        self.assertEqual(source, "medium_fallback")
        self.assertEqual([r.symbol for r in selected], ["M"])

        selected, source = select_global_overlay_candidates(
            [low],
            is_reliable_getter=lambda r: bool(r.is_reliable),
            reliability_reason_getter=lambda r: str(r.reliability_reason),
        )
        self.assertEqual(source, "all_results_fallback")
        self.assertEqual([r.symbol for r in selected], ["L"])

    def test_overlay_policy_metadata_declares_medium_and_global_fallback(self):
        policy = overlay_policy_metadata()
        self.assertEqual(policy["symbol_overlay_allowed_levels"], ["high"])
        self.assertEqual(policy["medium_policy"], "passes_minimum_gate_but_symbol_overlay_disabled")
        self.assertEqual(
            policy["global_overlay_priority"],
            ["high_only", "medium_fallback", "all_results_fallback"],
        )


class WalkForwardReliabilityTests(unittest.TestCase):
    def test_walk_forward_reliability_requires_more_than_profit_factor(self):
        self.assertEqual(
            _classify_walk_forward_reliability(
                {
                    "trade_count": 16,
                    "profit_factor": 1.18,
                    "sharpe": 0.5,
                    "total_return_pct": 6.0,
                },
                positive_window_ratio=0.55,
            ),
            "medium",
        )
        self.assertEqual(
            _classify_walk_forward_reliability(
                {
                    "trade_count": 16,
                    "profit_factor": 1.18,
                    "sharpe": 0.0,
                    "total_return_pct": 6.0,
                },
                positive_window_ratio=0.8,
            ),
            "low",
        )
        self.assertEqual(
            _classify_walk_forward_reliability(
                {
                    "trade_count": 4,
                    "profit_factor": 2.0,
                    "sharpe": 1.0,
                    "total_return_pct": 9.0,
                },
                positive_window_ratio=1.0,
            ),
            "insufficient",
        )


if __name__ == "__main__":
    unittest.main()
