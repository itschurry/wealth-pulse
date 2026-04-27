from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from services.execution_lifecycle import coerce_order_id
from services.execution_service import _normalize_runtime_account, get_execution_service
from services.operations_report_service import build_operations_report
from services.paper_runtime_store import read_execution_events, read_order_events

_ACCOUNT_STATE_PATH = Path(__file__).parent.parent.parent.parent / "storage" / "logs" / "paper_account_state.json"
_LIVE_PERFORMANCE_BASELINE_PATH = Path(__file__).parent.parent.parent.parent / "storage" / "logs" / "live_performance_baseline.json"
_FILLED_STATES = {"filled", "partial_fill"}
_LIFECYCLE_PRIORITY = {
    "intent": 0,
    "submitted": 1,
    "accepted": 2,
    "partial_fill": 3,
    "filled": 4,
    "failed": 4,
    "canceled": 4,
}


def _today_date_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return None


def _read_account_state() -> dict:
    return _read_json_file(_ACCOUNT_STATE_PATH)


def _safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _baseline_account_key(account: dict[str, Any]) -> str:
    mode = str(account.get("mode") or "unknown").strip().lower()
    product = str(account.get("account_product_code") or "").strip()
    return f"{mode}:{product}"


def _resolve_live_performance_baseline(
    account: dict[str, Any],
    *,
    cash_krw: float,
    cash_usd: float,
    equity_krw: float,
    realized_pnl_krw: float,
    unrealized_pnl_krw: float,
) -> dict[str, Any]:
    if str(account.get("mode") or "").strip().lower() != "real" or equity_krw <= 0:
        return {}

    current_key = _baseline_account_key(account)
    existing = _read_json_file(_LIVE_PERFORMANCE_BASELINE_PATH)
    existing_key = str(existing.get("account_key") or "")
    existing_equity = _safe_float(existing.get("starting_equity_krw"))
    if existing_key == current_key and existing_equity > 0:
        return existing

    inferred_starting_equity = equity_krw - realized_pnl_krw - unrealized_pnl_krw
    if inferred_starting_equity <= 0:
        inferred_starting_equity = equity_krw

    payload = {
        "account_key": current_key,
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "starting_equity_krw": round(inferred_starting_equity, 2),
        "initial_cash_krw": round(cash_krw, 2),
        "initial_cash_usd": round(cash_usd, 4),
    }
    _write_json_file(_LIVE_PERFORMANCE_BASELINE_PATH, payload)
    return payload


def _filter_since(rows: list[dict[str, Any]], session_start: str) -> list[dict[str, Any]]:
    if not session_start:
        return rows
    return [row for row in rows if str(row.get("logged_at") or row.get("timestamp") or "") >= session_start]


def _latest_execution_state_by_order(execution_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in execution_events:
        if not isinstance(item, dict):
            continue
        order_id = coerce_order_id(item)
        if not order_id:
            continue
        current = latest.get(order_id)
        timestamp = str(item.get("timestamp") or item.get("logged_at") or "")
        event_type = _normalize_order_status(str(item.get("event_type") or ""))
        priority = _LIFECYCLE_PRIORITY.get(event_type, -1)
        if current is None:
            latest[order_id] = item
            continue
        current_type = _normalize_order_status(str(current.get("event_type") or ""))
        current_priority = _LIFECYCLE_PRIORITY.get(current_type, -1)
        current_timestamp = str(current.get("timestamp") or current.get("logged_at") or "")
        if priority > current_priority or (priority == current_priority and timestamp >= current_timestamp):
            latest[order_id] = item
    return latest


def _normalize_order_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"order_sent", "submitted", "intent", "accepted", "partial_fill", "filled", "failed", "canceled"}:
        return normalized
    return ""


def _derive_order_status(order_event: dict[str, Any], latest_execution_state_by_order: dict[str, dict[str, Any]]) -> str:
    order_id = coerce_order_id(order_event)
    execution_state = latest_execution_state_by_order.get(order_id, {})
    candidates = [
        order_event.get("lifecycle_state"),
        order_event.get("execution_status"),
        execution_state.get("event_type"),
    ]
    for candidate in candidates:
        normalized = _normalize_order_status(str(candidate or ""))
        if normalized:
            return normalized
    if bool(order_event.get("success")) and str(order_event.get("filled_at") or "").strip():
        return "filled"
    if bool(order_event.get("success")):
        return "accepted"
    if str(order_event.get("canceled_at") or "").strip():
        return "canceled"
    return "failed"


def _order_status_label(status: str) -> str:
    mapping = {
        "intent": "주문 생성",
        "submitted": "주문 접수",
        "accepted": "접수 완료",
        "partial_fill": "부분 체결",
        "filled": "체결 완료",
        "failed": "주문 실패",
        "canceled": "주문 취소",
    }
    return mapping.get(status, "상태 미확인")


def _normalize_history_row(order_event: dict[str, Any], status: str, latest_execution_state_by_order: dict[str, dict[str, Any]]) -> dict[str, Any]:
    order_id = coerce_order_id(order_event)
    execution_state = latest_execution_state_by_order.get(order_id, {})
    quantity = order_event.get("quantity")
    if quantity in (None, ""):
        candidate_quantity = execution_state.get("filled_quantity") or execution_state.get("quantity")
        quantity = candidate_quantity if candidate_quantity not in (None, 0, "") else None
    return {
        "logged_at": order_event.get("logged_at"),
        "code": order_event.get("code"),
        "name": order_event.get("name"),
        "market": order_event.get("market"),
        "currency": order_event.get("currency"),
        "side": order_event.get("side"),
        "quantity": quantity,
        "filled_price_local": order_event.get("filled_price_local"),
        "filled_price_krw": order_event.get("filled_price_krw"),
        "notional_local": order_event.get("notional_local"),
        "notional_krw": order_event.get("notional_krw"),
        "fx_rate": order_event.get("fx_rate"),
        "status": status,
        "status_label": _order_status_label(status),
        "is_filled": status in _FILLED_STATES,
        "order_id": order_event.get("order_id"),
        "trace_id": order_event.get("trace_id"),
    }


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

        account = _normalize_runtime_account(account)

        order_events = account.get("orders") if isinstance(account.get("orders"), list) and account.get("orders") else read_order_events(limit=1000)
        execution_events = read_execution_events(limit=3000)
        session_start = str(account.get("created_at") or "")
        order_events = _filter_since(order_events, session_start)
        execution_events = _filter_since(execution_events, session_start)

        today = _today_date_str()
        latest_execution_state_by_order = _latest_execution_state_by_order(execution_events)

        today_events = [e for e in order_events if str(e.get("logged_at") or "")[:10] == today]
        today_live = [e for e in today_events if str(e.get("order_type") or "").lower() != "screened"]
        today_screened = [e for e in today_events if str(e.get("order_type") or "").lower() == "screened"]

        all_live = [e for e in order_events if str(e.get("order_type") or "").lower() != "screened"]
        order_history = [
            _normalize_history_row(event, _derive_order_status(event, latest_execution_state_by_order), latest_execution_state_by_order)
            for event in sorted(all_live, key=lambda x: str(x.get("logged_at") or ""), reverse=True)
        ]
        filled_history = [row for row in order_history if bool(row.get("is_filled"))]
        today_order_history = [
            _normalize_history_row(event, _derive_order_status(event, latest_execution_state_by_order), latest_execution_state_by_order)
            for event in today_live
        ]

        initial_cash = _safe_float(account.get("initial_cash_krw"))
        initial_cash_usd = _safe_float(account.get("initial_cash_usd"))
        cash_krw = _safe_float(account.get("cash_krw"))
        cash_usd = _safe_float(account.get("cash_usd"))
        realized_pnl = _safe_float(account.get("realized_pnl_krw"))
        realized_pnl_usd = _safe_float(account.get("realized_pnl_usd"))
        starting_equity_krw = _safe_float(account.get("starting_equity_krw"))
        equity_krw = _safe_float(account.get("equity_krw"))
        fx_rate = _safe_float(account.get("fx_rate"))
        positions_raw = account.get("positions") or engine_account.get("positions") or []
        if isinstance(positions_raw, dict):
            positions = [item for item in positions_raw.values() if isinstance(item, dict)]
        else:
            positions = [item for item in positions_raw if isinstance(item, dict)]
        unrealized_pnl = sum(_safe_float(p.get("unrealized_pnl_krw")) for p in positions)
        unrealized_pnl_usd = sum(
            _safe_float(p.get("unrealized_pnl_local"))
            for p in positions
            if str(p.get("currency") or "").upper() == "USD"
        )
        kospi_market_value_krw = sum(
            _safe_float(p.get("market_value_krw"))
            for p in positions
            if str(p.get("currency") or "").upper() != "USD"
        )
        us_market_value_usd = sum(
            _safe_float(p.get("market_value_usd"))
            for p in positions
            if str(p.get("currency") or "").upper() == "USD"
        )
        us_market_value_krw = sum(
            _safe_float(p.get("market_value_krw"))
            for p in positions
            if str(p.get("currency") or "").upper() == "USD"
        )

        live_baseline = _resolve_live_performance_baseline(
            account,
            cash_krw=cash_krw,
            cash_usd=cash_usd,
            equity_krw=equity_krw,
            realized_pnl_krw=realized_pnl,
            unrealized_pnl_krw=unrealized_pnl,
        )
        if live_baseline:
            initial_cash = _safe_float(live_baseline.get("initial_cash_krw"))
            initial_cash_usd = _safe_float(live_baseline.get("initial_cash_usd"))
            starting_equity_krw = _safe_float(live_baseline.get("starting_equity_krw"))

        total_return_pct = (
            ((equity_krw - starting_equity_krw) / starting_equity_krw) * 100
            if starting_equity_krw > 0 and equity_krw > 0 else (
                (realized_pnl + unrealized_pnl) / initial_cash * 100
                if initial_cash > 0 else None
            )
        )

        total_notional = sum(_safe_float(e.get("notional_krw")) for e in filled_history)
        avg_notional = total_notional / len(filled_history) if filled_history else None

        operations_report = build_operations_report(limit=500)

        live = {
            "today_signal_count": (
                int(((engine_state.get("last_summary") or {}).get("candidate_counts_by_market") or {}).get("KOSPI", 0))
                + int(((engine_state.get("last_summary") or {}).get("candidate_counts_by_market") or {}).get("NASDAQ", 0))
            ),
            "today_order_count": sum(1 for e in today_live if bool(e.get("success"))),
            "today_filled_count": sum(1 for row in today_order_history if bool(row.get("is_filled"))),
            "today_reject_count": sum(1 for e in today_live if not bool(e.get("success"))),
            "today_screened_block_count": sum(1 for e in today_screened if not bool(e.get("success"))),
            "total_order_count": len(order_history),
            "total_filled_count": len(filled_history),
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
            "order_history": order_history,
            "filled_history": filled_history,
            "operations_report": operations_report.get("report"),
            "alerts": operations_report.get("alerts"),
        }
        return 200, {"ok": True, "live": live}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
