"""백테스트/최적화용 고정 유니버스 조회."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from loguru import logger
from market_utils import normalize_market


class BacktestUniverseEntry(TypedDict):
    name: str
    code: str
    market: str


_UNIVERSE_DIR = Path(__file__).resolve().parent / "universes"
_KOSPI100_PATH = _UNIVERSE_DIR / "kospi100.json"
_SP100_PATH = _UNIVERSE_DIR / "sp100.json"


def _read_universe(path: Path, *, market_filter: str = "") -> list[BacktestUniverseEntry]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read backtest universe: {}", path)
        return []

    if not isinstance(payload, list):
        return []

    target_market = normalize_market(market_filter).upper()
    rows: list[BacktestUniverseEntry] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or row.get("Symbol") or row.get("Code") or "").strip().upper()
        name = str(row.get("name") or row.get("Name") or code).strip() or code
        market = normalize_market(str(row.get("market") or target_market or ""))
        if not code or code in seen:
            continue
        if target_market and market and market != target_market:
            continue
        seen.add(code)
        rows.append({
            "code": code,
            "name": name,
            "market": market or target_market or "KOSPI",
        })
    return rows


def get_sp100_nasdaq_universe() -> list[BacktestUniverseEntry]:
    return [entry for entry in get_sp100_universe() if normalize_market(entry["market"]) == "NASDAQ"]


def get_sp100_universe() -> list[BacktestUniverseEntry]:
    return _read_universe(_SP100_PATH)


def get_kospi100_universe() -> list[BacktestUniverseEntry]:
    return _read_universe(_KOSPI100_PATH, market_filter="KOSPI")


def get_kospi50_universe() -> list[BacktestUniverseEntry]:
    return get_kospi100_universe()[:50]


def get_sp50_universe() -> list[BacktestUniverseEntry]:
    return get_sp100_universe()[:50]


def get_kospi_universe() -> list[BacktestUniverseEntry]:
    return get_kospi100_universe()
