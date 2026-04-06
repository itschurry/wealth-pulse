from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_INSTALLED_STUBS: list[str] = []

if "config.settings" not in sys.modules:
    settings_stub = types.ModuleType("config.settings")
    settings_stub.REPORT_OUTPUT_DIR = Path("/tmp")
    settings_stub.API_DIR = ROOT
    settings_stub.BASE_DIR = ROOT.parent
    settings_stub.LOGS_DIR = Path("/tmp")
    sys.modules["config.settings"] = settings_stub
    _INSTALLED_STUBS.append("config.settings")

if "loguru" not in sys.modules:
    loguru_stub = types.ModuleType("loguru")
    loguru_stub.logger = types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, exception=lambda *a, **k: None)
    sys.modules["loguru"] = loguru_stub
    _INSTALLED_STUBS.append("loguru")

if "broker.kis_client" not in sys.modules:
    broker_stub = types.ModuleType("broker.kis_client")

    class _StubKISClient:
        @staticmethod
        def is_configured() -> bool:
            return False

    broker_stub.KISClient = _StubKISClient
    sys.modules["broker.kis_client"] = broker_stub
    _INSTALLED_STUBS.append("broker.kis_client")

if "services.execution_service" not in sys.modules:
    execution_stub = types.ModuleType("services.execution_service")
    execution_stub._default_auto_trader_config = lambda: {
        "market_profiles": {
            "KOSPI": {"signal_interval": "1d"},
            "NASDAQ": {"signal_range": "6mo"},
        }
    }
    execution_stub.get_execution_service = lambda: None
    sys.modules["services.execution_service"] = execution_stub
    _INSTALLED_STUBS.append("services.execution_service")

from routes.backtest import _parse_backtest_config
from routes.trading import _default_auto_trader_config

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


class StrategyConfigTests(unittest.TestCase):
    def test_backtest_parser_defaults_to_indicator_only_selection(self):
        cfg = _parse_backtest_config({"market_scope": ["kospi"]})

        self.assertFalse(cfg.candidate_selection_enabled)

    def test_backtest_parser_uses_market_specific_defaults(self):
        kospi = _parse_backtest_config({"market_scope": ["kospi"]})
        nasdaq = _parse_backtest_config({"market_scope": ["nasdaq"]})
        both = _parse_backtest_config({"market_scope": ["all"], "rsi_max": ["66"]})

        self.assertEqual(len(kospi.market_profiles), 1)
        self.assertEqual(kospi.market_profiles[0].market, "KOSPI")
        self.assertEqual(kospi.market_profiles[0].volume_ratio_min, 1.05)

        self.assertEqual(len(nasdaq.market_profiles), 1)
        self.assertEqual(nasdaq.market_profiles[0].market, "NASDAQ")
        self.assertEqual(nasdaq.market_profiles[0].max_holding_days, 30)

        self.assertEqual(len(both.market_profiles), 2)
        self.assertTrue(all(profile.rsi_max == 66.0 for profile in both.market_profiles))

    def test_backtest_parser_ignores_theme_candidate_params_when_selection_disabled(self):
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
        self.assertEqual(cfg.candidate_selection.min_score, 50.0)
        self.assertTrue(cfg.candidate_selection.include_neutral)
        self.assertTrue(cfg.candidate_selection.theme_gate_enabled)
        self.assertEqual(cfg.candidate_selection.theme_min_score, 2.5)
        self.assertEqual(cfg.candidate_selection.theme_min_news, 1)
        self.assertEqual(cfg.candidate_selection.theme_priority_bonus, 2.0)

    def test_backtest_parser_applies_theme_candidate_params_when_selection_enabled(self):
        cfg = _parse_backtest_config(
            {
                "market_scope": ["all"],
                "candidate_selection_enabled": ["true"],
                "min_score": ["61.5"],
                "include_neutral": ["false"],
                "theme_gate_enabled": ["false"],
                "theme_min_score": ["4.2"],
                "theme_min_news": ["3"],
                "theme_priority_bonus": ["5.5"],
            }
        )

        self.assertTrue(cfg.candidate_selection_enabled)
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
