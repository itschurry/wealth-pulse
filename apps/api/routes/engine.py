from __future__ import annotations

from services.execution_service import get_execution_service
from services.strategy_registry import summarize_registry
from services.strategy_engine import build_signal_book
from services.system_mode_service import get_mode_status


def handle_engine_status() -> tuple[int, dict]:
    try:
        _, execution_payload = get_execution_service().paper_engine_status()
        signal_book = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={})

        strategy_counts: dict[str, int] = {}
        for signal in signal_book.get("signals", []):
            key = str(signal.get("strategy_id") or signal.get("strategy_type") or "unknown")
            strategy_counts[key] = strategy_counts.get(key, 0) + 1

        return 200, {
            "ok": True,
            "mode": get_mode_status(),
            "execution": execution_payload,
            "registry": summarize_registry(),
            "allocator": {
                "strategy_counts": strategy_counts,
                "entry_allowed_count": signal_book.get("entry_allowed_count", 0),
                "blocked_count": signal_book.get("blocked_count", 0),
                "regime": signal_book.get("regime"),
                "risk_level": signal_book.get("risk_level"),
            },
            "risk_guard_state": signal_book.get("risk_guard_state", {}),
            "scanner": signal_book.get("scanner", []),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
