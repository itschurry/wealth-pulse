from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

if "holidays" not in sys.modules:
    sys.modules["holidays"] = types.SimpleNamespace(KR=lambda *args, **kwargs: set(), US=lambda *args, **kwargs: set())

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

settings_stub = types.ModuleType("config.settings")
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-test-logs"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)
validation_service_stub = types.ModuleType("services.validation_service")
validation_service_stub.run_backtest_with_extended_metrics = lambda query: {"ok": True, "query": query}
validation_service_stub.run_validation_diagnostics = lambda query: {"ok": True, "query": query}
validation_service_stub.run_walk_forward_validation = lambda query, refresh=False, cache_only=False: {"ok": True, "refresh": refresh, "cache_only": cache_only}

with patch.dict(sys.modules, {"config.settings": settings_stub, "services.validation_service": validation_service_stub}):
    from analyzer import candidate_selector
    from routes import strategies as strategies_route
    from routes import validation as validation_route
    from services import signal_service


class RouteBoolParsingTests(unittest.TestCase):
    def test_strategy_toggle_respects_false_string(self):
        with patch.object(strategies_route, "set_strategy_enabled", return_value={"strategy_id": "alpha", "enabled": False}) as mock_toggle:
            status, payload = strategies_route.handle_strategy_toggle({"strategy_id": "alpha", "enabled": "false"})

        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        mock_toggle.assert_called_once_with("alpha", False)

    def test_validation_walk_forward_accepts_true_false_query_strings(self):
        with patch.object(validation_route, "run_walk_forward_validation", return_value={"ok": True}) as mock_run:
            status, payload = validation_route.handle_validation_walk_forward({"refresh": ["true"], "cache_only": ["false"]})

        self.assertEqual(200, status)
        self.assertEqual({"ok": True}, payload)
        mock_run.assert_called_once_with({"refresh": ["true"], "cache_only": ["false"]}, refresh=True, cache_only=False)

    def test_signal_service_theme_gate_false_string_is_false(self):
        cfg = signal_service.parse_theme_gate_config({"theme_gate_enabled": "false"})
        self.assertFalse(cfg["theme_gate_enabled"])

    def test_candidate_selector_bool_strings_are_respected(self):
        cfg = candidate_selector.normalize_candidate_selection_config({
            "include_neutral": "false",
            "theme_gate_enabled": "false",
            "allow_recommendation_fallback": "true",
        })
        self.assertFalse(cfg.include_neutral)
        self.assertFalse(cfg.theme_gate_enabled)
        self.assertTrue(cfg.allow_recommendation_fallback)


if __name__ == "__main__":
    unittest.main()
