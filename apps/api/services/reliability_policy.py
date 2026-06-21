"""Shared reliability policy used across validation, reporting, and execution gates."""

from __future__ import annotations

from typing import Final

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

def classify_validation_reliability(
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


def should_keep_validation_result(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float,
) -> bool:
    is_reliable, reason = classify_validation_reliability(
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


def reliability_level_from_signal(
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
