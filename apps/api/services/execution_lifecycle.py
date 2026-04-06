from __future__ import annotations

from typing import Any
from uuid import uuid4


LIFECYCLE_INTENT = "intent"
LIFECYCLE_SUBMITTED = "submitted"
LIFECYCLE_ACCEPTED = "accepted"
LIFECYCLE_PARTIAL_FILL = "partial_fill"
LIFECYCLE_FILLED = "filled"
LIFECYCLE_FAILED = "failed"
LIFECYCLE_CANCELED = "canceled"

TERMINAL_LIFECYCLE_STATES = {
    LIFECYCLE_FILLED,
    LIFECYCLE_FAILED,
    LIFECYCLE_CANCELED,
}


def _normalize_reason_code(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return ""
    if "risk" in value and "block" in value:
        return "risk_blocked"
    if "insufficient" in value and ("cash" in value or "fund" in value):
        return "insufficient_funds"
    if "network" in value:
        return "network_error"
    if "broker" in value and ("reject" in value or "denied" in value):
        return "broker_rejected"
    if "cancel" in value:
        return "canceled"
    if value in {"buy_failed", "sell_failed", "order_failed"}:
        return "broker_rejected"
    return value.replace(" ", "_")


def normalize_execution_reason(raw_reason: Any, *, order_type: str = "") -> str:
    value = _normalize_reason_code(raw_reason)
    if value:
        return value
    if str(order_type or "").lower() == "screened":
        return "risk_blocked"
    return ""


def coerce_order_id(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("order_id") or "").strip()
    if explicit:
        return explicit
    market = str(payload.get("market") or "").strip().upper()
    code = str(payload.get("code") or "").strip().upper()
    side = str(payload.get("side") or "").strip().lower()
    timestamp = str(
        payload.get("submitted_at")
        or payload.get("timestamp")
        or payload.get("filled_at")
        or payload.get("logged_at")
        or ""
    ).strip()
    base = ":".join(part for part in (market, code, side, timestamp) if part)
    return base or str(uuid4())


def coerce_trace_id(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("trace_id") or "").strip()
    if explicit:
        return explicit
    return coerce_order_id(payload)


def build_execution_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    order_id = coerce_order_id(payload)
    trace_id = coerce_trace_id(payload)
    timestamp = str(payload.get("timestamp") or payload.get("submitted_at") or payload.get("filled_at") or "")
    submitted_at = str(payload.get("submitted_at") or timestamp or "")
    filled_at = str(payload.get("filled_at") or "")
    canceled_at = str(payload.get("canceled_at") or "")
    success = bool(payload.get("success"))
    quantity = int(payload.get("quantity") or 0)
    filled_quantity = int(payload.get("filled_quantity") or quantity)
    reason_code = normalize_execution_reason(
        payload.get("reason_code") or payload.get("failure_reason"),
        order_type=str(payload.get("order_type") or ""),
    )
    base = {
        "order_id": order_id,
        "trace_id": trace_id,
        "code": payload.get("code"),
        "market": payload.get("market"),
        "side": payload.get("side"),
        "quantity": quantity,
        "filled_quantity": filled_quantity,
        "order_type": payload.get("order_type"),
        "reason_code": reason_code,
        "message": payload.get("message") or payload.get("failure_reason") or "",
        "originating_cycle_id": payload.get("originating_cycle_id") or "",
        "originating_signal_key": payload.get("originating_signal_key") or "",
        "strategy_id": payload.get("strategy_id") or "",
        "strategy_name": payload.get("strategy_name") or "",
    }
    events: list[dict[str, Any]] = []
    events.append({
        **base,
        "event_type": LIFECYCLE_INTENT,
        "timestamp": timestamp or submitted_at or filled_at,
    })
    if submitted_at:
        events.append({
            **base,
            "event_type": LIFECYCLE_SUBMITTED,
            "timestamp": submitted_at,
        })
    if success:
        accepted_at = submitted_at or timestamp or filled_at
        if accepted_at:
            events.append({
                **base,
                "event_type": LIFECYCLE_ACCEPTED,
                "timestamp": accepted_at,
            })
        if filled_at and 0 < filled_quantity < quantity:
            events.append({
                **base,
                "event_type": LIFECYCLE_PARTIAL_FILL,
                "timestamp": filled_at,
            })
        if filled_at:
            events.append({
                **base,
                "event_type": LIFECYCLE_FILLED,
                "timestamp": filled_at,
            })
    elif canceled_at:
        events.append({
            **base,
            "event_type": LIFECYCLE_CANCELED,
            "timestamp": canceled_at,
        })
    else:
        events.append({
            **base,
            "event_type": LIFECYCLE_FAILED,
            "timestamp": timestamp or submitted_at or filled_at,
        })
    return [item for item in events if str(item.get("timestamp") or "").strip()]


def latest_lifecycle_state(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    return str(events[-1].get("event_type") or "")


def summarize_execution_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        LIFECYCLE_INTENT: 0,
        LIFECYCLE_SUBMITTED: 0,
        LIFECYCLE_ACCEPTED: 0,
        LIFECYCLE_PARTIAL_FILL: 0,
        LIFECYCLE_FILLED: 0,
        LIFECYCLE_FAILED: 0,
        LIFECYCLE_CANCELED: 0,
    }
    reason_counts: dict[str, int] = {}
    latest_by_order: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        if event_type in counts:
            counts[event_type] += 1
        reason_code = str(event.get("reason_code") or "")
        if event_type in {LIFECYCLE_FAILED, LIFECYCLE_CANCELED} and reason_code:
            reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
        order_id = str(
            event.get("order_id")
            or event.get("trace_id")
            or event.get("originating_signal_key")
            or event.get("timestamp")
            or ""
        )
        if not order_id:
            continue
        current = latest_by_order.get(order_id)
        if current is None or str(event.get("timestamp") or "") >= str(current.get("timestamp") or ""):
            latest_by_order[order_id] = event
    terminal_counts = {
        LIFECYCLE_FILLED: 0,
        LIFECYCLE_FAILED: 0,
        LIFECYCLE_CANCELED: 0,
    }
    for event in latest_by_order.values():
        event_type = str(event.get("event_type") or "")
        if event_type in terminal_counts:
            terminal_counts[event_type] += 1
    return {
        "counts": counts,
        "terminal_counts": terminal_counts,
        "reason_counts": reason_counts,
        "count": len(events),
        "order_count": len(latest_by_order),
    }
