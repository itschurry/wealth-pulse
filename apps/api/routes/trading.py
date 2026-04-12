"""Thin API route handlers delegating to execution service."""

from __future__ import annotations

from services.execution_service import _default_auto_trader_config, get_execution_service


def _parse_limit(query: dict[str, list[str]], default: int, minimum: int = 1, maximum: int = 500) -> int:
    raw = (query.get("limit", [str(default)])[0] or str(default)).strip()
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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


def handle_paper_engine_pause() -> tuple[int, dict]:
    return get_execution_service().paper_engine_pause()


def handle_paper_engine_resume() -> tuple[int, dict]:
    return get_execution_service().paper_engine_resume()


def handle_paper_engine_status() -> tuple[int, dict]:
    status, payload = get_execution_service().paper_engine_status()
    if not isinstance(payload, dict):
        return status, payload

    _, account_payload = get_execution_service().paper_account(False)
    if isinstance(account_payload, dict):
        payload["account"] = account_payload
    return status, payload


def handle_paper_engine_cycles(query: dict[str, list[str]]) -> tuple[int, dict]:
    limit = _parse_limit(query, default=50, maximum=300)
    return get_execution_service().paper_engine_cycles(limit)


def handle_paper_orders(query: dict[str, list[str]]) -> tuple[int, dict]:
    limit = _parse_limit(query, default=100, maximum=500)
    return get_execution_service().paper_orders(limit)


def handle_paper_account_history(query: dict[str, list[str]]) -> tuple[int, dict]:
    limit = _parse_limit(query, default=100, maximum=500)
    return get_execution_service().paper_account_history(limit)


def handle_paper_history_clear(payload: dict) -> tuple[int, dict]:
    return get_execution_service().paper_history_clear(payload)


def handle_paper_workflow(query: dict[str, list[str]]) -> tuple[int, dict]:
    limit = _parse_limit(query, default=120, maximum=500)
    return get_execution_service().paper_workflow(limit)
