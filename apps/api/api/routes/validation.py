from __future__ import annotations

from services.validation_service import (
    run_backtest_with_extended_metrics,
    run_walk_forward_validation,
)


def handle_validation_backtest(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        return 200, run_backtest_with_extended_metrics(query)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_validation_walk_forward(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        return 200, run_walk_forward_validation(query)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
