from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import stat

from services.json_utils import json_dump_text, read_json_file_cached



_API_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _API_DIR.parent.parent
_LOGS_DIR = Path(os.getenv("LOGS_DIR", str(_REPO_ROOT / "storage" / "logs")))
SEARCH_OPTIMIZED_PARAMS_PATH = _LOGS_DIR / "optimized_params.json"
RUNTIME_OPTIMIZED_PARAMS_PATH = _LOGS_DIR / "runtime_optimized_params.json"
_EXECUTION_APPROVED_SOURCES = {
    "validated_candidate",
    "quant_ops_saved_candidate",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        payload = read_json_file_cached(path)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def load_search_optimized_params() -> dict[str, Any] | None:
    return _read_json(SEARCH_OPTIMIZED_PARAMS_PATH)


def load_runtime_optimized_params() -> dict[str, Any] | None:
    return _read_json(RUNTIME_OPTIMIZED_PARAMS_PATH)


def _is_execution_approved_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    source = str(meta.get("global_overlay_source") or "").strip()
    applied_from = str(meta.get("applied_from") or "").strip()
    applied_candidate_id = str(meta.get("applied_candidate_id") or "").strip()
    return bool(
        source in _EXECUTION_APPROVED_SOURCES
        or applied_from in _EXECUTION_APPROVED_SOURCES
        or applied_candidate_id
        or bool(meta.get("execution_approved"))
    )


def load_effective_optimized_params() -> dict[str, Any] | None:
    runtime_payload = load_runtime_optimized_params()
    if runtime_payload:
        return runtime_payload
    return load_search_optimized_params()


def load_execution_optimized_params() -> dict[str, Any] | None:
    runtime_payload = load_runtime_optimized_params()
    if runtime_payload and _is_execution_approved_payload(runtime_payload):
        return runtime_payload

    search_payload = load_search_optimized_params()
    if _is_execution_approved_payload(search_payload):
        return search_payload
    return None


def _safe_target_ids(path: Path) -> tuple[int, int] | None:
    candidates = [path, path.parent]
    for candidate in candidates:
        try:
            st = candidate.stat()
            return st.st_uid, st.st_gid
        except Exception:
            continue
    return None


def _normalize_owner_and_mode(path: Path, *, mode: int = 0o664) -> None:
    try:
        os.chmod(path, mode)
    except Exception:
        pass

    target_ids = _safe_target_ids(path)
    if target_ids is None:
        return

    uid, gid = target_ids
    try:
        current = path.stat()
        if current.st_uid != uid or current.st_gid != gid:
            os.chown(path, uid, gid)
            os.chmod(path, mode)
    except PermissionError:
        # 비-root 환경에서는 chown이 안 될 수 있으니 읽기/쓰기 권한만 최대한 맞춘다.
        try:
            current_mode = stat.S_IMODE(path.stat().st_mode)
            os.chmod(path, current_mode | 0o664)
        except Exception:
            pass
    except Exception:
        pass


def write_runtime_optimized_params(payload: dict[str, Any]) -> Path:
    RUNTIME_OPTIMIZED_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_OPTIMIZED_PARAMS_PATH.write_text(
        json_dump_text(payload, indent=2),
        encoding="utf-8",
    )
    _normalize_owner_and_mode(RUNTIME_OPTIMIZED_PARAMS_PATH)
    return RUNTIME_OPTIMIZED_PARAMS_PATH


def clear_runtime_optimized_params() -> None:
    try:
        RUNTIME_OPTIMIZED_PARAMS_PATH.unlink(missing_ok=True)
    except Exception:
        pass
