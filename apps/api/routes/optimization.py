"""몬테카를로 최적화 API 엔드포인트."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from services.optimized_params_store import load_search_optimized_params
from services.quant_ops_service import (
    finalize_optimizer_search_handoff,
    register_optimizer_search_handoff,
)

_optimization_lock = threading.Lock()
_optimization_running = False
_OPT_RUNNING_FLAG = Path("/tmp/optimization_running")
_LOG_PATH = Path("/tmp/optimization.log")


def _optimizer_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "run_monte_carlo_optimizer.py"


def _read_pid_from_flag() -> int | None:
    try:
        raw = _OPT_RUNNING_FLAG.read_text(encoding="utf-8").strip()
        pid = int(raw)
        return pid if pid > 0 else None
    except Exception:
        return None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _pid_looks_like_optimizer(pid: int) -> bool:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = cmdline_path.read_bytes().decode("utf-8", errors="ignore").replace("\x00", " ").strip()
    except Exception:
        # 명령행을 읽을 수 없는 환경이면 보수적으로 살아있는 프로세스로 간주한다.
        return True

    script_name = _optimizer_script_path().name
    return script_name in cmdline


def _reconcile_running_state() -> bool:
    """메모리/플래그 상태를 실제 optimizer 프로세스 기준으로 정규화한다."""
    global _optimization_running

    had_marker = _optimization_running or _OPT_RUNNING_FLAG.exists()
    pid = _read_pid_from_flag() if _OPT_RUNNING_FLAG.exists() else None
    has_live_optimizer = bool(
        isinstance(pid, int)
        and _pid_exists(pid)
        and _pid_looks_like_optimizer(pid)
    )

    if has_live_optimizer:
        _optimization_running = True
        return True

    _optimization_running = False
    if had_marker:
        _OPT_RUNNING_FLAG.unlink(missing_ok=True)
    return False


def _is_running() -> bool:
    """메모리 플래그 또는 플래그 파일 기준으로 실행 중 여부 반환."""
    with _optimization_lock:
        return _reconcile_running_state()


def _to_int(value: Any, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _build_optimizer_command(payload: dict[str, Any] | None) -> list[str]:
    payload = payload if isinstance(payload, dict) else {}
    query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    command = [
        sys.executable,
        str(_optimizer_script_path()),
        "--simulations",
        "1000",
        "--top-n",
        "10",
        "--lookback-days",
        str(_to_int(settings.get("trainingDays"), 120, minimum=30)),
        "--validation-days",
        str(_to_int(settings.get("validationDays"), 40, minimum=20)),
    ]

    market_scope = str(query.get("market_scope") or "").strip().lower()
    if market_scope == "kospi":
        command.extend(["--market", "KOSPI"])
    elif market_scope == "nasdaq":
        command.extend(["--market", "NASDAQ"])

    return command


def handle_get_optimized_params() -> tuple[int, dict]:
    """GET /api/optimized-params — 최적화 결과 반환."""
    try:
        data = load_search_optimized_params()
        if data is None:
            return 200, {"status": "not_optimized", "message": "최적화 미실행 또는 파일 없음"}
        return 200, {"status": "ok", **data}
    except Exception as exc:
        return 500, {"error": str(exc)}


def handle_get_optimization_status() -> tuple[int, dict]:
    """GET /api/optimization-status — 현재 실행 여부 반환."""
    return 200, {"running": _is_running()}


def handle_run_optimization(payload: dict[str, Any] | None = None) -> tuple[int, dict]:
    """POST /api/run-optimization — 백그라운드 최적화 실행 트리거."""
    global _optimization_running

    with _optimization_lock:
        if _reconcile_running_state():
            return 200, {"status": "already_running"}
        _optimization_running = True

    register_optimizer_search_handoff(payload)
    command = _build_optimizer_command(payload)

    def _run() -> None:
        global _optimization_running
        proc = None
        logger = logging.getLogger(__name__)
        try:
            with _LOG_PATH.open("w") as log_f:
                proc = subprocess.Popen(
                    command,
                    stdout=log_f,
                    stderr=log_f,
                )
                _OPT_RUNNING_FLAG.write_text(str(proc.pid), encoding="utf-8")
                proc.wait(timeout=3600)
                if proc.returncode != 0:
                    logger.error(
                        "최적화 프로세스가 비정상 종료되었습니다 (returncode=%d). 로그: %s",
                        proc.returncode,
                        _LOG_PATH,
                    )
                    finalize_optimizer_search_handoff(
                        success=False,
                        error=f"optimizer_exit_{proc.returncode}",
                    )
                    return

                handoff_result = finalize_optimizer_search_handoff(success=True)
                if isinstance(handoff_result, dict) and not handoff_result.get("ok"):
                    logger.error(
                        "optimizer handoff 재검증이 실패했습니다. error=%s",
                        handoff_result.get("error") or "unknown",
                    )
        except subprocess.TimeoutExpired:
            logger.error("최적화 프로세스가 1시간 제한시간을 초과했습니다.")
            finalize_optimizer_search_handoff(success=False, error="optimizer_timeout")
            if proc is not None:
                proc.kill()
        except Exception as exc:
            logger.error("최적화 실행 중 예외 발생: %s", exc, exc_info=True)
            finalize_optimizer_search_handoff(success=False, error=str(exc))
        finally:
            _OPT_RUNNING_FLAG.unlink(missing_ok=True)
            with _optimization_lock:
                _optimization_running = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return 200, {"status": "started"}
