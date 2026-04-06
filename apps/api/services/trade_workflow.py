from __future__ import annotations

from functools import lru_cache
from typing import Any

from market_utils import lookup_company_listing


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


@lru_cache(maxsize=256)
def _resolve_company_identity(code: str, market: str, name: str) -> tuple[str, str]:
    normalized_code = str(code or "").strip().upper()
    normalized_market = str(market or "").strip().upper()
    normalized_name = str(name or "").strip()

    if not normalized_code:
        return normalized_name, normalized_market

    resolved_name = normalized_name
    resolved_market = normalized_market
    if not resolved_name or resolved_name.upper() == normalized_code:
        try:
            listing = lookup_company_listing(code=normalized_code, market=normalized_market)
        except Exception:
            listing = None

        if isinstance(listing, dict):
            candidate_name = str(listing.get("name") or "").strip()
            if candidate_name:
                resolved_name = candidate_name
            candidate_market = str(listing.get("market") or "").strip().upper()
            if candidate_market:
                resolved_market = candidate_market

    return resolved_name, resolved_market


def _enrich_symbol_meta(payload: dict[str, Any]) -> dict[str, Any]:
    market = str(payload.get("market") or "").strip().upper()
    code = str(payload.get("code") or "").strip().upper()
    name = str(payload.get("name") or "").strip()
    resolved_name, resolved_market = _resolve_company_identity(code=code, market=market, name=name)

    enriched = dict(payload)
    if resolved_name:
        enriched["name"] = resolved_name
    if resolved_market:
        enriched["market"] = resolved_market
    return enriched


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
        "lifecycle_state": "intent" if orderable else ("failed" if stage == "blocked" else ""),
    }


def derive_order_workflow(order: dict[str, Any]) -> dict[str, Any]:
    lifecycle_state = str(order.get("event_type") or order.get("lifecycle_state") or "").strip()
    success = bool(order.get("success"))
    filled_at = str(order.get("filled_at") or "").strip()
    if lifecycle_state == "filled" or (success and filled_at):
        workflow_stage = "filled"
        execution_status = "filled"
        lifecycle_state = "filled"
    elif lifecycle_state in {"accepted", "submitted", "partial_fill", "canceled", "failed"}:
        workflow_stage = "order_sent" if lifecycle_state in {"accepted", "submitted", "partial_fill"} else ("canceled" if lifecycle_state == "canceled" else "rejected")
        execution_status = lifecycle_state
    elif success:
        workflow_stage = "order_sent"
        execution_status = "submitted"
        lifecycle_state = "submitted"
    else:
        workflow_stage = "rejected"
        execution_status = str(order.get("reason_code") or order.get("failure_reason") or "rejected")
        lifecycle_state = "failed"
    return {
        "signal_key": _signal_key(order),
        "workflow_stage": workflow_stage,
        "execution_status": execution_status,
        "orderable": success,
        "lifecycle_state": lifecycle_state,
    }


def enrich_signal_payload(signal: dict[str, Any]) -> dict[str, Any]:
    return _enrich_symbol_meta({**signal, **derive_signal_workflow(signal)})


def enrich_order_payload(order: dict[str, Any]) -> dict[str, Any]:
    return _enrich_symbol_meta({**order, **derive_order_workflow(order)})


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
                "lifecycle_state": row.get("lifecycle_state"),
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
    lifecycle_counts = {
        "intent": 0,
        "submitted": 0,
        "accepted": 0,
        "partial_fill": 0,
        "filled": 0,
        "failed": 0,
        "canceled": 0,
    }
    for row in rows:
        stage = str(row.get("workflow_stage") or "watch")
        counts[stage] = counts.get(stage, 0) + 1
        lifecycle_state = str(row.get("lifecycle_state") or "")
        if lifecycle_state in lifecycle_counts:
            lifecycle_counts[lifecycle_state] += 1

    return {
        "counts": counts,
        "lifecycle_counts": lifecycle_counts,
        "items": rows,
        "count": len(rows),
    }
