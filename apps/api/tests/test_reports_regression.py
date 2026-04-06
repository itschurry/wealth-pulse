from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_INSTALLED_STUBS: list[str] = []

if "config.settings" not in sys.modules:
    settings_stub = types.ModuleType("config.settings")
    settings_stub.API_DIR = ROOT
    settings_stub.BASE_DIR = ROOT.parent
    settings_stub.REPORT_OUTPUT_DIR = Path("/tmp")
    settings_stub.RECOMMENDATIONS_OUTPUT_DIR = Path("/tmp")
    settings_stub.TODAY_PICKS_OUTPUT_DIR = Path("/tmp")
    sys.modules["config.settings"] = settings_stub
    _INSTALLED_STUBS.append("config.settings")

from routes.reports import _fallback_today_picks, _map_strategy_signal

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


class ReportsRegressionTests(unittest.TestCase):
    def test_fallback_today_picks_enriches_candidates_from_optimized_params(self):
        recommendations = {
            "generated_at": "2026-03-31T07:00:00+09:00",
            "recommendations": [
                {
                    "ticker": "005930.KOSPI",
                    "code": "005930",
                    "market": "KOSPI",
                    "name": "삼성전자",
                    "signal": "추천",
                    "score": 78.5,
                    "confidence": 64,
                    "reasons": ["실적 모멘텀"],
                    "risks": ["변동성 확대"],
                }
            ],
        }
        optimized_payload = {
            "per_symbol": {
                "005930": {
                    "trade_count": 34,
                    "validation_trades": 10,
                    "validation_sharpe": 0.42,
                    "max_drawdown_pct": -18.5,
                    "is_reliable": True,
                    "reliability_reason": "passed",
                    "composite_score": 41.2,
                    "score_components": {"tail_component": 4.0},
                    "tail_risk": {"return_p05_pct": -4.2},
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized_params.json"
            output_path.write_text(json.dumps(optimized_payload, ensure_ascii=False), encoding="utf-8")
            with patch("routes.reports._get_recommendations", return_value=recommendations), patch(
                "routes.reports._OPTIMIZED_PARAMS_PATH", output_path
            ):
                result = _fallback_today_picks()

        self.assertEqual(1, len(result["picks"]))
        pick = result["picks"][0]
        self.assertEqual("005930", pick["code"])
        self.assertEqual("high", pick["reliability"])
        self.assertEqual("high", pick["strategy_reliability"])
        self.assertEqual(0.42, pick["validation_sharpe"])
        self.assertEqual(-18.5, pick["max_drawdown_pct"])
        self.assertTrue(pick["is_reliable"])
        self.assertEqual("passed", pick["reliability_reason"])
        self.assertEqual({"tail_component": 4.0}, pick["strategy_scorecard"]["components"])

    def test_map_strategy_signal_prefers_validation_snapshot_fields(self):
        row = _map_strategy_signal(
            {
                "name": "삼성전자",
                "code": "005930",
                "market": "KOSPI",
                "strategy_type": "pullback",
                "entry_allowed": True,
                "ev_metrics": {
                    "expected_value": 1.8,
                    "win_probability": 0.63,
                    "reliability": "low",
                    "calibration": {
                        "sample_size": 7,
                        "trade_count": 21,
                        "validation_sharpe": 0.11,
                        "max_drawdown_pct": -29.0,
                        "reliability_reason": "weak_validation_sharpe",
                    },
                },
                "validation_snapshot": {
                    "strategy_reliability": "high",
                    "validation_trades": 11,
                    "validation_sharpe": 0.44,
                    "trade_count": 33,
                    "max_drawdown_pct": -17.0,
                    "reliability_reason": "passed",
                    "score_components": {"sample_component": 5.0},
                    "tail_risk": {"return_p05_pct": -3.1},
                },
            },
            1,
        )

        self.assertEqual("high", row["reliability"])
        self.assertEqual("passed", row["reliability_reason"])
        self.assertEqual(11, row["validation_trades"])
        self.assertEqual(0.44, row["validation_sharpe"])
        self.assertEqual(33, row["train_trade_count"])
        self.assertEqual(-17.0, row["max_drawdown_pct"])
        self.assertEqual({"sample_component": 5.0}, row["strategy_scorecard"]["components"])
        self.assertEqual({"return_p05_pct": -3.1}, row["strategy_scorecard"]["tail_risk"])


if __name__ == "__main__":
    unittest.main()
