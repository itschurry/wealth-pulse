"""Validation service with extended metrics and walk-forward summary."""

from __future__ import annotations

from dataclasses import replace
from math import sqrt
from typing import Any

from services.backtest_service import get_backtest_service


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
        "turnover": round(turnover, 2),
        "exposure_pct": round(exposure_pct, 2),
        "trade_count": len(trades),
    }


def _slice_by_index(seq: list[Any], start: int, end: int) -> list[Any]:
    start = max(0, start)
    end = max(start, end)
    return seq[start:end]


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


def run_backtest_with_extended_metrics(query: dict[str, list[str]]) -> dict[str, Any]:
    payload = get_backtest_service().run_with_optional_optimization(query)
    if not isinstance(payload, dict):
        return {"error": "invalid_backtest_payload"}

    equity_curve = payload.get("equity_curve") if isinstance(payload.get("equity_curve"), list) else []
    trades = payload.get("trades") if isinstance(payload.get("trades"), list) else []

    payload = dict(payload)
    payload.setdefault("metrics", {})
    payload["metrics"].update(_segment_metrics(equity_curve, trades))
    payload["metrics"]["exit_reason_stats"] = _exit_reason_stats(trades)
    payload["metrics"]["regime_stats"] = _regime_stats_from_curve(equity_curve)
    return payload


def run_walk_forward_validation(query: dict[str, list[str]]) -> dict[str, Any]:
    base_cfg = get_backtest_service().parse_config(query)
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
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)

    train_curve = _slice_by_index(equity_curve, 0, train_end)
    validation_curve = _slice_by_index(equity_curve, train_end, val_end)
    oos_curve = _slice_by_index(equity_curve, val_end, n)

    train_trades = [t for t in trades if t.get("exit_date") <= (train_curve[-1].get("date") if train_curve else "")]
    val_trades = [t for t in trades if (validation_curve and validation_curve[0].get("date") <= t.get("exit_date") <= validation_curve[-1].get("date"))]
    oos_trades = [t for t in trades if (oos_curve and t.get("exit_date") >= oos_curve[0].get("date"))]

    windows = []
    window_size = max(45, min(252, n // 3))
    step = max(20, window_size // 3)

    for start in range(0, max(1, n - window_size), step):
        end = min(n, start + window_size)
        segment = _slice_by_index(equity_curve, start, end)
        if len(segment) < 30:
            continue
        start_date = str(segment[0].get("date") or "")
        end_date = str(segment[-1].get("date") or "")
        segment_trades = [t for t in trades if start_date <= str(t.get("exit_date") or "") <= end_date]
        windows.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "metrics": _segment_metrics(segment, segment_trades),
            }
        )

    oos_metrics = _segment_metrics(oos_curve, oos_trades)
    positive_oos_windows = sum(1 for item in windows if _to_float((item.get("metrics") or {}).get("total_return_pct"), 0.0) > 0)

    reliability = "low"
    if oos_metrics.get("trade_count", 0) >= 15 and oos_metrics.get("profit_factor", 0.0) >= 1.2:
        reliability = "high"
    elif oos_metrics.get("trade_count", 0) >= 8 and oos_metrics.get("profit_factor", 0.0) >= 1.0:
        reliability = "medium"

    return {
        "ok": True,
        "config": {
            "markets": list(base_cfg.markets),
            "lookback_days": base_cfg.lookback_days,
            "walk_forward_window": {
                "window_size": window_size,
                "step": step,
            },
        },
        "segments": {
            "train": _segment_metrics(train_curve, train_trades),
            "validation": _segment_metrics(validation_curve, val_trades),
            "oos": oos_metrics,
        },
        "rolling_windows": windows,
        "summary": {
            "windows": len(windows),
            "positive_windows": positive_oos_windows,
            "oos_reliability": reliability,
            "exit_reason_stats": _exit_reason_stats(trades),
            "regime_stats": _regime_stats_from_curve(equity_curve),
        },
    }
