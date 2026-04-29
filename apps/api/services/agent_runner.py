"""Paper-first Agent Run orchestration.

Phase 1 keeps dependencies injectable so the audit/risk contract can be tested
without invoking Hermes or KIS. Production routes can start with a manual
candidate/decision payload and later swap in real tools.
"""

from __future__ import annotations

from typing import Any, Callable

from services.agent_risk_gate import evaluate_agent_decision_risk
from services.agent_schemas import parse_hermes_decision
from services.agent_store import AgentAuditStore, default_store

DecisionProvider = Callable[[dict[str, Any], list[dict[str, Any]]], str | dict[str, Any]]
AccountProvider = Callable[[], dict[str, Any]]
OrderExecutor = Callable[[dict[str, Any]], dict[str, Any]]


def _symbol(candidate: dict[str, Any]) -> str:
    return str(candidate.get("symbol") or candidate.get("code") or "").strip().upper()


def _default_decision_provider(candidate: dict[str, Any], _evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "action": "HOLD",
        "symbol": _symbol(candidate),
        "confidence": 0.0,
        "reason_summary": "No Hermes decision provider configured; treated as HOLD.",
        "evidence": [],
        "risk": {"entry_price": 0, "stop_loss": 0, "take_profit": 0, "max_position_ratio": 0},
    }


def _default_account_provider() -> dict[str, Any]:
    return {"cash_krw": 0.0, "equity_krw": 1.0, "positions": [], "orders": []}


def _default_order_executor(_intent: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": "No order executor configured"}


def run_agent_once(
    *,
    candidates: list[dict[str, Any]],
    evidence_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
    decision_provider: DecisionProvider | None = None,
    account_provider: AccountProvider | None = None,
    order_executor: OrderExecutor | None = None,
    config: dict[str, Any] | None = None,
    store: AgentAuditStore | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    store = store or default_store()
    config = dict(config or {})
    trading_mode = str(config.get("trading_mode") or "paper").strip().lower()
    evidence_by_symbol = evidence_by_symbol or {}
    decision_provider = decision_provider or _default_decision_provider
    account_provider = account_provider or _default_account_provider
    order_executor = order_executor or _default_order_executor

    run_id = store.create_run(trigger=trigger, trading_mode=trading_mode, status="running")
    summary = {
        "candidate_count": 0,
        "decisions": 0,
        "risk_approved": 0,
        "risk_rejected": 0,
        "orders_submitted": 0,
        "orders_skipped": 0,
    }
    status = "completed"
    try:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            symbol = _symbol(candidate)
            if not symbol:
                continue
            market = str(candidate.get("market") or "").strip().upper()
            candidate_id = store.add_candidate(
                run_id,
                symbol=symbol,
                market=market,
                name=str(candidate.get("name") or ""),
                source=str(candidate.get("source") or candidate.get("candidate_source") or "manual"),
                payload=candidate,
            )
            summary["candidate_count"] += 1

            evidence_rows = evidence_by_symbol.get(symbol, [])
            for evidence in evidence_rows:
                if not isinstance(evidence, dict):
                    continue
                store.add_evidence(
                    run_id,
                    candidate_id=candidate_id,
                    symbol=symbol,
                    evidence_type=str(evidence.get("type") or evidence.get("evidence_type") or "generic"),
                    payload=evidence.get("payload") if isinstance(evidence.get("payload"), dict) else evidence,
                )

            raw_decision = decision_provider(candidate, evidence_rows)
            parsed = parse_hermes_decision(raw_decision)
            decision = dict(parsed["decision"])
            if not str(decision.get("symbol") or "").strip():
                decision["symbol"] = symbol
            if not str(decision.get("market") or "").strip():
                decision["market"] = market
            payload = {**decision, "schema_errors": parsed["errors"]}
            decision_id = store.add_decision(
                run_id,
                candidate_id=candidate_id,
                symbol=decision.get("symbol") or symbol,
                action=decision.get("action") or "HOLD",
                confidence=float(decision.get("confidence") or 0.0),
                payload=payload,
                raw_response=parsed.get("raw_text") or "",
                schema_valid=bool(parsed.get("valid")),
            )
            summary["decisions"] += 1

            account = account_provider()
            recent_orders = account.get("orders") if isinstance(account.get("orders"), list) else []
            risk = evaluate_agent_decision_risk(
                decision=decision,
                account=account,
                config=config,
                recent_orders=recent_orders,
            )
            approved = bool(risk.get("approved"))
            if approved:
                summary["risk_approved"] += 1
            else:
                summary["risk_rejected"] += 1
            risk_event_id = store.add_risk_event(
                run_id,
                decision_id=decision_id,
                symbol=decision.get("symbol") or symbol,
                approved=approved,
                reason_code=str(risk.get("reason_code") or "unknown"),
                payload=risk,
            )

            if approved and risk.get("order_intent"):
                execution_result = order_executor(dict(risk["order_intent"]))
                order_status = "submitted" if bool(execution_result.get("ok")) else "failed"
                if order_status == "submitted":
                    summary["orders_submitted"] += 1
                else:
                    summary["orders_skipped"] += 1
                store.add_order(
                    run_id,
                    decision_id=decision_id,
                    risk_event_id=risk_event_id,
                    symbol=decision.get("symbol") or symbol,
                    action=str(decision.get("action") or "HOLD"),
                    trading_mode=trading_mode,
                    status=order_status,
                    payload={"intent": risk.get("order_intent"), "execution_result": execution_result},
                )
            else:
                summary["orders_skipped"] += 1
                store.add_order(
                    run_id,
                    decision_id=decision_id,
                    risk_event_id=risk_event_id,
                    symbol=decision.get("symbol") or symbol,
                    action=str(decision.get("action") or "HOLD"),
                    trading_mode=trading_mode,
                    status="skipped",
                    payload={"risk": risk},
                )
    except Exception as exc:
        status = "failed"
        summary["error"] = str(exc)
        raise
    finally:
        store.finish_run(run_id, status=status, summary=summary)

    return {"ok": status == "completed", "run_id": run_id, "summary": summary}
