from __future__ import annotations

from services.backtest_params_store import (
    load_persisted_validation_settings,
    reset_persisted_validation_settings,
    save_persisted_validation_settings,
)
from services.validation_service import (
    run_backtest_with_extended_metrics,
    run_validation_diagnostics,
    run_walk_forward_validation,
)


def _to_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if value in {"0", "false", "f", "no", "n", "off", ""}:
            return False
        return default
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return bool(raw)
    return default


def handle_validation_backtest(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        return 200, run_backtest_with_extended_metrics(query)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_validation_walk_forward(query: dict[str, list[str]]) -> tuple[int, dict]:
    refresh = _to_bool((query.get("refresh", ["0"])[0] or "0"), False)
    cache_only = _to_bool((query.get("cache_only", ["0"])[0] or "0"), False)
    try:
        return 200, run_walk_forward_validation(query, refresh=refresh, cache_only=cache_only)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_validation_diagnostics(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        return 200, run_validation_diagnostics(query)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_validation_settings_get() -> tuple[int, dict]:
    try:
        return 200, load_persisted_validation_settings()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_validation_settings_save(payload: dict) -> tuple[int, dict]:
    try:
        return 200, save_persisted_validation_settings(payload)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_validation_settings_reset() -> tuple[int, dict]:
    try:
        return 200, reset_persisted_validation_settings()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
