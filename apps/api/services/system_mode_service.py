"""System mode exposure for API/UI."""

from __future__ import annotations

import os

from modes import LIVE_DISABLED, LIVE_READY, PAPER, REPORT, SUPPORTED_MODES


def _mode_from_execution_env() -> str:
    execution_mode = str(os.getenv("EXECUTION_MODE", "") or "").strip().lower()
    if execution_mode == "live":
        return LIVE_READY
    if execution_mode == REPORT:
        return REPORT
    if execution_mode == PAPER:
        return PAPER
    return LIVE_DISABLED


def get_mode_status() -> dict:
    current = _mode_from_execution_env()
    return {
        "ok": True,
        "current_mode": current,
        "supported_modes": list(SUPPORTED_MODES),
    }
