"""공식 캘린더 기반 핵심 경제 이벤트 수집기."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

from collectors.models import EconomicCalendarEvent

_BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
_UTC = timezone.utc

_INTERESTING_EVENTS = {
    "consumer price index": ("inflation", "높음"),
    "producer price index": ("inflation", "높음"),
    "employment situation": ("labor", "높음"),
    "job openings": ("labor", "중간"),
    "import and export prices": ("inflation", "중간"),
    "productivity and costs": ("growth", "중간"),
    "consumer expenditures": ("consumption", "중간"),
}


def _unfold_ics_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if not raw:
            continue
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_ics_datetime(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=_UTC)
        if "T" in raw:
            return datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=_UTC)
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=_UTC)
    except ValueError:
        return None


def _event_meta(summary: str) -> tuple[str, str] | None:
    lowered = summary.lower()
    for keyword, meta in _INTERESTING_EVENTS.items():
        if keyword in lowered:
            return meta
    return None


def collect_calendar_events(window_days: int = 7, limit: int = 10) -> list[EconomicCalendarEvent]:
    """BLS 공식 캘린더에서 핵심 이벤트를 수집한다."""
    now = datetime.now(_UTC)
    start = now - timedelta(hours=12)
    end = now + timedelta(days=window_days)

    try:
        response = requests.get(
            _BLS_ICS_URL,
            timeout=12,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DailyMarketBrief/1.0)"},
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning(f"경제 일정 수집 실패 [BLS ICS]: {exc}")
        return []

    events: list[EconomicCalendarEvent] = []
    block: dict[str, str] = {}
    inside_event = False
    for line in _unfold_ics_lines(response.text):
        if line == "BEGIN:VEVENT":
            block = {}
            inside_event = True
            continue
        if line == "END:VEVENT":
            inside_event = False
            summary = block.get("SUMMARY", "").strip()
            meta = _event_meta(summary)
            if not meta:
                continue
            category, importance = meta
            scheduled_at = _parse_ics_datetime(block.get("DTSTART", ""))
            if scheduled_at is None or scheduled_at < start or scheduled_at > end:
                continue
            events.append(
                EconomicCalendarEvent(
                    name=summary,
                    country="US",
                    scheduled_at=scheduled_at,
                    source="BLS ICS",
                    category=category,
                    importance=importance,
                    url=block.get("URL", _BLS_ICS_URL),
                    summary=block.get("DESCRIPTION", "").strip()[:240],
                )
            )
            continue
        if not inside_event or ":" not in line:
            continue
        key, value = line.split(":", 1)
        block[key.split(";", 1)[0]] = value.strip()

    events.sort(key=lambda item: item.scheduled_at)
    return events[:limit]
