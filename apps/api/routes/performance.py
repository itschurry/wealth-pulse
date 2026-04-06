from __future__ import annotations

from services.execution_service import get_execution_service
from services.paper_runtime_store import read_order_events
from services.strategy_registry import list_strategies


def handle_performance_summary() -> tuple[int, dict]:
    try:
        strategies = list_strategies()
        _, execution_payload = get_execution_service().paper_engine_status()
        account = execution_payload.get("account") if isinstance(execution_payload, dict) else {}
        state = execution_payload.get("state") if isinstance(execution_payload, dict) else {}
        order_events = read_order_events(limit=400)
        research_rows = []
        for item in strategies:
            summary = item.get("research_summary") if isinstance(item.get("research_summary"), dict) else {}
            research_rows.append(
                {
                    "strategy_id": item.get("strategy_id"),
                    "strategy_kind": item.get("strategy_kind"),
                    "name": item.get("name"),
                    "approval_status": item.get("approval_status"),
                    "enabled": item.get("enabled"),
                    "backtest_return_pct": summary.get("backtest_return_pct"),
                    "max_drawdown_pct": summary.get("max_drawdown_pct"),
                    "win_rate_pct": summary.get("win_rate_pct"),
                    "sharpe": summary.get("sharpe"),
                    "walk_forward_return_pct": summary.get("walk_forward_return_pct"),
                }
            )

        live_order_events = [item for item in order_events if str(item.get("order_type") or "").lower() != "screened"]
        screened_events = [item for item in order_events if str(item.get("order_type") or "").lower() == "screened"]

        live_summary = {
            "today_signal_count": int(((state.get("last_summary") or {}).get("candidate_counts_by_market") or {}).get("KOSPI", 0)) + int(((state.get("last_summary") or {}).get("candidate_counts_by_market") or {}).get("NASDAQ", 0)),
            "today_order_count": sum(1 for item in live_order_events if bool(item.get("success"))),
            "today_reject_count": sum(1 for item in live_order_events if not bool(item.get("success"))),
            "today_screened_block_count": sum(1 for item in screened_events if not bool(item.get("success"))),
            "filled_count": sum(1 for item in live_order_events if bool(item.get("success")) and str(item.get("side") or "").lower() == "buy"),
            "realized_pnl_krw": account.get("realized_pnl_krw"),
            "unrealized_pnl_krw": sum(float(item.get("unrealized_pnl_krw") or 0.0) for item in (account.get("positions") or []) if isinstance(item, dict)),
            "positions": len(account.get("positions") or []),
        }
        return 200, {"ok": True, "research": research_rows, "live": live_summary}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
