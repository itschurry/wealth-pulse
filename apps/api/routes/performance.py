from __future__ import annotations

import datetime
import json
from pathlib import Path

from services.execution_service import get_execution_service
from services.operations_report_service import build_operations_report
from services.paper_runtime_store import read_order_events

_ACCOUNT_STATE_PATH = Path(__file__).parent.parent.parent.parent / "storage" / "logs" / "paper_account_state.json"


def _today_date_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _read_account_state() -> dict:
    try:
        return json.loads(_ACCOUNT_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def handle_performance_summary() -> tuple[int, dict]:
    try:
        _, execution_payload = get_execution_service().paper_engine_status()
        engine_state = execution_payload.get("state") if isinstance(execution_payload, dict) else {}
        engine_account = execution_payload.get("account") if isinstance(execution_payload, dict) else {}

        account = _read_account_state()
        if not account:
            account = engine_account or {}

        order_events = read_order_events(limit=1000)
        session_start = str(account.get("created_at") or "")
        if session_start:
            order_events = [e for e in order_events if str(e.get("logged_at") or "") >= session_start]

        today = _today_date_str()

        today_events = [e for e in order_events if str(e.get("logged_at") or "")[:10] == today]
        today_live = [e for e in today_events if str(e.get("order_type") or "").lower() != "screened"]
        today_screened = [e for e in today_events if str(e.get("order_type") or "").lower() == "screened"]

        all_live = [e for e in order_events if str(e.get("order_type") or "").lower() != "screened"]
        filled_events = [e for e in all_live if bool(e.get("success"))]

        initial_cash = float(account.get("initial_cash_krw") or 0)
        realized_pnl = float(account.get("realized_pnl_krw") or 0)
        positions = account.get("positions") or engine_account.get("positions") or []
        unrealized_pnl = sum(
            float(p.get("unrealized_pnl_krw") or 0)
            for p in positions
            if isinstance(p, dict)
        )
        total_return_pct = (
            (realized_pnl + unrealized_pnl) / initial_cash * 100
            if initial_cash > 0 else None
        )

        total_notional = sum(float(e.get("notional_krw") or 0) for e in filled_events)
        avg_notional = total_notional / len(filled_events) if filled_events else None

        filled_history = [
            {
                "logged_at": e.get("logged_at"),
                "code": e.get("code"),
                "market": e.get("market"),
                "side": e.get("side"),
                "quantity": e.get("quantity"),
                "filled_price_krw": e.get("filled_price_krw"),
                "notional_krw": e.get("notional_krw"),
            }
            for e in sorted(filled_events, key=lambda x: str(x.get("logged_at") or ""), reverse=True)
        ]

        operations_report = build_operations_report(limit=500)

        live = {
            "today_signal_count": (
                int(((engine_state.get("last_summary") or {}).get("candidate_counts_by_market") or {}).get("KOSPI", 0))
                + int(((engine_state.get("last_summary") or {}).get("candidate_counts_by_market") or {}).get("NASDAQ", 0))
            ),
            "today_order_count": sum(1 for e in today_live if bool(e.get("success"))),
            "today_reject_count": sum(1 for e in today_live if not bool(e.get("success"))),
            "today_screened_block_count": sum(1 for e in today_screened if not bool(e.get("success"))),
            "total_filled_count": len(filled_events),
            "total_reject_count": sum(1 for e in all_live if not bool(e.get("success"))),
            "total_screened_count": sum(1 for e in order_events if str(e.get("order_type") or "").lower() == "screened"),
            "realized_pnl_krw": realized_pnl,
            "unrealized_pnl_krw": unrealized_pnl,
            "total_return_pct": total_return_pct,
            "initial_cash_krw": initial_cash,
            "avg_notional_krw": avg_notional,
            "positions": len(positions),
            "filled_history": filled_history,
            "operations_report": operations_report.get("report"),
            "alerts": operations_report.get("alerts"),
        }
        return 200, {"ok": True, "live": live}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
