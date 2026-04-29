from __future__ import annotations

from services.agent_config import broker_status


def handle_kis_status() -> tuple[int, dict]:
    return 200, broker_status()
