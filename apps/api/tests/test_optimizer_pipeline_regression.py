from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "loguru" not in sys.modules:
    sys.modules["loguru"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None)
    )

if "config.settings" not in sys.modules:
    settings_stub = types.ModuleType("config.settings")
    settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-test-logs"
    settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    sys.modules["config.settings"] = settings_stub

from analyzer.monte_carlo import OptimizationResult, SimulationConfig, _compute_score_components
from scripts.run_monte_carlo_optimizer import _compute_global_params, _save_results, _write_text_atomic, build_stage1_param_grid


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_optimizer_results(name: str) -> list[OptimizationResult]:
    payload = json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return [OptimizationResult(**item) for item in payload]


class OptimizerPipelineRegressionTests(unittest.TestCase):
    def test_compute_global_params_prefers_high_only_pool(self):
        results = _load_optimizer_results("optimizer_results_high_medium_low.json")

        global_params, source = _compute_global_params(results)

        self.assertEqual("high_only", source)
        self.assertEqual(7.0, global_params["stop_loss_pct"])
        self.assertEqual(18.0, global_params["take_profit_pct"])
        self.assertEqual(21, global_params["max_holding_days"])

    def test_save_results_preserves_shape_and_overlay_metadata(self):
        results = _load_optimizer_results("optimizer_results_high_medium_low.json")
        sim_config = SimulationConfig(n_simulations=321, method="bootstrap")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized_params.json"
            with patch("scripts.run_monte_carlo_optimizer._OPTIMIZED_PARAMS_PATH", output_path):
                _save_results(results, sim_config, name_map={"AAA": "Alpha Corp"})

            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertIn("optimized_at", saved)
        self.assertIn("global_params", saved)
        self.assertIn("per_symbol", saved)
        self.assertIn("meta", saved)

        meta = saved["meta"]
        self.assertEqual(3, meta["n_symbols_optimized"])
        self.assertEqual(1, meta["n_reliable"])
        self.assertEqual(1, meta["n_medium"])
        self.assertEqual("high_only", meta["global_overlay_source"])
        self.assertIn("overlay_policy", meta)
        self.assertEqual(["high"], meta["overlay_policy"]["symbol_overlay_allowed_levels"])

        aaa = saved["per_symbol"]["AAA"]
        self.assertEqual("Alpha Corp", aaa["name"])
        self.assertTrue(aaa["is_reliable"])
        self.assertIn("score_components", aaa)
        self.assertIn("tail_risk", aaa)
        self.assertIn("robust_zone", aaa)

        bbb = saved["per_symbol"]["BBB"]
        self.assertEqual(2.0, bbb["stop_loss_pct"])
        self.assertEqual(30.0, bbb["take_profit_pct"])
        self.assertEqual(60, bbb["max_holding_days"])
        self.assertEqual(0.5, bbb["volume_ratio_min"])
        self.assertEqual(40.0, bbb["adx_min"])
        self.assertEqual(0.0, bbb["mfi_min"])
        self.assertEqual(100.0, bbb["mfi_max"])

    def test_save_results_uses_medium_fallback_without_high(self):
        results = _load_optimizer_results("optimizer_results_medium_low.json")
        sim_config = SimulationConfig(n_simulations=200, method="gbm")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized_params.json"
            with patch("scripts.run_monte_carlo_optimizer._OPTIMIZED_PARAMS_PATH", output_path):
                _save_results(results, sim_config)
            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("medium_fallback", saved["meta"]["global_overlay_source"])
        self.assertEqual(6.5, saved["global_params"]["stop_loss_pct"])
        self.assertEqual(16.0, saved["global_params"]["take_profit_pct"])

    def test_save_results_keeps_previous_artifact_when_results_are_empty(self):
        sim_config = SimulationConfig(n_simulations=200, method="gbm")
        previous_payload = {
            "optimized_at": "2026-04-01T19:00:00+09:00",
            "version": "search-2026-04-01T19:00:00+09:00",
            "global_params": {"stop_loss_pct": 5.0},
            "per_symbol": {"AAA": {"stop_loss_pct": 5.0}},
            "meta": {"n_symbols_optimized": 1},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized_params.json"
            output_path.write_text(json.dumps(previous_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            with patch("scripts.run_monte_carlo_optimizer._OPTIMIZED_PARAMS_PATH", output_path):
                written = _save_results([], sim_config)

            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertFalse(written)
        self.assertEqual(previous_payload, saved)

    def test_write_text_atomic_replaces_file_without_leaving_temp_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized_params.json"
            output_path.write_text("old", encoding="utf-8")

            _write_text_atomic(output_path, '{"version":"search-atomic"}')

            self.assertEqual('{"version":"search-atomic"}', output_path.read_text(encoding="utf-8"))
            self.assertEqual([], sorted(Path(tmpdir).glob(".optimized_params.json.*.tmp")))

    def test_write_text_atomic_normalizes_permissions_for_local_workflows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized_params.json"
            output_path.write_text("old", encoding="utf-8")
            output_path.chmod(0o600)

            _write_text_atomic(output_path, '{"version":"search-atomic"}')

            self.assertEqual(0o664, output_path.stat().st_mode & 0o777)

    def test_stage1_param_grid_only_expands_exit_dimensions(self):
        grid = build_stage1_param_grid({
            "stop_loss_pct": 6.0,
            "take_profit_pct": 14.0,
            "max_holding_days": 18,
            "rsi_min": 44,
            "rsi_max": 61,
            "volume_ratio_min": 1.1,
            "adx_min": 12.0,
            "mfi_min": 22.0,
            "mfi_max": 78.0,
            "bb_pct_min": 0.08,
            "bb_pct_max": 0.92,
            "stoch_k_min": 12.0,
            "stoch_k_max": 88.0,
        })

        self.assertGreater(len(grid.stop_loss_pct), 1)
        self.assertGreater(len(grid.take_profit_pct), 1)
        self.assertGreater(len(grid.max_holding_days), 1)
        self.assertEqual([44.0], grid.rsi_min)
        self.assertEqual([61.0], grid.rsi_max)
        self.assertEqual([1.1], grid.volume_ratio_min)
        self.assertEqual([12.0], grid.adx_min)
        self.assertEqual([22.0], grid.mfi_min)
        self.assertEqual([78.0], grid.mfi_max)
        self.assertEqual([0.08], grid.bb_pct_min)
        self.assertEqual([0.92], grid.bb_pct_max)
        self.assertEqual([12.0], grid.stoch_k_min)
        self.assertEqual([88.0], grid.stoch_k_max)

    def test_stage1_param_grid_switches_focus_for_mean_reversion(self):
        grid = build_stage1_param_grid({
            "strategy_kind": "mean_reversion",
            "rsi_min": 18,
            "rsi_max": 42,
            "bb_pct_max": 0.18,
            "stoch_k_max": 24,
        }, strategy_kind="mean_reversion")

        self.assertGreater(len(grid.rsi_min), 1)
        self.assertGreater(len(grid.rsi_max), 1)
        self.assertGreater(len(grid.bb_pct_max), 1)
        self.assertGreater(len(grid.stoch_k_max), 1)

    def test_score_components_reflect_objective_profile(self):
        aggressive = {
            "sharpe_ratio": 2.8,
            "avg_return_pct": 18.0,
            "win_rate_pct": 60.0,
            "trade_count": 45,
            "max_drawdown_pct": -24.0,
            "return_p05_pct": -11.0,
            "expected_shortfall_5_pct": -16.0,
        }
        defensive = {
            "sharpe_ratio": 1.0,
            "avg_return_pct": 3.8,
            "win_rate_pct": 55.0,
            "trade_count": 42,
            "max_drawdown_pct": -9.0,
            "return_p05_pct": -4.5,
            "expected_shortfall_5_pct": -6.0,
        }

        profit_scores = {
            "aggressive": _compute_score_components(aggressive, "수익 우선")["total_score"],
            "defensive": _compute_score_components(defensive, "수익 우선")["total_score"],
        }
        stability_scores = {
            "aggressive": _compute_score_components(aggressive, "안정성 우선")["total_score"],
            "defensive": _compute_score_components(defensive, "안정성 우선")["total_score"],
        }

        self.assertGreater(profit_scores["aggressive"], profit_scores["defensive"])
        self.assertGreater(stability_scores["defensive"], stability_scores["aggressive"])


if __name__ == "__main__":
    unittest.main()
