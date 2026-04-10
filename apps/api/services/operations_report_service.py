from __future__ import annotations

import datetime
from typing import Any

from services.execution_lifecycle import (
    LIFECYCLE_FAILED,
    LIFECYCLE_FILLED,
    summarize_execution_events,
)
from services.paper_runtime_store import read_execution_events, read_signal_snapshots


def _today_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _is_today(value: Any) -> bool:
    return str(value or "")[:10] == _today_str()


def _is_stale_reason(reason: str) -> bool:
    value = str(reason or "").strip().lower()
    return value in {"stale", "quote_stale", "stale_quote", "stale_signal_data"}



def _collect_warning_alerts(signal_snapshots: list[dict[str, Any]], execution_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    stale_count = 0
    data_missing_count = 0
    for item in signal_snapshots:
        reasons = [str(reason or "") for reason in item.get("reason_codes", []) if reason]
        risk_reason = str(item.get("risk_reason_code") or "")
        if any(_is_stale_reason(reason) for reason in reasons) or _is_stale_reason(risk_reason):
            stale_count += 1
        if "data_missing" in reasons or risk_reason == "data_missing":
            data_missing_count += 1
    if stale_count:
        alerts.append({
            "severity": "warning",
            "alert_code": "stale_signal_data",
            "message": f"stale 신호 {stale_count}건이 재검토 필요 상태입니다.",
            "details": {"count": stale_count},
        })
    if data_missing_count:
        alerts.append({
            "severity": "warning",
            "alert_code": "data_missing",
            "message": f"data_missing 신호 {data_missing_count}건이 판단 불가 상태입니다.",
            "details": {"count": data_missing_count},
        })
    failed_today = [
        item for item in execution_events
        if _is_today(item.get("timestamp")) and str(item.get("event_type") or "") == LIFECYCLE_FAILED
    ]
    if failed_today:
        alerts.append({
            "severity": "critical" if len(failed_today) >= 3 else "warning",
            "alert_code": "execution_failed",
            "message": f"오늘 실패 주문이 {len(failed_today)}건 발생했습니다.",
            "details": {"count": len(failed_today)},
        })
    if not alerts:
        alerts.append({
            "severity": "info",
            "alert_code": "operations_normal",
            "message": "현재 운영 리포트 기준 치명 이상은 없습니다.",
            "details": {},
        })
    return alerts


def build_operations_report(*, limit: int = 500) -> dict[str, Any]:
    signals = read_signal_snapshots(limit=limit)
    execution_events = read_execution_events(limit=limit * 4)
    today_signals = [item for item in signals if _is_today(item.get("timestamp") or item.get("logged_at"))]
    blocked_reason_counts: dict[str, int] = {}
    stale_count = 0
    data_missing_count = 0
    strategy_performance: dict[str, dict[str, Any]] = {}
    for item in today_signals:
        reasons = [str(reason or "") for reason in item.get("reason_codes", []) if reason]
        risk_reason = str(item.get("risk_reason_code") or "")
        if any(_is_stale_reason(reason) for reason in reasons) or _is_stale_reason(risk_reason):
            stale_count += 1
        if "data_missing" in reasons or risk_reason == "data_missing":
            data_missing_count += 1
        if bool(item.get("entry_allowed")):
            continue
        reasons = item.get("reason_codes") or [risk_reason or "blocked"]
        for reason in reasons:
            key = str(reason or "blocked")
            blocked_reason_counts[key] = blocked_reason_counts.get(key, 0) + 1
    for event in execution_events:
        if not _is_today(event.get("timestamp")):
            continue
        strategy_key = str(event.get("strategy_id") or event.get("strategy_name") or "unassigned")
        bucket = strategy_performance.setdefault(strategy_key, {
            "strategy_id": event.get("strategy_id") or "",
            "strategy_name": event.get("strategy_name") or strategy_key,
            "filled_count": 0,
            "failed_count": 0,
            "submitted_count": 0,
        })
        event_type = str(event.get("event_type") or "")
        if event_type == "submitted":
            bucket["submitted_count"] += 1
        elif event_type == LIFECYCLE_FILLED:
            bucket["filled_count"] += 1
        elif event_type == LIFECYCLE_FAILED:
            bucket["failed_count"] += 1
    execution_summary = summarize_execution_events(
        [item for item in execution_events if _is_today(item.get("timestamp"))]
    )
    alerts = _collect_warning_alerts(today_signals, execution_events)
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "report": {
            "today_signal_count": len(today_signals),
            "blocked_count": sum(blocked_reason_counts.values()),
            "blocked_reason_counts": blocked_reason_counts,
            "execution_counts": execution_summary.get("terminal_counts", {}),
            "execution_event_counts": execution_summary.get("counts", {}),
            "strategy_performance": list(strategy_performance.values()),
            "data_health": {
                "stale_count": stale_count,
                "data_missing_count": data_missing_count,
            },
        },
        "alerts": alerts,
    }
