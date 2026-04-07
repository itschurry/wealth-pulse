from __future__ import annotations

from typing import Any


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def summarize_order_decision(signal: dict[str, Any]) -> dict[str, Any]:
    signal_state = str(signal.get("signal_state") or "watch").lower()
    final_action = str(signal.get("final_action") or "").strip().lower()
    entry_allowed = bool(signal.get("entry_allowed"))
    size_recommendation = signal.get("size_recommendation") if isinstance(signal.get("size_recommendation"), dict) else {}
    order_qty = _to_int(size_recommendation.get("quantity") or 0)
    risk_check = signal.get("risk_check") if isinstance(signal.get("risk_check"), dict) else {}
    blocked_reason = str(risk_check.get("reason_code") or final_action or "risk_blocked")

    action = "hold"
    reason_code = "watch_only"
    orderable = False

    if signal_state == "exit":
      action = "sell"
      reason_code = "exit_signal"
    elif signal_state != "entry":
      if final_action == "watch_only":
          action = "hold"
          reason_code = "watch_only"
      else:
          action = "hold"
          reason_code = "non_entry_signal"
    elif not entry_allowed or final_action == "blocked":
      action = "block"
      reason_code = blocked_reason
    elif final_action == "review_for_entry":
      action = "buy" if order_qty > 0 else "hold"
      reason_code = "order_ready" if order_qty > 0 else "size_zero"
      orderable = order_qty > 0
    elif final_action == "watch_only":
      action = "hold"
      reason_code = "operator_review"
    else:
      action = "hold"
      reason_code = "signal_detected"

    ev_metrics = signal.get("ev_metrics") if isinstance(signal.get("ev_metrics"), dict) else {}
    confidence = float(ev_metrics.get("confidence") or ev_metrics.get("win_rate") or 0.0)
    return {
        "action": action,
        "reason_code": reason_code,
        "orderable": orderable,
        "order_quantity": order_qty,
        "blocked_reason": reason_code if action == "block" else "",
        "confidence": confidence,
        "sizing_summary": size_recommendation,
        "trace_id": str(signal.get("trace_id") or signal.get("signal_id") or ""),
    }
