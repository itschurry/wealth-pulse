from __future__ import annotations

from services.trading_pipeline.orchestrator import read_market_pipeline, refresh_market_pipeline


def _to_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if value in {"0", "false", "f", "no", "n", "off", ""}:
            return False
    return default


def _markets(query: dict[str, list[str]]) -> list[str]:
    items = [str(item or "").strip().upper() for item in query.get("market", []) if str(item or "").strip()]
    return items or ["KOSPI"]


def handle_universe_list(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = _to_bool((query.get("refresh", ["0"])[0] or "0"), False)
        rows: list[dict] = []
        for market in _markets(query):
            payload = refresh_market_pipeline(market, persist=False)["universe"] if refresh else read_market_pipeline(market)["universe"]
            if payload:
                rows.append(payload)
        return 200, {"ok": True, "items": rows, "count": len(rows), "source": "dynamic_trading_pipeline", "refresh": refresh, "persist": False}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
