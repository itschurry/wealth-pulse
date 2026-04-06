from __future__ import annotations

from typing import Any


_SIGNAL_STAGE_PRIORITY = {
    "blocked": 0,
    "watch": 1,
    "signal_generated": 2,
    "execution_decided": 3,
    "order_ready": 4,
    "order_sent": 5,
    "filled": 6,
    "rejected": 6,
}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _signal_key(payload: dict[str, Any]) -> str:
    market = str(payload.get("market") or "").upper()
    code = str(payload.get("code") or "").upper()
    if market and code:
        return f"{market}:{code}"
    return str(payload.get("originating_signal_key") or "").upper()


def derive_signal_workflow(signal: dict[str, Any]) -> dict[str, Any]:
    signal_state = str(signal.get("signal_state") or "watch").lower()
    final_action = str(signal.get("final_action") or "").strip().lower()
    entry_allowed = bool(signal.get("entry_allowed"))
    size_recommendation = signal.get("size_recommendation") if isinstance(signal.get("size_recommendation"), dict) else {}
    order_qty = _to_int(size_recommendation.get("quantity") or 0)
    risk_check = signal.get("risk_check") if isinstance(signal.get("risk_check"), dict) else {}
    blocked_reason = str(risk_check.get("reason_code") or final_action or "")

    stage = "watch"
    execution_status = "watch_only"
    orderable = False

    if signal_state == "exit":
        stage = "execution_decided"
        execution_status = "exit_signal"
    elif signal_state != "entry":
        if final_action == "watch_only":
            stage = "signal_generated"
            execution_status = "watch_only"
        else:
            stage = "blocked"
            execution_status = "non_entry_signal"
    elif not entry_allowed or final_action == "blocked":
        stage = "blocked"
        execution_status = blocked_reason or "risk_blocked"
    elif final_action == "review_for_entry":
        stage = "order_ready" if order_qty > 0 else "execution_decided"
        execution_status = "ready_for_order" if order_qty > 0 else "size_pending"
        orderable = order_qty > 0
    elif final_action == "watch_only":
        stage = "execution_decided"
        execution_status = "operator_review"
    else:
        stage = "signal_generated"
        execution_status = "signal_detected"

    return {
        "signal_key": _signal_key(signal),
        "workflow_stage": stage,
        "execution_status": execution_status,
        "orderable": orderable,
        "order_quantity": order_qty,
        "blocked_reason": blocked_reason if stage == "blocked" else "",
    }


def derive_order_workflow(order: dict[str, Any]) -> dict[str, Any]:
    success = bool(order.get("success"))
    filled_at = str(order.get("filled_at") or "").strip()
    if success and filled_at:
        workflow_stage = "filled"
        execution_status = "filled"
    elif success:
        workflow_stage = "order_sent"
        execution_status = "submitted"
    else:
        workflow_stage = "rejected"
        execution_status = str(order.get("reason_code") or order.get("failure_reason") or "rejected")
    return {
        "signal_key": _signal_key(order),
        "workflow_stage": workflow_stage,
        "execution_status": execution_status,
        "orderable": success,
    }


def enrich_signal_payload(signal: dict[str, Any]) -> dict[str, Any]:
    return {**signal, **derive_signal_workflow(signal)}


def enrich_order_payload(order: dict[str, Any]) -> dict[str, Any]:
    return {**order, **derive_order_workflow(order)}


def build_workflow_summary(signals: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, Any]:
    signal_rows = [enrich_signal_payload(item) for item in signals if isinstance(item, dict)]
    order_rows = [enrich_order_payload(item) for item in orders if isinstance(item, dict)]

    latest_by_key: dict[str, dict[str, Any]] = {}
    for row in signal_rows:
        key = str(row.get("signal_key") or "")
        if key and key not in latest_by_key:
            latest_by_key[key] = row
    for row in order_rows:
        key = str(row.get("signal_key") or "")
        if not key:
            continue
        current = latest_by_key.get(key)
        if current is None or _SIGNAL_STAGE_PRIORITY.get(str(row.get("workflow_stage") or ""), -1) >= _SIGNAL_STAGE_PRIORITY.get(str(current.get("workflow_stage") or ""), -1):
            merged = dict(current or {})
            merged.update({
                "signal_key": key,
                "workflow_stage": row.get("workflow_stage"),
                "execution_status": row.get("execution_status"),
                "orderable": row.get("orderable"),
                "last_order_side": row.get("side"),
                "last_order_success": row.get("success"),
                "last_order_at": row.get("filled_at") or row.get("submitted_at") or row.get("timestamp") or "",
                "last_order_reason": row.get("failure_reason") or row.get("reason_code") or "",
            })
            latest_by_key[key] = merged

    rows = list(latest_by_key.values())
    rows.sort(key=lambda item: str(item.get("last_order_at") or item.get("fetched_at") or item.get("timestamp") or item.get("logged_at") or ""), reverse=True)

    counts = {
        "scanned": 0,
        "signal_generated": 0,
        "execution_decided": 0,
        "order_ready": 0,
        "order_sent": 0,
        "filled": 0,
        "rejected": 0,
        "blocked": 0,
        "watch": 0,
    }
    for row in rows:
        stage = str(row.get("workflow_stage") or "watch")
        counts[stage] = counts.get(stage, 0) + 1

    return {
        "counts": counts,
        "items": rows,
        "count": len(rows),
    }
