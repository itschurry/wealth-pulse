"""Compatibility wrapper for the dynamic trading pipeline."""

from __future__ import annotations

from typing import Any

from services.trading_pipeline.decision import build_signal_book, context_snapshot, select_entry_candidates

DEFAULT_SIGNAL_MARKETS = ("KOSPI",)


def _context_snapshot() -> tuple[str, str]:
    return context_snapshot()


def determine_strategy_type(candidate: dict[str, Any]) -> str:
    return str(candidate.get("strategy_type") or "dynamic_market_scanner")


def allocator_weight(*, candidate: dict[str, Any], cfg: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    return {"enabled": True, "weight": 1.0}
