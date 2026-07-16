from __future__ import annotations

import datetime
import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from config.market_calendar import is_market_trading_day
from config.settings import RUNTIME_DIR
from services.json_utils import json_dump_text
from services.runtime_store import load_engine_state


KST = ZoneInfo("Asia/Seoul")
JOURNAL_DIR = RUNTIME_DIR / "daily_performance"
ENGINE_CYCLES_DIR = RUNTIME_DIR / "engine_cycles"
JOURNAL_TIME_KST = datetime.time(hour=15, minute=40, tzinfo=KST)
_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


def _validate_date_key(date_key: str) -> str:
    parsed = datetime.date.fromisoformat(str(date_key or ""))
    normalized = parsed.isoformat()
    if normalized != date_key:
        raise ValueError(f"잘못된 날짜 형식: {date_key}")
    return normalized


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 객체가 아님: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dump_text(payload, indent=2), encoding="utf-8")


def _read_cycles(date_key: str) -> list[dict[str, Any]]:
    path = ENGINE_CYCLES_DIR / f"{date_key}.jsonl"
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    if not rows:
        raise ValueError(f"엔진 사이클이 없음: {date_key}")
    return rows


def _kst_date(value: Any) -> str:
    parsed = datetime.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(KST).date().isoformat()


def _kst_iso(value: Any) -> str:
    parsed = datetime.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(KST).isoformat(timespec="seconds")


def _daily_orders(cycles: list[dict[str, Any]], date_key: str) -> list[dict[str, Any]]:
    account = cycles[-1].get("account") if isinstance(cycles[-1].get("account"), dict) else {}
    orders = account.get("orders") if isinstance(account.get("orders"), list) else []
    result = []
    for order in orders:
        if not isinstance(order, dict) or str(order.get("status") or "").lower() != "filled":
            continue
        timestamp = order.get("ts") or order.get("logged_at")
        if timestamp and _kst_date(timestamp) == date_key:
            result.append(dict(order))
    return sorted(result, key=lambda item: str(item.get("ts") or item.get("logged_at") or ""))


def _entry_metadata(cycles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cycle in cycles:
        buys = cycle.get("executed_buys") if isinstance(cycle.get("executed_buys"), list) else []
        for buy in buys:
            if not isinstance(buy, dict):
                continue
            code = str(buy.get("code") or "").strip()
            if code:
                result[code] = dict(buy)
    return result


def _build_round_trips(orders: list[dict[str, Any]], entry_meta: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    buys_by_code: dict[str, list[dict[str, Any]]] = {}
    trades: list[dict[str, Any]] = []
    for order in orders:
        code = str(order.get("code") or "").strip()
        side = str(order.get("side") or "").lower()
        if side == "buy":
            buys_by_code.setdefault(code, []).append(order)
            continue
        if side != "sell" or not buys_by_code.get(code):
            continue
        buy = buys_by_code[code].pop(0)
        meta = entry_meta.get(code, {})
        entry_price = _safe_float(buy.get("filled_price_krw"))
        exit_price = _safe_float(order.get("filled_price_krw"))
        quantity = min(int(_safe_float(buy.get("quantity"))), int(_safe_float(order.get("quantity"))))
        entry_notional = entry_price * quantity
        realized_pnl = _safe_float(order.get("realized_pnl_krw"))
        entry_ts = buy.get("ts") or buy.get("logged_at")
        exit_ts = order.get("ts") or order.get("logged_at")
        held_seconds = int(
            (
                datetime.datetime.fromisoformat(str(exit_ts).replace("Z", "+00:00"))
                - datetime.datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
            ).total_seconds()
        )
        trades.append({
            "code": code,
            "name": str(meta.get("name") or buy.get("name") or order.get("name") or code),
            "market": str(order.get("market") or buy.get("market") or ""),
            "quantity": quantity,
            "entry_at": _kst_iso(entry_ts),
            "exit_at": _kst_iso(exit_ts),
            "holding_seconds": held_seconds,
            "entry_price_krw": round(entry_price, 4),
            "exit_price_krw": round(exit_price, 4),
            "entry_notional_krw": round(entry_notional, 2),
            "entry_fee_krw": round(_safe_float(buy.get("fee_krw")), 2),
            "exit_fee_krw": round(_safe_float(order.get("fee_krw")), 2),
            "realized_pnl_krw": round(realized_pnl, 2),
            "return_pct": round(realized_pnl / entry_notional * 100, 4) if entry_notional > 0 else None,
            "exit_reason": str(order.get("note") or ""),
            "strategy_type": str(meta.get("strategy_type") or ""),
            "expected_value": meta.get("expected_value"),
            "entry_plan": {
                "entry_plan_price": buy.get("entry_plan_price"),
                "stop_loss_price": buy.get("stop_loss_price"),
                "take_profit_price": buy.get("take_profit_price"),
                "stop_loss_pct": buy.get("stop_loss_pct"),
                "take_profit_pct": buy.get("take_profit_pct"),
            },
        })
    return trades


def _market_snapshot(date_key: str, market_payload: dict[str, Any]) -> dict[str, Any]:
    history = market_payload.get("kospi_history") if isinstance(market_payload.get("kospi_history"), list) else []
    point = next((item for item in history if isinstance(item, dict) and item.get("date") == date_key), None)
    if point is None:
        raise ValueError(f"KOSPI 종가 데이터가 없음: {date_key}")
    return {
        "kospi_close": point.get("close"),
        "kospi_return_pct": point.get("pct"),
        "source": "naver_index_history",
    }


def build_daily_performance_journal(
    date_key: str,
    *,
    market_payload: dict[str, Any],
    generated_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    date_key = _validate_date_key(date_key)
    cycles = _read_cycles(date_key)
    first_account = cycles[0].get("account") if isinstance(cycles[0].get("account"), dict) else {}
    last_account = cycles[-1].get("account") if isinstance(cycles[-1].get("account"), dict) else {}
    if not first_account or not last_account:
        raise ValueError(f"계좌 스냅샷이 없는 엔진 사이클: {date_key}")

    orders = _daily_orders(cycles, date_key)
    trades = _build_round_trips(orders, _entry_metadata(cycles))
    starting_equity = _safe_float(first_account.get("equity_krw"))
    ending_equity = _safe_float(last_account.get("equity_krw"))
    net_pnl = ending_equity - starting_equity
    market = _market_snapshot(date_key, market_payload)
    daily_return = net_pnl / starting_equity * 100 if starting_equity > 0 else 0.0
    wins = [trade for trade in trades if _safe_float(trade.get("realized_pnl_krw")) > 0]
    losses = [trade for trade in trades if _safe_float(trade.get("realized_pnl_krw")) < 0]
    gross_profit = sum(_safe_float(trade.get("realized_pnl_krw")) for trade in wins)
    gross_loss = abs(sum(_safe_float(trade.get("realized_pnl_krw")) for trade in losses))
    skip_reasons: Counter[str] = Counter()
    blocked_reasons: Counter[str] = Counter()
    rotation_attempts = 0
    rotation_executions = 0
    for cycle in cycles:
        skip_reasons.update({str(key): int(value) for key, value in (cycle.get("skip_reason_counts") or {}).items()})
        blocked_reasons.update({str(key): int(value) for key, value in (cycle.get("blocked_reason_counts") or {}).items()})
        rotation = cycle.get("rotation_summary") if isinstance(cycle.get("rotation_summary"), dict) else {}
        rotation_attempts += int(rotation.get("attempted_count") or 0)
        rotation_executions += int(rotation.get("executed_count") or 0)

    initial_equity = _safe_float(last_account.get("starting_equity_krw") or last_account.get("initial_cash_krw"))
    now = (generated_at or datetime.datetime.now(KST)).astimezone(KST)
    payload = {
        "schema_version": 1,
        "date": date_key,
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": str(last_account.get("mode") or "unknown"),
        "account": {
            "starting_equity_krw": round(starting_equity, 2),
            "ending_equity_krw": round(ending_equity, 2),
            "ending_cash_krw": round(_safe_float(last_account.get("cash_krw")), 2),
            "ending_market_value_krw": round(_safe_float(last_account.get("market_value_krw")), 2),
            "net_pnl_krw": round(net_pnl, 2),
            "daily_return_pct": round(daily_return, 4),
            "cumulative_return_pct": round((ending_equity - initial_equity) / initial_equity * 100, 4) if initial_equity > 0 else None,
            "fees_krw": round(sum(_safe_float(order.get("fee_krw")) for order in orders), 2),
            "open_position_count": len(last_account.get("positions") or []),
        },
        "market": {
            **market,
            "excess_return_pct_points": round(daily_return - _safe_float(market.get("kospi_return_pct")), 4),
        },
        "trading": {
            "buy_count": sum(1 for order in orders if str(order.get("side") or "").lower() == "buy"),
            "sell_count": sum(1 for order in orders if str(order.get("side") or "").lower() == "sell"),
            "round_trip_count": len(trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else None,
            "gross_profit_krw": round(gross_profit, 2),
            "gross_loss_krw": round(gross_loss, 2),
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
            "average_holding_seconds": round(sum(int(trade["holding_seconds"]) for trade in trades) / len(trades), 2) if trades else None,
            "trades": trades,
        },
        "diagnostics": {
            "engine_cycle_count": len(cycles),
            "skip_reason_counts": dict(skip_reasons),
            "blocked_reason_counts": dict(blocked_reasons),
            "rotation_attempted_count": rotation_attempts,
            "rotation_executed_count": rotation_executions,
        },
        "strategy_config": load_engine_state(default={}).get("current_config") or {},
    }
    return payload


def generate_daily_performance_journal(
    date_key: str,
    *,
    market_loader: Callable[[], dict[str, Any]],
    generated_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    date_key = _validate_date_key(date_key)
    payload = build_daily_performance_journal(
        date_key,
        market_payload=market_loader(),
        generated_at=generated_at,
    )
    _write_json(JOURNAL_DIR / f"{date_key}.json", payload)
    return payload


def read_daily_performance_journal(date_key: str) -> dict[str, Any]:
    date_key = _validate_date_key(date_key)
    return _read_json(JOURNAL_DIR / f"{date_key}.json")


def list_daily_performance_journals(limit: int = 20) -> list[dict[str, Any]]:
    capped = max(1, min(100, int(limit)))
    paths = sorted(JOURNAL_DIR.glob("*.json"), reverse=True)[:capped]
    return [_read_json(path) for path in paths]


def _journal_is_due(now: datetime.datetime) -> bool:
    local_now = now.astimezone(KST)
    return is_market_trading_day("KR", local_now) and local_now.timetz() >= JOURNAL_TIME_KST


def _scheduler_loop(market_loader: Callable[[], dict[str, Any]]) -> None:
    attempted_dates: set[str] = set()
    while not _scheduler_stop.is_set():
        now = datetime.datetime.now(KST)
        date_key = now.date().isoformat()
        path = JOURNAL_DIR / f"{date_key}.json"
        if _journal_is_due(now) and date_key not in attempted_dates and not path.exists():
            attempted_dates.add(date_key)
            generate_daily_performance_journal(date_key, market_loader=market_loader, generated_at=now)
        _scheduler_stop.wait(30)


def start_daily_performance_journal_scheduler(market_loader: Callable[[], dict[str, Any]]) -> None:
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(market_loader,),
        name="daily-performance-journal",
        daemon=True,
    )
    _scheduler_thread.start()


def stop_daily_performance_journal_scheduler() -> None:
    _scheduler_stop.set()
    thread = _scheduler_thread
    if thread is not None:
        thread.join(timeout=2)
