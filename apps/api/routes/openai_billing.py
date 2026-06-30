from __future__ import annotations

from services.openai_billing_service import get_openai_billing_summary


def handle_openai_billing() -> tuple[int, dict]:
    try:
        return 200, get_openai_billing_summary()
    except Exception as exc:
        return 502, {"ok": False, "error": str(exc)}
