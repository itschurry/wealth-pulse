from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from analyzer.shared_strategy import default_strategy_profile, serialize_strategy_profile
from config.settings import LOGS_DIR
from market_utils import normalize_market


STRATEGY_REGISTRY_PATH = LOGS_DIR / "strategy_registry.json"
_ALLOWED_APPROVAL_STATUS = {"draft", "testing", "approved", "paused", "retired"}
_ALLOWED_MARKETS = {"KOSPI", "NASDAQ"}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_market(value: Any) -> str:
    normalized = normalize_market(str(value or "").strip().upper())
    return normalized if normalized in _ALLOWED_MARKETS else "KOSPI"


def _risk_limits(market: str, *, max_positions: int, position_size_pct: float, daily_loss_limit_pct: float) -> dict[str, Any]:
    return {
        "max_positions": int(max_positions),
        "position_size_pct": float(position_size_pct),
        "daily_loss_limit_pct": float(daily_loss_limit_pct),
        "min_liquidity": 150_000 if market == "KOSPI" else 400_000,
        "max_spread_pct": 0.6 if market == "KOSPI" else 0.45,
    }


_DEFAULT_STRATEGIES: list[dict[str, Any]] = [
    {
        "strategy_id": "kr_momentum_v1",
        "name": "KR Momentum v1",
        "enabled": True,
        "approval_status": "approved",
        "market": "KOSPI",
        "universe_rule": "top_liquidity_200",
        "scan_cycle": "5m",
        "entry_rule": "close > sma20 > sma60 and volume_ratio >= 1.0 and 38 <= rsi14 <= 62",
        "exit_rule": "close < sma20 or stop_loss_pct or max_holding_days",
        "params": {
            **serialize_strategy_profile(default_strategy_profile("KOSPI")),
            "scan_limit": 30,
            "candidate_top_n": 8,
        },
        "risk_limits": _risk_limits("KOSPI", max_positions=6, position_size_pct=0.12, daily_loss_limit_pct=0.02),
        "approved_at": "2026-04-01T08:45:00+09:00",
        "version": 3,
        "research_summary": {
            "backtest_return_pct": 18.4,
            "max_drawdown_pct": -8.1,
            "win_rate_pct": 54.2,
            "sharpe": 1.31,
            "walk_forward_return_pct": 9.8,
        },
    },
    {
        "strategy_id": "us_breakout_v2",
        "name": "US Breakout v2",
        "enabled": True,
        "approval_status": "approved",
        "market": "NASDAQ",
        "universe_rule": "us_mega_cap",
        "scan_cycle": "10m",
        "entry_rule": "close > sma20 > sma60 and macd_hist > 0 and volume_ratio >= 1.2",
        "exit_rule": "close < sma20 or stop_loss_pct or max_holding_days",
        "params": {
            **serialize_strategy_profile(default_strategy_profile("NASDAQ")),
            "scan_limit": 24,
            "candidate_top_n": 6,
        },
        "risk_limits": _risk_limits("NASDAQ", max_positions=5, position_size_pct=0.15, daily_loss_limit_pct=0.018),
        "approved_at": "2026-03-29T21:10:00+09:00",
        "version": 2,
        "research_summary": {
            "backtest_return_pct": 22.9,
            "max_drawdown_pct": -10.6,
            "win_rate_pct": 49.6,
            "sharpe": 1.48,
            "walk_forward_return_pct": 11.2,
        },
    },
    {
        "strategy_id": "kr_event_watch_v1",
        "name": "KR Event Watch v1",
        "enabled": False,
        "approval_status": "testing",
        "market": "KOSPI",
        "universe_rule": "volatility_breakout_pool",
        "scan_cycle": "15m",
        "entry_rule": "event-sensitive leaders with breakout confirmation",
        "exit_rule": "event fade or close < sma20",
        "params": {
            **serialize_strategy_profile(default_strategy_profile("KOSPI")),
            "scan_limit": 20,
            "candidate_top_n": 5,
        },
        "risk_limits": _risk_limits("KOSPI", max_positions=3, position_size_pct=0.08, daily_loss_limit_pct=0.01),
        "approved_at": "",
        "version": 1,
        "research_summary": {
            "backtest_return_pct": 7.1,
            "max_drawdown_pct": -12.8,
            "win_rate_pct": 46.3,
            "sharpe": 0.74,
            "walk_forward_return_pct": 1.4,
        },
    },
]


def _read_registry() -> list[dict[str, Any]]:
    try:
        payload = json.loads(STRATEGY_REGISTRY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_registry(rows: list[dict[str, Any]]) -> None:
    STRATEGY_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_REGISTRY_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(payload.get("strategy_id") or "").strip()
    if not strategy_id:
        raise ValueError("strategy_id is required")
    market = _normalize_market(payload.get("market"))
    approval_status = str(payload.get("approval_status") or "draft").strip().lower()
    if approval_status not in _ALLOWED_APPROVAL_STATUS:
        approval_status = "draft"
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    risk_limits = payload.get("risk_limits") if isinstance(payload.get("risk_limits"), dict) else {}
    research_summary = payload.get("research_summary") if isinstance(payload.get("research_summary"), dict) else {}
    version = int(payload.get("version") or 1)
    now_iso = _now_iso()
    normalized = {
        "strategy_id": strategy_id,
        "name": str(payload.get("name") or strategy_id).strip(),
        "enabled": bool(payload.get("enabled", False)),
        "approval_status": approval_status,
        "market": market,
        "universe_rule": str(payload.get("universe_rule") or "top_liquidity_200").strip() or "top_liquidity_200",
        "scan_cycle": str(payload.get("scan_cycle") or "5m").strip() or "5m",
        "entry_rule": str(payload.get("entry_rule") or "").strip(),
        "exit_rule": str(payload.get("exit_rule") or "").strip(),
        "params": {**serialize_strategy_profile(default_strategy_profile(market)), **params},
        "risk_limits": {
            **_risk_limits(market, max_positions=5, position_size_pct=0.1, daily_loss_limit_pct=0.02),
            **risk_limits,
        },
        "approved_at": str(payload.get("approved_at") or "").strip(),
        "version": max(1, version),
        "research_summary": research_summary,
        "updated_at": str(payload.get("updated_at") or now_iso),
    }
    return normalized


def ensure_registry_seeded() -> list[dict[str, Any]]:
    rows = _read_registry()
    if rows:
        normalized_rows = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_strategy(row)
            if normalized["strategy_id"] in seen:
                continue
            seen.add(normalized["strategy_id"])
            normalized_rows.append(normalized)
        if normalized_rows != rows:
            _write_registry(normalized_rows)
        return normalized_rows

    seeded = [_normalize_strategy(item) for item in _DEFAULT_STRATEGIES]
    _write_registry(seeded)
    return seeded


def list_strategies(*, live_only: bool = False, market: str | None = None) -> list[dict[str, Any]]:
    rows = ensure_registry_seeded()
    normalized_market = _normalize_market(market) if market else ""
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if normalized_market and row["market"] != normalized_market:
            continue
        if live_only and not (row.get("enabled") and row.get("approval_status") == "approved"):
            continue
        filtered.append(dict(row))
    filtered.sort(key=lambda item: (not bool(item.get("enabled")), str(item.get("strategy_id") or "")))
    return filtered


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    target = str(strategy_id or "").strip()
    if not target:
        return None
    for row in ensure_registry_seeded():
        if str(row.get("strategy_id") or "") == target:
            return dict(row)
    return None


def save_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    rows = ensure_registry_seeded()
    normalized = _normalize_strategy(payload)
    next_rows: list[dict[str, Any]] = []
    replaced = False
    for row in rows:
        if str(row.get("strategy_id") or "") == normalized["strategy_id"]:
            merged = dict(row)
            merged.update(normalized)
            merged["version"] = max(int(row.get("version") or 1), int(normalized.get("version") or 1))
            merged["updated_at"] = _now_iso()
            next_rows.append(_normalize_strategy(merged))
            replaced = True
        else:
            next_rows.append(row)
    if not replaced:
        normalized["updated_at"] = _now_iso()
        next_rows.append(normalized)
    _write_registry(next_rows)
    return get_strategy(normalized["strategy_id"]) or normalized


def delete_strategy(strategy_id: str) -> None:
    target = str(strategy_id or "").strip()
    if not target:
        raise ValueError("strategy_id is required")
    rows = ensure_registry_seeded()
    next_rows = [row for row in rows if str(row.get("strategy_id") or "") != target]
    if len(next_rows) == len(rows):
        raise KeyError(target)
    _write_registry(next_rows)


def set_strategy_enabled(strategy_id: str, enabled: bool) -> dict[str, Any]:
    strategy = get_strategy(strategy_id)
    if strategy is None:
        raise KeyError(strategy_id)
    strategy["enabled"] = bool(enabled)
    strategy["updated_at"] = _now_iso()
    if not strategy["enabled"] and strategy.get("approval_status") == "approved":
        strategy["approval_status"] = "paused"
    elif strategy["enabled"] and strategy.get("approval_status") == "paused":
        strategy["approval_status"] = "approved"
        if not strategy.get("approved_at"):
            strategy["approved_at"] = _now_iso()
    return save_strategy(strategy)


def summarize_registry() -> dict[str, Any]:
    strategies = ensure_registry_seeded()
    counts = {"approved": 0, "testing": 0, "paused": 0, "draft": 0, "retired": 0}
    enabled_count = 0
    for item in strategies:
        status = str(item.get("approval_status") or "draft")
        counts[status] = counts.get(status, 0) + 1
        if bool(item.get("enabled")):
            enabled_count += 1
    return {
        "total": len(strategies),
        "enabled": enabled_count,
        "counts": counts,
    }
