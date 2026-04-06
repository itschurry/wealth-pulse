"""Daily entrypoint that orchestrates the explainability report service."""

from __future__ import annotations

from services.report_service import run_report_pipeline


async def run_daily_report() -> None:
    """Keep backward-compatible entrypoint used by scheduler and tests."""
    await run_report_pipeline()
