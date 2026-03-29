"""몬테카를로 최적화 API 엔드포인트."""
from __future__ import annotations

import subprocess
import threading
import os
from pathlib import Path

from services.execution_service import _load_optimized_params

_optimization_lock = threading.Lock()
_optimization_running = False
_OPT_RUNNING_FLAG = Path("/tmp/optimization_running")


def _is_running() -> bool:
    """메모리 플래그 또는 플래그 파일 기준으로 실행 중 여부 반환."""
    if _optimization_running:
        return True
    # 서버 재시작 후에도 파일이 남아있으면 실행 중으로 간주
    # (단, 프로세스가 실제로 살아있는지 PID로 확인)
    if _OPT_RUNNING_FLAG.exists():
        try:
            pid = int(_OPT_RUNNING_FLAG.read_text().strip())
            os.kill(pid, 0)  # PID가 살아있으면 예외 없이 통과
            return True
        except Exception:
            _OPT_RUNNING_FLAG.unlink(missing_ok=True)
    return False


def handle_get_optimized_params() -> tuple[int, dict]:
    """GET /api/optimized-params — 최적화 결과 반환."""
    try:
        data = _load_optimized_params()
        if data is None:
            return 200, {"status": "not_optimized", "message": "최적화 미실행 또는 파일 없음"}
        return 200, {"status": "ok", **data}
    except Exception as exc:
        return 500, {"error": str(exc)}


def handle_get_optimization_status() -> tuple[int, dict]:
    """GET /api/optimization-status — 현재 실행 여부 반환."""
    return 200, {"running": _is_running()}


def handle_run_optimization() -> tuple[int, dict]:
    """POST /api/run-optimization — 백그라운드 최적화 실행 트리거."""
    global _optimization_running

    with _optimization_lock:
        if _is_running():
            return 200, {"status": "already_running"}
        _optimization_running = True

    def _run() -> None:
        global _optimization_running
        proc = None
        try:
            import sys
            import logging
            _logger = logging.getLogger(__name__)
            script = str(Path(__file__).parent.parent.parent /
                         "scripts" / "run_monte_carlo_optimizer.py")
            log_path = Path("/tmp/optimization.log")
            with log_path.open("w") as log_f:
                proc = subprocess.Popen(
                    [sys.executable, script,
                     "--simulations", "1000",
                     "--top-n", "10",
                     "--lookback-days", "120",
                     "--validation-days", "40"],
                    stdout=log_f,
                    stderr=log_f,
                )
                _OPT_RUNNING_FLAG.write_text(str(proc.pid))
                proc.wait(timeout=3600)
                if proc.returncode != 0:
                    _logger.error(
                        "최적화 프로세스가 비정상 종료되었습니다 (returncode=%d). "
                        "로그: %s", proc.returncode, log_path
                    )
        except subprocess.TimeoutExpired:
            import logging
            logging.getLogger(__name__).error(
                "최적화 프로세스가 1시간 제한시간을 초과했습니다.")
            if proc is not None:
                proc.kill()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "최적화 실행 중 예외 발생: %s", exc, exc_info=True)
        finally:
            _OPT_RUNNING_FLAG.unlink(missing_ok=True)
            with _optimization_lock:
                _optimization_running = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return 200, {"status": "started"}
