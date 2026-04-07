from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from analyzer.shared_strategy import default_strategy_profile, serialize_strategy_profile
from config.settings import LOGS_DIR
from market_utils import normalize_market


STRATEGY_REGISTRY_PATH = LOGS_DIR / "strategy_registry.json"

# status: human-readable lifecycle label, independent from enabled flag
# enabled is the only thing the engine reads — status is for operator context
_ALLOWED_STATUS = {"draft", "ready", "paused", "archived"}
_ALLOWED_MARKETS = {"KOSPI", "NASDAQ"}
_UNIVERSE_RULE_ALIASES = {
    "top_liquidity_200": "kospi",
    "us_mega_cap": "sp500",
    "volatility_breakout_pool": "sp500",
    "kr_core_bluechips": "kospi",
}

# Params that belong to execution context, not signal tuning.
# These are managed via the outer strategy fields, not inside params.
_PARAMS_CONTEXT_FIELDS = {
    "market", "strategy_kind", "regime_mode",
    "signal_interval", "signal_range",
    "scan_limit", "candidate_top_n",
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_market(value: Any) -> str:
    normalized = normalize_market(str(value or "").strip().upper())
    return normalized if normalized in _ALLOWED_MARKETS else "KOSPI"


def _normalize_status(value: Any, *, fallback: str = "draft") -> str:
    """Return a valid status value. Accepts legacy approval_status values."""
    raw = str(value or "").strip().lower()
    if raw in _ALLOWED_STATUS:
        return raw
    # migrate legacy approval_status values
    if raw == "approved" or raw == "testing":
        return "ready"
    if raw == "retired":
        return "archived"
    return fallback


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
        "strategy_id": "trend_following",
        "strategy_kind": "trend_following",
        "name": "Trend Following",
        "enabled": True,
        "status": "ready",
        "market": "KOSPI",
        "universe_rule": "kospi",
        "scan_cycle": "5m",
        "entry_rule": "bull regime -> trend alignment, volume confirmation, positive momentum",
        "exit_rule": "trend breakdown or risk stop",
        "params": {
            **serialize_strategy_profile(default_strategy_profile("KOSPI", strategy_kind="trend_following", risk_profile="balanced")),
            "scan_limit": 30,
            "candidate_top_n": 8,
        },
        "risk_limits": _risk_limits("KOSPI", max_positions=6, position_size_pct=0.12, daily_loss_limit_pct=0.02),
        "enabled_at": "2026-04-01T08:45:00+09:00",
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
        "strategy_id": "mean_reversion",
        "strategy_kind": "mean_reversion",
        "name": "Mean Reversion",
        "enabled": True,
        "status": "ready",
        "market": "KOSPI",
        "universe_rule": "kospi",
        "scan_cycle": "10m",
        "entry_rule": "sideways regime -> oversold rebound, lower band, early reversal",
        "exit_rule": "mean reversion complete or defensive stop",
        "params": {
            **serialize_strategy_profile(default_strategy_profile("KOSPI", strategy_kind="mean_reversion", risk_profile="balanced")),
            "scan_limit": 24,
            "candidate_top_n": 6,
        },
        "risk_limits": _risk_limits("KOSPI", max_positions=4, position_size_pct=0.1, daily_loss_limit_pct=0.015),
        "enabled_at": "2026-03-29T21:10:00+09:00",
        "version": 2,
        "research_summary": {
            "backtest_return_pct": 14.1,
            "max_drawdown_pct": -7.2,
            "win_rate_pct": 58.4,
            "sharpe": 1.22,
            "walk_forward_return_pct": 8.6,
        },
    },
    {
        "strategy_id": "defensive",
        "strategy_kind": "defensive",
        "name": "Defensive",
        "enabled": True,
        "status": "ready",
        "market": "NASDAQ",
        "universe_rule": "sp500",
        "scan_cycle": "15m",
        "entry_rule": "bear or risk_off regime -> selective entry, short hold, strict guardrail",
        "exit_rule": "protect capital quickly",
        "params": {
            **serialize_strategy_profile(default_strategy_profile("NASDAQ", strategy_kind="defensive", risk_profile="balanced")),
            "scan_limit": 20,
            "candidate_top_n": 5,
        },
        "risk_limits": _risk_limits("NASDAQ", max_positions=3, position_size_pct=0.08, daily_loss_limit_pct=0.01),
        "enabled_at": "2026-03-27T10:00:00+09:00",
        "version": 1,
        "research_summary": {
            "backtest_return_pct": 8.3,
            "max_drawdown_pct": -4.9,
            "win_rate_pct": 62.1,
            "sharpe": 0.98,
            "walk_forward_return_pct": 5.1,
        },
    },
]


def _read_registry() -> tuple[list[dict[str, Any]], bool]:
    """Returns (rows, file_exists)."""
    try:
        payload = json.loads(STRATEGY_REGISTRY_PATH.read_text(encoding="utf-8"))
        return (payload if isinstance(payload, list) else [], True)
    except FileNotFoundError:
        return [], False
    except (OSError, json.JSONDecodeError):
        return [], True


def _write_registry(rows: list[dict[str, Any]]) -> None:
    STRATEGY_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_REGISTRY_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(payload.get("strategy_id") or "").strip()
    if not strategy_id:
        raise ValueError("strategy_id is required")

    market = _normalize_market(payload.get("market"))
    enabled = bool(payload.get("enabled", False))

    # status is independent from enabled — engine reads enabled, status is operator label
    # also migrate legacy approval_status field
    raw_status = payload.get("status") or payload.get("approval_status")
    status = _normalize_status(raw_status)

    # enabled_at: recorded when first enabled (migrates legacy approved_at)
    enabled_at = str(payload.get("enabled_at") or payload.get("approved_at") or "").strip()
    if enabled and not enabled_at:
        enabled_at = _now_iso()

    version = int(payload.get("version") or 1)
    now_iso = _now_iso()

    params_raw = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    risk_limits = payload.get("risk_limits") if isinstance(payload.get("risk_limits"), dict) else {}
    research_summary = payload.get("research_summary") if isinstance(payload.get("research_summary"), dict) else {}

    strategy_kind = str(payload.get("strategy_kind") or strategy_id).strip() or strategy_id

    _risk_profile = str(params_raw.get("risk_profile") or "balanced")
    merged_params = {
        **serialize_strategy_profile(default_strategy_profile(market, strategy_kind=strategy_kind, risk_profile=_risk_profile)),
        **params_raw,
        # outer market always wins — prevents clone-from-different-market contamination
        "market": market,
    }

    return {
        "strategy_id": strategy_id,
        "strategy_kind": strategy_kind,
        "name": str(payload.get("name") or strategy_id).strip(),
        "enabled": enabled,
        "status": status,
        "market": market,
        "universe_rule": _UNIVERSE_RULE_ALIASES.get(
            str(payload.get("universe_rule") or ("kospi" if market == "KOSPI" else "sp500")).strip().lower(),
            str(payload.get("universe_rule") or ("kospi" if market == "KOSPI" else "sp500")).strip() or ("kospi" if market == "KOSPI" else "sp500"),
        ),
        "scan_cycle": str(payload.get("scan_cycle") or ("5m" if market == "KOSPI" else "15m")).strip() or ("5m" if market == "KOSPI" else "15m"),
        "entry_rule": str(payload.get("entry_rule") or "").strip(),
        "exit_rule": str(payload.get("exit_rule") or "").strip(),
        "params": merged_params,
        "risk_limits": {
            **_risk_limits(market, max_positions=5, position_size_pct=0.1, daily_loss_limit_pct=0.02),
            **risk_limits,
        },
        "enabled_at": enabled_at,
        "version": max(1, version),
        "research_summary": research_summary,
        "updated_at": str(payload.get("updated_at") or now_iso),
    }


def ensure_registry_seeded() -> list[dict[str, Any]]:
    rows, file_exists = _read_registry()
    if not file_exists:
        seeded = [_normalize_strategy(item) for item in _DEFAULT_STRATEGIES]
        _write_registry(seeded)
        return seeded
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


def list_strategies(*, live_only: bool = False, market: str | None = None) -> list[dict[str, Any]]:
    rows = ensure_registry_seeded()
    normalized_market = _normalize_market(market) if market else ""
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if normalized_market and row["market"] != normalized_market:
            continue
        if live_only and not row.get("enabled"):
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
    # status is not touched on toggle — it's the operator's label, not derived from enabled
    if enabled and not strategy.get("enabled_at"):
        strategy["enabled_at"] = _now_iso()
    strategy["updated_at"] = _now_iso()
    return save_strategy(strategy)


def seed_default_strategies() -> list[str]:
    """Insert missing default strategies. Never overwrites existing IDs."""
    seeded: list[str] = []
    for item in _DEFAULT_STRATEGIES:
        sid = str(item.get("strategy_id") or "")
        if sid and get_strategy(sid) is None:
            save_strategy(item)
            seeded.append(sid)
    return seeded


def summarize_registry() -> dict[str, Any]:
    strategies = ensure_registry_seeded()
    counts: dict[str, int] = {s: 0 for s in _ALLOWED_STATUS}
    enabled_count = 0
    for item in strategies:
        st = str(item.get("status") or "draft")
        counts[st] = counts.get(st, 0) + 1
        if bool(item.get("enabled")):
            enabled_count += 1
    return {
        "total": len(strategies),
        "enabled": enabled_count,
        "counts": counts,
    }
