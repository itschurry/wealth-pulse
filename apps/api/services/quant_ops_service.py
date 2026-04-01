from __future__ import annotations

import copy
import datetime as dt
import json
import os
import uuid
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from services.backtest_params_store import (
    BACKTEST_VALIDATION_SETTINGS_PATH,
    _normalize_query as _normalize_saved_query,
    _normalize_settings as _normalize_saved_settings,
    load_persisted_validation_settings,
)
from services.optimized_params_store import (
    RUNTIME_OPTIMIZED_PARAMS_PATH,
    SEARCH_OPTIMIZED_PARAMS_PATH,
    load_runtime_optimized_params,
    load_search_optimized_params,
    write_runtime_optimized_params,
)
from services.validation_service import run_validation_diagnostics
from services.signal_service import normalize_runtime_candidate_source_mode


_QUANT_OPS_STATE_PATH = LOGS_DIR / "quant_ops_state.json"
_OPT_RUNNING_FLAG = Path("/tmp/optimization_running")
_OPTIMIZER_SCRIPT_NAME = "run_monte_carlo_optimizer.py"
_OPTIMIZABLE_KEYS = {
    "stop_loss_pct",
    "take_profit_pct",
    "max_holding_days",
    "rsi_min",
    "rsi_max",
    "volume_ratio_min",
    "adx_min",
    "mfi_min",
    "mfi_max",
    "bb_pct_min",
    "bb_pct_max",
    "stoch_k_min",
    "stoch_k_max",
}
_OPTIMIZED_PARAMS_MAX_AGE_DAYS = 30
_OPTIMIZER_MAX_RUNTIME_SECONDS = 3900
_SYMBOL_APPROVAL_STATUSES = {"approved", "rejected", "hold"}


def _default_state() -> dict[str, Any]:
    return {
        "latest_candidate": None,
        "candidate_history": [],
        "saved_candidate": None,
        "saved_history": [],
        "runtime_apply": None,
        "pending_search_handoff": None,
        "last_search_handoff": None,
        "latest_symbol_candidates": {},
        "symbol_candidate_history": {},
        "symbol_approvals": {},
        "saved_symbol_candidates": {},
        "saved_symbol_history": {},
        "runtime_symbol_apply": {},
    }


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else dict(default)
    except Exception:
        return dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_state(raw_state: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    default_state = _default_state()
    source = raw_state if isinstance(raw_state, dict) else {}
    normalized: dict[str, Any] = {}
    changed = not isinstance(raw_state, dict)

    for key, default_value in default_state.items():
        if key not in source:
            normalized[key] = copy.deepcopy(default_value)
            changed = True
            continue

        value = source.get(key)
        if default_value is None:
            normalized[key] = copy.deepcopy(value)
        elif isinstance(default_value, list):
            if isinstance(value, list):
                normalized[key] = copy.deepcopy(value)
            else:
                normalized[key] = copy.deepcopy(default_value)
                changed = True
        elif isinstance(default_value, dict):
            if isinstance(value, dict):
                normalized[key] = copy.deepcopy(value)
            else:
                normalized[key] = copy.deepcopy(default_value)
                changed = True
        elif value is None:
            normalized[key] = copy.deepcopy(default_value)
            changed = True
        else:
            normalized[key] = copy.deepcopy(value)

    for key, value in source.items():
        if key not in normalized:
            normalized[key] = copy.deepcopy(value)

    return normalized, changed


def _load_state() -> dict[str, Any]:
    payload = _read_json(_QUANT_OPS_STATE_PATH, _default_state())
    normalized, _ = _normalize_state(payload)
    return normalized


def _save_state(state: dict[str, Any]) -> None:
    normalized, _ = _normalize_state(state)
    _write_json(_QUANT_OPS_STATE_PATH, normalized)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_stale(optimized_at: str) -> bool:
    if not optimized_at:
        return False
    try:
        optimized_ts = dt.datetime.fromisoformat(optimized_at)
        age_days = (dt.datetime.now(dt.timezone.utc) - optimized_ts.astimezone(dt.timezone.utc)).days
        return age_days > _OPTIMIZED_PARAMS_MAX_AGE_DAYS
    except Exception:
        return True


def _age_seconds(timestamp: str) -> float | None:
    if not timestamp:
        return None
    try:
        parsed = dt.datetime.fromisoformat(timestamp)
        now = dt.datetime.now(dt.timezone.utc)
        return max(0.0, (now - parsed.astimezone(dt.timezone.utc)).total_seconds())
    except Exception:
        return None


def _parse_iso_timestamp(timestamp: str) -> dt.datetime | None:
    if not timestamp:
        return None
    try:
        return dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc)
    except Exception:
        return None


def _path_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, dt.datetime.now().timestamp() - path.stat().st_mtime)
    except Exception:
        return None


def _path_is_newer(candidate: Path, reference: Path) -> bool:
    try:
        if not candidate.exists() or not reference.exists():
            return False
        return candidate.stat().st_mtime >= reference.stat().st_mtime
    except Exception:
        return False


def _recover_search_payload(payload: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    if isinstance(payload, dict):
        return payload, True
    if not SEARCH_OPTIMIZED_PARAMS_PATH.exists():
        return {}, False
    return _read_json(SEARCH_OPTIMIZED_PARAMS_PATH, {}), True


def _optimizer_job_active() -> bool:
    if not _OPT_RUNNING_FLAG.exists():
        return False
    try:
        pid = int(_OPT_RUNNING_FLAG.read_text(encoding="utf-8").strip())
        if pid <= 0:
            _OPT_RUNNING_FLAG.unlink(missing_ok=True)
            return False
    except Exception:
        _OPT_RUNNING_FLAG.unlink(missing_ok=True)
        return False

    try:
        os.kill(pid, 0)
    except Exception:
        _OPT_RUNNING_FLAG.unlink(missing_ok=True)
        return False

    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = cmdline_path.read_bytes().decode("utf-8", errors="ignore").replace("\x00", " ")
    except Exception:
        if _path_is_newer(SEARCH_OPTIMIZED_PARAMS_PATH, _OPT_RUNNING_FLAG):
            _OPT_RUNNING_FLAG.unlink(missing_ok=True)
            return False
        marker_age = _path_age_seconds(_OPT_RUNNING_FLAG)
        if marker_age is not None and marker_age > _OPTIMIZER_MAX_RUNTIME_SECONDS:
            _OPT_RUNNING_FLAG.unlink(missing_ok=True)
            return False
        # 프로세스 명령행을 확인할 수 없는 환경에서는 새 결과 파일이 없을 때만 활성 상태로 취급한다.
        return True
    if _OPTIMIZER_SCRIPT_NAME not in cmdline:
        _OPT_RUNNING_FLAG.unlink(missing_ok=True)
        return False
    return True


def _search_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload, artifact_present = _recover_search_payload(payload)
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    global_params = payload.get("global_params") if isinstance(payload.get("global_params"), dict) else {}
    per_symbol = payload.get("per_symbol") if isinstance(payload.get("per_symbol"), dict) else {}
    optimized_at = str(payload.get("optimized_at") or "")
    search_context = meta.get("search_context") if isinstance(meta.get("search_context"), dict) else {}
    has_materialized_payload = bool(payload) or bool(global_params) or bool(per_symbol) or bool(meta) or bool(optimized_at)
    version = str(payload.get("version") or optimized_at or "")
    return {
        "available": bool(artifact_present),
        "has_materialized_payload": bool(has_materialized_payload),
        "version": version,
        "version_known": bool(version),
        "optimized_at": optimized_at,
        "is_stale": _is_stale(optimized_at),
        "global_params": global_params,
        "param_count": len(global_params),
        "per_symbol_count": len(per_symbol),
        "n_symbols_optimized": _to_int(meta.get("n_symbols_optimized"), len(per_symbol)),
        "n_reliable": _to_int(meta.get("n_reliable"), 0),
        "n_medium": _to_int(meta.get("n_medium"), 0),
        "global_overlay_source": meta.get("global_overlay_source"),
        "context": search_context,
        "source": str(SEARCH_OPTIMIZED_PARAMS_PATH),
    }


def _reconstructed_runtime_apply_state(runtime_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(runtime_payload, dict) or not runtime_payload:
        return None
    meta = runtime_payload.get("meta") if isinstance(runtime_payload.get("meta"), dict) else {}
    candidate_id = str(meta.get("applied_candidate_id") or "")
    applied_at = str(runtime_payload.get("applied_at") or "")
    approved_symbols = meta.get("approved_symbols") if isinstance(meta.get("approved_symbols"), list) else []
    approved_symbol_count = _to_int(meta.get("approved_symbol_count"), len(approved_symbols))
    if not candidate_id and not applied_at and approved_symbol_count <= 0:
        return None
    return {
        "candidate_id": candidate_id,
        "applied_at": applied_at,
        "applied_symbol_count": approved_symbol_count,
        "engine_state": None,
        "next_run_at": None,
    }


def _reconstructed_runtime_symbol_apply_state(runtime_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(runtime_payload, dict) or not runtime_payload:
        return None
    per_symbol = runtime_payload.get("per_symbol") if isinstance(runtime_payload.get("per_symbol"), dict) else {}
    if not per_symbol:
        return None
    candidate_ids: dict[str, str] = {}
    for raw_symbol, raw_payload in per_symbol.items():
        symbol = _symbol_code(raw_symbol)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        candidate_id = str(payload.get("approved_candidate_id") or "")
        if symbol and candidate_id:
            candidate_ids[symbol] = candidate_id
    return {
        "applied_at": str(runtime_payload.get("applied_at") or ""),
        "candidate_ids": candidate_ids,
        "symbol_count": len(candidate_ids),
        "skipped_symbols": {},
    }


def _self_heal_state(runtime_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state_exists = _QUANT_OPS_STATE_PATH.exists()
    raw_state = _read_json(_QUANT_OPS_STATE_PATH, _default_state()) if state_exists else _default_state()
    state, changed = _normalize_state(raw_state)

    reconstructed_runtime_apply = _reconstructed_runtime_apply_state(runtime_payload)
    if reconstructed_runtime_apply and not isinstance(state.get("runtime_apply"), dict):
        state["runtime_apply"] = reconstructed_runtime_apply
        changed = True

    reconstructed_runtime_symbol_apply = _reconstructed_runtime_symbol_apply_state(runtime_payload)
    current_runtime_symbol_apply = state.get("runtime_symbol_apply")
    if reconstructed_runtime_symbol_apply and (
        not isinstance(current_runtime_symbol_apply, dict)
        or not isinstance(current_runtime_symbol_apply.get("candidate_ids"), dict)
        or not current_runtime_symbol_apply.get("candidate_ids")
    ):
        state["runtime_symbol_apply"] = reconstructed_runtime_symbol_apply
        changed = True

    if (not state_exists) or changed:
        _save_state(state)
    return state


def _load_current_validation_baseline() -> dict[str, Any]:
    try:
        payload = load_persisted_validation_settings()
    except Exception:
        payload = {}
    saved_at = str((payload or {}).get("saved_at") or "")
    return {
        "available": bool(saved_at or BACKTEST_VALIDATION_SETTINGS_PATH.exists()),
        "query": _normalize_saved_query(payload.get("query") if isinstance(payload, dict) else None),
        "settings": _normalize_saved_settings(payload.get("settings") if isinstance(payload, dict) else None),
        "saved_at": saved_at,
    }


def _resolve_validation_context(
    query: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    baseline: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    baseline = baseline if isinstance(baseline, dict) else _load_current_validation_baseline()
    baseline_query = dict(baseline.get("query") or {}) if baseline.get("available") else {}
    baseline_settings = dict(baseline.get("settings") or {}) if baseline.get("available") else {}

    normalized_query = _normalize_saved_query({
        **baseline_query,
        **(query if isinstance(query, dict) else {}),
    })
    normalized_settings = _normalize_saved_settings({
        **baseline_settings,
        **(settings if isinstance(settings, dict) else {}),
    })
    return baseline, normalized_query, normalized_settings


def _matches_validation_baseline(
    query: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    baseline: dict[str, Any],
) -> bool:
    if not baseline.get("available"):
        return True
    return (
        _normalize_saved_query(query if isinstance(query, dict) else None) == dict(baseline.get("query") or {})
        and _normalize_saved_settings(settings if isinstance(settings, dict) else None) == dict(baseline.get("settings") or {})
    )


def _candidate_activity_state(
    candidate: dict[str, Any] | None,
    search: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {
            "status": "missing",
            "active": False,
            "reasons": ["candidate_missing"],
            "candidate_id": "",
            "search_version": "",
            "baseline_matches": False,
        }

    reasons: list[str] = []
    baseline_matches = _matches_validation_baseline(
        candidate.get("base_query") if isinstance(candidate.get("base_query"), dict) else None,
        candidate.get("settings") if isinstance(candidate.get("settings"), dict) else None,
        baseline,
    )
    if not baseline_matches:
        reasons.append("validation_settings_changed")
    if not search.get("available"):
        reasons.append("optimizer_search_missing")
    elif str(search.get("version") or "") and str(candidate.get("search_version") or "") != str(search.get("version") or ""):
        reasons.append("optimizer_search_version_changed")

    return {
        "status": "active" if not reasons else "stale",
        "active": len(reasons) == 0,
        "reasons": reasons,
        "candidate_id": str(candidate.get("id") or ""),
        "search_version": str(candidate.get("search_version") or ""),
        "baseline_matches": baseline_matches,
    }


def _canonicalize_runtime_summary(runtime_payload: dict[str, Any], saved_candidate: dict[str, Any] | None) -> dict[str, Any]:
    summary = copy.deepcopy(runtime_payload)
    reasons: list[str] = []
    if not summary.get("available"):
        summary["status"] = "missing"
        summary["active"] = False
        summary["reasons"] = []
        return summary

    if isinstance(saved_candidate, dict):
        if str(summary.get("candidate_id") or "") != str(saved_candidate.get("id") or ""):
            reasons.append("runtime_candidate_mismatch")

    summary["status"] = "applied" if not reasons else "stale"
    summary["active"] = len(reasons) == 0
    summary["reasons"] = reasons
    return summary


def _canonicalize_search_handoff(
    handoff: dict[str, Any] | None,
    *,
    search: dict[str, Any],
    baseline: dict[str, Any],
    latest_candidate: dict[str, Any] | None,
    latest_candidate_state: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(handoff, dict):
        return None

    normalized = copy.deepcopy(handoff)
    reasons: list[str] = []
    baseline_matches = _matches_validation_baseline(
        normalized.get("query") if isinstance(normalized.get("query"), dict) else None,
        normalized.get("settings") if isinstance(normalized.get("settings"), dict) else None,
        baseline,
    )
    if not baseline_matches:
        reasons.append("validation_settings_changed")

    search_available = bool(search.get("available"))
    current_search_version = str(search.get("version") or "")
    handoff_search_version = str(normalized.get("search_version") or "")
    if search_available and current_search_version and handoff_search_version and handoff_search_version != current_search_version:
        reasons.append("optimizer_search_version_changed")

    status = str(normalized.get("status") or "unknown")
    if status == "pending":
        if (
            latest_candidate_state.get("active")
            and isinstance(latest_candidate, dict)
            and str(latest_candidate.get("search_version") or "") == current_search_version
            and baseline_matches
        ):
            decision = latest_candidate.get("decision") if isinstance(latest_candidate.get("decision"), dict) else {}
            status = "candidate_updated"
            normalized.setdefault("candidate_id", str(latest_candidate.get("id") or ""))
            normalized.setdefault("search_version", str(latest_candidate.get("search_version") or ""))
            normalized.setdefault("decision_status", str(decision.get("status") or ""))
            normalized.setdefault("decision_label", str(decision.get("label") or ""))
        elif not search_available:
            pending_age = _age_seconds(str(normalized.get("requested_at") or ""))
            if pending_age is not None and pending_age > 3900:
                status = "stale"
                reasons.append("optimizer_handoff_expired")
        elif search_available:
            status = "pending_revalidation"

    if status in {"pending", "pending_revalidation"} and reasons:
        status = "stale"

    if status not in {"optimizer_failed", "revalidate_failed", "candidate_updated", "pending", "pending_revalidation"} and reasons:
        status = "stale"

    normalized["status"] = status
    normalized["active"] = status in {"candidate_updated", "pending", "pending_revalidation"} and len(reasons) == 0
    normalized["baseline_matches"] = baseline_matches
    normalized["search_available"] = search_available
    normalized["reasons"] = reasons
    return normalized


def _build_service_query(query: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, list[str]]:
    service_query: dict[str, list[str]] = {}
    for key, value in (query or {}).items():
        if value is None or value == "":
            continue
        service_query[str(key)] = [str(value)]
    settings = settings or {}
    if settings:
        mapping = {
            "trainingDays": "training_days",
            "validationDays": "validation_days",
            "walkForward": "walk_forward",
            "minTrades": "validation_min_trades",
            "objective": "objective",
        }
        for raw_key, value in settings.items():
            if value is None or value == "":
                continue
            key = mapping.get(raw_key, raw_key)
            if raw_key == "walkForward":
                service_query[key] = ["true" if bool(value) else "false"]
            else:
                service_query[key] = [str(value)]
    return service_query


def _merge_query_patch(query: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(query or {})
    for key, value in (patch or {}).items():
        if key not in _OPTIMIZABLE_KEYS:
            continue
        merged[key] = value
    return merged


def _patch_lines(base_query: dict[str, Any], mutated_query: dict[str, Any], patch: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in sorted(patch.keys()):
        before = base_query.get(key)
        after = mutated_query.get(key)
        if before == after:
            continue
        lines.append(f"{key}: {before} → {after}")
    return lines


def _read_validation_metrics(validation_payload: dict[str, Any]) -> dict[str, Any]:
    segments = validation_payload.get("segments") if isinstance(validation_payload.get("segments"), dict) else {}
    summary = validation_payload.get("summary") if isinstance(validation_payload.get("summary"), dict) else {}
    oos = segments.get("oos") if isinstance(segments.get("oos"), dict) else {}
    scorecard = validation_payload.get("scorecard") if isinstance(validation_payload.get("scorecard"), dict) else {}
    if not scorecard and isinstance(oos.get("strategy_scorecard"), dict):
        scorecard = oos.get("strategy_scorecard")
    tail_risk = scorecard.get("tail_risk") if isinstance(scorecard.get("tail_risk"), dict) else {}
    reliability_diagnostic = summary.get("reliability_diagnostic") if isinstance(summary.get("reliability_diagnostic"), dict) else {}
    return {
        "oos_return_pct": round(_to_float(oos.get("total_return_pct"), 0.0), 4),
        "profit_factor": round(_to_float(oos.get("profit_factor"), 0.0), 4),
        "max_drawdown_pct": round(_to_float(oos.get("max_drawdown_pct"), 0.0), 4),
        "trade_count": _to_int(oos.get("trade_count"), 0),
        "win_rate_pct": round(_to_float(oos.get("win_rate_pct"), 0.0), 4),
        "positive_window_ratio": round(_to_float(summary.get("positive_window_ratio"), 0.0), 4),
        "windows": _to_int(summary.get("windows"), 0),
        "reliability": str(summary.get("oos_reliability") or "insufficient"),
        "composite_score": round(_to_float(scorecard.get("composite_score"), 0.0), 4),
        "expected_shortfall_5_pct": round(_to_float(tail_risk.get("expected_shortfall_5_pct"), 0.0), 4),
        "return_p05_pct": round(_to_float(tail_risk.get("return_p05_pct"), 0.0), 4),
        "reliability_target_reached": bool(reliability_diagnostic.get("target_reached")),
    }


def _blocked_guardrail_reasons(
    *,
    decision_status: str,
    can_save: bool,
    can_apply: bool,
    reasons: list[str] | None,
    fallback: str,
) -> list[str]:
    normalized = [str(item).strip() for item in (reasons or []) if str(item).strip()]
    if normalized:
        return normalized
    if can_save and can_apply:
        return []
    if decision_status == "hold":
        return ["decision_hold"]
    if decision_status == "reject":
        return ["decision_reject"]
    return [fallback]


def _candidate_decision(metrics: dict[str, Any], *, min_trades: int, search_is_stale: bool, search_version_changed: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    oos_return = _to_float(metrics.get("oos_return_pct"), 0.0)
    profit_factor = _to_float(metrics.get("profit_factor"), 0.0)
    max_drawdown_pct = _to_float(metrics.get("max_drawdown_pct"), 0.0)
    trade_count = _to_int(metrics.get("trade_count"), 0)
    reliability = str(metrics.get("reliability") or "insufficient")
    positive_window_ratio = _to_float(metrics.get("positive_window_ratio"), 0.0)
    expected_shortfall = _to_float(metrics.get("expected_shortfall_5_pct"), 0.0)

    decision_status = "hold"
    decision_label = "보류"
    summary = "재검증은 끝났지만 아직 저장/런타임 반영까지 가기엔 근거가 부족합니다."

    hard_reasons: list[str] = []
    if trade_count < max(1, min_trades):
        hard_reasons.append("validation_min_trades_not_met")
    if reliability in {"low", "insufficient"}:
        hard_reasons.append("oos_reliability_low")
    if profit_factor < 0.95:
        hard_reasons.append("profit_factor_too_low")
    if oos_return < -2.0:
        hard_reasons.append("oos_return_negative")
    if abs(max_drawdown_pct) > 30.0:
        hard_reasons.append("max_drawdown_too_large")
    if expected_shortfall < -20.0:
        hard_reasons.append("tail_risk_too_large")

    if not hard_reasons:
        if (
            oos_return > 0.0
            and reliability == "high"
            and profit_factor >= 1.1
            and abs(max_drawdown_pct) <= 20.0
            and trade_count >= max(1, min_trades)
            and positive_window_ratio >= 0.5
            and expected_shortfall >= -14.0
        ):
            decision_status = "adopt"
            decision_label = "채택 후보"
            summary = "OOS·신뢰도·표본·테일리스크 조건을 모두 통과해서 저장 후보로 승격할 수 있습니다."
        else:
            decision_status = "hold"
            decision_label = "보류"
            summary = "핵심 위험은 치명적이지 않지만 채택 조건을 아직 충분히 넘지 못했습니다."
    else:
        decision_status = "reject"
        decision_label = "거절"
        summary = "현재 후보는 재검증 조건을 넘지 못해서 저장/반영을 막습니다."

    guardrail_reasons = list(hard_reasons)
    if search_is_stale:
        guardrail_reasons.append("optimizer_search_stale")
    if search_version_changed:
        guardrail_reasons.append("optimizer_search_version_changed")

    can_save = decision_status == "adopt" and not search_is_stale and not search_version_changed
    can_apply = can_save
    if not can_save and decision_status == "adopt" and search_is_stale:
        summary = "재검증은 통과했지만 optimizer 결과가 오래돼서 저장을 막습니다. 먼저 후보 탐색을 다시 실행하세요."
    if not can_save and decision_status == "adopt" and search_version_changed:
        summary = "재검증한 optimizer 버전과 현재 탐색 결과가 달라져서 저장을 막습니다. 다시 재검증해야 합니다."

    return {
        "status": decision_status,
        "label": decision_label,
        "summary": summary,
        "hard_reasons": hard_reasons,
    }, {
        "can_save": can_save,
        "can_apply": can_apply,
        "reasons": _blocked_guardrail_reasons(
            decision_status=decision_status,
            can_save=can_save,
            can_apply=can_apply,
            reasons=guardrail_reasons,
            fallback="save_guardrail_blocked",
        ),
    }


def _refresh_candidate(candidate: dict[str, Any] | None, search: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    refreshed = copy.deepcopy(candidate)
    metrics = refreshed.get("metrics") if isinstance(refreshed.get("metrics"), dict) else {}
    settings = refreshed.get("settings") if isinstance(refreshed.get("settings"), dict) else {}
    min_trades = _to_int(settings.get("minTrades"), 8)
    search_version_changed = bool(search.get("available")) and bool(search.get("version")) and str(refreshed.get("search_version") or "") != str(search.get("version") or "")
    decision, guardrails = _candidate_decision(
        metrics,
        min_trades=min_trades,
        search_is_stale=bool(search.get("is_stale")),
        search_version_changed=search_version_changed,
    )
    refreshed["decision"] = decision
    refreshed["guardrails"] = guardrails
    return refreshed


def _build_candidate(
    *,
    search: dict[str, Any],
    base_query: dict[str, Any],
    mutated_query: dict[str, Any],
    settings: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    validation = diagnostics.get("validation") if isinstance(diagnostics.get("validation"), dict) else {}
    diagnosis = diagnostics.get("diagnosis") if isinstance(diagnostics.get("diagnosis"), dict) else {}
    research = diagnostics.get("research") if isinstance(diagnostics.get("research"), dict) else {}
    metrics = _read_validation_metrics(validation)
    patch = {key: value for key, value in (search.get("global_params") or {}).items() if key in _OPTIMIZABLE_KEYS}
    search_version_changed = False
    decision, guardrails = _candidate_decision(
        metrics,
        min_trades=_to_int(settings.get("minTrades"), 8),
        search_is_stale=bool(search.get("is_stale")),
        search_version_changed=search_version_changed,
    )
    runtime_candidate_source_mode = normalize_runtime_candidate_source_mode(settings.get("runtime_candidate_source_mode"))
    return {
        "id": f"cand-{uuid.uuid4().hex[:12]}",
        "created_at": _now_iso(),
        "source": "optimizer_global_overlay",
        "runtime_candidate_source_mode": runtime_candidate_source_mode,
        "strategy_label": str(settings.get("strategy") or "퀀트 전략 엔진"),
        "search_version": str(search.get("version") or ""),
        "search_optimized_at": str(search.get("optimized_at") or ""),
        "search_is_stale": bool(search.get("is_stale")),
        "base_query": base_query,
        "candidate_query": mutated_query,
        "settings": settings,
        "patch": patch,
        "patch_lines": _patch_lines(base_query, mutated_query, patch),
        "metrics": metrics,
        "decision": decision,
        "guardrails": guardrails,
        "diagnosis": diagnosis,
        "research": research,
        "validation": validation,
    }


def _history_push(items: list[dict[str, Any]], candidate: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    candidate_id = str(candidate.get("id") or "")
    deduped = [item for item in items if str(item.get("id") or "") != candidate_id]
    return [candidate, *deduped][:limit]


def _symbol_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _extract_symbol_patch(symbol_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in (symbol_payload or {}).items()
        if key in _OPTIMIZABLE_KEYS and value not in (None, "")
    }


def _extract_symbol_snapshot(symbol_payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "is_reliable",
        "strategy_reliability",
        "reliability_reason",
        "trade_count",
        "validation_trades",
        "validation_sharpe",
        "max_drawdown_pct",
        "composite_score",
        "expected_shortfall_5_pct",
        "return_p05_pct",
    )
    return {key: symbol_payload.get(key) for key in keys if key in symbol_payload}


def _symbol_search_candidates(search_payload: dict[str, Any] | None, search: dict[str, Any]) -> dict[str, dict[str, Any]]:
    search_payload = search_payload or {}
    per_symbol = search_payload.get("per_symbol") if isinstance(search_payload.get("per_symbol"), dict) else {}
    items: dict[str, dict[str, Any]] = {}
    for raw_symbol, raw_payload in per_symbol.items():
        symbol = _symbol_code(raw_symbol)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        patch = _extract_symbol_patch(payload)
        items[symbol] = {
            "symbol": symbol,
            "search_version": str(search.get("version") or ""),
            "search_optimized_at": str(search.get("optimized_at") or ""),
            "search_is_stale": bool(search.get("is_stale")),
            "patch": patch,
            "patch_lines": [f"{key}: {value}" for key, value in sorted(patch.items())],
            "snapshot": _extract_symbol_snapshot(payload),
            "raw": payload,
        }
    return items


def _read_symbol_approval(state: dict[str, Any], symbol: str) -> dict[str, Any]:
    approvals = state.get("symbol_approvals") if isinstance(state.get("symbol_approvals"), dict) else {}
    payload = approvals.get(symbol) if isinstance(approvals.get(symbol), dict) else {}
    status = str(payload.get("status") or "hold")
    if status not in _SYMBOL_APPROVAL_STATUSES:
        status = "hold"
    return {
        "status": status,
        "note": str(payload.get("note") or ""),
        "reason": str(payload.get("reason") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
        "candidate_id": str(payload.get("candidate_id") or ""),
    }


def _symbol_save_guardrails(
    candidate: dict[str, Any] | None,
    approval: dict[str, Any],
    *,
    search: dict[str, Any],
    search_item: dict[str, Any] | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    can_save = False
    can_apply = False
    if not isinstance(candidate, dict):
        reasons.append("symbol_candidate_missing")
    else:
        if str(candidate.get("validation_status") or "failed") != "passed":
            reasons.append("symbol_validation_failed")
        guardrails = candidate.get("guardrails") if isinstance(candidate.get("guardrails"), dict) else {}
        if not bool(guardrails.get("can_save")):
            reasons.append("symbol_validation_guardrail_blocked")
        if approval.get("status") != "approved":
            reasons.append("operator_approval_required")
        if approval.get("candidate_id") and str(approval.get("candidate_id") or "") != str(candidate.get("id") or ""):
            reasons.append("operator_approval_stale")
        candidate_search_version = str(candidate.get("search_version") or "")
        if search.get("available") and candidate_search_version != str(search.get("version") or ""):
            reasons.append("optimizer_search_version_changed")
        if search.get("is_stale"):
            reasons.append("optimizer_search_stale")
        if isinstance(search_item, dict) and not (search_item.get("patch") or {}):
            reasons.append("symbol_overlay_patch_missing")
    can_save = len(reasons) == 0
    can_apply = can_save
    return {
        "can_save": can_save,
        "can_apply": can_apply,
        "reasons": _blocked_guardrail_reasons(
            decision_status=str((candidate or {}).get("decision", {}).get("status") or "hold"),
            can_save=can_save,
            can_apply=can_apply,
            reasons=reasons,
            fallback="symbol_save_guardrail_blocked",
        ),
    }


def _refresh_symbol_candidate(
    candidate: dict[str, Any] | None,
    search: dict[str, Any],
    search_item: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    refreshed = _refresh_candidate(candidate, search)
    if not isinstance(refreshed, dict):
        return None
    if isinstance(search_item, dict):
        refreshed["search_symbol_snapshot"] = search_item.get("snapshot") or {}
        refreshed["search_symbol_patch"] = search_item.get("patch") or {}
        if not refreshed.get("patch") and isinstance(search_item.get("patch"), dict):
            refreshed["patch"] = dict(search_item.get("patch") or {})
    refreshed["validation_status"] = str(refreshed.get("validation_status") or "passed")
    return refreshed


def _build_symbol_candidate(
    *,
    symbol: str,
    search: dict[str, Any],
    search_item: dict[str, Any],
    base_query: dict[str, Any],
    mutated_query: dict[str, Any],
    settings: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    base = _build_candidate(
        search=search,
        base_query=base_query,
        mutated_query=mutated_query,
        settings=settings,
        diagnostics=diagnostics,
    )
    patch = dict(search_item.get("patch") or {})
    return {
        **base,
        "id": f"symcand-{symbol.lower()}-{uuid.uuid4().hex[:10]}",
        "runtime_candidate_source_mode": base.get("runtime_candidate_source_mode", "quant_only"),
        "symbol": symbol,
        "source": "optimizer_symbol_overlay",
        "patch": patch,
        "patch_lines": _patch_lines(base_query, mutated_query, patch),
        "search_symbol_patch": patch,
        "search_symbol_snapshot": dict(search_item.get("snapshot") or {}),
        "validation_status": "passed",
    }


def _symbol_runtime_overlay(saved_candidate: dict[str, Any]) -> dict[str, Any]:
    patch = saved_candidate.get("patch") if isinstance(saved_candidate.get("patch"), dict) else {}
    snapshot = saved_candidate.get("search_symbol_snapshot") if isinstance(saved_candidate.get("search_symbol_snapshot"), dict) else {}
    metrics = saved_candidate.get("metrics") if isinstance(saved_candidate.get("metrics"), dict) else {}
    payload = dict(snapshot)
    payload.update({
        key: value
        for key, value in patch.items()
        if key in _OPTIMIZABLE_KEYS and value not in (None, "")
    })
    if "trade_count" not in payload and metrics.get("trade_count") is not None:
        payload["trade_count"] = metrics.get("trade_count")
    if "strategy_reliability" not in payload and metrics.get("reliability"):
        payload["strategy_reliability"] = metrics.get("reliability")
    payload["is_reliable"] = bool(payload.get("is_reliable", False)) or str(metrics.get("reliability") or "") == "high"
    payload["approved_candidate_id"] = saved_candidate.get("id")
    payload["approved_saved_at"] = saved_candidate.get("saved_at")
    payload["approved_by_quant_ops"] = True
    return payload


def _refresh_symbol_states(
    state: dict[str, Any],
    search: dict[str, Any],
    search_items: dict[str, dict[str, Any]],
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    latest_map = state.get("latest_symbol_candidates") if isinstance(state.get("latest_symbol_candidates"), dict) else {}
    saved_map = state.get("saved_symbol_candidates") if isinstance(state.get("saved_symbol_candidates"), dict) else {}
    runtime_map = state.get("runtime_symbol_apply") if isinstance(state.get("runtime_symbol_apply"), dict) else {}
    runtime_candidates = runtime_map.get("candidate_ids") if isinstance(runtime_map.get("candidate_ids"), dict) else {}

    symbols = sorted(set(search_items.keys()) | set(latest_map.keys()) | set(saved_map.keys()) | set(runtime_candidates.keys()))
    refreshed_latest: dict[str, Any] = {}
    refreshed_saved: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    approved_count = 0
    saved_count = 0
    runtime_count = 0
    for symbol in symbols:
        search_item = search_items.get(symbol)
        latest_candidate_raw = _refresh_symbol_candidate(
            latest_map.get(symbol) if isinstance(latest_map.get(symbol), dict) else None,
            search,
            search_item,
        )
        latest_candidate_state = _candidate_activity_state(latest_candidate_raw, search, baseline)
        latest_candidate = latest_candidate_raw if latest_candidate_state.get("active") else None
        if latest_candidate:
            refreshed_latest[symbol] = latest_candidate
        approval = _read_symbol_approval(state, symbol)
        if latest_candidate and approval.get("status") == "approved":
            approved_count += 1
        latest_guardrails = _symbol_save_guardrails(latest_candidate, approval, search=search, search_item=search_item)

        saved_candidate_raw = _refresh_symbol_candidate(
            saved_map.get(symbol) if isinstance(saved_map.get(symbol), dict) else None,
            search,
            search_item,
        )
        saved_candidate_state = _candidate_activity_state(saved_candidate_raw, search, baseline)
        saved_candidate = saved_candidate_raw if saved_candidate_state.get("active") else None
        if saved_candidate:
            refreshed_saved[symbol] = saved_candidate
            saved_count += 1
        saved_guardrails = _symbol_save_guardrails(saved_candidate, approval, search=search, search_item=search_item)

        runtime_candidate_id = str(runtime_candidates.get(symbol) or "")
        runtime_applied_at = str(runtime_map.get("applied_at") or "")
        runtime_applied = bool(runtime_candidate_id and (not saved_candidate or str(saved_candidate.get("id") or "") == runtime_candidate_id))
        if runtime_applied:
            runtime_count += 1

        should_include_row = bool(search_item or latest_candidate or saved_candidate or runtime_candidate_id or approval.get("status") != "hold")
        if not should_include_row:
            continue

        rows.append({
            "symbol": symbol,
            "search_candidate": search_item,
            "latest_candidate": latest_candidate,
            "latest_candidate_state": latest_candidate_state,
            "approval": approval,
            "saved_candidate": saved_candidate,
            "saved_candidate_state": saved_candidate_state,
            "latest_guardrails": latest_guardrails,
            "saved_guardrails": saved_guardrails,
            "runtime": {
                "applied": runtime_applied,
                "candidate_id": runtime_candidate_id,
                "applied_at": runtime_applied_at,
            },
        })

    summary = {
        "search_count": len(search_items),
        "validated_count": len(refreshed_latest),
        "approved_count": approved_count,
        "saved_count": saved_count,
        "runtime_applied_count": runtime_count,
    }
    return rows, refreshed_latest, refreshed_saved, summary


def _runtime_summary(runtime_payload: dict[str, Any] | None, state_runtime: dict[str, Any] | None) -> dict[str, Any]:
    runtime_payload = runtime_payload or {}
    state_runtime = state_runtime if isinstance(state_runtime, dict) else {}
    meta = runtime_payload.get("meta") if isinstance(runtime_payload.get("meta"), dict) else {}
    return {
        "available": bool(runtime_payload),
        "status": "applied" if runtime_payload else "missing",
        "runtime_candidate_source_mode": normalize_runtime_candidate_source_mode(
            runtime_payload.get("runtime_candidate_source_mode") or meta.get("runtime_candidate_source_mode") or "quant_only"
        ),
        "candidate_id": str(meta.get("applied_candidate_id") or state_runtime.get("candidate_id") or ""),
        "applied_at": str(runtime_payload.get("applied_at") or state_runtime.get("applied_at") or ""),
        "applied_symbol_count": _to_int(meta.get("approved_symbol_count"), _to_int(state_runtime.get("applied_symbol_count"), 0)),
        "applied_symbols": meta.get("approved_symbols") if isinstance(meta.get("approved_symbols"), list) else [],
        "version": str(runtime_payload.get("version") or runtime_payload.get("optimized_at") or ""),
        "effective_source": "runtime" if runtime_payload else "search",
        "source": str(RUNTIME_OPTIMIZED_PARAMS_PATH),
        "engine_state": state_runtime.get("engine_state"),
        "next_run_at": state_runtime.get("next_run_at"),
    }


def get_quant_ops_workflow() -> dict[str, Any]:
    runtime_payload = load_runtime_optimized_params()
    state = _self_heal_state(runtime_payload)
    baseline = _load_current_validation_baseline()
    search_payload = load_search_optimized_params()
    search = _search_summary(search_payload)
    if _recover_pending_search_handoff(search, baseline) is not None:
        state = _self_heal_state(runtime_payload)
    search_items = _symbol_search_candidates(search_payload, search)

    latest_candidate_raw = _refresh_candidate(state.get("latest_candidate"), search)
    latest_candidate_state = _candidate_activity_state(latest_candidate_raw, search, baseline)
    latest_candidate = latest_candidate_raw if latest_candidate_state.get("active") else None

    saved_candidate_raw = _refresh_candidate(state.get("saved_candidate"), search)
    saved_candidate_state = _candidate_activity_state(saved_candidate_raw, search, baseline)
    saved_candidate = saved_candidate_raw if saved_candidate_state.get("active") else None

    symbol_rows, refreshed_latest_symbols, refreshed_saved_symbols, symbol_summary = _refresh_symbol_states(
        state,
        search,
        search_items,
        baseline,
    )
    runtime_apply = _canonicalize_runtime_summary(
        _runtime_summary(runtime_payload, state.get("runtime_apply")),
        saved_candidate,
    )
    raw_search_handoff = state.get("pending_search_handoff") if isinstance(state.get("pending_search_handoff"), dict) else state.get("last_search_handoff")
    search_handoff = _canonicalize_search_handoff(
        raw_search_handoff,
        search=search,
        baseline=baseline,
        latest_candidate=latest_candidate,
        latest_candidate_state=latest_candidate_state,
    )

    stage_status = {
        "candidate_search": "ready" if search.get("available") else "missing",
        "revalidation": str(((latest_candidate or {}).get("decision") or {}).get("status") or "missing"),
        "save": "saved" if saved_candidate else "missing",
        "runtime_apply": str(runtime_apply.get("status") or "missing"),
        "symbol_revalidation": "ready" if symbol_summary.get("validated_count", 0) > 0 else "missing",
        "symbol_approval": "approved" if symbol_summary.get("approved_count", 0) > 0 else "missing",
        "symbol_save": "saved" if symbol_summary.get("saved_count", 0) > 0 else "missing",
        "symbol_runtime_apply": "applied" if symbol_summary.get("runtime_applied_count", 0) > 0 else "missing",
    }

    return {
        "ok": True,
        "search_result": search,
        "search_available": bool(search.get("available")),
        "candidate_search": stage_status["candidate_search"],
        "latest_candidate": latest_candidate,
        "latest_candidate_state": latest_candidate_state,
        "saved_candidate": saved_candidate,
        "saved_candidate_state": saved_candidate_state,
        "symbol_candidates": symbol_rows,
        "symbol_summary": symbol_summary,
        "latest_symbol_candidates": refreshed_latest_symbols,
        "saved_symbol_candidates": refreshed_saved_symbols,
        "runtime_apply": runtime_apply,
        "search_handoff": search_handoff,
        "validation_baseline": baseline,
        "stage_status": stage_status,
        "notes": [
            "optimizer 결과는 후보 탐색용이고, latest_candidate는 재검증이 끝난 운영 후보입니다.",
            "saved_candidate는 재검증 통과 후 저장된 스냅샷이고, runtime_apply는 실제 런타임에 적용된 상태입니다.",
            "symbol_candidates는 종목별 탐색/재검증/승인/저장/반영 상태를 분리해서 보여줍니다.",
        ],
    }


def _sanitize_search_handoff_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    raw_query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
    raw_settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    baseline = _load_current_validation_baseline()
    if not raw_query and not raw_settings and not baseline.get("available"):
        return None
    _, query, settings = _resolve_validation_context(raw_query, raw_settings, baseline)
    return {
        "query": copy.deepcopy(query),
        "settings": copy.deepcopy(settings),
    }


def register_optimizer_search_handoff(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    handoff = _sanitize_search_handoff_payload(payload)
    if not handoff:
        return None
    state = _load_state()
    state["pending_search_handoff"] = {
        **handoff,
        "requested_at": _now_iso(),
        "status": "pending",
    }
    _save_state(state)
    return state["pending_search_handoff"]


def _finalize_search_handoff_record(
    pending: dict[str, Any],
    *,
    status: str,
    error: str = "",
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = _load_state()
    finalized = {
        **copy.deepcopy(pending),
        "completed_at": _now_iso(),
        "status": status,
        "error": error,
    }
    if isinstance(candidate, dict):
        decision = candidate.get("decision") if isinstance(candidate.get("decision"), dict) else {}
        finalized.update({
            "candidate_id": str(candidate.get("id") or ""),
            "search_version": str(candidate.get("search_version") or ""),
            "decision_status": str(decision.get("status") or ""),
            "decision_label": str(decision.get("label") or ""),
        })
    state["pending_search_handoff"] = None
    state["last_search_handoff"] = finalized
    _save_state(state)
    return finalized


def _revalidate_optimizer_candidate_impl(query: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    search = _search_summary(load_search_optimized_params())
    if not search.get("available"):
        return {"ok": False, "error": "optimizer_search_missing"}
    if not search.get("global_params"):
        return {"ok": False, "error": "optimizer_global_params_missing"}

    _, resolved_query, resolved_settings = _resolve_validation_context(query, settings)
    mutated_query = _merge_query_patch(resolved_query, search.get("global_params") or {})
    diagnostics = run_validation_diagnostics(_build_service_query(mutated_query, resolved_settings))
    if not isinstance(diagnostics, dict) or diagnostics.get("error") or not diagnostics.get("ok"):
        return {
            "ok": False,
            "error": str((diagnostics or {}).get("error") or "candidate_revalidation_failed"),
            "details": diagnostics,
        }

    candidate = _build_candidate(
        search=search,
        base_query=resolved_query,
        mutated_query=mutated_query,
        settings=resolved_settings,
        diagnostics=diagnostics,
    )
    candidate["runtime_candidate_source_mode"] = normalize_runtime_candidate_source_mode(
        settings.get("runtime_candidate_source_mode")
    )
    state = _load_state()
    state["latest_candidate"] = candidate
    state["candidate_history"] = _history_push(
        state.get("candidate_history") if isinstance(state.get("candidate_history"), list) else [],
        candidate,
    )
    _save_state(state)
    return {
        "ok": True,
        "candidate": candidate,
    }


def _recover_pending_search_handoff(search: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any] | None:
    state = _load_state()
    pending = state.get("pending_search_handoff") if isinstance(state.get("pending_search_handoff"), dict) else None
    if not pending:
        return None

    status = str(pending.get("status") or "pending")
    if status not in {"pending", "pending_revalidation"}:
        return None

    pending_query = pending.get("query") if isinstance(pending.get("query"), dict) else {}
    pending_settings = pending.get("settings") if isinstance(pending.get("settings"), dict) else {}
    pending_age = _age_seconds(str(pending.get("requested_at") or ""))
    optimizer_active = _optimizer_job_active()
    baseline_matches = _matches_validation_baseline(pending_query, pending_settings, baseline)
    if not baseline_matches:
        return _finalize_search_handoff_record(
            pending,
            status="revalidate_failed",
            error="validation_settings_changed",
        )

    if not search.get("available"):
        if pending_age is not None and pending_age > 3900:
            return _finalize_search_handoff_record(
                pending,
                status="optimizer_failed",
                error="optimizer_handoff_expired",
            )
        if not optimizer_active:
            return _finalize_search_handoff_record(
                pending,
                status="optimizer_failed",
                error="optimizer_not_running",
            )
        return None

    requested_at = _parse_iso_timestamp(str(pending.get("requested_at") or ""))
    optimized_at = _parse_iso_timestamp(str(search.get("optimized_at") or ""))
    if requested_at and optimized_at and optimized_at < requested_at:
        if optimizer_active and (pending_age is None or pending_age <= 3900):
            return None
        return _finalize_search_handoff_record(
            pending,
            status="optimizer_failed",
            error="optimizer_result_obsolete",
        )

    latest_candidate_raw = state.get("latest_candidate") if isinstance(state.get("latest_candidate"), dict) else None
    latest_candidate = _refresh_candidate(latest_candidate_raw, search)
    latest_candidate_state = _candidate_activity_state(latest_candidate, search, baseline)
    if (
        latest_candidate_state.get("active")
        and isinstance(latest_candidate, dict)
        and str(latest_candidate.get("search_version") or "") == str(search.get("version") or "")
    ):
        return _finalize_search_handoff_record(
            pending,
            status="candidate_updated",
            candidate=latest_candidate,
        )

    try:
        result = _revalidate_optimizer_candidate_impl(pending_query, pending_settings)
    except Exception as exc:
        return _finalize_search_handoff_record(
            pending,
            status="revalidate_failed",
            error=str(exc),
        )

    candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else None
    return _finalize_search_handoff_record(
        pending,
        status="candidate_updated" if result.get("ok") else "revalidate_failed",
        error=str(result.get("error") or ""),
        candidate=candidate,
    )


def finalize_optimizer_search_handoff(*, success: bool, error: str = "") -> dict[str, Any] | None:
    state = _load_state()
    pending = state.get("pending_search_handoff") if isinstance(state.get("pending_search_handoff"), dict) else None
    if not pending:
        return None
    if not success:
        finalized = _finalize_search_handoff_record(pending, status="optimizer_failed", error=error)
        return {
            "ok": False,
            "error": error or "optimizer_failed",
            "handoff": finalized,
            "workflow": get_quant_ops_workflow(),
        }

    try:
        result = _revalidate_optimizer_candidate_impl(
            pending.get("query") if isinstance(pending.get("query"), dict) else {},
            pending.get("settings") if isinstance(pending.get("settings"), dict) else {},
        )
    except Exception as exc:
        finalized = _finalize_search_handoff_record(pending, status="revalidate_failed", error=str(exc))
        return {
            "ok": False,
            "error": str(exc),
            "handoff": finalized,
            "workflow": get_quant_ops_workflow(),
        }

    candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else None
    finalized = _finalize_search_handoff_record(
        pending,
        status="candidate_updated" if result.get("ok") else "revalidate_failed",
        error=str(result.get("error") or error or ""),
        candidate=candidate,
    )
    return {
        "ok": bool(result.get("ok")),
        "error": str(result.get("error") or error or ""),
        "handoff": finalized,
        "candidate": candidate,
        "workflow": get_quant_ops_workflow(),
    }


def revalidate_optimizer_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    result = _revalidate_optimizer_candidate_impl(query, settings)
    result["workflow"] = get_quant_ops_workflow()
    return result


def _resolve_candidate_for_save(candidate_id: str | None = None) -> dict[str, Any] | None:
    state = _load_state()
    latest = state.get("latest_candidate") if isinstance(state.get("latest_candidate"), dict) else None
    if not candidate_id:
        return latest
    if latest and str(latest.get("id") or "") == candidate_id:
        return latest
    history = state.get("candidate_history") if isinstance(state.get("candidate_history"), list) else []
    for item in history:
        if isinstance(item, dict) and str(item.get("id") or "") == candidate_id:
            return item
    return None


def save_validated_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(payload.get("candidate_id") or "").strip() or None
    note = str(payload.get("note") or "").strip()
    search = _search_summary(load_search_optimized_params())
    candidate = _refresh_candidate(_resolve_candidate_for_save(candidate_id), search)
    if not candidate:
        return {"ok": False, "error": "validated_candidate_missing", "workflow": get_quant_ops_workflow()}
    guardrails = candidate.get("guardrails") if isinstance(candidate.get("guardrails"), dict) else {}
    if not bool(guardrails.get("can_save")):
        return {
            "ok": False,
            "error": "save_guardrail_blocked",
            "candidate": candidate,
            "workflow": get_quant_ops_workflow(),
        }

    saved_candidate = {
        **candidate,
        "saved_at": _now_iso(),
        "save_note": note,
    }
    state = _load_state()
    state["saved_candidate"] = saved_candidate
    state["saved_history"] = _history_push(
        state.get("saved_history") if isinstance(state.get("saved_history"), list) else [],
        saved_candidate,
    )
    _save_state(state)
    return {
        "ok": True,
        "candidate": saved_candidate,
        "workflow": get_quant_ops_workflow(),
    }


def revalidate_symbol_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = _symbol_code(payload.get("symbol"))
    query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    _, resolved_query, resolved_settings = _resolve_validation_context(query, settings)
    search_payload = load_search_optimized_params()
    search = _search_summary(search_payload)
    search_items = _symbol_search_candidates(search_payload, search)
    if not symbol:
        return {"ok": False, "error": "symbol_required", "workflow": get_quant_ops_workflow()}
    search_item = search_items.get(symbol)
    if not search_item:
        return {
            "ok": False,
            "error": "symbol_search_candidate_missing",
            "symbol": symbol,
            "workflow": get_quant_ops_workflow(),
        }
    patch = search_item.get("patch") if isinstance(search_item.get("patch"), dict) else {}
    if not patch:
        return {
            "ok": False,
            "error": "symbol_overlay_patch_missing",
            "symbol": symbol,
            "workflow": get_quant_ops_workflow(),
        }

    mutated_query = _merge_query_patch(resolved_query, patch)
    diagnostics = run_validation_diagnostics(_build_service_query(mutated_query, resolved_settings))
    if not isinstance(diagnostics, dict) or diagnostics.get("error") or not diagnostics.get("ok"):
        return {
            "ok": False,
            "error": str((diagnostics or {}).get("error") or "symbol_candidate_revalidation_failed"),
            "symbol": symbol,
            "details": diagnostics,
            "workflow": get_quant_ops_workflow(),
        }
    candidate = _build_symbol_candidate(
        symbol=symbol,
        search=search,
        search_item=search_item,
        base_query=resolved_query,
        mutated_query=mutated_query,
        settings=resolved_settings,
        diagnostics=diagnostics,
    )
    candidate["runtime_candidate_source_mode"] = normalize_runtime_candidate_source_mode(
        settings.get("runtime_candidate_source_mode")
    )
    state = _load_state()
    latest_symbol_candidates = state.get("latest_symbol_candidates") if isinstance(state.get("latest_symbol_candidates"), dict) else {}
    latest_symbol_candidates[symbol] = candidate
    state["latest_symbol_candidates"] = latest_symbol_candidates
    history_map = state.get("symbol_candidate_history") if isinstance(state.get("symbol_candidate_history"), dict) else {}
    history = history_map.get(symbol) if isinstance(history_map.get(symbol), list) else []
    history_map[symbol] = _history_push(history, candidate)
    state["symbol_candidate_history"] = history_map
    approvals = state.get("symbol_approvals") if isinstance(state.get("symbol_approvals"), dict) else {}
    approvals[symbol] = {
        "status": "hold",
        "note": "",
        "reason": "awaiting_operator_review",
        "updated_at": _now_iso(),
        "candidate_id": candidate.get("id"),
    }
    state["symbol_approvals"] = approvals
    _save_state(state)
    return {
        "ok": True,
        "symbol": symbol,
        "candidate": candidate,
        "workflow": get_quant_ops_workflow(),
    }


def set_symbol_candidate_approval(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = _symbol_code(payload.get("symbol"))
    status = str(payload.get("status") or "hold").strip().lower()
    if status not in _SYMBOL_APPROVAL_STATUSES:
        return {"ok": False, "error": "symbol_approval_status_invalid", "workflow": get_quant_ops_workflow()}
    state = _load_state()
    latest_map = state.get("latest_symbol_candidates") if isinstance(state.get("latest_symbol_candidates"), dict) else {}
    latest_candidate = latest_map.get(symbol) if isinstance(latest_map.get(symbol), dict) else None
    if not latest_candidate:
        return {
            "ok": False,
            "error": "symbol_validated_candidate_missing",
            "symbol": symbol,
            "workflow": get_quant_ops_workflow(),
        }
    note = str(payload.get("note") or "").strip()
    reason = str(payload.get("reason") or "").strip() or (
        "operator_approved" if status == "approved" else "operator_rejected" if status == "rejected" else "operator_hold"
    )
    approvals = state.get("symbol_approvals") if isinstance(state.get("symbol_approvals"), dict) else {}
    approvals[symbol] = {
        "status": status,
        "note": note,
        "reason": reason,
        "updated_at": _now_iso(),
        "candidate_id": latest_candidate.get("id"),
    }
    state["symbol_approvals"] = approvals
    _save_state(state)
    return {
        "ok": True,
        "symbol": symbol,
        "approval": approvals[symbol],
        "workflow": get_quant_ops_workflow(),
    }


def save_symbol_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = _symbol_code(payload.get("symbol"))
    if not symbol:
        return {"ok": False, "error": "symbol_required", "workflow": get_quant_ops_workflow()}
    state = _load_state()
    latest_map = state.get("latest_symbol_candidates") if isinstance(state.get("latest_symbol_candidates"), dict) else {}
    latest_candidate = latest_map.get(symbol) if isinstance(latest_map.get(symbol), dict) else None
    search_payload = load_search_optimized_params()
    search = _search_summary(search_payload)
    search_items = _symbol_search_candidates(search_payload, search)
    search_item = search_items.get(symbol)
    latest_candidate = _refresh_symbol_candidate(latest_candidate, search, search_item)
    approval = _read_symbol_approval(state, symbol)
    guardrails = _symbol_save_guardrails(latest_candidate, approval, search=search, search_item=search_item)
    if not latest_candidate:
        return {
            "ok": False,
            "error": "symbol_validated_candidate_missing",
            "symbol": symbol,
            "workflow": get_quant_ops_workflow(),
        }
    if not bool(guardrails.get("can_save")):
        return {
            "ok": False,
            "error": "symbol_save_guardrail_blocked",
            "symbol": symbol,
            "candidate": latest_candidate,
            "guardrails": guardrails,
            "workflow": get_quant_ops_workflow(),
        }
    saved_candidate = {
        **latest_candidate,
        "saved_at": _now_iso(),
        "save_note": str(payload.get("note") or "").strip(),
        "approval": approval,
    }
    saved_map = state.get("saved_symbol_candidates") if isinstance(state.get("saved_symbol_candidates"), dict) else {}
    saved_map[symbol] = saved_candidate
    state["saved_symbol_candidates"] = saved_map
    history_map = state.get("saved_symbol_history") if isinstance(state.get("saved_symbol_history"), dict) else {}
    history = history_map.get(symbol) if isinstance(history_map.get(symbol), list) else []
    history_map[symbol] = _history_push(history, saved_candidate)
    state["saved_symbol_history"] = history_map
    _save_state(state)
    return {
        "ok": True,
        "symbol": symbol,
        "candidate": saved_candidate,
        "workflow": get_quant_ops_workflow(),
    }


def _global_runtime_validation_baseline(candidate: dict[str, Any]) -> dict[str, Any]:
    validation = candidate.get("validation") if isinstance(candidate.get("validation"), dict) else {}
    segments = validation.get("segments") if isinstance(validation.get("segments"), dict) else {}
    summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    oos = segments.get("oos") if isinstance(segments.get("oos"), dict) else {}
    reliability_diagnostic = summary.get("reliability_diagnostic") if isinstance(summary.get("reliability_diagnostic"), dict) else {}
    current = reliability_diagnostic.get("current") if isinstance(reliability_diagnostic.get("current"), dict) else {}
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    scorecard = validation.get("scorecard") if isinstance(validation.get("scorecard"), dict) else {}

    passes_minimum_gate = current.get("passes_minimum_gate")
    if passes_minimum_gate is None:
        passes_minimum_gate = reliability_diagnostic.get("target_reached")
    if passes_minimum_gate is None:
        passes_minimum_gate = metrics.get("reliability_target_reached")

    is_reliable = current.get("is_reliable")
    if is_reliable is None:
        is_reliable = str(metrics.get("reliability") or summary.get("oos_reliability") or "") == "high"

    trade_count = _to_int(current.get("trade_count"), _to_int(metrics.get("trade_count"), _to_int(oos.get("trade_count"), 0)))
    validation_trades = _to_int(current.get("validation_signals"), trade_count)
    validation_sharpe = _to_float(current.get("validation_sharpe"), _to_float(oos.get("sharpe"), 0.0))
    max_drawdown_pct = current.get("max_drawdown_pct")
    if max_drawdown_pct is None:
        max_drawdown_pct = metrics.get("max_drawdown_pct")
    if max_drawdown_pct is None:
        max_drawdown_pct = oos.get("max_drawdown_pct")

    return {
        "source": "validated_candidate",
        "candidate_id": candidate.get("id"),
        "runtime_candidate_source_mode": normalize_runtime_candidate_source_mode(candidate.get("runtime_candidate_source_mode")),
        "trade_count": trade_count,
        "validation_trades": validation_trades,
        "validation_sharpe": round(validation_sharpe, 4),
        "max_drawdown_pct": round(_to_float(max_drawdown_pct, 0.0), 4) if max_drawdown_pct is not None else None,
        "strategy_reliability": str(current.get("label") or metrics.get("reliability") or summary.get("oos_reliability") or "insufficient"),
        "reliability_reason": str(current.get("reason") or ""),
        "passes_minimum_gate": bool(passes_minimum_gate),
        "is_reliable": bool(is_reliable),
        "composite_score": metrics.get("composite_score") if metrics.get("composite_score") is not None else scorecard.get("composite_score"),
        "approved_candidate_id": candidate.get("id"),
        "approved_saved_at": candidate.get("saved_at"),
        "approved_by_quant_ops": True,
    }


def _build_runtime_payload(
    candidate: dict[str, Any],
    search_payload: dict[str, Any] | None,
    saved_symbol_candidates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    search_payload = search_payload or {}
    meta = search_payload.get("meta") if isinstance(search_payload.get("meta"), dict) else {}
    applied_at = _now_iso()
    symbol_candidates = saved_symbol_candidates if isinstance(saved_symbol_candidates, dict) else {}
    per_symbol_overlay = {
        symbol: _symbol_runtime_overlay(item)
        for symbol, item in symbol_candidates.items()
        if isinstance(item, dict)
    }
    runtime_candidate_source_mode = normalize_runtime_candidate_source_mode(candidate.get("runtime_candidate_source_mode"))
    return {
        "optimized_at": applied_at,
        "applied_at": applied_at,
        "version": f"runtime-{candidate.get('id')}",
        "global_params": dict(candidate.get("patch") or {}),
        "runtime_candidate_source_mode": runtime_candidate_source_mode,
        "validation_baseline": _global_runtime_validation_baseline(candidate),
        "per_symbol": per_symbol_overlay,
        "meta": {
            **meta,
            "applied_candidate_id": candidate.get("id"),
            "applied_candidate_saved_at": candidate.get("saved_at"),
            "applied_from": "quant_ops_saved_candidate",
            "search_version": candidate.get("search_version"),
            "search_optimized_at": candidate.get("search_optimized_at"),
            "runtime_candidate_source_mode": runtime_candidate_source_mode,
            "global_overlay_source": "validated_candidate",
            "validation_baseline_source": "validated_candidate",
            "approved_symbol_count": len(per_symbol_overlay),
            "approved_symbols": sorted(per_symbol_overlay.keys()),
        },
    }


def apply_saved_candidate_to_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(payload.get("candidate_id") or "").strip() or None
    state = _load_state()
    raw_saved = state.get("saved_candidate") if isinstance(state.get("saved_candidate"), dict) else None
    if candidate_id and raw_saved and str(raw_saved.get("id") or "") != candidate_id:
        history = state.get("saved_history") if isinstance(state.get("saved_history"), list) else []
        raw_saved = next((item for item in history if isinstance(item, dict) and str(item.get("id") or "") == candidate_id), None)
    search = _search_summary(load_search_optimized_params())
    saved_candidate = _refresh_candidate(raw_saved, search)
    if not saved_candidate:
        return {"ok": False, "error": "saved_candidate_missing", "workflow": get_quant_ops_workflow()}
    guardrails = saved_candidate.get("guardrails") if isinstance(saved_candidate.get("guardrails"), dict) else {}
    if not bool(guardrails.get("can_apply")):
        return {
            "ok": False,
            "error": "runtime_apply_guardrail_blocked",
            "candidate": saved_candidate,
            "workflow": get_quant_ops_workflow(),
        }

    search_payload = load_search_optimized_params()
    search = _search_summary(search_payload)
    search_items = _symbol_search_candidates(search_payload, search)
    approvals = state.get("symbol_approvals") if isinstance(state.get("symbol_approvals"), dict) else {}
    saved_symbol_map = state.get("saved_symbol_candidates") if isinstance(state.get("saved_symbol_candidates"), dict) else {}
    approved_saved_symbols: dict[str, dict[str, Any]] = {}
    skipped_symbols: dict[str, list[str]] = {}
    for raw_symbol, raw_candidate in saved_symbol_map.items():
        symbol = _symbol_code(raw_symbol)
        candidate_item = _refresh_symbol_candidate(
            raw_candidate if isinstance(raw_candidate, dict) else None,
            search,
            search_items.get(symbol),
        )
        approval = {
            **_read_symbol_approval(state, symbol),
            "status": str((approvals.get(symbol) or {}).get("status") or "hold"),
        }
        symbol_guardrails = _symbol_save_guardrails(
            candidate_item,
            approval,
            search=search,
            search_item=search_items.get(symbol),
        )
        if candidate_item and symbol_guardrails.get("can_apply"):
            approved_saved_symbols[symbol] = candidate_item
        else:
            skipped_symbols[symbol] = list(symbol_guardrails.get("reasons") or ["symbol_runtime_apply_guardrail_blocked"])

    runtime_payload = _build_runtime_payload(saved_candidate, search_payload, approved_saved_symbols)
    write_runtime_optimized_params(runtime_payload)

    engine_state_payload: dict[str, Any] = {}
    try:
        from services.execution_service import apply_quant_candidate_runtime_config

        engine_state_payload = apply_quant_candidate_runtime_config(saved_candidate)
    except Exception as exc:  # pragma: no cover - defensive route handling
        engine_state_payload = {"ok": False, "error": str(exc)}

    runtime_apply = {
        "candidate_id": saved_candidate.get("id"),
        "applied_at": runtime_payload.get("applied_at"),
        "engine_state": ((engine_state_payload.get("state") or {}).get("engine_state") if isinstance(engine_state_payload.get("state"), dict) else None),
        "next_run_at": ((engine_state_payload.get("state") or {}).get("next_run_at") if isinstance(engine_state_payload.get("state"), dict) else None),
        "applied_symbol_count": len(approved_saved_symbols),
        "skipped_symbols": skipped_symbols,
    }
    saved_candidate = {
        **saved_candidate,
        "applied_at": runtime_payload.get("applied_at"),
    }
    state["saved_candidate"] = saved_candidate
    state["runtime_apply"] = runtime_apply
    state["runtime_symbol_apply"] = {
        "applied_at": runtime_payload.get("applied_at"),
        "candidate_ids": {
            symbol: str(item.get("id") or "")
            for symbol, item in approved_saved_symbols.items()
            if isinstance(item, dict)
        },
        "symbol_count": len(approved_saved_symbols),
        "skipped_symbols": skipped_symbols,
    }
    _save_state(state)
    return {
        "ok": True,
        "candidate": saved_candidate,
        "runtime_apply": runtime_apply,
        "symbol_apply": state.get("runtime_symbol_apply"),
        "engine": engine_state_payload,
        "workflow": get_quant_ops_workflow(),
    }
