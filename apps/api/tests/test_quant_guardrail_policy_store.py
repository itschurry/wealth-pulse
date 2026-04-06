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

settings_stub = types.ModuleType("config.settings")
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-policy-test-logs"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)

with patch.dict(sys.modules, {"config.settings": settings_stub}):
    from services import quant_guardrail_policy_store as store  # noqa: E402


class QuantGuardrailPolicyStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.policy_path = Path(self.tmpdir.name) / "quant_guardrail_policy.json"

    def test_load_returns_normalized_defaults_when_file_missing(self):
        with patch.object(store, "QUANT_GUARDRAIL_POLICY_PATH", self.policy_path):
            payload = store.load_quant_guardrail_policy()

        self.assertTrue(payload["ok"])
        self.assertEqual(1, payload["policy"]["version"])
        self.assertEqual(["insufficient", "low"], payload["policy"]["thresholds"]["reject"]["blocked_reliability_levels"])
        self.assertEqual(2, payload["policy"]["thresholds"]["limited_adopt_runtime"]["max_positions_per_market_cap"])

    def test_save_normalizes_invalid_values(self):
        with patch.object(store, "QUANT_GUARDRAIL_POLICY_PATH", self.policy_path):
            payload = store.save_quant_guardrail_policy({
                "policy": {
                    "version": 0,
                    "thresholds": {
                        "reject": {
                            "blocked_reliability_levels": ["LOW", "weird"],
                            "max_drawdown_pct": -99,
                        },
                        "limited_adopt": {
                            "min_near_miss_count": 3,
                            "max_near_miss_count": 1,
                        },
                        "limited_adopt_runtime": {
                            "risk_per_trade_pct_multiplier": 4,
                            "max_market_exposure_pct_cap": 120,
                        },
                    },
                },
            })

        self.assertEqual(1, payload["policy"]["version"])
        self.assertEqual(["low"], payload["policy"]["thresholds"]["reject"]["blocked_reliability_levels"])
        self.assertEqual(0.0, payload["policy"]["thresholds"]["reject"]["max_drawdown_pct"])
        self.assertEqual(3, payload["policy"]["thresholds"]["limited_adopt"]["min_near_miss_count"])
        self.assertEqual(3, payload["policy"]["thresholds"]["limited_adopt"]["max_near_miss_count"])
        self.assertEqual(1.0, payload["policy"]["thresholds"]["limited_adopt_runtime"]["risk_per_trade_pct_multiplier"])
        self.assertEqual(100.0, payload["policy"]["thresholds"]["limited_adopt_runtime"]["max_market_exposure_pct_cap"])
        persisted = json.loads(self.policy_path.read_text(encoding="utf-8"))
        self.assertIn("saved_at", persisted)

    def test_reset_restores_default_policy(self):
        with patch.object(store, "QUANT_GUARDRAIL_POLICY_PATH", self.policy_path):
            store.save_quant_guardrail_policy({"policy": {"thresholds": {"adopt": {"min_profit_factor": 1.5}}}})
            payload = store.reset_quant_guardrail_policy()

        self.assertEqual(1.08, payload["policy"]["thresholds"]["adopt"]["min_profit_factor"])


if __name__ == "__main__":
    unittest.main()
