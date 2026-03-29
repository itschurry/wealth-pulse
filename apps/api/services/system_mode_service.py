"""System mode exposure for API/UI."""

from __future__ import annotations

import os

from app.modes import LIVE_DISABLED, SUPPORTED_MODES, normalize_mode


def get_mode_status() -> dict:
    configured = os.getenv("AUTO_INVEST_MODE", LIVE_DISABLED)
    current = normalize_mode(configured, default=LIVE_DISABLED)
    return {
        "ok": True,
        "current_mode": current,
        "supported_modes": list(SUPPORTED_MODES),
    }
