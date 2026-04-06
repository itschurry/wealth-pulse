from __future__ import annotations

from schemas.strategy_metadata import build_strategy_metadata_payload
from services.strategy_registry import delete_strategy, get_strategy, list_strategies, save_strategy, set_strategy_enabled, summarize_registry


def handle_strategies_list(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        market = (query.get("market", [""])[0] or "").strip().upper()
        live_only = (query.get("live_only", ["0"])[0] or "0").strip() == "1"
        rows = list_strategies(live_only=live_only, market=market or None)
        return 200, {
            "ok": True,
            "items": rows,
            "summary": summarize_registry(),
            "count": len(rows),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_strategy_metadata() -> tuple[int, dict]:
    try:
        return 200, build_strategy_metadata_payload()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_strategy_detail(path: str) -> tuple[int, dict]:
    try:
        strategy_id = path[len("/api/strategies/"):].strip()
        if not strategy_id:
            return 400, {"ok": False, "error": "strategy_id required"}
        item = get_strategy(strategy_id)
        if item is None:
            return 404, {"ok": False, "error": f"strategy not found: {strategy_id}"}
        return 200, {"ok": True, "item": item}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_strategy_toggle(payload: dict) -> tuple[int, dict]:
    try:
        strategy_id = str(payload.get("strategy_id") or "").strip()
        enabled = bool(payload.get("enabled"))
        if not strategy_id:
            return 400, {"ok": False, "error": "strategy_id required"}
        item = set_strategy_enabled(strategy_id, enabled)
        return 200, {"ok": True, "item": item}
    except KeyError as exc:
        return 404, {"ok": False, "error": f"strategy not found: {exc.args[0]}"}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_strategy_delete(payload: dict) -> tuple[int, dict]:
    try:
        strategy_id = str(payload.get("strategy_id") or "").strip()
        if not strategy_id:
            return 400, {"ok": False, "error": "strategy_id required"}
        delete_strategy(strategy_id)
        return 200, {"ok": True, "strategy_id": strategy_id}
    except KeyError as exc:
        return 404, {"ok": False, "error": f"strategy not found: {exc.args[0]}"}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_strategy_save(payload: dict) -> tuple[int, dict]:
    try:
        item = save_strategy(payload)
        return 200, {"ok": True, "item": item}
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
