from __future__ import annotations

from services.agent_config import default_risk_config_store


def handle_risk_config_get() -> tuple[int, dict]:
    return 200, {"ok": True, "config": default_risk_config_store().load()}


def handle_risk_config_save(payload: dict) -> tuple[int, dict]:
    payload = payload if isinstance(payload, dict) else {}
    config = default_risk_config_store().save(payload)
    return 200, {"ok": True, "config": config}
