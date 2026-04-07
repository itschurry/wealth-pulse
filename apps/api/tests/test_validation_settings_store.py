from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
        self.assertEqual(180, payload["settings"]["trainingDays"])
        self.assertEqual("", payload["saved_at"])
        self.assertEqual(1, payload["version"])
        self.assertEqual("saved", payload["state"]["saved"]["status"])
        self.assertEqual("displayed", payload["state"]["displayed"]["status"])

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
        self.assertEqual(120, payload["settings"]["trainingDays"])
        self.assertFalse(payload["settings"]["walkForward"])
        self.assertEqual(payload["saved_at"], payload["updated_at"])
        self.assertEqual(payload["query"], payload["state"]["saved"]["query"])
        self.assertEqual(payload["settings"], payload["state"]["displayed"]["settings"])
        self.assertTrue(self.path.exists())

    def test_reset_persists_defaults(self):
        with patch.object(store, "BACKTEST_VALIDATION_SETTINGS_PATH", self.path):
            store.save_persisted_validation_settings({
                "query": {"market_scope": "all", "lookback_days": 365},
                "settings": {"walkForward": False},
            })
            payload = store.reset_persisted_validation_settings()

        self.assertTrue(payload["ok"])
        self.assertEqual("kospi", payload["query"]["market_scope"])
        self.assertEqual(1095, payload["query"]["lookback_days"])
        self.assertEqual(180, payload["settings"]["trainingDays"])
        self.assertTrue(payload["settings"]["walkForward"])


if __name__ == "__main__":
    unittest.main()
