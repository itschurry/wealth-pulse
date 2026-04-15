from __future__ import annotations

from services.execution_service import get_execution_service
from services.paper_runtime_store import list_strategy_scans
from services.strategy_registry import summarize_registry
from services.strategy_engine import _context_snapshot
from services.system_mode_service import get_mode_status


def _allocator_snapshot(scans: list[dict]) -> tuple[dict[str, int], int, int, dict]:
    strategy_counts: dict[str, int] = {}
    entry_allowed_count = 0
    blocked_count = 0
    risk_guard_state: dict = {}

    for scan in scans:
        sid = str(scan.get("strategy_id") or scan.get("strategy_type") or "unknown")
        candidates = scan.get("top_candidates") or []
        if not isinstance(candidates, list):
            candidates = []
        strategy_counts[sid] = len(candidates)
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if bool(candidate.get("entry_allowed")):
                entry_allowed_count += 1
            elif str(candidate.get("signal_state") or "") == "entry":
                blocked_count += 1
            if not risk_guard_state and isinstance(candidate.get("risk_guard_state"), dict):
                risk_guard_state = candidate["risk_guard_state"]

    return strategy_counts, entry_allowed_count, blocked_count, risk_guard_state


def _compact_last_summary(summary: dict | None) -> dict:
    if not isinstance(summary, dict):
        return {}

    keep_keys = {
        "ok",
        "cycle_id",
        "started_at",
        "finished_at",
        "ran_at",
        "executed_buy_count",
        "executed_sell_count",
        "candidate_counts_by_market",
        "blocked_reason_counts",
        "rotation_summary",
        "skip_reason_counts",
        "market_stats",
        "closed_markets",
        "risk_guard_state",
        "validation_gate_summary",
        "pnl_snapshot",
        "error",
    }
    compact = {key: summary[key] for key in keep_keys if key in summary}
    skipped = summary.get("skipped")
    compact["skipped_count"] = len(skipped) if isinstance(skipped, list) else 0
    return compact


def _compact_execution_payload(execution_payload: dict | None) -> dict:
    if not isinstance(execution_payload, dict):
        return {"ok": False, "state": {}}

    state = execution_payload.get("state") if isinstance(execution_payload.get("state"), dict) else {}
    account = execution_payload.get("account") if isinstance(execution_payload.get("account"), dict) else {}
    keep_keys = {
        "engine_state",
        "running",
        "started_at",
        "paused_at",
        "stopped_at",
        "last_run_at",
        "next_run_at",
        "last_success_at",
        "last_error",
        "last_error_at",
        "latest_cycle_id",
        "today_order_counts",
        "order_failure_summary",
        "today_realized_pnl",
        "current_equity",
        "validation_policy",
        "optimized_params",
    }
    compact_state = {key: state[key] for key in keep_keys if key in state}
    compact_state["last_summary"] = _compact_last_summary(state.get("last_summary"))
    compact_account = {
        "equity_krw": account.get("equity_krw"),
        "cash_krw": account.get("cash_krw"),
        "cash_usd": account.get("cash_usd"),
        "positions": account.get("positions") if isinstance(account.get("positions"), list) else [],
    }
    return {
        "ok": execution_payload.get("ok", True),
        "state": compact_state,
        "account": compact_account,
    }


def handle_engine_status() -> tuple[int, dict]:
    try:
        _, execution_payload = get_execution_service().paper_engine_status()

        # Use cached scan results only — do NOT trigger fresh scans here.
        # build_signal_book with live scanning can take 100s+ and this
        # endpoint is polled every 15 seconds.
        scans = list_strategy_scans()
        strategy_counts, entry_allowed_count, blocked_count, risk_guard_state = _allocator_snapshot(scans)

        regime, risk_level = _context_snapshot()

        return 200, {
            "ok": True,
            "mode": get_mode_status(),
            "execution": execution_payload,
            "registry": summarize_registry(),
            "allocator": {
                "strategy_counts": strategy_counts,
                "entry_allowed_count": entry_allowed_count,
                "blocked_count": blocked_count,
                "regime": regime,
                "risk_level": risk_level,
            },
            "risk_guard_state": risk_guard_state,
            "scanner": scans,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_engine_summary() -> tuple[int, dict]:
    try:
        _, execution_payload = get_execution_service().paper_engine_status()
        scans = list_strategy_scans()
        strategy_counts, entry_allowed_count, blocked_count, risk_guard_state = _allocator_snapshot(scans)
        regime, risk_level = _context_snapshot()
        compact_execution = _compact_execution_payload(execution_payload)

        if not risk_guard_state:
            last_summary = compact_execution.get("state", {}).get("last_summary", {})
            if isinstance(last_summary, dict) and isinstance(last_summary.get("risk_guard_state"), dict):
                risk_guard_state = last_summary["risk_guard_state"]

        return 200, {
            "ok": True,
            "mode": get_mode_status(),
            "execution": compact_execution,
            "allocator": {
                "strategy_counts": strategy_counts,
                "entry_allowed_count": entry_allowed_count,
                "blocked_count": blocked_count,
                "regime": regime,
                "risk_level": risk_level,
            },
            "risk_guard_state": risk_guard_state,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
