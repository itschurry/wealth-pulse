from __future__ import annotations

import datetime
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, settings


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _format_number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:,.{digits}f}"


def _format_signed_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:+.2f}%"


def _format_signed_number(value: Any, digits: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:+,.{digits}f}"


def _format_currency_krw(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{int(round(number)):,}원"


def _format_market_line(market: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    kospi = market.get("kospi")
    kospi_pct = market.get("kospi_pct")
    kosdaq = market.get("kosdaq")
    kosdaq_pct = market.get("kosdaq_pct")
    usd_krw = market.get("usd_krw")
    wti = market.get("wti")
    wti_pct = market.get("wti_pct")
    if kospi is not None or kospi_pct is not None:
        lines.append(f"- 코스피: {_format_number(kospi)} ({_format_signed_percent(kospi_pct)})")
    if kosdaq is not None or kosdaq_pct is not None:
        lines.append(f"- 코스닥: {_format_number(kosdaq)} ({_format_signed_percent(kosdaq_pct)})")
    if usd_krw is not None:
        lines.append(f"- 원/달러: {_format_number(usd_krw)}")
    if wti is not None or wti_pct is not None:
        lines.append(f"- WTI: {_format_number(wti)} ({_format_signed_percent(wti_pct)})")
    return lines


def _candidate_title(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    code = str(item.get("code") or "").strip().upper()
    market = str(item.get("market") or "").strip().upper()
    base = name or code or "미상"
    if code and name and code != name:
        base = f"{name}({code})"
    elif code and not name:
        base = code
    if market:
        return f"{base} [{market}]"
    return base


def _candidate_reason(item: dict[str, Any]) -> str:
    for key in ("brief_reason", "reason", "recommendation_reason", "summary"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    reasons = item.get("reasons")
    if isinstance(reasons, list):
        for value in reasons:
            text = str(value or "").strip()
            if text:
                return text
    tags = item.get("reason_codes")
    if isinstance(tags, list):
        compact = [str(tag).strip() for tag in tags if str(tag).strip()]
        if compact:
            return ", ".join(compact[:2])
    return "근거 수집 중"


def _format_candidate_section(title: str, items: list[dict[str, Any]]) -> list[str]:
    lines = [title]
    if not items:
        lines.append("- 없음")
        return lines
    for item in items[:3]:
        lines.append(f"- {_candidate_title(item)}: {_candidate_reason(item)}")
    return lines


class TelegramNotifier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_error = ""
        self._last_sent_at = ""

    @property
    def enabled(self) -> bool:
        return _as_bool(getattr(settings, "telegram_enabled", False), False)

    @property
    def configured(self) -> bool:
        return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

    def _telegram_url(self) -> str:
        token = str(TELEGRAM_BOT_TOKEN or "").strip()
        return f"https://api.telegram.org/bot{token}/sendMessage"

    def send_message(self, message: str) -> bool:
        text = str(message or "").strip()
        if not text:
            return False
        if not self.enabled:
            return False
        if not self.configured:
            with self._lock:
                self._last_error = "telegram_not_configured"
            return False
        payload = urllib.parse.urlencode({
            "chat_id": str(TELEGRAM_CHAT_ID),
            "text": text,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        request = urllib.request.Request(
            self._telegram_url(),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            ok = bool(parsed.get("ok")) if isinstance(parsed, dict) else False
            with self._lock:
                if ok:
                    self._last_sent_at = _now_iso()
                    self._last_error = ""
                else:
                    self._last_error = "telegram_send_failed"
            return ok
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            with self._lock:
                self._last_error = str(exc)
            return False

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "channel": "telegram",
                "enabled": self.enabled,
                "configured": self.configured,
                "chat_id_configured": bool(TELEGRAM_CHAT_ID),
                "last_sent_at": self._last_sent_at,
                "last_error": self._last_error,
                "updated_at": _now_iso(),
            }

    def notify_engine_started(self, payload: dict[str, Any]) -> None:
        markets = payload.get("markets") or []
        interval = payload.get("interval_seconds")
        message = (
            "[WealthPulse] 자동매매 시작\n"
            f"시각: {_now_iso()}\n"
            f"주기: {interval}초\n"
            f"대상시장: {', '.join(markets) if isinstance(markets, list) and markets else '-'}"
        )
        self.send_message(message)

    def notify_engine_stopped(self, payload: dict[str, Any]) -> None:
        message = (
            "[WealthPulse] 자동매매 중지\n"
            f"시각: {_now_iso()}\n"
            f"사유: {payload.get('reason') or 'manual_stop'}"
        )
        self.send_message(message)

    def notify_engine_paused(self) -> None:
        self.send_message(f"[WealthPulse] 자동매매 일시정지\n시각: {_now_iso()}")

    def notify_engine_resumed(self) -> None:
        self.send_message(f"[WealthPulse] 자동매매 재개\n시각: {_now_iso()}")

    def notify_engine_error(self, *, error: str, cycle_id: str) -> None:
        message = (
            "[WealthPulse] 자동매매 엔진 오류\n"
            f"시각: {_now_iso()}\n"
            f"오류: {error}\n"
            f"cycle: {cycle_id or '-'}"
        )
        self.send_message(message)

    def notify_order_failure(self, payload: dict[str, Any]) -> None:
        message = (
            "[WealthPulse] 주문 실패\n"
            f"종목: {payload.get('code') or '-'} ({payload.get('market') or '-'})\n"
            f"유형: {payload.get('side') or '-'}\n"
            f"사유: {payload.get('failure_reason') or '-'}\n"
            f"cycle: {payload.get('originating_cycle_id') or '-'}"
        )
        self.send_message(message)

    def notify_daily_loss_limit(self, payload: dict[str, Any]) -> None:
        message = (
            "[WealthPulse] 일일 손실 한도 도달\n"
            f"시각: {_now_iso()}\n"
            f"잔여 손실 여력: {payload.get('daily_loss_left')}\n"
            f"사유: {payload.get('reason') or 'daily_loss_limit_reached'}"
        )
        self.send_message(message)

    def notify_order_filled(self, event: dict[str, Any], cycle_id: str = "") -> None:
        side = "매수" if str(event.get("side")).lower() == "buy" else "매도"
        lines = [
            "[WealthPulse] 거래 발생",
            f"- 시간: {event.get('ts') or _now_iso()}",
            f"- 유형: {side}",
            f"- 종목: {event.get('name') or event.get('code') or '-'} ({event.get('market') or '-'})",
            f"- 수량: {event.get('quantity') or 0}",
            f"- 가격: {_format_number(event.get('filled_price_local'), 4)}",
        ]
        if event.get("notional_krw") is not None:
            lines.append(f"- 금액: {_format_currency_krw(event.get('notional_krw'))}")
        quote_source = str(event.get("quote_source") or "").strip()
        if quote_source:
            lines.append(f"- 메모: {quote_source} 기준 체결")
        if cycle_id:
            lines.append(f"- cycle: {cycle_id}")
        self.send_message("\n".join(lines))

    def notify_market_open_brief(self, payload: dict[str, Any]) -> None:
        market_name = str(payload.get("market_name") or "오늘 장")
        market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), dict) else {}
        summary_line = str(payload.get("summary_line") or "").strip()
        strategy_line = str(payload.get("strategy_line") or "").strip()
        risk_line = str(payload.get("risk_line") or "").strip()
        generated_at = str(payload.get("generated_at") or _now_iso())

        lines = [
            f"[{market_name} 브리프]",
            f"- 시간: {generated_at}",
            f"- 오늘 장 한줄: {summary_line or '시장 요약 수집 중'}",
            f"- 전략 판단: {strategy_line or '현재 전략 기준으로 후보를 선별 중'}",
        ]
        market_lines = _format_market_line(market)
        if market_lines:
            lines.append("")
            lines.append("[시장 체크]")
            lines.extend(market_lines)
        if risk_line:
            lines.append(f"- 주의: {risk_line}")
        context_risks = context.get("risks") if isinstance(context.get("risks"), list) else []
        if context_risks and not risk_line:
            first_risk = str(context_risks[0] or "").strip()
            if first_risk:
                lines.append(f"- 주의: {first_risk}")

        lines.append("")
        lines.extend(_format_candidate_section("[매수 후보]", candidates.get("buy") if isinstance(candidates.get("buy"), list) else []))
        lines.append("")
        lines.extend(_format_candidate_section("[매도 후보]", candidates.get("sell") if isinstance(candidates.get("sell"), list) else []))
        lines.append("")
        lines.extend(_format_candidate_section("[보류 후보]", candidates.get("hold") if isinstance(candidates.get("hold"), list) else []))
        lines.append("")
        lines.extend(_format_candidate_section("[차단 후보]", candidates.get("blocked") if isinstance(candidates.get("blocked"), list) else []))

        memo = str(payload.get("memo") or "").strip()
        if memo:
            lines.append("")
            lines.append("[누나 한줄]")
            lines.append(f"- {memo}")
        self.send_message("\n".join(lines))


class NullNotificationService:
    """설정이 꺼져 있거나 토큰이 없을 때 호출부를 깨지 않게 유지하는 no-op notifier."""

    def status(self) -> dict[str, Any]:
        return {
            "channel": "disabled",
            "enabled": False,
            "configured": False,
            "last_sent_at": "",
            "last_error": "notifications_disabled",
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

    def notify_market_open_brief(self, payload: dict[str, Any]) -> None:
        return None


_notification_service: TelegramNotifier | NullNotificationService | None = None


def get_notification_service() -> TelegramNotifier | NullNotificationService:
    global _notification_service
    if _notification_service is None:
        enabled = _as_bool(getattr(settings, "telegram_enabled", False), False)
        configured = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        _notification_service = TelegramNotifier() if enabled and configured else NullNotificationService()
    return _notification_service
