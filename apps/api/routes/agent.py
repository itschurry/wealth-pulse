from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

from routes.candidate_monitor import handle_candidate_monitor_watchlist
from routes.research import handle_research_latest_snapshot
from routes.trading import handle_paper_order, handle_paper_account
from services.agent_decision_provider import call_hermes_trade_decision, research_analysis_to_trade_decision
from services.agent_runner import run_agent_once
from services.agent_store import default_store


def _query_int(query: dict[str, list[str]], name: str, default: int = 50) -> int:
    try:
        return int((query.get(name) or [str(default)])[0] or default)
    except (TypeError, ValueError):
        return default


def _symbol(candidate: dict[str, Any]) -> str:
    return str(candidate.get("symbol") or candidate.get("code") or "").strip().upper()


def _markets_from_payload(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("markets") or payload.get("market") or ["KOSPI"]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return ["KOSPI"]
    markets = [str(item or "").strip().upper() for item in raw if str(item or "").strip()]
    return markets or ["KOSPI"]


def _collect_monitor_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    query = {
        "refresh": ["1" if bool(payload.get("refresh", True)) else "0"],
        "limit": [str(max(1, min(200, int(payload.get("limit") or 10))))],
        "mode": [str(payload.get("mode") or "missing_or_stale")],
        "market": _markets_from_payload(payload),
    }
    status, result = handle_candidate_monitor_watchlist(query)
    if status != 200 or not isinstance(result, dict):
        return []
    pending_items = result.get("pending_items")
    if not isinstance(pending_items, list):
        pending_items = result.get("items") if isinstance(result.get("items"), list) else []
    return [dict(item) for item in pending_items if isinstance(item, dict)]


def _latest_research_evidence(symbol: str, market: str, provider: str) -> list[dict[str, Any]]:
    if not symbol:
        return []
    query = {"symbol": [symbol], "market": [market], "provider": [provider]}
    status, result = handle_research_latest_snapshot(query)
    if status != 200 or not isinstance(result, dict):
        return []
    snapshot = result.get("snapshot") if isinstance(result.get("snapshot"), dict) else result.get("item")
    if not isinstance(snapshot, dict):
        return []
    return [{"type": "research_snapshot", "payload": snapshot}]


def _evidence_from_payload(payload: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    evidence_by_symbol = payload.get("evidence_by_symbol") if isinstance(payload.get("evidence_by_symbol"), dict) else {}
    normalized: dict[str, list[dict[str, Any]]] = {
        str(k).upper(): [dict(item) for item in v if isinstance(item, dict)]
        for k, v in evidence_by_symbol.items()
        if isinstance(v, list)
    }
    if bool(payload.get("include_research_snapshot", True)):
        provider = str(payload.get("research_provider") or "default")
        for candidate in candidates:
            symbol = _symbol(candidate)
            market = str(candidate.get("market") or "").strip().upper()
            normalized.setdefault(symbol, [])
            normalized[symbol].extend(_latest_research_evidence(symbol, market, provider))
    return normalized


def _decision_provider_from_payload(payload: dict[str, Any]):
    decision_source = str(payload.get("decision_source") or "manual").strip().lower()
    decisions_by_symbol = payload.get("decisions_by_symbol") if isinstance(payload.get("decisions_by_symbol"), dict) else {}
    default_decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else None

    def _provider(candidate: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any] | str:
        symbol = _symbol(candidate)
        if decision_source == "hermes":
            try:
                return call_hermes_trade_decision(
                    candidate,
                    evidence,
                    agent_command=payload.get("agent_command"),
                    timeout=int(payload.get("timeout") or 300),
                )
            except Exception as exc:
                return {
                    "action": "HOLD",
                    "symbol": symbol,
                    "market": str(candidate.get("market") or "").strip().upper(),
                    "confidence": 0.0,
                    "reason_summary": f"Hermes decision failed; treated as HOLD: {exc}",
                    "evidence": [],
                    "risk": {"entry_price": 0, "stop_loss": 0, "take_profit": 0, "max_position_ratio": 0},
                }
        if decision_source == "research_snapshot":
            snapshot = next((item.get("payload") for item in evidence if isinstance(item, dict) and item.get("type") == "research_snapshot" and isinstance(item.get("payload"), dict)), None)
            if isinstance(snapshot, dict):
                return research_analysis_to_trade_decision(snapshot, candidate)
        value = decisions_by_symbol.get(symbol) or default_decision
        if value is None:
            return {
                "action": "HOLD",
                "symbol": symbol,
                "market": str(candidate.get("market") or "").strip().upper(),
                "confidence": 0.0,
                "reason_summary": "No decision supplied for manual Agent Run.",
                "evidence": [],
                "risk": {"entry_price": 0, "stop_loss": 0, "take_profit": 0, "max_position_ratio": 0},
            }
        return value

    return _provider


def _submit_paper_order(payload: dict[str, Any]) -> dict[str, Any]:
    status, result = handle_paper_order(payload)
    if not isinstance(result, dict):
        result = {"raw": result}
    return {"ok": 200 <= int(status) < 300 and bool(result.get("ok", True)), "status_code": status, **result}


def _paper_order_executor(intent: dict[str, Any]) -> dict[str, Any]:
    action = str(intent.get("action") or "").strip().lower()
    side = "buy" if action == "buy" else "sell" if action == "sell" else action
    payload = {
        "side": side,
        "code": str(intent.get("symbol") or "").strip().upper(),
        "market": str(intent.get("market") or "KOSPI").strip().upper() or "KOSPI",
        "quantity": int(intent.get("quantity") or 0),
        "order_type": "market",
    }
    return _submit_paper_order(payload)


def _account_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    account = payload.get("account") if isinstance(payload.get("account"), dict) else None
    if account is not None:
        return account
    try:
        status, result = handle_paper_account(False)
        if status == 200 and isinstance(result, dict):
            nested = result.get("account")
            return nested if isinstance(nested, dict) else result
    except Exception:
        pass
    return {"cash_krw": 0, "equity_krw": 1, "positions": [], "orders": []}


def handle_agent_run(payload: dict) -> tuple[int, dict]:
    payload = payload if isinstance(payload, dict) else {}
    trading_mode = str(payload.get("trading_mode") or "paper").strip().lower()
    if trading_mode != "paper":
        return 400, {"ok": False, "error": "agent_run_phase1_supports_paper_only"}

    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    candidates = [item for item in candidates if isinstance(item, dict)]
    if not candidates or str(payload.get("candidate_source") or "").strip().lower() == "monitor_watchlist":
        candidates = _collect_monitor_candidates(payload)
    evidence_by_symbol = _evidence_from_payload(payload, candidates)
    risk_config = payload.get("risk_config") if isinstance(payload.get("risk_config"), dict) else {}
    config = {"trading_mode": "paper", "enable_live_trading": False, **risk_config}
    account = _account_from_payload(payload)

    result = run_agent_once(
        candidates=candidates,
        evidence_by_symbol=evidence_by_symbol,
        decision_provider=_decision_provider_from_payload(payload),
        account_provider=lambda: account,
        order_executor=_paper_order_executor,
        config=config,
        store=default_store(),
        trigger=str(payload.get("trigger") or "manual"),
    )
    result["candidate_source"] = str(payload.get("candidate_source") or ("manual" if payload.get("candidates") else "monitor_watchlist"))
    result["decision_source"] = str(payload.get("decision_source") or "manual")
    return 200, result


def handle_agent_runs(query: dict[str, list[str]]) -> tuple[int, dict]:
    items = default_store().list_runs(limit=_query_int(query, "limit", 50))
    return 200, {"ok": True, "items": items}


def handle_agent_run_detail(path: str) -> tuple[int, dict]:
    raw_id = path.rstrip("/").split("/")[-1]
    try:
        run_id = int(raw_id)
    except ValueError:
        return 400, {"ok": False, "error": "invalid_run_id"}
    detail = default_store().get_run_detail(run_id)
    if detail.get("run") is None:
        return 404, {"ok": False, "error": "run_not_found"}
    return 200, {"ok": True, **detail}


def handle_agent_decisions(query: dict[str, list[str]]) -> tuple[int, dict]:
    return 200, {"ok": True, "items": default_store().list_decisions(limit=_query_int(query, "limit", 50))}


def handle_agent_orders(query: dict[str, list[str]]) -> tuple[int, dict]:
    return 200, {"ok": True, "items": default_store().list_orders(limit=_query_int(query, "limit", 50))}


def handle_agent_evidence(path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
    symbol = unquote(path.rstrip("/").split("/")[-1]).strip().upper()
    return 200, {"ok": True, "symbol": symbol, "items": default_store().list_evidence(symbol=symbol, limit=_query_int(query, "limit", 50))}
