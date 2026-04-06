"""Job wrappers used by scheduler.

Scheduler keeps timing policy only and delegates business execution to jobs/services.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from loguru import logger

from main import run_daily_report


def run_report_job() -> None:
    try:
        asyncio.run(run_daily_report())
    except Exception:
        logger.exception("report job failed")
        raise


def run_optimization_job() -> None:
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "run_monte_carlo_optimizer.py")
    logger.info("몬테카를로 최적화 시작: {}", script)
    result = subprocess.run(
        [sys.executable, script],
        timeout=3600,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("몬테카를로 최적화 완료")
        return
    logger.error("몬테카를로 최적화 실패 (rc={}): {}", result.returncode, result.stderr[-2000:])
    raise RuntimeError(f"optimization failed: rc={result.returncode}")
