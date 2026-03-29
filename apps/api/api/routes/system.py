from __future__ import annotations

from services.system_mode_service import get_mode_status


def handle_system_mode() -> tuple[int, dict]:
    try:
        return 200, get_mode_status()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
