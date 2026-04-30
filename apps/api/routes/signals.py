from __future__ import annotations

from services.runtime_execution_service import get_execution_service
from services.strategy_engine import build_signal_book


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

        payload = build_signal_book(markets=markets or None, cfg={}, account=_load_runtime_account())
        signals = payload.get("signals", [])
        payload["signals"] = signals[:max_items]
        payload["count"] = len(payload["signals"])
        return 200, payload
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_signal_detail(path: str) -> tuple[int, dict]:
    try:
        raw = path[len("/api/signals/"):].strip()
        if not raw:
            return 400, {"ok": False, "error": "signal code required"}
        code = raw.upper()
        payload = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={}, account=_load_runtime_account())
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
