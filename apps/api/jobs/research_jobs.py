"""Research-layer batch jobs.

These jobs are intentionally separated from live operation jobs so that
backtest/optimization/approval work never sits on the intraday execution path.
"""

from __future__ import annotations

from loguru import logger

from jobs.runtime_jobs import run_optimization_job


def run_nightly_backtest_job() -> None:
    logger.info("nightly_backtest_job started")
    logger.info("nightly_backtest_job completed (placeholder)")


def run_strategy_approval_job() -> None:
    logger.info("strategy_approval_job started")
    logger.info("strategy_approval_job completed (registry-driven placeholder)")


def run_optimizer_batch_job() -> None:
    run_optimization_job()
