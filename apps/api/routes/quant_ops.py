from __future__ import annotations

from services.quant_guardrail_policy_store import (
    load_quant_guardrail_policy,
    reset_quant_guardrail_policy,
    save_quant_guardrail_policy,
)
from services.quant_ops_service import (
    apply_saved_candidate_to_runtime,
    get_quant_ops_workflow,
    reset_quant_ops_workflow_results,
    revalidate_optimizer_candidate,
    save_validated_candidate,
)


def handle_get_quant_ops_workflow() -> tuple[int, dict]:
    try:
        return 200, get_quant_ops_workflow()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_revalidate(payload: dict) -> tuple[int, dict]:
    try:
        result = revalidate_optimizer_candidate(payload)
        return (200 if result.get("ok") else 400), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_save_candidate(payload: dict) -> tuple[int, dict]:
    try:
        result = save_validated_candidate(payload)
        return (200 if result.get("ok") else 409), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_apply_runtime(payload: dict) -> tuple[int, dict]:
    try:
        result = apply_saved_candidate_to_runtime(payload)
        return (200 if result.get("ok") else 409), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_reset_workflow(payload: dict) -> tuple[int, dict]:
    try:
        result = reset_quant_ops_workflow_results(payload)
        return (200 if result.get("ok") else 409), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_get_quant_ops_policy() -> tuple[int, dict]:
    try:
        return 200, load_quant_guardrail_policy()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_save_policy(payload: dict) -> tuple[int, dict]:
    try:
        return 200, save_quant_guardrail_policy(payload)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_reset_policy() -> tuple[int, dict]:
    try:
        return 200, reset_quant_guardrail_policy()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
