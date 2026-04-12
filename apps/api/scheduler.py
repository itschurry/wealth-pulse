from __future__ import annotations

from datetime import datetime, timezone

from config.market_calendar import is_market_half_hour_slot


def _run() -> None:
    """Placeholder scheduler hook. Production wiring can replace this."""
    return None



def _off_session_job() -> None:
    now_utc = datetime.now(timezone.utc)
    if is_market_half_hour_slot("KR", now_utc):
        return
    _run()
