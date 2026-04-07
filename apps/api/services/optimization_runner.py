"""
몬테카를로 최적화 실행 서비스.

routes/optimization.py 에 있던 최적화 비즈니스 로직을 서비스 계층으로 추출.
routes 계층 → services 계층의 역방향 임포트를 제거하기 위해 만들어졌다.

routes/optimization.py 와 services/backtest_service.py 모두 이 모듈에서 임포트한다.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from services.optimized_params_store import SEARCH_OPTIMIZED_PARAMS_PATH, load_search_optimized_params
from services.quant_ops_service import (
    finalize_optimizer_search_handoff,
    register_optimizer_search_handoff,
)

_optimization_lock = threading.Lock()
_optimization_running = False
_OPT_RUNNING_FLAG = Path("/tmp/optimization_running")
_LOG_PATH = Path("/tmp/optimization.log")
_OPTIMIZER_MAX_RUNTIME_SECONDS = 3900
_ALLOWED_STRATEGY_KINDS = {"trend_following", "mean_reversion", "defensive"}


def _optimizer_script_path() -> Path:
    # services/ 와 routes/ 는 모두 apps/api/ 아래에 위치하므로 parents[1] 이 동일하다.
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


def _pid_looks_like_optimizer(pid: int) -> bool | None:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = cmdline_path.read_bytes().decode("utf-8", errors="ignore").replace("\x00", " ").strip()
    except Exception:
        return None
    script_name = _optimizer_script_path().name
    return script_name in cmdline


def _marker_age_seconds() -> float | None:
    try:
        import time
        return max(0.0, time.time() - _OPT_RUNNING_FLAG.stat().st_mtime)
    except Exception:
        return None


def _search_artifact_is_newer_than_marker() -> bool:
    try:
        if not SEARCH_OPTIMIZED_PARAMS_PATH.exists() or not _OPT_RUNNING_FLAG.exists():
            return False
        return SEARCH_OPTIMIZED_PARAMS_PATH.stat().st_mtime >= _OPT_RUNNING_FLAG.stat().st_mtime
    except Exception:
        return False


def _reconcile_running_state() -> bool:
    """메모리/플래그 상태를 실제 optimizer 프로세스 기준으로 정규화한다."""
    global _optimization_running

    had_marker = _optimization_running or _OPT_RUNNING_FLAG.exists()
    pid = _read_pid_from_flag() if _OPT_RUNNING_FLAG.exists() else None
    looks_like_optimizer: bool | None = False
    if isinstance(pid, int) and _pid_exists(pid):
        looks_like_optimizer = _pid_looks_like_optimizer(pid)

    if looks_like_optimizer is True:
        _optimization_running = True
        return True

    if looks_like_optimizer is None:
        marker_age = _marker_age_seconds()
        if not _search_artifact_is_newer_than_marker() and not (
            marker_age is not None and marker_age > _OPTIMIZER_MAX_RUNTIME_SECONDS
        ):
            _optimization_running = True
            return True

    _optimization_running = False
    if had_marker:
        _OPT_RUNNING_FLAG.unlink(missing_ok=True)
    return False


def is_optimization_running() -> bool:
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
    lookback_days = _to_int(query.get("lookback_days"), 1095, minimum=180)
    training_days = _to_int(settings.get("trainingDays"), 180, minimum=30)
    validation_days = _to_int(settings.get("validationDays"), 60, minimum=20)
    command = [
        sys.executable,
        str(_optimizer_script_path()),
        "--simulations",
        "1000",
        "--top-n",
        "10",
        "--lookback-days",
        str(lookback_days),
        "--validation-days",
        str(validation_days),
        "--objective",
        str(settings.get("objective") or "수익 우선"),
        "--base-query-json",
        __import__("json").dumps(query, ensure_ascii=False),
    ]
    _ = training_days  # 향후 스크립트 지원 시 활용

    market_scope = str(query.get("market_scope") or "").strip().lower()
    if market_scope == "kospi":
        command.extend(["--market", "KOSPI"])
    elif market_scope == "nasdaq":
        command.extend(["--market", "NASDAQ"])

    strategy_kind = str(query.get("strategy_kind") or "").strip().lower()
    if strategy_kind:
        command.extend(["--strategy-kind", strategy_kind])

    return command


def build_aggregate_robust_zone(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """전략별 optimizer 결과에서 공통 안정 구간을 집계한다."""
    if not isinstance(payload, dict):
        return None
    per_symbol = payload.get("per_symbol") if isinstance(payload.get("per_symbol"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    search_context = meta.get("search_context") if isinstance(meta.get("search_context"), dict) else {}
    target_strategy_kind = str(search_context.get("strategy_kind") or "").strip().lower()
    global_params = payload.get("global_params") if isinstance(payload.get("global_params"), dict) else {}

    bands_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in per_symbol.values():
        if not isinstance(row, dict):
            continue
        if target_strategy_kind and str(row.get("strategy_kind") or "").strip().lower() != target_strategy_kind:
            continue
        robust_zone = row.get("robust_zone") if isinstance(row.get("robust_zone"), dict) else {}
        parameter_bands = robust_zone.get("parameter_bands") if isinstance(robust_zone.get("parameter_bands"), dict) else {}
        for key, band in parameter_bands.items():
            if isinstance(band, dict):
                bands_by_key.setdefault(str(key), []).append(band)

    if not bands_by_key:
        return None

    aggregate_parameter_bands: dict[str, dict[str, Any]] = {}
    for key, band_rows in bands_by_key.items():
        mins = [float(item["min"]) for item in band_rows if item.get("min") is not None]
        maxs = [float(item["max"]) for item in band_rows if item.get("max") is not None]
        if not mins or not maxs:
            continue
        intersection_min = max(mins)
        intersection_max = min(maxs)
        aggregate_parameter_bands[key] = {
            "label": next((item.get("label") for item in band_rows if item.get("label")), key),
            "selected": global_params.get(key, next((item.get("selected") for item in band_rows if item.get("selected") is not None), None)),
            "min": round(intersection_min if intersection_min <= intersection_max else min(mins), 4),
            "max": round(intersection_max if intersection_min <= intersection_max else max(maxs), 4),
            "sample_count": len(band_rows),
        }

    if not aggregate_parameter_bands:
        return None

    return {
        "label": "optimizer_aggregate_robust_zone",
        "summary": "전략별 optimizer 결과에서 공통으로 겹치는 안정 구간을 집계했습니다.",
        "parameter_bands": aggregate_parameter_bands,
    }


def handle_get_optimized_params() -> tuple[int, dict]:
    """GET /api/optimized-params — 최적화 결과 반환."""
    try:
        data = load_search_optimized_params()
        if data is None:
            return 200, {"status": "not_optimized", "message": "최적화 미실행 또는 파일 없음"}
        aggregate_robust_zone = build_aggregate_robust_zone(data)
        response = {"status": "ok", **data}
        if aggregate_robust_zone:
            response["aggregate_robust_zone"] = aggregate_robust_zone
        return 200, response
    except Exception as exc:
        return 500, {"error": str(exc)}


def handle_get_optimization_status() -> tuple[int, dict]:
    """GET /api/optimization-status — 현재 실행 여부 반환."""
    return 200, {"running": is_optimization_running()}


def handle_run_optimization(payload: dict[str, Any] | None = None) -> tuple[int, dict]:
    """POST /api/run-optimization — 백그라운드 최적화 실행 트리거."""
    global _optimization_running

    with _optimization_lock:
        if _reconcile_running_state():
            return 200, {"status": "already_running"}
        _optimization_running = True

    query = payload.get("query") if isinstance(payload, dict) and isinstance(payload.get("query"), dict) else {}
    strategy_kind = str(query.get("strategy_kind") or "").strip().lower()
    if strategy_kind not in _ALLOWED_STRATEGY_KINDS:
        with _optimization_lock:
            _optimization_running = False
        return 400, {
            "status": "invalid_request",
            "error": "strategy_kind is required and must be one of trend_following, mean_reversion, defensive",
        }

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
