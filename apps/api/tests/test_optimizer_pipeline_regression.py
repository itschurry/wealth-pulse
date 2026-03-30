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

from analyzer.monte_carlo import OptimizationResult, SimulationConfig
from scripts.run_monte_carlo_optimizer import _compute_global_params, _save_results


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


if __name__ == "__main__":
    unittest.main()
