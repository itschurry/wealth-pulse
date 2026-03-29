from __future__ import annotations

import unittest

from analyzer.shared_strategy import (
    default_strategy_profile,
    should_enter_from_snapshot,
    should_exit_from_snapshot,
)


class SharedStrategyTests(unittest.TestCase):
    def test_default_profiles_are_market_specific(self):
        kospi = default_strategy_profile("KOSPI")
        nasdaq = default_strategy_profile("NASDAQ")
        nyse = default_strategy_profile("NYSE")

        self.assertEqual(kospi.max_holding_days, 15)
        self.assertEqual(kospi.rsi_max, 62.0)
        self.assertEqual(kospi.volume_ratio_min, 1.0)
        self.assertEqual(kospi.stop_loss_pct, 5.0)
        self.assertIsNone(kospi.take_profit_pct)

        self.assertEqual(nasdaq.max_holding_days, 30)
        self.assertEqual(nasdaq.rsi_max, 68.0)
        self.assertEqual(nasdaq.volume_ratio_min, 1.2)
        self.assertIsNone(nasdaq.stop_loss_pct)
        self.assertIsNone(nasdaq.take_profit_pct)

        self.assertEqual(nyse.market, "NASDAQ")
        self.assertEqual(nyse.max_holding_days, nasdaq.max_holding_days)

    def test_entry_and_exit_rules_use_shared_snapshot_fields(self):
        profile = default_strategy_profile("KOSPI")
        bullish_snapshot = {
            "current_price": 110.0,
            "close": 110.0,
            "trade_price": 110.0,
            "sma20": 102.0,
            "sma60": 95.0,
            "volume_ratio": 1.4,
            "rsi14": 58.0,
            "macd": 1.8,
            "macd_signal": 1.2,
            "macd_hist": 0.6,
        }
        bearish_snapshot = {
            **bullish_snapshot,
            "current_price": 93.0,
            "close": 93.0,
            "trade_price": 93.0,
            "sma20": 101.0,
            "macd": 0.5,
            "macd_signal": 0.8,
            "macd_hist": -0.3,
        }

        self.assertTrue(should_enter_from_snapshot(bullish_snapshot, profile))
        self.assertEqual(
            should_exit_from_snapshot(
                bearish_snapshot,
                entry_price=100.0,
                holding_days=3,
                profile=profile,
            ),
            "손절",
        )


if __name__ == "__main__":
    unittest.main()
