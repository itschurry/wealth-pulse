from __future__ import annotations

import unittest

from api_server import _default_auto_trader_config, _parse_backtest_config


class StrategyConfigTests(unittest.TestCase):
    def test_backtest_parser_uses_market_specific_defaults(self):
        kospi = _parse_backtest_config({"market_scope": ["kospi"]})
        nasdaq = _parse_backtest_config({"market_scope": ["nasdaq"]})
        both = _parse_backtest_config({"market_scope": ["all"], "rsi_max": ["66"]})

        self.assertEqual(len(kospi.market_profiles), 1)
        self.assertEqual(kospi.market_profiles[0].market, "KOSPI")
        self.assertEqual(kospi.market_profiles[0].volume_ratio_min, 1.0)

        self.assertEqual(len(nasdaq.market_profiles), 1)
        self.assertEqual(nasdaq.market_profiles[0].market, "NASDAQ")
        self.assertEqual(nasdaq.market_profiles[0].max_holding_days, 30)

        self.assertEqual(len(both.market_profiles), 2)
        self.assertTrue(all(profile.rsi_max == 66.0 for profile in both.market_profiles))

    def test_backtest_parser_includes_candidate_selection_config(self):
        cfg = _parse_backtest_config(
            {
                "market_scope": ["all"],
                "candidate_selection_enabled": ["false"],
                "min_score": ["61.5"],
                "include_neutral": ["false"],
                "theme_gate_enabled": ["false"],
                "theme_min_score": ["4.2"],
                "theme_min_news": ["3"],
                "theme_priority_bonus": ["5.5"],
            }
        )

        self.assertFalse(cfg.candidate_selection_enabled)
        self.assertEqual(cfg.candidate_selection.min_score, 61.5)
        self.assertFalse(cfg.candidate_selection.include_neutral)
        self.assertFalse(cfg.candidate_selection.theme_gate_enabled)
        self.assertEqual(cfg.candidate_selection.theme_min_score, 4.2)
        self.assertEqual(cfg.candidate_selection.theme_min_news, 3)
        self.assertEqual(cfg.candidate_selection.theme_priority_bonus, 5.5)

    def test_auto_trader_default_config_exposes_market_profiles(self):
        cfg = _default_auto_trader_config()
        profiles = cfg.get("market_profiles") or {}

        self.assertIn("KOSPI", profiles)
        self.assertIn("NASDAQ", profiles)
        self.assertEqual(profiles["KOSPI"]["signal_interval"], "1d")
        self.assertEqual(profiles["NASDAQ"]["signal_range"], "6mo")


if __name__ == "__main__":
    unittest.main()
