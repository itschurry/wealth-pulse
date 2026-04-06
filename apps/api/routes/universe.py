from __future__ import annotations

from services.strategy_registry import list_strategies
from services.universe_builder import get_universe_snapshot, list_current_universes
from market_utils import normalize_market


def handle_universe_list(query: dict[str, list[str]]) -> tuple[int, dict]:
    try:
        refresh = (query.get("refresh", ["0"])[0] or "0").strip() == "1"
        rule_name = (query.get("rule_name", [""])[0] or "").strip()
        market = (query.get("market", [""])[0] or "").strip()
        if rule_name:
            item = get_universe_snapshot(rule_name, market=normalize_market(market) or None, refresh=refresh)
            return 200, {"ok": True, "items": [item], "count": 1}

        rows = list_current_universes()
        if refresh or not rows:
            refreshed: list[dict] = []
            seen: set[tuple[str, str]] = set()
            for strategy in list_strategies():
                key = (str(strategy.get("universe_rule") or ""), str(strategy.get("market") or ""))
                if key in seen:
                    continue
                seen.add(key)
                refreshed.append(get_universe_snapshot(key[0], market=normalize_market(key[1]) or None, refresh=True))
            rows = refreshed
        return 200, {"ok": True, "items": rows, "count": len(rows)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
