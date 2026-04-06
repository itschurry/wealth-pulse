from __future__ import annotations

import datetime
from typing import Any


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


class NullNotificationService:
    """앱 내부 채널 발송을 제거한 뒤에도 호출부를 깨지 않게 유지하는 no-op notifier."""

    def status(self) -> dict[str, Any]:
        return {
            "channel": "disabled",
            "enabled": False,
            "configured": False,
            "last_sent_at": "",
            "last_error": "notifications_removed",
            "updated_at": _now_iso(),
        }

    def send_message(self, message: str) -> bool:
        return False

    def notify_engine_started(self, payload: dict[str, Any]) -> None:
        return None

    def notify_engine_stopped(self, payload: dict[str, Any]) -> None:
        return None

    def notify_engine_paused(self) -> None:
        return None

    def notify_engine_resumed(self) -> None:
        return None

    def notify_engine_error(self, *, error: str, cycle_id: str) -> None:
        return None

    def notify_order_failure(self, payload: dict[str, Any]) -> None:
        return None

    def notify_daily_loss_limit(self, payload: dict[str, Any]) -> None:
        return None

    def notify_order_filled(self, event: dict[str, Any], cycle_id: str = "") -> None:
        return None


_notification_service: NullNotificationService | None = None


def get_notification_service() -> NullNotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NullNotificationService()
    return _notification_service
