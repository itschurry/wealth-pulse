from __future__ import annotations

from services.runtime_execution_service import get_execution_service
from services.runtime_store import load_engine_state, read_signal_snapshots
from services.strategy_engine import build_signal_book, _context_snapshot


def _load_runtime_account() -> dict:
    service = get_execution_service()
    runtime_account = getattr(service, "runtime_account", None)
    if not callable(runtime_account):
        return {}
    _, payload = runtime_account(False)
    if not isinstance(payload, dict):
        return {}
    account = payload.get("account")
    return account if isinstance(account, dict) else payload


def handle_signals_rank(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        markets = query.get("market", [])
        max_items_raw = (query.get("limit", ["100"])[0] or "100").strip()
        try:
            max_items = max(1, min(500, int(max_items_raw)))
        except (TypeError, ValueError):
            max_items = 100

        market_set = {str(item).strip().upper() for item in markets if str(item).strip()}
        snapshots = read_signal_snapshots(limit=max(200, max_items))
        signals = [_compact_signal_snapshot(item) for item in snapshots if isinstance(item, dict)]
        if market_set:
            signals = [item for item in signals if str(item.get("market") or "").upper() in market_set]
        regime, risk_level = _context_snapshot()
        state = load_engine_state(default={})
        risk_guard_state = {}
        last_summary = state.get("last_summary") if isinstance(state.get("last_summary"), dict) else {}
        if isinstance(last_summary.get("risk_guard_state"), dict):
            risk_guard_state = last_summary["risk_guard_state"]
        return 200, {
            "ok": True,
            "generated_at": state.get("last_run_at") or (signals[0].get("timestamp") if signals else ""),
            "signals": signals[:max_items],
            "count": min(len(signals), max_items),
            "regime": regime,
            "risk_level": risk_level,
            "risk_guard_state": risk_guard_state,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def _compact_signal_snapshot(item: dict) -> dict:
    size_recommendation = item.get("size_recommendation") if isinstance(item.get("size_recommendation"), dict) else {}
    ev_metrics = item.get("ev_metrics") if isinstance(item.get("ev_metrics"), dict) else {}
    validation_snapshot = item.get("validation_snapshot") if isinstance(item.get("validation_snapshot"), dict) else {}
    final_action_snapshot = item.get("final_action_snapshot") if isinstance(item.get("final_action_snapshot"), dict) else {}
    return {
        "logged_at": item.get("logged_at"),
        "timestamp": item.get("timestamp"),
        "cycle_id": item.get("cycle_id"),
        "code": item.get("code") or item.get("symbol"),
        "symbol": item.get("symbol") or item.get("code"),
        "name": item.get("name"),
        "market": item.get("market"),
        "strategy_id": item.get("strategy_id"),
        "strategy_name": item.get("strategy_name"),
        "strategy_type": item.get("strategy_type"),
        "signal_state": item.get("signal_state"),
        "score": item.get("score"),
        "entry_allowed": bool(item.get("entry_allowed")),
        "reason_codes": item.get("reason_codes") if isinstance(item.get("reason_codes"), list) else [],
        "candidate_source": item.get("candidate_source"),
        "research_status": item.get("research_status"),
        "research_unavailable": item.get("research_unavailable"),
        "research_score": item.get("research_score"),
        "final_action": item.get("final_action") or final_action_snapshot.get("final_action"),
        "final_action_snapshot": {
            key: final_action_snapshot.get(key)
            for key in ("final_action", "decision_reason", "execution_mode", "timestamp")
            if key in final_action_snapshot
        },
        "size_recommendation": {
            key: size_recommendation.get(key)
            for key in ("quantity", "reason", "risk_budget_krw", "qty_by_risk", "qty_by_cash", "qty_by_caps")
            if key in size_recommendation
        },
        "ev_metrics": {
            key: ev_metrics.get(key)
            for key in ("expected_value", "win_probability", "reliability")
            if key in ev_metrics
        },
        "validation_snapshot": {
            key: validation_snapshot.get(key)
            for key in ("strategy_reliability", "reliability_reason", "validation_trades", "validation_sharpe")
            if key in validation_snapshot
        },
    }


def handle_signal_detail(path: str) -> tuple[int, dict]:
    try:
        raw = path[len("/api/signals/"):].strip()
        if not raw:
            return 400, {"ok": False, "error": "signal code required"}
        code = raw.upper()
        payload = build_signal_book(markets=["KOSPI"], cfg={}, account=_load_runtime_account())
        for item in payload.get("signals", []):
            if str(item.get("code") or "").upper() == code:
                return 200, {"ok": True, "signal": item, "generated_at": payload.get("generated_at")}
        return 404, {"ok": False, "error": f"signal not found: {code}"}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_signal_snapshots(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        raw = (query.get("limit", ["200"])[0] or "200").strip()
        try:
            limit = max(1, min(500, int(raw)))
        except (TypeError, ValueError):
            limit = 200
        return get_execution_service().signal_snapshots(limit)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
