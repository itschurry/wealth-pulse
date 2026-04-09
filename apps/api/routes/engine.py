from __future__ import annotations

from services.execution_service import get_execution_service
from services.paper_runtime_store import list_strategy_scans
from services.strategy_registry import summarize_registry
from services.strategy_engine import _context_snapshot
from services.system_mode_service import get_mode_status


def handle_engine_status() -> tuple[int, dict]:
    try:
        _, execution_payload = get_execution_service().paper_engine_status()

        # Use cached scan results only — do NOT trigger fresh scans here.
        # build_signal_book with live scanning can take 100s+ and this
        # endpoint is polled every 15 seconds.
        scans = list_strategy_scans()
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
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                if bool(c.get("entry_allowed")):
                    entry_allowed_count += 1
                elif str(c.get("signal_state") or "") == "entry":
                    blocked_count += 1
                if not risk_guard_state and isinstance(c.get("risk_guard_state"), dict):
                    risk_guard_state = c["risk_guard_state"]

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
