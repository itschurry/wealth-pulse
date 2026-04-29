from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "loguru" not in sys.modules:
    sys.modules["loguru"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    )

from services.agent_config import AgentRiskConfigStore, broker_status
from routes import risk as risk_routes
from routes import broker as broker_routes


class AgentConfigRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.store = AgentRiskConfigStore(Path(self.tmpdir.name) / "risk_config.json")
        patcher = patch.object(risk_routes, "default_risk_config_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_risk_config_defaults_are_safe(self):
        config = self.store.load()

        self.assertEqual("paper", config["trading_mode"])
        self.assertFalse(config["enable_live_trading"])
        self.assertGreaterEqual(config["min_confidence"], 0.7)

    def test_risk_config_route_saves_allowed_fields_only(self):
        status, payload = risk_routes.handle_risk_config_save({
            "min_confidence": 0.8,
            "enable_live_trading": True,
            "unknown": "ignored",
        })

        self.assertEqual(200, status)
        self.assertEqual(0.8, payload["config"]["min_confidence"])
        self.assertFalse(payload["config"]["enable_live_trading"])
        self.assertNotIn("unknown", payload["config"])

    def test_broker_status_redacts_credentials_and_does_not_connect(self):
        with patch.dict(os.environ, {"KIS_APP_KEY": "key", "KIS_APP_SECRET": "secret", "KIS_ACCOUNT_CANO": "12345678"}, clear=False):
            status = broker_status()

        self.assertTrue(status["configured"])
        self.assertEqual("[REDACTED]", status["credentials"]["app_key"])
        self.assertEqual("[REDACTED]", status["credentials"]["app_secret"])
        self.assertNotIn("'secret'", str(status))

    def test_broker_route_returns_status(self):
        status, payload = broker_routes.handle_kis_status()

        self.assertEqual(200, status)
        self.assertIn("configured", payload)


if __name__ == "__main__":
    unittest.main()
