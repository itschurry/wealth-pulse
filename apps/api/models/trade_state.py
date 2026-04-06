from __future__ import annotations

from enum import Enum


class TradeState(str, Enum):
    SCANNED = "scanned"
    SIGNAL_GENERATED = "signal_generated"
    EXECUTION_DECIDED = "execution_decided"
    ORDER_CREATED = "order_created"
    ORDER_SENT = "order_sent"
    FILLED = "filled"
    REJECTED = "rejected"


def trade_state_value(value: TradeState | str | None, default: TradeState = TradeState.SCANNED) -> str:
    if isinstance(value, TradeState):
        return value.value
    normalized = str(value or "").strip().lower()
    return normalized or default.value
