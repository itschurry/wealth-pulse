from __future__ import annotations

from services.quant_ops_service import (
    apply_saved_candidate_to_runtime,
    get_quant_ops_workflow,
    revalidate_optimizer_candidate,
    revalidate_symbol_candidate,
    save_symbol_candidate,
    save_validated_candidate,
    set_symbol_candidate_approval,
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


def handle_quant_ops_revalidate_symbol(payload: dict) -> tuple[int, dict]:
    try:
        result = revalidate_symbol_candidate(payload)
        return (200 if result.get("ok") else 400), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_set_symbol_approval(payload: dict) -> tuple[int, dict]:
    try:
        result = set_symbol_candidate_approval(payload)
        return (200 if result.get("ok") else 409), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_quant_ops_save_symbol_candidate(payload: dict) -> tuple[int, dict]:
    try:
        result = save_symbol_candidate(payload)
        return (200 if result.get("ok") else 409), result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
