"""Validation service with extended metrics and walk-forward summary."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import lru_cache
from math import floor, sqrt
from threading import RLock
from typing import Any

from market_utils import lookup_company_listing, normalize_market
from services.backtest_service import get_backtest_service
from services.reliability_service import (
    build_reliability_diagnostic,
    classify_walk_forward_reliability,
    explain_walk_forward_reliability,
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _segment_metrics(equity_curve: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not equity_curve:
        return {
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "profit_factor": 0.0,
            "win_rate_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "avg_trade_return_pct": 0.0,
            "turnover": 0.0,
            "exposure_pct": 0.0,
            "trade_count": 0,
        }

    equities = [_to_float(item.get("equity")) for item in equity_curve]
    initial = equities[0] if equities else 0.0
    final = equities[-1] if equities else initial
    years = max(len(equities) / 252.0, 1.0 / 252.0)

    peak = equities[0]
    max_dd = 0.0
    for equity in equities:
        peak = max(peak, equity)
        dd = ((equity / peak) - 1.0) * 100.0 if peak > 0 else 0.0
        max_dd = min(max_dd, dd)

    returns = []
    for prev, curr in zip(equities, equities[1:]):
        if prev > 0:
            returns.append((curr / prev) - 1.0)

    sharpe = 0.0
    sortino = 0.0
    if returns:
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        stdev = variance ** 0.5
        if stdev > 0:
            sharpe = (mean_r / stdev) * sqrt(252)

        downside = [min(0.0, r) for r in returns]
        downside_var = sum(d ** 2 for d in downside) / max(1, len(downside))
        downside_dev = downside_var ** 0.5
        if downside_dev > 0:
            sortino = (mean_r / downside_dev) * sqrt(252)

    pnl_pct = [_to_float(t.get("pnl_pct")) for t in trades]
    wins = [x for x in pnl_pct if x > 0]
    losses = [x for x in pnl_pct if x < 0]

    gross_win = sum(wins)
    gross_loss_abs = abs(sum(losses))
    profit_factor = (gross_win / gross_loss_abs) if gross_loss_abs > 0 else (999.0 if gross_win > 0 else 0.0)

    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    avg_trade_return = (sum(pnl_pct) / len(pnl_pct)) if pnl_pct else 0.0
    win_rate = (len(wins) / len(pnl_pct) * 100.0) if pnl_pct else 0.0

    turnover = len(trades) / max(1.0, years)
    with_position_days = sum(1 for item in equity_curve if item.get("positions"))
    exposure_pct = (with_position_days / max(1, len(equity_curve))) * 100.0

    return {
        "total_return_pct": round(((final / initial) - 1.0) * 100.0 if initial > 0 else 0.0, 2),
        "cagr_pct": round((((final / initial) ** (1.0 / years)) - 1.0) * 100.0 if initial > 0 else 0.0, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "profit_factor": round(min(profit_factor, 999.0), 2),
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "avg_trade_return_pct": round(avg_trade_return, 2),
        "turnover": round(turnover, 2),
        "exposure_pct": round(exposure_pct, 2),
        "trade_count": len(trades),
    }


def _slice_by_index(seq: list[Any], start: int, end: int) -> list[Any]:
    start = max(0, start)
    end = max(start, end)
    return seq[start:end]


def _query_int(query: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (query.get(name, [str(default)])[0] or str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _query_bool(query: dict[str, list[str]], name: str, default: bool) -> bool:
    raw = (query.get(name, [str(default)])[0] or str(default)).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _exit_reason_stats(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for trade in trades:
        reason = str(trade.get("reason") or "unknown")
        bucket = stats.setdefault(reason, {"count": 0, "sum_pnl_pct": 0.0, "wins": 0})
        pnl_pct = _to_float(trade.get("pnl_pct"))
        bucket["count"] += 1
        bucket["sum_pnl_pct"] += pnl_pct
        if pnl_pct > 0:
            bucket["wins"] += 1

    for reason, bucket in stats.items():
        count = max(1, int(bucket["count"]))
        bucket["avg_pnl_pct"] = round(bucket["sum_pnl_pct"] / count, 2)
        bucket["win_rate_pct"] = round((bucket["wins"] / count) * 100.0, 2)
        del bucket["sum_pnl_pct"]
        del bucket["wins"]
    return stats


_EXIT_REASON_DEFINITIONS: dict[str, dict[str, Any]] = {
    "stop_loss": {
        "label": "손절",
        "category": "risk_cut",
        "aliases": {"손절", "stop_loss", "stoploss", "sl"},
    },
    "moving_average_breakdown": {
        "label": "20일선 이탈",
        "category": "trend_failure",
        "aliases": {
            "20일선 이탈",
            "moving_average_breakdown",
            "ma_breakdown",
            "sma_breakdown",
            "sma20_breakdown",
            "20ma_breakdown",
        },
    },
    "macd_weakness": {
        "label": "MACD 약세",
        "category": "momentum_failure",
        "aliases": {
            "MACD 약세 전환",
            "macd_weakness",
            "macd_bearish",
            "macd_bearish_turn",
        },
    },
    "holding_period_expiry": {
        "label": "보유기간 만료",
        "category": "time_exit",
        "aliases": {
            "보유기간 만료",
            "timeout",
            "time_exit",
            "holding_period_expiry",
            "holding_period",
            "max_holding",
        },
    },
    "rsi_overheat": {
        "label": "RSI 과열",
        "category": "overheat_exit",
        "aliases": {
            "RSI 과열",
            "rsi_overheat",
            "rsi_overbought",
            "overbought_exit",
        },
    },
    "take_profit": {
        "label": "익절",
        "category": "profit_capture",
        "aliases": {"익절", "take_profit", "takeprofit", "tp", "profit_target"},
    },
    "unknown": {
        "label": "기타",
        "category": "unknown",
        "aliases": {"unknown", "기타", "other"},
    },
}

_EXIT_REASON_ALIAS_TO_KEY: dict[str, str] = {}
for _exit_reason_key, _exit_reason_meta in _EXIT_REASON_DEFINITIONS.items():
    for _alias in _exit_reason_meta.get("aliases", set()):
        _EXIT_REASON_ALIAS_TO_KEY[str(_alias).strip().lower().replace("-", "_").replace(" ", "_")] = _exit_reason_key


_WALK_FORWARD_CACHE: dict[str, dict[str, Any]] = {}
_WALK_FORWARD_CACHE_LOCK = RLock()
_WALK_FORWARD_CACHE_MAX_ENTRIES = 12


def _normalize_cache_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_normalize_cache_value(item) for item in value]
    if isinstance(value, list):
        return [_normalize_cache_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_cache_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _normalize_cache_value(value[key]) for key in sorted(value.keys(), key=str)}
    if hasattr(value, "__dict__"):
        return _normalize_cache_value(vars(value))
    return str(value)


def _extract_backtest_cache_key(base_cfg: Any) -> str:
    try:
        cache_service = get_backtest_service()
        config_key_fn = getattr(cache_service, "_config_cache_key", None)
        if callable(config_key_fn):
            return str(config_key_fn(base_cfg))
    except Exception:
        pass

    return json.dumps(
        {
            "base_cfg": _normalize_cache_value(base_cfg),
            "markets": list(getattr(base_cfg, "markets", ())),
            "selected_symbols": list(getattr(base_cfg, "selected_symbols", ())),
            "lookback_days": getattr(base_cfg, "lookback_days", None),
            "initial_cash": getattr(base_cfg, "initial_cash", None),
            "base_currency": getattr(base_cfg, "base_currency", None),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _build_walk_forward_cache_key(query: dict[str, list[str]], *, base_cfg) -> str:
    payload_key = {
        "base_cfg": _extract_backtest_cache_key(base_cfg),
        "training_days": _query_int(query, "training_days", 180, 30, 3650),
        "validation_days": _query_int(query, "validation_days", 60, 20, 3650),
        "walk_forward": _query_bool(query, "walk_forward", True),
        "validation_min_trades": _query_int(query, "validation_min_trades", 8, 1, 500),
    }
    return json.dumps(payload_key, ensure_ascii=False, sort_keys=True)


def _load_cached_walk_forward(cache_key: str) -> dict[str, Any] | None:
    with _WALK_FORWARD_CACHE_LOCK:
        payload = _WALK_FORWARD_CACHE.get(cache_key)
        if payload is None:
            return None
        return dict(payload)


def _store_cached_walk_forward(cache_key: str, payload: dict[str, Any]) -> None:
    cached = dict(payload)
    with _WALK_FORWARD_CACHE_LOCK:
        _WALK_FORWARD_CACHE.pop(cache_key, None)
        _WALK_FORWARD_CACHE[cache_key] = cached
        if len(_WALK_FORWARD_CACHE) > _WALK_FORWARD_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(_WALK_FORWARD_CACHE))
            if oldest_key != cache_key:
                _WALK_FORWARD_CACHE.pop(oldest_key, None)


def _annotate_walk_forward_source(payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    response = dict(payload)
    response["source"] = source
    return response


def _normalize_exit_reason(reason: Any) -> tuple[str, str, str]:
    raw = str(reason or "unknown").strip()
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    key = _EXIT_REASON_ALIAS_TO_KEY.get(normalized, "unknown")
    meta = _EXIT_REASON_DEFINITIONS.get(key, _EXIT_REASON_DEFINITIONS["unknown"])
    return key, str(meta.get("label") or raw or "기타"), str(meta.get("category") or "unknown")


@lru_cache(maxsize=2048)
def _lookup_trade_listing(code: str, name: str, market: str) -> dict[str, Any] | None:
    return lookup_company_listing(
        code=code,
        name=name,
        market=market,
        ticker=code,
        scope="live",
    )


def _fallback_sector_for_market(market: str) -> str:
    normalized_market = normalize_market(market)
    if normalized_market in {"KOSPI", "KOSDAQ"}:
        return "국내주식"
    if normalized_market == "NASDAQ":
        return "미국주식"
    return "미분류"


def _trade_identity(trade: dict[str, Any]) -> dict[str, str]:
    code = str(trade.get("code") or trade.get("symbol") or "").strip().upper()
    name = str(trade.get("name") or "").strip()
    market = normalize_market(str(trade.get("market") or "").strip())
    sector = str(trade.get("sector") or "").strip()

    listing = _lookup_trade_listing(code, name, market) if (code or name) else None
    if listing:
        if not code:
            code = str(listing.get("code") or "").strip().upper()
        if not name:
            name = str(listing.get("name") or "").strip()
        if not market:
            market = normalize_market(str(listing.get("market") or ""))
        if not sector:
            sector = str(listing.get("sector") or "").strip()

    symbol_key = code or name or "unknown"
    symbol_label = "미상 종목"
    if code and name and name.upper() != code:
        symbol_label = f"{name} ({code})"
    elif name:
        symbol_label = name
    elif code:
        symbol_label = code

    sector_label = sector or _fallback_sector_for_market(market)
    return {
        "code": code,
        "name": name,
        "market": market,
        "sector": sector_label,
        "symbol_key": symbol_key,
        "symbol_label": symbol_label,
        "sector_key": sector_label,
        "sector_label": sector_label,
    }


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _build_scope_weakness_rows(
    trades: list[dict[str, Any]],
    *,
    scope: str,
) -> list[dict[str, Any]]:
    total_gross_loss = sum(abs(_to_float(trade.get("pnl_pct"), 0.0)) for trade in trades if _to_float(trade.get("pnl_pct"), 0.0) < 0)
    buckets: dict[str, dict[str, Any]] = {}

    for trade in trades:
        pnl_pct = _to_float(trade.get("pnl_pct"), 0.0)
        identity = _trade_identity(trade)
        if scope == "sector":
            bucket_key = identity["sector_key"]
            bucket_label = identity["sector_label"]
        else:
            bucket_key = identity["symbol_key"]
            bucket_label = identity["symbol_label"]

        bucket = buckets.setdefault(
            bucket_key,
            {
                "key": bucket_key,
                "label": bucket_label,
                "count": 0,
                "loss_trades": 0,
                "net_pnl_pct": 0.0,
                "gross_loss_pct": 0.0,
                "pnl_values": [],
                "loss_values": [],
                "reason_losses": {},
                "markets": set(),
            },
        )
        bucket["count"] += 1
        bucket["net_pnl_pct"] += pnl_pct
        bucket["pnl_values"].append(pnl_pct)
        if identity["market"]:
            bucket["markets"].add(identity["market"])

        if pnl_pct < 0:
            reason_key, reason_label, _ = _normalize_exit_reason(trade.get("reason"))
            bucket["loss_trades"] += 1
            bucket["gross_loss_pct"] += abs(pnl_pct)
            bucket["loss_values"].append(pnl_pct)
            reason_bucket = bucket["reason_losses"].setdefault(
                reason_key,
                {"label": reason_label, "gross_loss_pct": 0.0},
            )
            reason_bucket["gross_loss_pct"] += abs(pnl_pct)

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        if bucket["gross_loss_pct"] <= 0:
            continue
        top_reason_key = None
        top_reason_label = None
        top_reason_gross_loss = 0.0
        if bucket["reason_losses"]:
            top_reason_key, top_reason_data = max(
                bucket["reason_losses"].items(),
                key=lambda item: float(item[1].get("gross_loss_pct", 0.0)),
            )
            top_reason_label = str(top_reason_data.get("label") or top_reason_key)
            top_reason_gross_loss = _to_float(top_reason_data.get("gross_loss_pct"), 0.0)

        loss_share_pct = (bucket["gross_loss_pct"] / total_gross_loss * 100.0) if total_gross_loss > 0 else 0.0
        top_reason_share_pct = (top_reason_gross_loss / bucket["gross_loss_pct"] * 100.0) if bucket["gross_loss_pct"] > 0 else 0.0
        rows.append(
            {
                "key": bucket["key"],
                "label": bucket["label"],
                "count": int(bucket["count"]),
                "loss_trades": int(bucket["loss_trades"]),
                "gross_loss_pct": round(bucket["gross_loss_pct"], 4),
                "loss_share_pct": round(loss_share_pct, 2),
                "net_pnl_pct": round(bucket["net_pnl_pct"], 4),
                "avg_pnl_pct": round(_mean(bucket["pnl_values"]), 4),
                "avg_loss_pct": round(_mean(bucket["loss_values"]), 4),
                "top_reason_key": top_reason_key,
                "top_reason_label": top_reason_label,
                "top_reason_loss_share_pct": round(top_reason_share_pct, 2),
                "markets": sorted(bucket["markets"]),
                "summary": (
                    f"{bucket['label']} {int(bucket['loss_trades'])}건 · 손실 {bucket['gross_loss_pct']:.2f}%"
                    + (
                        f" · {top_reason_label} 비중 {top_reason_share_pct:.1f}%"
                        if top_reason_label
                        else ""
                    )
                ),
            }
        )

    rows.sort(
        key=lambda item: (
            float(item.get("gross_loss_pct", 0.0)),
            float(item.get("loss_share_pct", 0.0)),
            int(item.get("loss_trades", 0)),
        ),
        reverse=True,
    )
    return rows


def _classify_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "level": "unknown",
            "label": "데이터 없음",
            "unique_count": 0,
            "top_share_pct": 0.0,
            "top3_share_pct": 0.0,
        }

    unique_count = len(rows)
    top_share_pct = _to_float(rows[0].get("loss_share_pct"), 0.0)
    top3_share_pct = sum(_to_float(item.get("loss_share_pct"), 0.0) for item in rows[:3])

    if unique_count <= 1:
        level = "single"
        label = "단일 집중"
    elif top_share_pct >= 60.0 or unique_count <= 2 or top3_share_pct >= 90.0:
        level = "concentrated"
        label = "집중형"
    elif unique_count >= 5 and top_share_pct <= 35.0 and top3_share_pct <= 75.0:
        level = "broad"
        label = "분산형"
    else:
        level = "mixed"
        label = "혼합형"

    return {
        "level": level,
        "label": label,
        "unique_count": unique_count,
        "top_share_pct": round(top_share_pct, 2),
        "top3_share_pct": round(top3_share_pct, 2),
    }


def _strategy_issue_bias(symbol_distribution: dict[str, Any], sector_distribution: dict[str, Any]) -> tuple[str, str]:
    symbol_level = str(symbol_distribution.get("level") or "unknown")
    sector_level = str(sector_distribution.get("level") or "unknown")

    if symbol_level == "broad" and sector_level == "broad":
        return "broad", "전략 전반 이슈"
    if symbol_level in {"single", "concentrated"} or sector_level in {"single", "concentrated"}:
        return "concentrated", "특정 종목/섹터 집중"
    if symbol_level == "unknown" and sector_level == "unknown":
        return "unknown", "판정 보류"
    return "mixed", "혼합형"


def _build_reason_concentration_verdicts(
    trades: list[dict[str, Any]],
    reason_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []

    for reason_row in reason_rows:
        gross_loss_pct = _to_float(reason_row.get("gross_loss_pct"), 0.0)
        if gross_loss_pct <= 0:
            continue

        reason_key = str(reason_row.get("key") or "unknown")
        reason_loss_trades = [
            trade
            for trade in trades
            if _to_float(trade.get("pnl_pct"), 0.0) < 0
            and _normalize_exit_reason(trade.get("reason"))[0] == reason_key
        ]
        if not reason_loss_trades:
            continue

        symbol_rows = _build_scope_weakness_rows(reason_loss_trades, scope="symbol")
        sector_rows = _build_scope_weakness_rows(reason_loss_trades, scope="sector")
        symbol_distribution = _classify_concentration(symbol_rows)
        sector_distribution = _classify_concentration(sector_rows)
        bias, bias_label = _strategy_issue_bias(symbol_distribution, sector_distribution)
        top_symbol = symbol_rows[0] if symbol_rows else None
        top_sector = sector_rows[0] if sector_rows else None

        if bias == "broad":
            summary = (
                f"{reason_row['label']} 손실이 {symbol_distribution['unique_count']}개 종목 · {sector_distribution['unique_count']}개 섹터에 퍼져 있어 "
                "전략 exit rule 점검이 먼저입니다."
            )
        elif bias == "concentrated":
            focused_parts = []
            if top_symbol:
                focused_parts.append(str(top_symbol.get("label") or "미상 종목"))
            if top_sector:
                focused_parts.append(str(top_sector.get("label") or "미분류"))
            focus_text = " / ".join(focused_parts) if focused_parts else "특정 구간"
            summary = (
                f"{reason_row['label']} 손실은 {focus_text} 쏠림이 커서 "
                "개별 종목·섹터 편향 가능성이 큽니다."
            )
        else:
            summary = (
                f"{reason_row['label']} 손실은 일부 집중과 일부 분산이 섞여 있어 "
                "룰 자체와 대상 편향을 같이 봐야 합니다."
            )

        verdicts.append(
            {
                "key": reason_key,
                "label": reason_row.get("label") or reason_key,
                "count": int(reason_row.get("count", 0) or 0),
                "gross_loss_pct": round(gross_loss_pct, 4),
                "loss_share_pct": round(_to_float(reason_row.get("loss_share_pct"), 0.0), 2),
                "symbol_count": int(symbol_distribution.get("unique_count", 0) or 0),
                "sector_count": int(sector_distribution.get("unique_count", 0) or 0),
                "symbol_distribution_level": symbol_distribution.get("level"),
                "symbol_distribution_label": symbol_distribution.get("label"),
                "symbol_top_share_pct": round(_to_float(symbol_distribution.get("top_share_pct"), 0.0), 2),
                "sector_distribution_level": sector_distribution.get("level"),
                "sector_distribution_label": sector_distribution.get("label"),
                "sector_top_share_pct": round(_to_float(sector_distribution.get("top_share_pct"), 0.0), 2),
                "strategy_issue_bias": bias,
                "strategy_issue_label": bias_label,
                "top_symbols": symbol_rows[:3],
                "top_sectors": sector_rows[:3],
                "summary": summary,
            }
        )

    bias_priority = {"concentrated": 2, "broad": 1, "mixed": 0, "unknown": -1}
    verdicts.sort(
        key=lambda item: (
            bias_priority.get(str(item.get("strategy_issue_bias") or "unknown"), -1),
            float(item.get("gross_loss_pct", 0.0)),
            float(item.get("loss_share_pct", 0.0)),
        ),
        reverse=True,
    )
    return verdicts


def _build_exit_reason_analysis(trades: list[dict[str, Any]], *, segment_label: str | None = None) -> dict[str, Any]:
    segment_label = str(segment_label or "").strip()
    total_trades = len(trades)
    total_gross_loss = 0.0
    total_gross_profit = 0.0
    buckets: dict[str, dict[str, Any]] = {}

    for trade in trades:
        pnl_pct = _to_float(trade.get("pnl_pct"), 0.0)
        holding_days = _to_float(trade.get("holding_days"), 0.0)
        raw_reason = str(trade.get("reason") or "unknown")
        key, label, category = _normalize_exit_reason(raw_reason)

        bucket = buckets.setdefault(
            key,
            {
                "key": key,
                "label": label,
                "category": category,
                "count": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl_pct": 0.0,
                "gross_profit_pct": 0.0,
                "gross_loss_pct": 0.0,
                "pnl_values": [],
                "holding_days_values": [],
                "win_values": [],
                "loss_values": [],
                "raw_reason_counts": {},
            },
        )
        bucket["count"] += 1
        bucket["net_pnl_pct"] += pnl_pct
        bucket["pnl_values"].append(pnl_pct)
        if holding_days > 0:
            bucket["holding_days_values"].append(holding_days)

        raw_counts = bucket["raw_reason_counts"]
        raw_counts[raw_reason] = int(raw_counts.get(raw_reason, 0)) + 1

        if pnl_pct > 0:
            bucket["wins"] += 1
            bucket["gross_profit_pct"] += pnl_pct
            bucket["win_values"].append(pnl_pct)
            total_gross_profit += pnl_pct
        elif pnl_pct < 0:
            bucket["losses"] += 1
            bucket["gross_loss_pct"] += abs(pnl_pct)
            bucket["loss_values"].append(pnl_pct)
            total_gross_loss += abs(pnl_pct)

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        count = max(1, int(bucket["count"]))
        avg_pnl = _mean(bucket["pnl_values"])
        row = {
            "key": bucket["key"],
            "label": bucket["label"],
            "category": bucket["category"],
            "count": int(bucket["count"]),
            "share_of_trades_pct": round((bucket["count"] / max(1, total_trades)) * 100.0, 2),
            "net_pnl_pct": round(bucket["net_pnl_pct"], 4),
            "gross_pnl_pct": round(bucket["net_pnl_pct"], 4),
            "gross_profit_pct": round(bucket["gross_profit_pct"], 4),
            "gross_loss_pct": round(bucket["gross_loss_pct"], 4),
            "profit_share_pct": round((bucket["gross_profit_pct"] / total_gross_profit) * 100.0, 2) if total_gross_profit > 0 else 0.0,
            "loss_share_pct": round((bucket["gross_loss_pct"] / total_gross_loss) * 100.0, 2) if total_gross_loss > 0 else 0.0,
            "avg_pnl_pct": round(avg_pnl, 4),
            "median_pnl_pct": round(_median(bucket["pnl_values"]), 4),
            "avg_win_pct": round(_mean(bucket["win_values"]), 4),
            "avg_loss_pct": round(_mean(bucket["loss_values"]), 4),
            "win_rate_pct": round((bucket["wins"] / count) * 100.0, 2),
            "loss_rate_pct": round((bucket["losses"] / count) * 100.0, 2),
            "avg_holding_days": round(_mean(bucket["holding_days_values"]), 2),
            "raw_reasons": [
                raw_reason
                for raw_reason, _count in sorted(
                    bucket["raw_reason_counts"].items(),
                    key=lambda item: (-int(item[1]), str(item[0])),
                )
            ],
        }
        rows.append(row)

    rows.sort(
        key=lambda item: (
            float(item.get("gross_loss_pct", 0.0)),
            -float(item.get("gross_profit_pct", 0.0)),
            int(item.get("count", 0)),
            -float(item.get("avg_pnl_pct", 0.0)),
        ),
        reverse=True,
    )

    symbol_weaknesses = _build_scope_weakness_rows(trades, scope="symbol")
    sector_weaknesses = _build_scope_weakness_rows(trades, scope="sector")
    concentration_verdicts = _build_reason_concentration_verdicts(trades, rows)

    loss_focus = [item for item in rows if float(item.get("gross_loss_pct", 0.0)) > 0][:3]
    profit_focus = [item for item in sorted(rows, key=lambda item: float(item.get("gross_profit_pct", 0.0)), reverse=True) if float(item.get("gross_profit_pct", 0.0)) > 0][:2]

    prefix = f"{segment_label} " if segment_label else ""
    summary_lines: list[str] = []
    if not rows:
        summary_lines.append(f"{prefix}청산 사유 데이터가 아직 없습니다.")
    else:
        if loss_focus:
            top_loss = loss_focus[0]
            summary_lines.append(
                f"{prefix}{top_loss['label']} 쪽 손실이 큽니다. 총손실 비중 {top_loss['loss_share_pct']:.1f}% · 평균 {top_loss['avg_pnl_pct']:.2f}%"
            )
        if len(loss_focus) >= 2:
            secondary_loss = loss_focus[1]
            summary_lines.append(
                f"{prefix}{secondary_loss['label']}도 약점입니다. {secondary_loss['count']}건 · 평균 {secondary_loss['avg_pnl_pct']:.2f}%"
            )
        if profit_focus:
            top_profit = profit_focus[0]
            summary_lines.append(
                f"{prefix}{top_profit['label']}은 이익 잠금 역할입니다. 이익 기여 {top_profit['profit_share_pct']:.1f}%"
            )
        if concentration_verdicts:
            summary_lines.append(f"{prefix}{str(concentration_verdicts[0].get('summary') or '')}")

    focus_items: list[dict[str, Any]] = []
    for row in loss_focus:
        focus_items.append(
            {
                "kind": "loss_driver",
                "key": row["key"],
                "label": row["label"],
                "count": row["count"],
                "summary": f"{row['label']} {row['count']}건 · 손실 비중 {row['loss_share_pct']:.1f}% · 평균 {row['avg_pnl_pct']:.2f}%",
                "gross_loss_pct": row["gross_loss_pct"],
                "loss_share_pct": row["loss_share_pct"],
                "avg_pnl_pct": row["avg_pnl_pct"],
            }
        )
    for row in profit_focus[:1]:
        focus_items.append(
            {
                "kind": "profit_capture",
                "key": row["key"],
                "label": row["label"],
                "count": row["count"],
                "summary": f"{row['label']} {row['count']}건 · 이익 기여 {row['profit_share_pct']:.1f}% · 평균 {row['avg_pnl_pct']:.2f}%",
                "gross_profit_pct": row["gross_profit_pct"],
                "profit_share_pct": row["profit_share_pct"],
                "avg_pnl_pct": row["avg_pnl_pct"],
            }
        )

    return {
        "trade_count": total_trades,
        "gross_loss_pct": round(total_gross_loss, 4),
        "gross_profit_pct": round(total_gross_profit, 4),
        "net_pnl_pct": round(sum(_to_float(trade.get("pnl_pct"), 0.0) for trade in trades), 4),
        "reasons": rows,
        "symbol_weaknesses": symbol_weaknesses[:6],
        "sector_weaknesses": sector_weaknesses[:6],
        "concentration_verdicts": concentration_verdicts[:6],
        "focus_items": focus_items,
        "summary_lines": summary_lines,
    }


def _build_exit_reason_cluster_summary(segment_analysis: dict[str, dict[str, Any]]) -> dict[str, Any]:
    segment_labels = {"train": "학습", "validation": "검증", "oos": "OOS"}
    segment_priority = {"train": 0, "validation": 1, "oos": 2}

    weakness_clusters: list[dict[str, Any]] = []
    persistent: dict[str, dict[str, Any]] = {}

    for segment, analysis in segment_analysis.items():
        rows = analysis.get("reasons") if isinstance(analysis.get("reasons"), list) else []
        for row in rows:
            gross_loss_pct = _to_float(row.get("gross_loss_pct"), 0.0)
            if gross_loss_pct <= 0:
                continue

            weakness_clusters.append(
                {
                    "segment": segment,
                    "segment_label": segment_labels.get(segment, segment),
                    "key": row.get("key"),
                    "label": row.get("label"),
                    "count": int(row.get("count", 0) or 0),
                    "gross_loss_pct": round(gross_loss_pct, 4),
                    "loss_share_pct": round(_to_float(row.get("loss_share_pct"), 0.0), 2),
                    "avg_pnl_pct": round(_to_float(row.get("avg_pnl_pct"), 0.0), 4),
                    "summary": f"{segment_labels.get(segment, segment)}에서 {row.get('label')} {int(row.get('count', 0) or 0)}건 · 손실 비중 {_to_float(row.get('loss_share_pct'), 0.0):.1f}%",
                }
            )

            if segment not in {"validation", "oos"}:
                continue

            key = str(row.get("key") or "unknown")
            bucket = persistent.setdefault(
                key,
                {
                    "key": key,
                    "label": row.get("label") or key,
                    "segments": [],
                    "combined_gross_loss_pct": 0.0,
                    "combined_count": 0,
                    "max_loss_share_pct": 0.0,
                },
            )
            bucket["segments"].append(segment)
            bucket["combined_gross_loss_pct"] += gross_loss_pct
            bucket["combined_count"] += int(row.get("count", 0) or 0)
            bucket["max_loss_share_pct"] = max(bucket["max_loss_share_pct"], _to_float(row.get("loss_share_pct"), 0.0))

    weakness_clusters.sort(
        key=lambda item: (
            segment_priority.get(str(item.get("segment") or "train"), 0),
            float(item.get("loss_share_pct", 0.0)),
            float(item.get("gross_loss_pct", 0.0)),
            int(item.get("count", 0)),
        ),
        reverse=True,
    )

    persistent_negative_reasons = [
        {
            **item,
            "segments": sorted(set(item["segments"]), key=lambda segment: segment_priority.get(segment, 0)),
            "combined_gross_loss_pct": round(item["combined_gross_loss_pct"], 4),
            "max_loss_share_pct": round(item["max_loss_share_pct"], 2),
            "summary": f"검증/OOS에서 {item['label']} 약점이 반복됩니다. 누적 손실 {item['combined_gross_loss_pct']:.2f}% · 최대 비중 {item['max_loss_share_pct']:.1f}%",
        }
        for item in persistent.values()
        if len(set(item["segments"])) >= 2
    ]
    persistent_negative_reasons.sort(
        key=lambda item: (
            float(item.get("combined_gross_loss_pct", 0.0)),
            float(item.get("max_loss_share_pct", 0.0)),
            int(item.get("combined_count", 0)),
        ),
        reverse=True,
    )

    headlines: list[str] = []
    if weakness_clusters:
        top_cluster = weakness_clusters[0]
        headlines.append(
            f"{top_cluster['segment_label']} 약점은 {top_cluster['label']}입니다. 손실 비중 {top_cluster['loss_share_pct']:.1f}%"
        )
    if persistent_negative_reasons:
        headlines.append(str(persistent_negative_reasons[0].get("summary") or ""))
    concentration_headline = None
    for segment in ("oos", "validation"):
        verdicts = segment_analysis.get(segment, {}).get("concentration_verdicts")
        if isinstance(verdicts, list) and verdicts:
            concentration_headline = str(verdicts[0].get("summary") or "")
            if concentration_headline:
                break
    if concentration_headline:
        headlines.append(concentration_headline)

    return {
        "weakness_clusters": weakness_clusters[:8],
        "persistent_negative_reasons": persistent_negative_reasons[:5],
        "headlines": headlines,
    }


def _walk_forward_positive_ratio(windows: list[dict[str, Any]]) -> float:
    if not windows:
        return 0.0
    positive = sum(
        1
        for item in windows
        if _to_float((item.get("metrics") or {}).get("total_return_pct"), 0.0) > 0.0
    )
    return positive / len(windows)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pct = max(0.0, min(100.0, percentile)) / 100.0
    position = (len(ordered) - 1) * pct
    lower = int(floor(position))
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight



def _tail_risk_snapshot(trades: list[dict[str, Any]]) -> dict[str, float]:
    pnl_pct = [
        _to_float(trade.get("pnl_pct"))
        for trade in trades
        if trade.get("pnl_pct") is not None
    ]
    if not pnl_pct:
        return {
            "median_return_pct": 0.0,
            "return_p01_pct": 0.0,
            "return_p05_pct": 0.0,
            "expected_shortfall_5_pct": 0.0,
            "worst_case_return_pct": 0.0,
            "loss_rate_pct": 0.0,
        }

    p05 = _percentile(pnl_pct, 5)
    tail_bucket = [value for value in pnl_pct if value <= p05] or [p05]
    losses = [value for value in pnl_pct if value < 0.0]
    return {
        "median_return_pct": round(_percentile(pnl_pct, 50), 4),
        "return_p01_pct": round(_percentile(pnl_pct, 1), 4),
        "return_p05_pct": round(p05, 4),
        "expected_shortfall_5_pct": round(sum(tail_bucket) / len(tail_bucket), 4),
        "worst_case_return_pct": round(min(pnl_pct), 4),
        "loss_rate_pct": round((len(losses) / len(pnl_pct)) * 100.0, 4),
    }



def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))



def _score_components(metrics: dict[str, Any], tail_risk: dict[str, float]) -> dict[str, float]:
    sharpe = _to_float(metrics.get("sharpe"), 0.0)
    avg_return_pct = _to_float(
        metrics.get("avg_trade_return_pct", metrics.get("cagr_pct", metrics.get("total_return_pct", 0.0))),
        0.0,
    )
    win_rate_pct = _to_float(metrics.get("win_rate_pct"), 0.0)
    trade_count = int(metrics.get("trade_count", 0) or 0)
    max_dd = _to_float(metrics.get("max_drawdown_pct"), 0.0)

    sharpe_component = _clamp(sharpe * 22.0, -24.0, 55.0)
    return_component = _clamp(avg_return_pct * 1.8, -16.0, 28.0)
    win_rate_component = _clamp((win_rate_pct - 50.0) * 0.7, -15.0, 15.0)

    if trade_count >= 40:
        sample_component = 10.0
    elif trade_count >= 30:
        sample_component = 5.0
    elif trade_count >= 20:
        sample_component = -4.0
    else:
        sample_component = -18.0

    if max_dd < -30.0:
        drawdown_component = -28.0
    elif max_dd < -20.0:
        drawdown_component = -16.0
    elif max_dd < -12.0:
        drawdown_component = -6.0
    else:
        drawdown_component = 4.0

    if tail_risk["expected_shortfall_5_pct"] < -20.0 or tail_risk["return_p05_pct"] < -15.0:
        tail_component = -26.0
    elif tail_risk["expected_shortfall_5_pct"] < -14.0 or tail_risk["return_p05_pct"] < -10.0:
        tail_component = -14.0
    elif tail_risk["expected_shortfall_5_pct"] < -8.0 or tail_risk["return_p05_pct"] < -6.0:
        tail_component = -6.0
    else:
        tail_component = 4.0

    total_score = (
        sharpe_component
        + return_component
        + win_rate_component
        + sample_component
        + drawdown_component
        + tail_component
    )
    return {
        "sharpe_component": round(sharpe_component, 2),
        "return_component": round(return_component, 2),
        "win_rate_component": round(win_rate_component, 2),
        "sample_component": round(sample_component, 2),
        "drawdown_component": round(drawdown_component, 2),
        "tail_component": round(tail_component, 2),
        "total_score": round(total_score, 2),
    }



def _build_strategy_scorecard(metrics: dict[str, Any], trades: list[dict[str, Any]]) -> dict[str, Any]:
    tail_risk = _tail_risk_snapshot(trades)
    components = _score_components(metrics, tail_risk)
    return {
        "composite_score": components.get("total_score", 0.0),
        "components": components,
        "tail_risk": tail_risk,
    }



def _classify_walk_forward_reliability(
    oos_metrics: dict[str, Any],
    *,
    positive_window_ratio: float,
) -> str:
    assessment = classify_walk_forward_reliability(
        trade_count=int(oos_metrics.get("trade_count", 0) or 0),
        profit_factor=_to_float(oos_metrics.get("profit_factor"), 0.0),
        sharpe=_to_float(oos_metrics.get("sharpe"), 0.0),
        total_return_pct=_to_float(oos_metrics.get("total_return_pct"), 0.0),
        positive_window_ratio=positive_window_ratio,
    )
    return assessment.label


def _diagnose_walk_forward_result(payload: dict[str, Any]) -> dict[str, Any]:
    oos_metrics = payload.get("segments", {}).get("oos") or {}
    summary = payload.get("summary") or {}
    positive_window_ratio = _to_float(summary.get("positive_window_ratio"), 0.0)
    return explain_walk_forward_reliability(
        trade_count=int(oos_metrics.get("trade_count", 0) or 0),
        profit_factor=_to_float(oos_metrics.get("profit_factor"), 0.0),
        sharpe=_to_float(oos_metrics.get("sharpe"), 0.0),
        total_return_pct=_to_float(oos_metrics.get("total_return_pct"), 0.0),
        positive_window_ratio=positive_window_ratio,
    )


def _query_number_or_none(query: dict[str, list[str]], name: str) -> float | None:
    raw = (query.get(name, [""])[0] or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _clone_query(query: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: list(values) for key, values in query.items()}


def _apply_query_patch(query: dict[str, list[str]], patch: dict[str, float | int | None]) -> dict[str, list[str]]:
    mutated = _clone_query(query)
    for key, value in patch.items():
        if value is None:
            mutated[key] = [""]
        elif isinstance(value, int) and not isinstance(value, bool):
            mutated[key] = [str(value)]
        else:
            mutated[key] = [f"{float(value):.4f}".rstrip("0").rstrip(".")]
    return mutated


def _append_research_probe(
    probes: list[dict[str, Any]],
    seen: set[tuple[tuple[str, str], ...]],
    *,
    label: str,
    rationale: str,
    patch: dict[str, float | int | None],
) -> None:
    key = tuple(sorted((name, "" if value is None else str(value)) for name, value in patch.items()))
    if not patch or key in seen:
        return
    seen.add(key)
    probes.append({"label": label, "rationale": rationale, "patch": patch})


def _bounded_local_research_probes(query: dict[str, list[str]], diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    blocker_metrics = {str(item.get("metric") or "") for item in diagnosis.get("blockers", [])}
    needs_more_samples = bool({"trade_count", "positive_window_ratio"} & blocker_metrics)
    needs_better_quality = bool({"profit_factor", "sharpe", "total_return_pct"} & blocker_metrics)

    def add_shift(name: str, delta: float, *, label: str, rationale: str, minimum: float | None = None, maximum: float | None = None, integer: bool = False) -> None:
        current = _query_number_or_none(query, name)
        if current is None:
            return
        next_value = current + delta
        if minimum is not None:
            next_value = max(minimum, next_value)
        if maximum is not None:
            next_value = min(maximum, next_value)
        if integer:
            next_value = int(round(next_value))
            if int(round(current)) == next_value:
                return
        elif abs(next_value - current) < 1e-9:
            return
        _append_research_probe(probes, seen, label=label, rationale=rationale, patch={name: next_value})

    if needs_more_samples:
        add_shift("rsi_min", -4.0, label="RSI 하한 완화", rationale="진입 조건을 조금 풀어서 표본 수를 늘리는 probe", minimum=10.0, maximum=90.0)
        add_shift("rsi_max", 4.0, label="RSI 상한 완화", rationale="진입 허용 범위를 넓혀 거래 수와 윈도우 일관성을 확인", minimum=10.0, maximum=90.0)
        add_shift("volume_ratio_min", -0.2, label="거래량 필터 완화", rationale="거래량 필터를 약간 낮춰 희소성을 줄이는 probe", minimum=0.5, maximum=5.0)
        add_shift("adx_min", -5.0, label="ADX 필터 완화", rationale="추세 강도 필터를 완화해 표본 수 증가 여부를 확인", minimum=5.0, maximum=40.0)
        add_shift("mfi_min", -10.0, label="MFI 하한 완화", rationale="오버필터링 여부를 점검하는 local probe", minimum=0.0, maximum=100.0)
        add_shift("mfi_max", 10.0, label="MFI 상한 완화", rationale="진입 범위를 넓혀 검증 표본 확장 가능성 확인", minimum=0.0, maximum=100.0)

    if needs_better_quality:
        add_shift("max_holding_days", -5.0, label="보유 기간 단축", rationale="약한 포지션을 더 빨리 정리하면 PF/샤프가 나아지는지 확인", minimum=1.0, maximum=180.0, integer=True)
        add_shift("stop_loss_pct", -1.5, label="손절 타이트닝", rationale="낙폭과 꼬리손실을 줄여 품질 지표 개선 여부 확인", minimum=1.0, maximum=50.0)
        add_shift("take_profit_pct", -4.0, label="익절 조기화", rationale="수익 실현을 빠르게 해서 PF 개선 가능성 확인", minimum=1.0, maximum=100.0)
        add_shift("take_profit_pct", 4.0, label="익절 여유 확대", rationale="추세 수익을 더 길게 가져가 수익률 개선 가능성 확인", minimum=1.0, maximum=100.0)

    if needs_more_samples and needs_better_quality:
        _append_research_probe(
            probes,
            seen,
            label="진입 범위 완화 + 보유 단축",
            rationale="표본 수를 늘리되 약한 포지션은 빨리 정리하는 2축 probe",
            patch={
                "rsi_min": max(10.0, (_query_number_or_none(query, "rsi_min") or 45.0) - 4.0),
                "rsi_max": min(90.0, (_query_number_or_none(query, "rsi_max") or 65.0) + 4.0),
                "max_holding_days": int(max(1.0, (_query_number_or_none(query, "max_holding_days") or 15.0) - 5.0)),
            },
        )

    return probes[:10]


def _label_rank(label: str) -> int:
    return {"insufficient": 0, "low": 1, "medium": 2, "high": 3}.get(label, 0)


def _summarize_patch(base_query: dict[str, list[str]], patch: dict[str, float | int | None]) -> list[str]:
    lines: list[str] = []
    for key, value in patch.items():
        current = (base_query.get(key, [""])[0] or "").strip() or "미설정"
        target = "미설정" if value is None else str(value)
        lines.append(f"{key}: {current} → {target}")
    return lines


def _run_local_research(query: dict[str, list[str]], base_payload: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    probes = _bounded_local_research_probes(query, diagnosis)
    evaluated: list[dict[str, Any]] = []
    errors: list[str] = []
    base_rank = _label_rank(str(diagnosis.get("label") or ""))

    for probe in probes:
        mutated_query = _apply_query_patch(query, probe["patch"])
        try:
            payload = run_walk_forward_validation(mutated_query)
        except Exception as exc:  # pragma: no cover - defensive route handling
            errors.append(f"{probe['label']}: {exc}")
            continue
        if payload.get("error"):
            errors.append(f"{probe['label']}: {payload['error']}")
            continue

        probe_diagnosis = _diagnose_walk_forward_result(payload)
        oos = payload.get("segments", {}).get("oos") or {}
        evaluated.append(
            {
                "label": str(probe_diagnosis.get("label") or "low"),
                "reached_target": _label_rank(str(probe_diagnosis.get("label") or "")) >= _label_rank("medium"),
                "improvement": _label_rank(str(probe_diagnosis.get("label") or "")) - base_rank,
                "probe_label": probe["label"],
                "rationale": probe["rationale"],
                "patch": probe["patch"],
                "changes": _summarize_patch(query, probe["patch"]),
                "diagnosis": probe_diagnosis,
                "metrics": {
                    "trade_count": int(oos.get("trade_count", 0) or 0),
                    "profit_factor": round(_to_float(oos.get("profit_factor"), 0.0), 4),
                    "sharpe": round(_to_float(oos.get("sharpe"), 0.0), 4),
                    "total_return_pct": round(_to_float(oos.get("total_return_pct"), 0.0), 4),
                    "positive_window_ratio": round(_to_float((payload.get("summary") or {}).get("positive_window_ratio"), 0.0), 4),
                },
            }
        )

    evaluated.sort(
        key=lambda item: (
            1 if item["reached_target"] else 0,
            _label_rank(item["label"]),
            item["metrics"].get("total_return_pct", 0.0),
            item["metrics"].get("sharpe", 0.0),
            item["metrics"].get("profit_factor", 0.0),
        ),
        reverse=True,
    )

    best = evaluated[0] if evaluated else None
    return {
        "target_label": "medium",
        "base_label": str(diagnosis.get("label") or "low"),
        "trials_run": len(evaluated),
        "trial_limit": len(probes),
        "improvement_found": any(bool(item.get("reached_target")) for item in evaluated),
        "best_label": str(best.get("label")) if best else str(diagnosis.get("label") or "low"),
        "suggestions": evaluated[:5],
        "errors": errors[:5],
        "notes": [
            "이 탐색은 전체 최적화가 아니라 현재 설정 주변의 작은 단일/이중 변경만 시험한 local probe입니다.",
            "target_label은 medium이며, 근처 파라미터만 다시 평가합니다.",
        ],
    }


def _regime_stats_from_curve(equity_curve: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if len(equity_curve) < 25:
        return {}
    regimes: dict[str, list[float]] = {"risk_on": [], "risk_off": []}
    equities = [_to_float(item.get("equity")) for item in equity_curve]
    for idx in range(20, len(equities) - 1):
        base = equities[idx - 20]
        curr = equities[idx]
        nxt = equities[idx + 1]
        if base <= 0 or curr <= 0:
            continue
        trend = (curr / base) - 1.0
        daily = (nxt / curr) - 1.0 if curr > 0 else 0.0
        key = "risk_on" if trend >= 0 else "risk_off"
        regimes[key].append(daily)

    result: dict[str, dict[str, Any]] = {}
    for key, values in regimes.items():
        if not values:
            continue
        avg = sum(values) / len(values)
        result[key] = {
            "samples": len(values),
            "avg_daily_return_pct": round(avg * 100.0, 4),
            "annualized_return_pct": round(((1.0 + avg) ** 252 - 1.0) * 100.0, 2),
        }
    return result


def run_backtest_with_extended_metrics(query: dict[str, list[str]], *, auto_optimize: bool = True) -> dict[str, Any]:
    payload = get_backtest_service().run_with_optional_optimization(query, auto_optimize=auto_optimize)
    if not isinstance(payload, dict):
        return {"error": "invalid_backtest_payload"}

    equity_curve = payload.get("equity_curve") if isinstance(payload.get("equity_curve"), list) else []
    trades = payload.get("trades") if isinstance(payload.get("trades"), list) else []

    payload = dict(payload)
    payload.setdefault("metrics", {})
    payload["metrics"].update(_segment_metrics(equity_curve, trades))
    payload["metrics"]["exit_reason_stats"] = _exit_reason_stats(trades)
    payload["metrics"]["exit_reason_analysis"] = _build_exit_reason_analysis(trades, segment_label="백테스트")
    payload["metrics"]["regime_stats"] = _regime_stats_from_curve(equity_curve)
    payload["reliability_diagnostic"] = build_reliability_diagnostic(
        trade_count=int(payload["metrics"].get("trade_count", 0) or 0),
        validation_signals=int(payload["metrics"].get("trade_count", 0) or 0),
        validation_sharpe=_to_float(payload["metrics"].get("sharpe"), 0.0),
        max_drawdown_pct=_to_float(payload["metrics"].get("max_drawdown_pct"), 0.0),
        target_label="medium",
    )
    payload["scorecard"] = _build_strategy_scorecard(payload["metrics"], trades)
    return payload


def _build_light_validation_payload(backtest_payload: dict[str, Any]) -> dict[str, Any]:
    metrics = backtest_payload.get("metrics") if isinstance(backtest_payload.get("metrics"), dict) else {}
    scorecard = backtest_payload.get("scorecard") if isinstance(backtest_payload.get("scorecard"), dict) else {}
    reliability_diagnostic = backtest_payload.get("reliability_diagnostic") if isinstance(backtest_payload.get("reliability_diagnostic"), dict) else {}
    trade_count = int(metrics.get("trade_count", 0) or 0)
    positive_window_ratio = 1.0 if trade_count > 0 and _to_float(metrics.get("total_return_pct"), 0.0) > 0.0 else 0.0
    return {
        "ok": True,
        "config": {
            "mode": "light",
            "walk_forward": False,
        },
        "segments": {
            "oos": {
                **metrics,
                "strategy_scorecard": scorecard,
                "exit_reason_analysis": metrics.get("exit_reason_analysis") if isinstance(metrics.get("exit_reason_analysis"), dict) else {},
            },
        },
        "rolling_windows": [],
        "summary": {
            "windows": 1 if trade_count > 0 else 0,
            "positive_windows": 1 if positive_window_ratio > 0 else 0,
            "positive_window_ratio": positive_window_ratio,
            "oos_reliability": classify_walk_forward_reliability(
                trade_count=trade_count,
                profit_factor=_to_float(metrics.get("profit_factor"), 0.0),
                sharpe=_to_float(metrics.get("sharpe"), 0.0),
                total_return_pct=_to_float(metrics.get("total_return_pct"), 0.0),
                positive_window_ratio=positive_window_ratio,
            ).label,
            "reliability_diagnostic": reliability_diagnostic,
            "composite_score": scorecard.get("composite_score"),
            "exit_reason_stats": metrics.get("exit_reason_stats") if isinstance(metrics.get("exit_reason_stats"), dict) else {},
            "exit_reason_analysis": metrics.get("exit_reason_analysis") if isinstance(metrics.get("exit_reason_analysis"), dict) else {},
            "regime_stats": metrics.get("regime_stats") if isinstance(metrics.get("regime_stats"), dict) else {},
        },
        "scorecard": scorecard,
        "source": "backtest_light",
    }


def run_validation_diagnostics(query: dict[str, list[str]], *, mode: str = "full") -> dict[str, Any]:
    normalized_mode = str(mode or "full").strip().lower()
    if normalized_mode == "light":
        base_backtest = run_backtest_with_extended_metrics(query, auto_optimize=False)
        if not isinstance(base_backtest, dict):
            return {"ok": False, "error": "invalid_validation_payload"}
        if base_backtest.get("error"):
            return {"ok": False, **base_backtest}
        validation_payload = _build_light_validation_payload(base_backtest)
        diagnosis = _diagnose_walk_forward_result(validation_payload)
        return {
            "ok": True,
            "validation": validation_payload,
            "diagnosis": diagnosis,
            "research": {
                "target_label": "medium",
                "base_label": str(diagnosis.get("label") or "low"),
                "trials_run": 0,
                "trial_limit": 0,
                "improvement_found": False,
                "best_label": str(diagnosis.get("label") or "low"),
                "suggestions": [],
                "errors": [],
                "notes": [
                    "light diagnostics mode: revalidate에서는 full walk-forward 대신 단일 백테스트 기반 핵심 지표만 사용합니다.",
                    "전체 walk-forward 및 local probe 탐색은 별도 validation 경로에서 실행하세요.",
                ],
            },
        }

    base_payload = run_walk_forward_validation(query)
    if not isinstance(base_payload, dict):
        return {"ok": False, "error": "invalid_validation_payload"}
    if base_payload.get("error"):
        return {"ok": False, **base_payload}

    diagnosis = _diagnose_walk_forward_result(base_payload)
    research = _run_local_research(query, base_payload, diagnosis)
    return {
        "ok": True,
        "validation": base_payload,
        "diagnosis": diagnosis,
        "research": research,
    }


def _compute_walk_forward_payload(base_cfg, query: dict[str, list[str]]) -> dict[str, Any]:
    base_result = get_backtest_service().run(base_cfg)

    equity_curve = base_result.get("equity_curve") if isinstance(base_result.get("equity_curve"), list) else []
    trades = base_result.get("trades") if isinstance(base_result.get("trades"), list) else []
    if len(equity_curve) < 60:
        return {
            "error": "insufficient_equity_curve_for_walk_forward",
            "min_points": 60,
            "points": len(equity_curve),
        }

    n = len(equity_curve)
    requested_training_days = _query_int(query, "training_days", 180, 30, 3650)
    requested_validation_days = _query_int(query, "validation_days", 60, 20, 3650)
    walk_forward_enabled = _query_bool(query, "walk_forward", True)

    effective_training_days = min(requested_training_days, max(30, n - 40))
    effective_validation_days = min(requested_validation_days, max(20, n - 20))
    oos_days = effective_validation_days
    required_points = effective_training_days + effective_validation_days + oos_days
    clipped = False
    clipping_reason = None
    if required_points > n:
        clipped = True
        clipping_reason = "insufficient_equity_curve_length"
        oos_days = max(20, min(effective_validation_days, n // 5))
        effective_validation_days = max(20, min(effective_validation_days, max(20, (n - oos_days) // 3)))
        effective_training_days = max(30, min(effective_training_days, max(30, n - effective_validation_days - oos_days)))

    oos_start = max(0, n - oos_days)
    validation_start = max(0, oos_start - effective_validation_days)
    train_start = max(0, validation_start - effective_training_days)

    train_curve = _slice_by_index(equity_curve, train_start, validation_start)
    validation_curve = _slice_by_index(equity_curve, validation_start, oos_start)
    oos_curve = _slice_by_index(equity_curve, oos_start, n)

    if not train_curve or not validation_curve or not oos_curve:
        train_end = int(n * 0.6)
        val_end = int(n * 0.8)
        train_curve = _slice_by_index(equity_curve, 0, train_end)
        validation_curve = _slice_by_index(equity_curve, train_end, val_end)
        oos_curve = _slice_by_index(equity_curve, val_end, n)

    train_trades = [t for t in trades if train_curve and str(t.get("exit_date") or "") <= str(train_curve[-1].get("date") or "")]
    val_trades = [t for t in trades if (validation_curve and str(validation_curve[0].get("date") or "") <= str(t.get("exit_date") or "") <= str(validation_curve[-1].get("date") or ""))]
    oos_trades = [t for t in trades if (oos_curve and str(t.get("exit_date") or "") >= str(oos_curve[0].get("date") or ""))]

    windows = []
    if walk_forward_enabled:
        window_size = min(n, effective_training_days + effective_validation_days)
        step = max(20, effective_validation_days)
        for start in range(0, max(1, n - window_size + 1), step):
            train_end = start + effective_training_days
            eval_end = min(n, train_end + effective_validation_days)
            segment = _slice_by_index(equity_curve, train_end, eval_end)
            if len(segment) < 20:
                continue
            start_date = str(segment[0].get("date") or "")
            end_date = str(segment[-1].get("date") or "")
            segment_trades = [t for t in trades if start_date <= str(t.get("exit_date") or "") <= end_date]
            windows.append(
                {
                    "train_start_date": str(equity_curve[start].get("date") or "") if start < len(equity_curve) else "",
                    "train_end_date": str(equity_curve[max(start, train_end - 1)].get("date") or "") if train_end - 1 < len(equity_curve) else "",
                    "start_date": start_date,
                    "end_date": end_date,
                    "metrics": _segment_metrics(segment, segment_trades),
                }
            )
    else:
        start_date = str(oos_curve[0].get("date") or "") if oos_curve else ""
        end_date = str(oos_curve[-1].get("date") or "") if oos_curve else ""
        windows.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "metrics": _segment_metrics(oos_curve, oos_trades),
            }
        )

    train_metrics = _segment_metrics(train_curve, train_trades)
    validation_metrics = _segment_metrics(validation_curve, val_trades)
    oos_metrics = _segment_metrics(oos_curve, oos_trades)
    train_scorecard = _build_strategy_scorecard(train_metrics, train_trades)
    validation_scorecard = _build_strategy_scorecard(validation_metrics, val_trades)
    oos_scorecard = _build_strategy_scorecard(oos_metrics, oos_trades)
    train_exit_reason_analysis = _build_exit_reason_analysis(train_trades, segment_label="학습")
    validation_exit_reason_analysis = _build_exit_reason_analysis(val_trades, segment_label="검증")
    oos_exit_reason_analysis = _build_exit_reason_analysis(oos_trades, segment_label="OOS")
    walk_forward_exit_reason_analysis = {
        "overall": _build_exit_reason_analysis(trades),
        "train": train_exit_reason_analysis,
        "validation": validation_exit_reason_analysis,
        "oos": oos_exit_reason_analysis,
        **_build_exit_reason_cluster_summary(
            {
                "train": train_exit_reason_analysis,
                "validation": validation_exit_reason_analysis,
                "oos": oos_exit_reason_analysis,
            }
        ),
    }
    positive_oos_windows = sum(1 for item in windows if _to_float((item.get("metrics") or {}).get("total_return_pct"), 0.0) > 0)
    positive_window_ratio = round(_walk_forward_positive_ratio(windows), 4)
    reliability = _classify_walk_forward_reliability(
        oos_metrics,
        positive_window_ratio=positive_window_ratio,
    )
    reliability_diagnostic = build_reliability_diagnostic(
        trade_count=int(oos_metrics.get("trade_count", 0) or 0),
        validation_signals=int(oos_metrics.get("trade_count", 0) or 0),
        validation_sharpe=_to_float(oos_metrics.get("sharpe"), 0.0),
        max_drawdown_pct=_to_float(oos_metrics.get("max_drawdown_pct"), 0.0),
        target_label="medium",
    )

    return {
        "ok": True,
        "config": {
            "markets": list(base_cfg.markets),
            "lookback_days": base_cfg.lookback_days,
            "training_days": requested_training_days,
            "validation_days": requested_validation_days,
            "walk_forward": walk_forward_enabled,
            "effective_window": {
                "available_points": n,
                "training_days": effective_training_days,
                "validation_days": effective_validation_days,
                "oos_days": oos_days,
                "clipped": clipped,
                "clipping_reason": clipping_reason,
            },
            "walk_forward_window": {
                "window_size": (effective_training_days + effective_validation_days) if walk_forward_enabled else len(oos_curve),
                "step": max(20, effective_validation_days) if walk_forward_enabled else len(oos_curve),
            },
        },
        "segments": {
            "train": {**train_metrics, "strategy_scorecard": train_scorecard, "exit_reason_analysis": train_exit_reason_analysis},
            "validation": {**validation_metrics, "strategy_scorecard": validation_scorecard, "exit_reason_analysis": validation_exit_reason_analysis},
            "oos": {**oos_metrics, "strategy_scorecard": oos_scorecard, "exit_reason_analysis": oos_exit_reason_analysis},
        },
        "rolling_windows": windows,
        "summary": {
            "windows": len(windows),
            "positive_windows": positive_oos_windows,
            "positive_window_ratio": positive_window_ratio,
            "oos_reliability": reliability,
            "reliability_diagnostic": reliability_diagnostic,
            "composite_score": oos_scorecard.get("composite_score"),
            "exit_reason_stats": _exit_reason_stats(trades),
            "exit_reason_analysis": walk_forward_exit_reason_analysis,
            "regime_stats": _regime_stats_from_curve(equity_curve),
        },
        "scorecard": oos_scorecard,
    }


def run_walk_forward_validation(query: dict[str, list[str]], refresh: bool = False, cache_only: bool = False) -> dict[str, Any]:
    base_cfg = get_backtest_service().parse_config(query)
    cache_key = _build_walk_forward_cache_key(query, base_cfg=base_cfg)
    if not refresh and cache_only:
        cached = _load_cached_walk_forward(cache_key)
        if cached is not None:
            return _annotate_walk_forward_source(cached, source="cache")
        return {
            "ok": False,
            "error": "validation_cache_miss",
            "source": "walk_forward_cache_miss",
        }

    if not refresh:
        cached = _load_cached_walk_forward(cache_key)
        if cached is not None:
            return _annotate_walk_forward_source(cached, source="cache")

    payload = _compute_walk_forward_payload(base_cfg, query)
    _store_cached_walk_forward(cache_key, payload)
    return _annotate_walk_forward_source(payload, source="live")
