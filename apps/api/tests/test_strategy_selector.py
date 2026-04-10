from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.shared_strategy import build_strategy_profile
from analyzer.shared_strategy import should_enter_from_snapshot
from routes.strategies import handle_strategy_metadata
from services.strategy_selector import resolve_strategy


class StrategySelectorTests(unittest.TestCase):
    def test_auto_regime_maps_bull_to_trend_following(self):
        profile = build_strategy_profile("KOSPI", strategy_kind="mean_reversion", regime_mode="auto")
        selection = resolve_strategy(profile, {
            "close": 110.0,
            "current_price": 110.0,
            "trade_price": 110.0,
            "sma20": 103.0,
            "sma60": 98.0,
            "volume_ratio": 1.3,
            "rsi14": 58.0,
        })

        self.assertEqual("bull", selection["regime"])
        self.assertEqual("trend_following", selection["strategy_kind"])

    def test_auto_regime_maps_bear_to_defensive(self):
        profile = build_strategy_profile("NASDAQ", strategy_kind="trend_following", regime_mode="auto")
        selection = resolve_strategy(profile, {
            "close": 90.0,
            "current_price": 90.0,
            "trade_price": 90.0,
            "sma20": 95.0,
            "sma60": 100.0,
            "volume_ratio": 0.8,
            "rsi14": 38.0,
        })

        self.assertEqual("bear", selection["regime"])
        self.assertEqual("defensive", selection["strategy_kind"])

    def test_manual_mode_preserves_custom_entry_thresholds(self):
        profile = build_strategy_profile(
            "NASDAQ",
            strategy_kind="trend_following",
            regime_mode="manual",
            risk_profile="aggressive",
            volume_ratio_min=0.35,
            adx_min=12.0,
            bb_pct_max=1.0,
            stoch_k_max=99.0,
            stop_loss_pct=4.0,
            take_profit_pct=8.0,
        )
        snapshot = {
            "close": 1574.45,
            "current_price": 1574.45,
            "trade_price": 1574.45,
            "sma20": 1416.22,
            "sma60": 1318.37,
            "volume_ratio": 0.91,
            "rsi14": 64.3,
            "macd": 36.787,
            "macd_signal": 24.795,
            "macd_hist": 11.993,
            "adx14": 17.7,
            "mfi14": 62.1,
            "bb_pct": 1.0,
            "stoch_k": 92.1,
        }

        selection = resolve_strategy(profile, snapshot)

        self.assertEqual("trend_following", selection["strategy_kind"])
        self.assertEqual(0.35, selection["profile"].volume_ratio_min)
        self.assertEqual(12.0, selection["profile"].adx_min)
        self.assertEqual(1.0, selection["profile"].bb_pct_max)
        self.assertEqual(99.0, selection["profile"].stoch_k_max)
        self.assertTrue(should_enter_from_snapshot(snapshot, profile))

    def test_strategy_metadata_endpoint_exposes_three_strategies(self):
        status, payload = handle_strategy_metadata()

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            {"trend_following", "mean_reversion", "defensive"},
            {item["strategy_kind"] for item in payload["available_strategies"]},
        )
        trend_item = next(item for item in payload["available_strategies"] if item["strategy_kind"] == "trend_following")
        self.assertIn("defaults_by_market_and_risk", trend_item)
        self.assertIn("balanced", trend_item["defaults_by_market_and_risk"]["KOSPI"])


if __name__ == "__main__":
    unittest.main()
