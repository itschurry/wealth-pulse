from __future__ import annotations

from services.runtime_execution_service import get_execution_service
from services.risk_guard_service import build_risk_guard_state
from services.strategy_engine import _context_snapshot


def handle_portfolio_state(refresh_quotes: bool) -> tuple[int, dict]:
    try:
        status, account = get_execution_service().runtime_account(refresh_quotes)
        if not isinstance(account, dict):
            return 500, {"ok": False, "error": "account payload invalid"}
        if status >= 400 or account.get("ok") is False or account.get("error"):
            return status if status >= 400 else 500, {
                "ok": False,
                "error": account.get("error") or "account_unavailable",
                "account": account,
            }

        # Use cached context snapshot instead of running a full signal scan.
        regime, risk_level = _context_snapshot()
        risk_guard_state = build_risk_guard_state(
            account=account,
            cfg={},
            regime=regime,
            risk_level=risk_level,
        )
        return 200, {
            "ok": True,
            "account": account,
            "risk_guard_state": risk_guard_state,
            "regime": regime,
            "risk_level": risk_level,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
