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

        account_status, account_payload = get_execution_service().paper_account(False)
        if account_status == 200 and isinstance(account_payload, dict):
            account = account_payload

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
        initial_cash_usd = float(account.get("initial_cash_usd") or 0)
        cash_krw = float(account.get("cash_krw") or 0)
        cash_usd = float(account.get("cash_usd") or 0)
        realized_pnl = float(account.get("realized_pnl_krw") or 0)
        realized_pnl_usd = float(account.get("realized_pnl_usd") or 0)
        starting_equity_krw = float(account.get("starting_equity_krw") or 0)
        equity_krw = float(account.get("equity_krw") or 0)
        fx_rate = float(account.get("fx_rate") or 0)
        positions_raw = account.get("positions") or engine_account.get("positions") or []
        if isinstance(positions_raw, dict):
            positions = [item for item in positions_raw.values() if isinstance(item, dict)]
        else:
            positions = [item for item in positions_raw if isinstance(item, dict)]
        unrealized_pnl = sum(float(p.get("unrealized_pnl_krw") or 0) for p in positions)
        unrealized_pnl_usd = sum(
            float(p.get("unrealized_pnl_local") or 0)
            for p in positions
            if str(p.get("currency") or "").upper() == "USD"
        )
        kospi_market_value_krw = sum(
            float(p.get("market_value_krw") or 0)
            for p in positions
            if str(p.get("currency") or "").upper() != "USD"
        )
        us_market_value_usd = sum(
            float(p.get("market_value_usd") or 0)
            for p in positions
            if str(p.get("currency") or "").upper() == "USD"
        )
        us_market_value_krw = sum(
            float(p.get("market_value_krw") or 0)
            for p in positions
            if str(p.get("currency") or "").upper() == "USD"
        )
        total_return_pct = (
            ((equity_krw - starting_equity_krw) / starting_equity_krw) * 100
            if starting_equity_krw > 0 and equity_krw > 0 else (
                (realized_pnl + unrealized_pnl) / initial_cash * 100
                if initial_cash > 0 else None
            )
        )

        total_notional = sum(float(e.get("notional_krw") or 0) for e in filled_events)
        avg_notional = total_notional / len(filled_events) if filled_events else None

        filled_history = [
            {
                "logged_at": e.get("logged_at"),
                "code": e.get("code"),
                "market": e.get("market"),
                "currency": e.get("currency"),
                "side": e.get("side"),
                "quantity": e.get("quantity"),
                "filled_price_local": e.get("filled_price_local"),
                "filled_price_krw": e.get("filled_price_krw"),
                "notional_local": e.get("notional_local"),
                "notional_krw": e.get("notional_krw"),
                "fx_rate": e.get("fx_rate"),
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
            "realized_pnl_usd": realized_pnl_usd,
            "unrealized_pnl_krw": unrealized_pnl,
            "unrealized_pnl_usd": unrealized_pnl_usd,
            "total_return_pct": total_return_pct,
            "initial_cash_krw": initial_cash,
            "initial_cash_usd": initial_cash_usd,
            "cash_krw": cash_krw,
            "cash_usd": cash_usd,
            "equity_krw": equity_krw,
            "starting_equity_krw": starting_equity_krw,
            "fx_rate": fx_rate,
            "market_value_krw": kospi_market_value_krw + us_market_value_krw,
            "market_value_usd": us_market_value_usd,
            "market_value_krw_only": kospi_market_value_krw,
            "market_value_usd_krw": us_market_value_krw,
            "avg_notional_krw": avg_notional,
            "positions": len(positions),
            "filled_history": filled_history,
            "operations_report": operations_report.get("report"),
            "alerts": operations_report.get("alerts"),
        }
        return 200, {"ok": True, "live": live}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
