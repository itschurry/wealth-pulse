from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

settings_stub = types.ModuleType("config.settings")
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-test-logs"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)

with patch.dict(sys.modules, {"config.settings": settings_stub}):
    from services import backtest_params_store as store


class ValidationSettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = Path(self.tmpdir.name) / "backtest_validation_settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def test_load_returns_defaults_when_store_missing(self):
        with patch.object(store, "BACKTEST_VALIDATION_SETTINGS_PATH", self.path):
            payload = store.load_persisted_validation_settings()

        self.assertTrue(payload["ok"])
        self.assertEqual("kospi", payload["query"]["market_scope"])
        self.assertEqual(1095, payload["query"]["lookback_days"])
        self.assertEqual("퀀트 전략 엔진", payload["settings"]["strategy"])
        self.assertEqual("", payload["saved_at"])

    def test_save_normalizes_and_persists_payload(self):
        with patch.object(store, "BACKTEST_VALIDATION_SETTINGS_PATH", self.path):
            payload = store.save_persisted_validation_settings({
                "query": {
                    "market_scope": "NASDAQ",
                    "lookback_days": "365",
                    "initial_cash": "2500000",
                    "max_positions": "3",
                    "max_holding_days": "0",
                    "rsi_min": "40",
                    "rsi_max": "70",
                    "volume_ratio_min": "1.5",
                    "stop_loss_pct": "6.5",
                    "take_profit_pct": "12.5",
                    "bb_pct_max": "2.0",
                },
                "settings": {
                    "strategy": "공유 검증 전략",
                    "trainingDays": "120",
                    "validationDays": "30",
                    "walkForward": False,
                    "minTrades": "4",
                    "objective": "수익+안정 균형",
                },
            })

        self.assertTrue(payload["ok"])
        self.assertEqual("nasdaq", payload["query"]["market_scope"])
        self.assertEqual(365, payload["query"]["lookback_days"])
        self.assertEqual(1, payload["query"]["max_holding_days"])
        self.assertEqual(1.0, payload["query"]["bb_pct_max"])
        self.assertEqual("공유 검증 전략", payload["settings"]["strategy"])
        self.assertFalse(payload["settings"]["walkForward"])
        self.assertEqual("quant_only", payload["settings"]["runtime_candidate_source_mode"])
        self.assertTrue(self.path.exists())

    def test_save_normalizes_runtime_candidate_source_mode(self):
        with patch.object(store, "BACKTEST_VALIDATION_SETTINGS_PATH", self.path):
            payload = store.save_persisted_validation_settings({
                "settings": {"runtime_candidate_source_mode": "RESEARCH_ONLY"},
            })

        self.assertTrue(payload["ok"])
        self.assertEqual("quant_only", payload["settings"]["runtime_candidate_source_mode"])

    def test_reset_persists_defaults(self):
        with patch.object(store, "BACKTEST_VALIDATION_SETTINGS_PATH", self.path):
            store.save_persisted_validation_settings({
                "query": {"market_scope": "all", "lookback_days": 365},
                "settings": {"strategy": "임시 전략", "walkForward": False},
            })
            payload = store.reset_persisted_validation_settings()

        self.assertTrue(payload["ok"])
        self.assertEqual("kospi", payload["query"]["market_scope"])
        self.assertEqual(1095, payload["query"]["lookback_days"])
        self.assertEqual("퀀트 전략 엔진", payload["settings"]["strategy"])
        self.assertTrue(payload["settings"]["walkForward"])
        self.assertEqual("quant_only", payload["settings"]["runtime_candidate_source_mode"])


if __name__ == "__main__":
    unittest.main()
