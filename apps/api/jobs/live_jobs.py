"""Live-operation jobs.

These jobs are intentionally isolated from research jobs. They only read the
strategy registry, universe snapshots, runtime account state, and scanner data.
"""

from __future__ import annotations

from loguru import logger

from services.execution_service import get_execution_service
from services.live_signal_engine import scan_live_strategies
from services.universe_builder import get_universe_snapshot
from services.strategy_registry import list_strategies
from market_utils import normalize_market


def run_premarket_universe_job() -> None:
    for strategy in list_strategies():
        get_universe_snapshot(
            str(strategy.get("universe_rule") or "kospi"),
            market=normalize_market(str(strategy.get("market") or "")) or None,
            refresh=True,
        )
    logger.info("premarket_universe_job completed")


def run_intraday_signal_scan_job() -> None:
    _, payload = get_execution_service().paper_engine_status()
    account = payload.get("account") if isinstance(payload, dict) else {}
    scan_live_strategies(account=account if isinstance(account, dict) else {}, refresh=True)
    logger.info("intraday_signal_scan_job completed")


def run_eod_performance_job() -> None:
    logger.info("eod_performance_job completed (performance summary placeholder)")
