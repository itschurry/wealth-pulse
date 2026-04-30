from __future__ import annotations

from services.execution_service import (
    handle_runtime_account,
    handle_runtime_account_history,
    handle_runtime_auto_invest,
    handle_runtime_engine_cycles,
    handle_runtime_engine_pause,
    handle_runtime_engine_resume,
    handle_runtime_engine_start,
    handle_runtime_engine_status,
    handle_runtime_engine_stop,
    handle_runtime_history_clear,
    handle_runtime_order,
    handle_runtime_order_events,
    handle_runtime_reset,
    handle_runtime_workflow,
    handle_signal_snapshots,
    hydrate_runtime_state,
)


class RuntimeExecutionService:
    def runtime_account(self, refresh_quotes: bool) -> tuple[int, dict]:
        return handle_runtime_account(refresh_quotes)

    def runtime_order(self, payload: dict) -> tuple[int, dict]:
        return handle_runtime_order(payload)

    def runtime_reset(self, payload: dict) -> tuple[int, dict]:
        return handle_runtime_reset(payload)

    def runtime_auto_invest(self, payload: dict) -> tuple[int, dict]:
        return handle_runtime_auto_invest(payload)

    def runtime_engine_start(self, payload: dict) -> tuple[int, dict]:
        return handle_runtime_engine_start(payload)

    def runtime_engine_stop(self) -> tuple[int, dict]:
        return handle_runtime_engine_stop()

    def runtime_engine_pause(self) -> tuple[int, dict]:
        return handle_runtime_engine_pause()

    def runtime_engine_resume(self) -> tuple[int, dict]:
        return handle_runtime_engine_resume()

    def runtime_engine_status(self) -> tuple[int, dict]:
        return handle_runtime_engine_status()

    def runtime_engine_cycles(self, limit: int = 50) -> tuple[int, dict]:
        return handle_runtime_engine_cycles(limit)

    def runtime_orders(self, limit: int = 100) -> tuple[int, dict]:
        return handle_runtime_order_events(limit)

    def runtime_account_history(self, limit: int = 100) -> tuple[int, dict]:
        return handle_runtime_account_history(limit)

    def runtime_history_clear(self, payload: dict) -> tuple[int, dict]:
        return handle_runtime_history_clear(payload)

    def signal_snapshots(self, limit: int = 200) -> tuple[int, dict]:
        return handle_signal_snapshots(limit)

    def runtime_workflow(self, limit: int = 120) -> tuple[int, dict]:
        return handle_runtime_workflow(limit)


_runtime_execution_service: RuntimeExecutionService | None = None


def get_execution_service() -> RuntimeExecutionService:
    global _runtime_execution_service
    if _runtime_execution_service is None:
        _runtime_execution_service = RuntimeExecutionService()
    hydrate_runtime_state()
    return _runtime_execution_service
