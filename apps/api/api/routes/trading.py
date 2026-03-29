"""Thin API route handlers delegating to execution service."""

from __future__ import annotations

from services.execution_service import _default_auto_trader_config, get_execution_service


def handle_paper_account(refresh_quotes: bool) -> tuple[int, dict]:
    return get_execution_service().paper_account(refresh_quotes)


def handle_paper_order(payload: dict) -> tuple[int, dict]:
    return get_execution_service().paper_order(payload)


def handle_paper_reset(payload: dict) -> tuple[int, dict]:
    return get_execution_service().paper_reset(payload)


def handle_paper_auto_invest(payload: dict) -> tuple[int, dict]:
    return get_execution_service().paper_auto_invest(payload)


def handle_paper_engine_start(payload: dict) -> tuple[int, dict]:
    return get_execution_service().paper_engine_start(payload)


def handle_paper_engine_stop() -> tuple[int, dict]:
    return get_execution_service().paper_engine_stop()


def handle_paper_engine_status() -> tuple[int, dict]:
    return get_execution_service().paper_engine_status()
