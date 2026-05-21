from __future__ import annotations

from functools import lru_cache
from typing import Any

from market_utils import normalize_market
from services.universe_builder import get_configured_universe_snapshot


DEFAULT_BLUECHIP_TOP_N_KOSPI = 20
DEFAULT_BLUECHIP_TOP_N_US = 20


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_market(value: Any) -> str:
    normalized = normalize_market(str(value or "").strip())
    return str(normalized or value or "").strip().upper()


def bluechip_rule_for_market(market: str) -> str:
    normalized = _normalize_market(market)
    return "sp500" if normalized in {"NASDAQ", "NYSE", "AMEX", "US", "USA"} else "kospi"


def bluechip_top_n_for_market(market: str, cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg if isinstance(cfg, dict) else {}
    normalized = _normalize_market(market)
    if normalized in {"NASDAQ", "NYSE", "AMEX", "US", "USA"}:
        return max(1, _to_int(cfg.get("bluechip_top_n_us"), DEFAULT_BLUECHIP_TOP_N_US))
    return max(1, _to_int(cfg.get("bluechip_top_n_kospi"), DEFAULT_BLUECHIP_TOP_N_KOSPI))


@lru_cache(maxsize=16)
def _bluechip_symbols(rule_name: str, market: str, top_n: int) -> tuple[str, ...]:
    snapshot_market = None if rule_name == "sp500" else market
    snapshot = get_configured_universe_snapshot(rule_name, market=snapshot_market)
    rows = snapshot.get("symbols") if isinstance(snapshot, dict) else []
    symbols: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        symbol = _normalize_symbol(row.get("code") or row.get("symbol"))
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= top_n:
            break
    return tuple(symbols)


def bluechip_meta(symbol: str, market: str, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = _normalize_market(market)
    top_n = bluechip_top_n_for_market(normalized_market, cfg)
    rule_name = bluechip_rule_for_market(normalized_market)
    symbols = _bluechip_symbols(rule_name, normalized_market, top_n)
    is_bluechip = bool(normalized_symbol and normalized_symbol in symbols)
    return {
        "bluechip": is_bluechip,
        "bluechip_reason": f"{rule_name}_top_{top_n}" if is_bluechip else "",
        "bluechip_rule": rule_name,
        "bluechip_top_n": top_n,
    }


def is_bluechip(symbol: str, market: str, cfg: dict[str, Any] | None = None) -> bool:
    return bool(bluechip_meta(symbol, market, cfg).get("bluechip"))
