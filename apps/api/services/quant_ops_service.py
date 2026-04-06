from __future__ import annotations

import copy
import datetime as dt
import os
import uuid
from pathlib import Path
from typing import Any

from config.settings import LOGS_DIR
from services.json_utils import json_dump_text, read_json_file_cached
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
from services.quant_guardrail_policy_store import load_quant_guardrail_policy
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


def _default_state() -> dict[str, Any]:
    return {
        "latest_candidate": None,
        "candidate_history": [],
        "saved_candidate": None,
        "saved_history": [],
        "runtime_apply": None,
        "pending_search_handoff": None,
        "last_search_handoff": None,
    }


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = read_json_file_cached(path)
        return payload if isinstance(payload, dict) else dict(default)
    except Exception:
        return dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dump_text(payload, indent=2), encoding="utf-8")


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


def _strategy_candidate_rank(reliability: str) -> int:
    normalized = str(reliability or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    return 2


def _strategy_candidate_patch(item: dict[str, Any]) -> dict[str, Any]:
    raw_patch = item.get("patch") if isinstance(item.get("patch"), dict) else {}
    if raw_patch:
        return {
            key: value
            for key, value in raw_patch.items()
            if key in _OPTIMIZABLE_KEYS and value not in (None, "")
        }
    return {
        key: value
        for key, value in item.items()
        if key in _OPTIMIZABLE_KEYS and value not in (None, "")
    }


def _normalize_strategy_candidates(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = payload if isinstance(payload, dict) else {}
    raw_candidates = payload.get("strategy_candidates")
    if not isinstance(raw_candidates, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_candidates, start=1):
        item = raw_item if isinstance(raw_item, dict) else {}
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else item
        patch = _strategy_candidate_patch(item)
        patch_lines = item.get("patch_lines") if isinstance(item.get("patch_lines"), list) else []
        key = str(
            item.get("key")
            or item.get("candidate_key")
            or item.get("id")
            or f"strategy-candidate-{index}"
        ).strip()
        reliability = str(
            item.get("reliability")
            or metrics.get("reliability")
            or metrics.get("strategy_reliability")
            or ""
        ).strip()
        rows.append({
            "key": key,
            "label": str(item.get("label") or item.get("name") or key),
            "summary": str(item.get("summary") or metrics.get("summary") or ""),
            "source": str(item.get("source") or item.get("selection_source") or ""),
            "reliability": reliability,
            "is_reliable": bool(item.get("is_reliable")),
            "reliability_reason": str(item.get("reliability_reason") or metrics.get("reliability_reason") or ""),
            "composite_score": _to_float(metrics.get("composite_score")),
            "profit_factor": _to_float(metrics.get("profit_factor")),
            "validation_sharpe": _to_float(metrics.get("validation_sharpe")),
            "trade_count": _to_int(metrics.get("trade_count"), 0),
            "max_drawdown_pct": _to_float(metrics.get("max_drawdown_pct")),
            "patch": patch,
            "patch_lines": [str(line) for line in patch_lines if str(line).strip()] or [f"{param}: {value}" for param, value in sorted(patch.items())],
            "_rank": _strategy_candidate_rank(reliability),
            "_order": _to_int(item.get("rank"), index),
        })
    rows.sort(
        key=lambda row: (
            row.get("_rank", 9),
            row.get("_order", 999999),
            -(row.get("composite_score") or -999999),
            str(row.get("key") or ""),
        )
    )
    for row in rows:
        row.pop("_rank", None)
        row.pop("_order", None)
    return rows


def _search_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload, artifact_present = _recover_search_payload(payload)
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    global_params = payload.get("global_params") if isinstance(payload.get("global_params"), dict) else {}
    per_symbol = payload.get("per_symbol") if isinstance(payload.get("per_symbol"), dict) else {}
    strategy_candidates = _normalize_strategy_candidates(payload)
    optimized_at = str(payload.get("optimized_at") or "")
    search_context = meta.get("search_context") if isinstance(meta.get("search_context"), dict) else {}
    has_materialized_payload = bool(payload) or bool(global_params) or bool(strategy_candidates) or bool(per_symbol) or bool(meta) or bool(optimized_at)
    version = str(payload.get("version") or optimized_at or "")
    reliable_count = sum(1 for item in strategy_candidates if str(item.get("reliability") or "").strip().lower() == "high")
    medium_count = sum(1 for item in strategy_candidates if str(item.get("reliability") or "").strip().lower() == "medium")
    strategy_candidates_ready = len(strategy_candidates) > 0
    strategy_candidate_payload_missing = bool(artifact_present) and bool(has_materialized_payload) and not strategy_candidates_ready
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
        "strategy_candidate_count": len(strategy_candidates),
        "strategy_candidates_ready": strategy_candidates_ready,
        "strategy_candidate_payload_missing": strategy_candidate_payload_missing,
        "n_symbols_optimized": _to_int(meta.get("n_symbols_optimized"), len(per_symbol)),
        "n_reliable": reliable_count,
        "n_medium": medium_count,
        "global_overlay_source": meta.get("global_overlay_source"),
        "context": search_context,
        "source": str(SEARCH_OPTIMIZED_PARAMS_PATH),
        "strategy_candidates": strategy_candidates,
        "strategy_candidate_source": "strategy_candidates" if strategy_candidates_ready else "missing",
        "candidates": strategy_candidates,
        "candidate_count": len(strategy_candidates),
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


def _self_heal_state(runtime_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state_exists = _QUANT_OPS_STATE_PATH.exists()
    raw_state = _read_json(_QUANT_OPS_STATE_PATH, _default_state()) if state_exists else _default_state()
    state, changed = _normalize_state(raw_state)

    reconstructed_runtime_apply = _reconstructed_runtime_apply_state(runtime_payload)
    if reconstructed_runtime_apply and not isinstance(state.get("runtime_apply"), dict):
        state["runtime_apply"] = reconstructed_runtime_apply
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


def _merge_query_patch(
    query: dict[str, Any],
    patch: dict[str, Any],
    *,
    preserve_keys: set[str] | None = None,
) -> dict[str, Any]:
    merged = copy.deepcopy(query or {})
    protected = {str(key) for key in (preserve_keys or set())}
    for key, value in (patch or {}).items():
        if key not in _OPTIMIZABLE_KEYS:
            continue
        if key in protected:
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




def _current_guardrail_policy() -> dict[str, Any]:
    payload = load_quant_guardrail_policy()
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    return {
        "version": policy.get("version"),
        "thresholds": copy.deepcopy(policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}),
        "saved_at": str(payload.get("saved_at") or ""),
        "source": str(payload.get("source") or ""),
    }
def _candidate_decision(
    metrics: dict[str, Any],
    *,
    min_trades: int,
    search_is_stale: bool,
    search_version_changed: bool,
    policy: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    oos_return = _to_float(metrics.get("oos_return_pct"), 0.0)
    profit_factor = _to_float(metrics.get("profit_factor"), 0.0)
    max_drawdown_pct = _to_float(metrics.get("max_drawdown_pct"), 0.0)
    trade_count = _to_int(metrics.get("trade_count"), 0)
    reliability = str(metrics.get("reliability") or "insufficient")
    positive_window_ratio = _to_float(metrics.get("positive_window_ratio"), 0.0)
    expected_shortfall = _to_float(metrics.get("expected_shortfall_5_pct"), 0.0)
    policy = policy if isinstance(policy, dict) else _current_guardrail_policy()
    thresholds = policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}
    reject_thresholds = thresholds.get("reject") if isinstance(thresholds.get("reject"), dict) else {}
    adopt_thresholds = thresholds.get("adopt") if isinstance(thresholds.get("adopt"), dict) else {}
    limited_thresholds = thresholds.get("limited_adopt") if isinstance(thresholds.get("limited_adopt"), dict) else {}
    blocked_reliability_levels = {
        str(item).strip().lower()
        for item in (reject_thresholds.get("blocked_reliability_levels") if isinstance(reject_thresholds.get("blocked_reliability_levels"), list) else [])
    }
    allowed_reliability_levels = {
        str(item).strip().lower()
        for item in (limited_thresholds.get("allowed_reliability_levels") if isinstance(limited_thresholds.get("allowed_reliability_levels"), list) else [])
    }

    decision_status = "hold"
    decision_label = "보류"
    summary = "재검증은 끝났지만 아직 저장/런타임 반영까지 가기엔 근거가 부족합니다."
    approval_level = "blocked"
    near_miss_metrics: list[str] = []

    hard_reasons: list[str] = []
    if trade_count < max(1, min_trades):
        hard_reasons.append("validation_min_trades_not_met")
    if reliability in blocked_reliability_levels:
        hard_reasons.append("oos_reliability_low")
    if profit_factor < _to_float(reject_thresholds.get("min_profit_factor"), 0.95):
        hard_reasons.append("profit_factor_too_low")
    if oos_return < _to_float(reject_thresholds.get("min_oos_return_pct"), -2.0):
        hard_reasons.append("oos_return_negative")
    if abs(max_drawdown_pct) > _to_float(reject_thresholds.get("max_drawdown_pct"), 30.0):
        hard_reasons.append("max_drawdown_too_large")
    if expected_shortfall < _to_float(reject_thresholds.get("min_expected_shortfall_5_pct"), -20.0):
        hard_reasons.append("tail_risk_too_large")

    if not hard_reasons:
        if (
            oos_return > _to_float(adopt_thresholds.get("min_oos_return_pct"), 0.0)
            and reliability == str(adopt_thresholds.get("required_reliability") or "high")
            and profit_factor >= _to_float(adopt_thresholds.get("min_profit_factor"), 1.08)
            and abs(max_drawdown_pct) <= _to_float(adopt_thresholds.get("max_drawdown_pct"), 22.0)
            and trade_count >= max(1, min_trades)
            and positive_window_ratio >= _to_float(adopt_thresholds.get("min_positive_window_ratio"), 0.5)
            and expected_shortfall >= _to_float(adopt_thresholds.get("min_expected_shortfall_5_pct"), -15.0)
        ):
            decision_status = "adopt"
            decision_label = "채택 후보"
            summary = "OOS·신뢰도·표본·테일리스크 조건을 모두 통과해서 저장 후보로 승격할 수 있습니다."
            approval_level = "full"
        else:
            limited_core_pass = (
                oos_return > _to_float(limited_thresholds.get("min_oos_return_pct"), 0.0)
                and reliability in allowed_reliability_levels
                and trade_count >= max(1, min_trades)
                and profit_factor >= _to_float(limited_thresholds.get("min_profit_factor"), 1.0)
                and abs(max_drawdown_pct) <= _to_float(limited_thresholds.get("max_drawdown_pct"), 25.0)
                and positive_window_ratio >= _to_float(limited_thresholds.get("min_positive_window_ratio"), 0.45)
                and expected_shortfall >= _to_float(limited_thresholds.get("min_expected_shortfall_5_pct"), -16.0)
            )
            threshold_checks = [
                ("profit_factor", profit_factor >= _to_float(adopt_thresholds.get("min_profit_factor"), 1.08)),
                ("max_drawdown_pct", abs(max_drawdown_pct) <= _to_float(adopt_thresholds.get("max_drawdown_pct"), 22.0)),
                ("positive_window_ratio", positive_window_ratio >= _to_float(adopt_thresholds.get("min_positive_window_ratio"), 0.5)),
                ("expected_shortfall_5_pct", expected_shortfall >= _to_float(adopt_thresholds.get("min_expected_shortfall_5_pct"), -15.0)),
            ]
            near_miss_metrics = [metric for metric, passed in threshold_checks if not passed]
            min_near_miss = _to_int(limited_thresholds.get("min_near_miss_count"), 1)
            max_near_miss = _to_int(limited_thresholds.get("max_near_miss_count"), 2)
            medium_quality_override = (
                limited_core_pass
                and len(near_miss_metrics) == 0
                and reliability == "medium"
                and oos_return > 0.0
                and profit_factor >= _to_float(limited_thresholds.get("min_profit_factor"), 1.0)
                and abs(max_drawdown_pct) <= _to_float(limited_thresholds.get("max_drawdown_pct"), 25.0)
                and expected_shortfall >= _to_float(limited_thresholds.get("min_expected_shortfall_5_pct"), -16.0)
            )
            if limited_core_pass and min_near_miss <= len(near_miss_metrics) <= max_near_miss:
                decision_status = "limited_adopt"
                decision_label = "제한 채택 후보"
                summary = "핵심 품질 게이트는 통과했지만 일부 위험 지표가 풀채택 기준에 근접 미달이라 제한 운영으로만 반영할 수 있습니다."
                approval_level = "probationary"
            elif medium_quality_override:
                decision_status = "limited_adopt"
                decision_label = "제한 채택 후보"
                summary = "중간 신뢰도 후보지만 수익·표본·낙폭·테일리스크 조건이 충분히 양호해서 제한 운영 후보로 승격합니다."
                approval_level = "probationary"
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

    can_save = decision_status in {"adopt", "limited_adopt"} and not search_is_stale and not search_version_changed
    can_apply = can_save
    if not can_save and decision_status in {"adopt", "limited_adopt"} and search_is_stale:
        summary = "재검증은 통과했지만 optimizer 결과가 오래돼서 저장을 막습니다. 먼저 후보 탐색을 다시 실행하세요."
    if not can_save and decision_status in {"adopt", "limited_adopt"} and search_version_changed:
        summary = "재검증한 optimizer 버전과 현재 탐색 결과가 달라져서 저장을 막습니다. 다시 재검증해야 합니다."

    return {
        "status": decision_status,
        "label": decision_label,
        "summary": summary,
        "approval_level": approval_level,
        "near_miss_metrics": near_miss_metrics,
        "hard_reasons": hard_reasons,
        "policy_version": policy.get("version"),
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
    policy = _current_guardrail_policy()
    min_trades = _to_int(settings.get("minTrades"), 8)
    search_version_changed = bool(search.get("available")) and bool(search.get("version")) and str(refreshed.get("search_version") or "") != str(search.get("version") or "")
    decision, guardrails = _candidate_decision(
        metrics,
        min_trades=min_trades,
        search_is_stale=bool(search.get("is_stale")),
        search_version_changed=search_version_changed,
        policy=policy,
    )
    refreshed["decision"] = decision
    refreshed["guardrails"] = guardrails
    refreshed["guardrail_policy"] = copy.deepcopy(policy)
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
    policy = _current_guardrail_policy()
    patch = {key: value for key, value in (search.get("global_params") or {}).items() if key in _OPTIMIZABLE_KEYS}
    search_version_changed = False
    decision, guardrails = _candidate_decision(
        metrics,
        min_trades=_to_int(settings.get("minTrades"), 8),
        search_is_stale=bool(search.get("is_stale")),
        search_version_changed=search_version_changed,
        policy=policy,
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
        "guardrail_policy": copy.deepcopy(policy),
        "diagnosis": diagnosis,
        "research": research,
        "validation": validation,
    }


def _history_push(items: list[dict[str, Any]], candidate: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    candidate_id = str(candidate.get("id") or "")
    deduped = [item for item in items if str(item.get("id") or "") != candidate_id]
    return [candidate, *deduped][:limit]


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

    latest_candidate_raw = _refresh_candidate(state.get("latest_candidate"), search)
    latest_candidate_state = _candidate_activity_state(latest_candidate_raw, search, baseline)
    latest_candidate = latest_candidate_raw if latest_candidate_state.get("active") else None

    saved_candidate_raw = _refresh_candidate(state.get("saved_candidate"), search)
    saved_candidate_state = _candidate_activity_state(saved_candidate_raw, search, baseline)
    saved_candidate = saved_candidate_raw if saved_candidate_state.get("active") else None

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
    }

    return {
        "ok": True,
        "guardrail_policy": _current_guardrail_policy(),
        "search_result": search,
        "search_available": bool(search.get("available")),
        "candidate_search": stage_status["candidate_search"],
        "latest_candidate": latest_candidate,
        "latest_candidate_state": latest_candidate_state,
        "saved_candidate": saved_candidate,
        "saved_candidate_state": saved_candidate_state,
        "runtime_apply": runtime_apply,
        "search_handoff": search_handoff,
        "validation_baseline": baseline,
        "stage_status": stage_status,
        "notes": [
            "전략 설정 탐색 결과는 strategy_candidates 목록으로 제공되고, latest_candidate는 선택된 전략 후보를 재검증한 운영 후보입니다.",
            "saved_candidate는 재검증 통과 후 저장된 전략 후보 스냅샷이고, runtime_apply는 저장된 운영 후보만 실제 런타임에 반영한 상태입니다.",
            "strategy_candidates가 비어 있으면 OpenClaw payload가 아직 전략 후보 셋을 보내지 않은 상태로 간주합니다.",
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


def _run_revalidation_diagnostics(service_query: dict[str, list[str]]) -> dict[str, Any]:
    try:
        return run_validation_diagnostics(service_query, mode="light")
    except TypeError:
        return run_validation_diagnostics(service_query)


def _revalidate_optimizer_candidate_impl(
    query: dict[str, Any],
    settings: dict[str, Any],
    *,
    candidate_key: str | None = None,
) -> dict[str, Any]:
    search = _search_summary(load_search_optimized_params())
    if not search.get("available"):
        return {"ok": False, "error": "optimizer_search_missing"}

    raw_query = query if isinstance(query, dict) else {}
    _, resolved_query, resolved_settings = _resolve_validation_context(raw_query, settings)
    explicit_override_keys = {
        str(key) for key in raw_query.keys()
        if str(key) in _OPTIMIZABLE_KEYS
    }
    strategy_candidates = search.get("strategy_candidates") if isinstance(search.get("strategy_candidates"), list) else []
    selected_search_candidate = None
    patch_source = search.get("global_params") or {}
    candidate_key = str(candidate_key or "").strip() or None
    if candidate_key:
        selected_search_candidate = next(
            (
                item for item in strategy_candidates
                if str(item.get("key") or "").strip() == candidate_key
            ),
            None,
        )
        if not isinstance(selected_search_candidate, dict):
            return {"ok": False, "error": "search_candidate_missing"}
        patch_source = selected_search_candidate.get("patch") or {}
    elif not patch_source:
        return {"ok": False, "error": "optimizer_global_params_missing"}

    mutated_query = _merge_query_patch(
        resolved_query,
        patch_source,
        preserve_keys=explicit_override_keys,
    )
    diagnostics = _run_revalidation_diagnostics(
        _build_service_query(mutated_query, resolved_settings),
    )
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
    if isinstance(selected_search_candidate, dict):
        candidate["source"] = "optimizer_search_candidate"
        candidate["search_candidate_key"] = str(selected_search_candidate.get("key") or "")
        candidate["search_candidate_label"] = str(selected_search_candidate.get("label") or "")
        candidate["search_candidate_summary"] = str(selected_search_candidate.get("summary") or "")
        candidate["search_candidate_source"] = str(selected_search_candidate.get("source") or "")
        candidate["patch"] = dict(selected_search_candidate.get("patch") or {})
        candidate["patch_lines"] = list(selected_search_candidate.get("patch_lines") or [])
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
    candidate_key = str(payload.get("candidate_key") or "").strip() or None
    result = _revalidate_optimizer_candidate_impl(query, settings, candidate_key=candidate_key)
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


def _global_runtime_validation_baseline(candidate: dict[str, Any]) -> dict[str, Any]:
    validation = candidate.get("validation") if isinstance(candidate.get("validation"), dict) else {}
    segments = validation.get("segments") if isinstance(validation.get("segments"), dict) else {}
    summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    oos = segments.get("oos") if isinstance(segments.get("oos"), dict) else {}
    reliability_diagnostic = summary.get("reliability_diagnostic") if isinstance(summary.get("reliability_diagnostic"), dict) else {}
    current = reliability_diagnostic.get("current") if isinstance(reliability_diagnostic.get("current"), dict) else {}
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    scorecard = validation.get("scorecard") if isinstance(validation.get("scorecard"), dict) else {}
    decision = candidate.get("decision") if isinstance(candidate.get("decision"), dict) else {}

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
        "approval_level": str(decision.get("approval_level") or "blocked"),
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


def _runtime_restrictions_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    decision = candidate.get("decision") if isinstance(candidate.get("decision"), dict) else {}
    policy = candidate.get("guardrail_policy") if isinstance(candidate.get("guardrail_policy"), dict) else _current_guardrail_policy()
    thresholds = policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}
    runtime_thresholds = thresholds.get("limited_adopt_runtime") if isinstance(thresholds.get("limited_adopt_runtime"), dict) else {}
    if str(decision.get("status") or "") != "limited_adopt":
        return {
            "enabled": False,
            "approval_level": str(decision.get("approval_level") or "full"),
            "reason": "full_adopt",
            "policy_version": policy.get("version"),
        }
    return {
        "enabled": True,
        "approval_level": str(decision.get("approval_level") or "probationary"),
        "reason": "limited_adopt_probationary_runtime",
        "policy_version": policy.get("version"),
        **copy.deepcopy(runtime_thresholds),
    }

def _build_runtime_payload(
    candidate: dict[str, Any],
    search_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    search_payload = search_payload or {}
    meta = search_payload.get("meta") if isinstance(search_payload.get("meta"), dict) else {}
    applied_at = _now_iso()
    runtime_candidate_source_mode = normalize_runtime_candidate_source_mode(candidate.get("runtime_candidate_source_mode"))
    decision = candidate.get("decision") if isinstance(candidate.get("decision"), dict) else {}
    runtime_restrictions = _runtime_restrictions_for_candidate(candidate)
    guardrail_policy = candidate.get("guardrail_policy") if isinstance(candidate.get("guardrail_policy"), dict) else _current_guardrail_policy()
    return {
        "optimized_at": applied_at,
        "applied_at": applied_at,
        "version": f"runtime-{candidate.get('id')}",
        "global_params": dict(candidate.get("patch") or {}),
        "runtime_candidate_source_mode": runtime_candidate_source_mode,
        "runtime_restrictions": runtime_restrictions,
        "validation_baseline": _global_runtime_validation_baseline(candidate),
        "guardrail_policy": copy.deepcopy(guardrail_policy),
        "per_symbol": {},
        "meta": {
            **meta,
            "applied_candidate_id": candidate.get("id"),
            "applied_candidate_saved_at": candidate.get("saved_at"),
            "applied_from": "quant_ops_saved_candidate",
            "search_version": candidate.get("search_version"),
            "search_optimized_at": candidate.get("search_optimized_at"),
            "runtime_candidate_source_mode": runtime_candidate_source_mode,
            "approval_level": str(decision.get("approval_level") or "blocked"),
            "decision_status": str(decision.get("status") or "hold"),
            "global_overlay_source": "validated_candidate",
            "validation_baseline_source": "validated_candidate",
            "runtime_restrictions": runtime_restrictions,
            "guardrail_policy_version": guardrail_policy.get("version"),
            "guardrail_policy_saved_at": guardrail_policy.get("saved_at"),
            "guardrail_policy": copy.deepcopy(guardrail_policy),
            "approved_symbol_count": 0,
            "approved_symbols": [],
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
    runtime_payload = _build_runtime_payload(saved_candidate, search_payload)
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
        "applied_symbol_count": 0,
        "skipped_symbols": {},
    }
    saved_candidate = {
        **saved_candidate,
        "applied_at": runtime_payload.get("applied_at"),
    }
    state["saved_candidate"] = saved_candidate
    state["runtime_apply"] = runtime_apply
    _save_state(state)
    return {
        "ok": True,
        "candidate": saved_candidate,
        "runtime_apply": runtime_apply,
        "engine": engine_state_payload,
        "workflow": get_quant_ops_workflow(),
    }


def reset_quant_ops_workflow_results(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    clear_search = bool(payload.get("clear_search", True))

    state = _default_state()
    _save_state(state)

    if clear_search:
        try:
            SEARCH_OPTIMIZED_PARAMS_PATH.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "ok": True,
        "message": "전략 검증 결과를 초기화했어요. 운영 중인 runtime 반영값은 건드리지 않았습니다.",
        "workflow": get_quant_ops_workflow(),
        "cleared": {
            "quant_ops_state": True,
            "search_result": clear_search,
            "runtime_payload": False,
        },
    }
