from __future__ import annotations

from services.strategy_engine import build_signal_book


def handle_signals_rank(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        markets = query.get("market", [])
        max_items_raw = (query.get("limit", ["100"])[0] or "100").strip()
        try:
            max_items = max(1, min(500, int(max_items_raw)))
        except (TypeError, ValueError):
            max_items = 100

        payload = build_signal_book(markets=markets or None, cfg={})
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
        payload = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={})
        for item in payload.get("signals", []):
            if str(item.get("code") or "").upper() == code:
                return 200, {"ok": True, "signal": item, "generated_at": payload.get("generated_at")}
        return 404, {"ok": False, "error": f"signal not found: {code}"}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
