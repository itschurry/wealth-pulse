"""Runtime operation modes for the auto-invest platform."""

from __future__ import annotations

from dataclasses import dataclass

REPORT = "report"
PAPER = "paper"
LIVE_DISABLED = "live_disabled"
LIVE_READY = "live_ready"

SUPPORTED_MODES = (REPORT, PAPER, LIVE_DISABLED, LIVE_READY)


@dataclass(frozen=True)
class ModeStatus:
    current: str
    supported: tuple[str, ...] = SUPPORTED_MODES


def normalize_mode(value: str | None, default: str = PAPER) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in SUPPORTED_MODES:
        return candidate
    return default
