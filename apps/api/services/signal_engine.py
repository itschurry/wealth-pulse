from __future__ import annotations

from typing import Any

from models.trade_state import TradeState


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_signal_payload(
    candidate: dict[str, Any],
    *,
    scan_time: str,
    source: str,
) -> dict[str, Any]:
    signal = dict(candidate)
    signal_state = str(signal.get("signal_state") or "watch")
    entry_allowed = bool(signal.get("entry_allowed")) and signal_state == "entry"
    reason_codes = [str(item) for item in (signal.get("reason_codes") or []) if str(item)]
    if not reason_codes:
        reason_codes = [str(item) for item in (signal.get("reasons") or []) if str(item)]

    decision_preview = "block"
    if signal_state == "entry" and entry_allowed:
        decision_preview = "allow"
    elif signal_state not in {"entry", "watch", "exit"}:
        decision_preview = "skip"
    elif signal_state in {"watch", "exit"}:
        decision_preview = "skip"

    order_preview_status = "not_created"
    if decision_preview == "allow":
        order_preview_status = "order_ready"
    elif signal_state == "entry":
        order_preview_status = "blocked"

    signal["trade_state"] = TradeState.SIGNAL_GENERATED.value
    signal["signal_payload"] = {
        "signal_id": signal.get("signal_id"),
        "strategy_id": signal.get("strategy_id"),
        "signal_state": signal_state,
        "score": _to_float(signal.get("score"), 0.0),
        "threshold": _to_float(signal.get("threshold"), 0.0),
        "price": _to_float(signal.get("price"), _to_float(signal.get("current_price"), 0.0)),
        "reason_codes": reason_codes,
        "generated_at": scan_time,
        "source": source,
    }
    signal["execution_decision"] = signal.get("execution_decision") or decision_preview
    signal["execution_decision_label"] = signal.get("execution_decision_label") or (
        "진입 검토" if decision_preview == "allow" else "차단" if signal_state == "entry" else "관찰"
    )
    signal["order_preview"] = signal.get("order_preview") or {
        "status": order_preview_status,
        "status_label": "주문 준비" if order_preview_status == "order_ready" else "미생성" if order_preview_status == "not_created" else "차단",
        "quantity": int(((signal.get("size_recommendation") or {}).get("quantity") or 0) if isinstance(signal.get("size_recommendation"), dict) else 0),
        "price": _to_float(signal.get("price"), _to_float(signal.get("current_price"), 0.0)),
    }
    signal["scan_status"] = signal.get("scan_status") or {
        "trade_state": TradeState.SCANNED.value,
        "status_label": "스캔 완료",
        "scanned_at": scan_time,
        "source": source,
    }
    return signal


def build_stage_summary(
    *,
    scanner: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    scanned_count = sum(int(item.get("scanned_symbol_count") or 0) for item in scanner if isinstance(item, dict))
    signal_count = len(signals)
    entry_count = sum(1 for item in signals if str(item.get("signal_state") or "") == "entry")
    allowed_count = sum(1 for item in signals if bool(item.get("entry_allowed")))
    blocked_count = sum(1 for item in signals if str(item.get("signal_state") or "") == "entry" and not bool(item.get("entry_allowed")))
    return {
        "generated_at": generated_at,
        "scanned_count": scanned_count,
        "signal_count": signal_count,
        "entry_count": entry_count,
        "allowed_count": allowed_count,
        "blocked_count": blocked_count,
    }
