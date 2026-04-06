"""Shared reliability policy used across optimization, reporting, and execution gates."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, TypeVar

MIN_TRAIN_TRADES: Final[int] = 20
MIN_RELIABLE_TRAIN_TRADES: Final[int] = 30
MIN_VALIDATION_SIGNALS: Final[int] = 8
MIN_VALIDATION_SHARPE_FILTER: Final[float] = 0.2
MIN_VALIDATION_SHARPE_RELIABLE: Final[float] = 0.35
MAX_DRAWDOWN_FILTER_PCT: Final[float] = -30.0
MAX_DRAWDOWN_RELIABLE_PCT: Final[float] = -25.0

BORDERLINE_REASONS: Final[set[str]] = {
    "borderline_train_trades",
    "borderline_drawdown",
    "borderline_validation_sharpe",
}

SYMBOL_OVERLAY_ALLOWED_LEVELS: Final[set[str]] = {"high"}
GLOBAL_OVERLAY_PRIORITY: Final[tuple[str, str, str]] = (
    "high_only",
    "medium_fallback",
    "all_results_fallback",
)

T = TypeVar("T")


def classify_optimization_reliability(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float,
) -> tuple[bool, str]:
    if trade_count < MIN_TRAIN_TRADES:
        return False, "insufficient_train_trades"
    if validation_signals < MIN_VALIDATION_SIGNALS:
        return False, "insufficient_validation_signals"
    if max_drawdown_pct < MAX_DRAWDOWN_FILTER_PCT:
        return False, "excessive_drawdown"
    if validation_sharpe < MIN_VALIDATION_SHARPE_FILTER:
        return False, "weak_validation_sharpe"
    if trade_count < MIN_RELIABLE_TRAIN_TRADES:
        return False, "borderline_train_trades"
    if max_drawdown_pct < MAX_DRAWDOWN_RELIABLE_PCT:
        return False, "borderline_drawdown"
    if validation_sharpe < MIN_VALIDATION_SHARPE_RELIABLE:
        return False, "borderline_validation_sharpe"
    return True, "passed"


def should_keep_optimization_result(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float,
) -> bool:
    is_reliable, reason = classify_optimization_reliability(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=max_drawdown_pct,
    )
    return is_reliable or reason in BORDERLINE_REASONS


def reliability_level_from_validation(
    *,
    validation_trades: int,
    validation_sharpe: float,
) -> str:
    if validation_trades < MIN_VALIDATION_SIGNALS:
        return "insufficient"
    if validation_sharpe < MIN_VALIDATION_SHARPE_FILTER:
        return "low"
    if validation_sharpe >= MIN_VALIDATION_SHARPE_RELIABLE:
        return "high"
    return "medium"


def reliability_level_from_optimization(
    *,
    is_reliable: bool,
    reliability_reason: str,
    validation_trades: int,
    validation_sharpe: float,
) -> str:
    if is_reliable:
        return "high"
    if reliability_reason in BORDERLINE_REASONS:
        return "medium"
    if reliability_reason in {"excessive_drawdown", "weak_validation_sharpe"}:
        return "low"
    if reliability_reason in {"insufficient_train_trades", "insufficient_validation_signals"}:
        return "insufficient"
    return reliability_level_from_validation(
        validation_trades=validation_trades,
        validation_sharpe=validation_sharpe,
    )


def should_apply_symbol_overlay(*, is_reliable: bool, reliability_reason: str) -> bool:
    if is_reliable:
        return True
    _ = reliability_reason
    return False


def select_global_overlay_candidates(
    results: Sequence[T],
    *,
    is_reliable_getter: Callable[[T], bool],
    reliability_reason_getter: Callable[[T], str],
) -> tuple[list[T], str]:
    high = [item for item in results if is_reliable_getter(item)]
    if high:
        return high, "high_only"

    medium = [
        item
        for item in results
        if reliability_reason_getter(item) in BORDERLINE_REASONS
    ]
    if medium:
        return medium, "medium_fallback"

    return list(results), "all_results_fallback"


def overlay_policy_metadata() -> dict[str, object]:
    return {
        "symbol_overlay_allowed_levels": sorted(SYMBOL_OVERLAY_ALLOWED_LEVELS),
        "medium_policy": "passes_minimum_gate_but_symbol_overlay_disabled",
        "global_overlay_priority": list(GLOBAL_OVERLAY_PRIORITY),
    }
