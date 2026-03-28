from __future__ import annotations

from services.execution_service import get_execution_service
from services.risk_guard_service import build_risk_guard_state
from services.strategy_engine import build_signal_book


def handle_portfolio_state(refresh_quotes: bool) -> tuple[int, dict]:
    try:
        _, account = get_execution_service().paper_account(refresh_quotes)
        if not isinstance(account, dict):
            return 500, {"ok": False, "error": "account payload invalid"}

        book = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={}, account=account)
        risk_guard_state = build_risk_guard_state(
            account=account,
            cfg={},
            regime=str(book.get("regime") or "neutral"),
            risk_level=str(book.get("risk_level") or "중간"),
        )
        return 200, {
            "ok": True,
            "account": account,
            "risk_guard_state": risk_guard_state,
            "regime": book.get("regime"),
            "risk_level": book.get("risk_level"),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
