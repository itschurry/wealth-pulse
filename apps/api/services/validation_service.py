"""Validation service with extended metrics and walk-forward summary."""

from __future__ import annotations

from dataclasses import replace
from math import floor, sqrt
from typing import Any

from services.backtest_service import get_backtest_service
from services.reliability_service import classify_walk_forward_reliability


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
    payload["scorecard"] = _build_strategy_scorecard(payload["metrics"], trades)
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
    positive_oos_windows = sum(1 for item in windows if _to_float((item.get("metrics") or {}).get("total_return_pct"), 0.0) > 0)
    positive_window_ratio = round(_walk_forward_positive_ratio(windows), 4)
    reliability = _classify_walk_forward_reliability(
        oos_metrics,
        positive_window_ratio=positive_window_ratio,
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
            "train": {**train_metrics, "strategy_scorecard": train_scorecard},
            "validation": {**validation_metrics, "strategy_scorecard": validation_scorecard},
            "oos": {**oos_metrics, "strategy_scorecard": oos_scorecard},
        },
        "rolling_windows": windows,
        "summary": {
            "windows": len(windows),
            "positive_windows": positive_oos_windows,
            "positive_window_ratio": positive_window_ratio,
            "oos_reliability": reliability,
            "composite_score": oos_scorecard.get("composite_score"),
            "exit_reason_stats": _exit_reason_stats(trades),
            "regime_stats": _regime_stats_from_curve(equity_curve),
        },
        "scorecard": oos_scorecard,
    }
