from __future__ import annotations

from analyzer.kospi_backtest import BacktestConfig
from services.backtest_service import get_backtest_service


def _parse_backtest_config(query: dict[str, list[str]]) -> BacktestConfig:
    """Backward-compatible symbol used by existing tests."""
    return get_backtest_service().parse_config(query)


def handle_backtest_run(query: dict) -> tuple[int, dict]:
    try:
        payload = get_backtest_service().run_with_optional_optimization(query, auto_optimize=False)
        return 200, payload
    except Exception as e:
        return 500, {"error": str(e)}


def handle_kospi_backtest() -> tuple[int, dict]:
    try:
        return 200, get_backtest_service().get_latest_kospi()
    except Exception as e:
        return 500, {"error": str(e)}
