"""몬테카를로 최적화 API 엔드포인트 호환 wrapper."""
from __future__ import annotations

import services.optimization_runner as _runner

SEARCH_OPTIMIZED_PARAMS_PATH = _runner.SEARCH_OPTIMIZED_PARAMS_PATH
_LOG_PATH = _runner._LOG_PATH
_OPT_RUNNING_FLAG = _runner._OPT_RUNNING_FLAG
_optimization_running = _runner._optimization_running
_optimizer_script_path = _runner._optimizer_script_path
_pid_exists = _runner._pid_exists
_pid_looks_like_optimizer = _runner._pid_looks_like_optimizer
register_optimizer_search_handoff = _runner.register_optimizer_search_handoff
finalize_optimizer_search_handoff = _runner.finalize_optimizer_search_handoff
threading = _runner.threading
subprocess = _runner.subprocess


def _sync_runner_state() -> None:
    _runner.SEARCH_OPTIMIZED_PARAMS_PATH = SEARCH_OPTIMIZED_PARAMS_PATH
    _runner._LOG_PATH = _LOG_PATH
    _runner._OPT_RUNNING_FLAG = _OPT_RUNNING_FLAG
    _runner._optimization_running = _optimization_running
    _runner._pid_exists = _pid_exists
    _runner._pid_looks_like_optimizer = _pid_looks_like_optimizer
    _runner.register_optimizer_search_handoff = register_optimizer_search_handoff
    _runner.finalize_optimizer_search_handoff = finalize_optimizer_search_handoff
    _runner.threading = threading
    _runner.subprocess = subprocess


def _pull_runner_state() -> None:
    global _optimization_running
    _optimization_running = _runner._optimization_running


def handle_get_optimized_params():
    _sync_runner_state()
    result = _runner.handle_get_optimized_params()
    _pull_runner_state()
    return result


def handle_get_optimization_status():
    _sync_runner_state()
    result = _runner.handle_get_optimization_status()
    _pull_runner_state()
    return result


def handle_run_optimization(payload=None):
    _sync_runner_state()
    result = _runner.handle_run_optimization(payload)
    _pull_runner_state()
    return result


__all__ = [
    "SEARCH_OPTIMIZED_PARAMS_PATH",
    "_LOG_PATH",
    "_OPT_RUNNING_FLAG",
    "_optimization_running",
    "_optimizer_script_path",
    "_pid_exists",
    "_pid_looks_like_optimizer",
    "register_optimizer_search_handoff",
    "finalize_optimizer_search_handoff",
    "threading",
    "subprocess",
    "handle_get_optimized_params",
    "handle_get_optimization_status",
    "handle_run_optimization",
]
