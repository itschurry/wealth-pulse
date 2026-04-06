from __future__ import annotations

import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_INSTALLED_STUBS: list[str] = []

quant_ops_stub = types.ModuleType("services.quant_ops_service")
quant_ops_stub.register_optimizer_search_handoff = lambda payload=None: payload
quant_ops_stub.finalize_optimizer_search_handoff = lambda **kwargs: {"ok": True, **kwargs}
sys.modules["services.quant_ops_service"] = quant_ops_stub
_INSTALLED_STUBS.append("services.quant_ops_service")

from routes import optimization as route  # noqa: E402

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


class _ImmediateThread:
    def __init__(self, target=None, daemon=None, **_: object) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        if self._target is not None:
            self._target()


class OptimizationRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        route._optimization_running = False

    def test_run_optimization_uses_api_script_path_and_saved_settings(self):
        commands: list[list[str]] = []

        class _FakePopen:
            def __init__(self, command, stdout=None, stderr=None):
                commands.append(list(command))
                self.pid = 43210
                self.returncode = 0

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        payload = {
            "query": {"market_scope": "nasdaq", "lookback_days": 1095, "stop_loss_pct": 5.0, "strategy_kind": "trend_following"},
            "settings": {"trainingDays": 180, "validationDays": 60, "objective": "안정성 우선"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "optimization_running"
            log_path = Path(tmpdir) / "optimization.log"
            with patch.object(route, "_OPT_RUNNING_FLAG", flag_path), \
                 patch.object(route, "_LOG_PATH", log_path), \
                 patch.object(route, "register_optimizer_search_handoff") as mock_register, \
                 patch.object(route, "finalize_optimizer_search_handoff", return_value={"ok": True}) as mock_finalize, \
                 patch.object(route.threading, "Thread", _ImmediateThread), \
                 patch.object(route.subprocess, "Popen", _FakePopen):
                status, response = route.handle_run_optimization(payload)

        self.assertEqual(200, status)
        self.assertEqual("started", response["status"])
        self.assertEqual(1, len(commands))
        self.assertEqual(sys.executable, commands[0][0])
        self.assertEqual(str(route._optimizer_script_path()), commands[0][1])
        self.assertIn("--market", commands[0])
        self.assertIn("NASDAQ", commands[0])
        self.assertIn("1095", commands[0])
        self.assertIn("60", commands[0])
        lookback_index = commands[0].index("--lookback-days")
        validation_index = commands[0].index("--validation-days")
        self.assertEqual("1095", commands[0][lookback_index + 1])
        self.assertEqual("60", commands[0][validation_index + 1])
        self.assertIn("--objective", commands[0])
        self.assertIn("안정성 우선", commands[0])
        self.assertIn("--base-query-json", commands[0])
        mock_register.assert_called_once_with(payload)
        mock_finalize.assert_called_once_with(success=True)

    def test_run_optimization_self_heals_orphan_in_memory_running_state(self):
        commands: list[list[str]] = []

        class _FakePopen:
            def __init__(self, command, stdout=None, stderr=None):
                commands.append(list(command))
                self.pid = 12345
                self.returncode = 0

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        route._optimization_running = True
        with tempfile.TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "optimization_running"
            log_path = Path(tmpdir) / "optimization.log"
            with patch.object(route, "_OPT_RUNNING_FLAG", flag_path), \
                 patch.object(route, "_LOG_PATH", log_path), \
                 patch.object(route, "register_optimizer_search_handoff") as mock_register, \
                 patch.object(route, "finalize_optimizer_search_handoff", return_value={"ok": True}), \
                 patch.object(route.threading, "Thread", _ImmediateThread), \
                 patch.object(route.subprocess, "Popen", _FakePopen):
                status, response = route.handle_run_optimization({"query": {"strategy_kind": "trend_following"}, "settings": {}})

        self.assertEqual(200, status)
        self.assertEqual("started", response["status"])
        self.assertEqual(1, len(commands))
        self.assertFalse(route._optimization_running)
        mock_register.assert_called_once()

    def test_run_optimization_clears_unconfirmed_stale_flag_when_search_artifact_is_newer(self):
        commands: list[list[str]] = []

        class _FakePopen:
            def __init__(self, command, stdout=None, stderr=None):
                commands.append(list(command))
                self.pid = 56789
                self.returncode = 0

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        with tempfile.TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "optimization_running"
            flag_path.write_text("34567", encoding="utf-8")
            log_path = Path(tmpdir) / "optimization.log"
            search_path = Path(tmpdir) / "optimized_params.json"
            search_path.write_text('{"version": "search-ready"}', encoding="utf-8")
            flag_ts = time.time() - 30
            search_ts = flag_ts + 10
            os.utime(flag_path, (flag_ts, flag_ts))
            os.utime(search_path, (search_ts, search_ts))

            with patch.object(route, "_OPT_RUNNING_FLAG", flag_path), \
                 patch.object(route, "_LOG_PATH", log_path), \
                 patch.object(route, "SEARCH_OPTIMIZED_PARAMS_PATH", search_path), \
                 patch.object(route, "_pid_exists", return_value=True), \
                 patch.object(route, "_pid_looks_like_optimizer", return_value=None), \
                 patch.object(route, "register_optimizer_search_handoff") as mock_register, \
                 patch.object(route, "finalize_optimizer_search_handoff", return_value={"ok": True}), \
                 patch.object(route.threading, "Thread", _ImmediateThread), \
                 patch.object(route.subprocess, "Popen", _FakePopen):
                status, response = route.handle_run_optimization({"query": {"strategy_kind": "trend_following"}, "settings": {}})

        self.assertEqual(200, status)
        self.assertEqual("started", response["status"])
        self.assertEqual(1, len(commands))
        mock_register.assert_called_once()

    def test_run_optimization_returns_already_running_only_for_live_optimizer_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "optimization_running"
            flag_path.write_text("34567", encoding="utf-8")
            with patch.object(route, "_OPT_RUNNING_FLAG", flag_path), \
                 patch.object(route, "_pid_exists", return_value=True), \
                 patch.object(route, "_pid_looks_like_optimizer", return_value=True), \
                 patch.object(route, "register_optimizer_search_handoff") as mock_register:
                status, response = route.handle_run_optimization({"query": {}, "settings": {}})

        self.assertEqual(200, status)
        self.assertEqual("already_running", response["status"])
        mock_register.assert_not_called()

    def test_run_optimization_requires_strategy_kind(self):
        status, response = route.handle_run_optimization({"query": {"market_scope": "kospi"}, "settings": {}})

        self.assertEqual(400, status)
        self.assertEqual("invalid_request", response["status"])
        self.assertIn("strategy_kind is required", response["error"])


if __name__ == "__main__":
    unittest.main()
