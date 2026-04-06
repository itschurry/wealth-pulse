"""Shared reliability thresholds for optimizer, execution, calibration, and reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.reliability_policy import (
    BORDERLINE_REASONS,
    MAX_DRAWDOWN_FILTER_PCT,
    MAX_DRAWDOWN_RELIABLE_PCT,
    MIN_RELIABLE_TRAIN_TRADES,
    MIN_TRAIN_TRADES,
    MIN_VALIDATION_SHARPE_FILTER,
    MIN_VALIDATION_SHARPE_RELIABLE,
    MIN_VALIDATION_SIGNALS,
    classify_optimization_reliability,
)


@dataclass(frozen=True)
class ValidationReliabilityAssessment:
    label: str
    reason: str
    trade_count: int
    validation_signals: int
    validation_sharpe: float
    max_drawdown_pct: float | None
    passes_minimum_gate: bool
    is_reliable: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WalkForwardReliabilityAssessment:
    label: str
    trade_count: int
    profit_factor: float
    sharpe: float
    total_return_pct: float
    positive_window_ratio: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def reliability_thresholds() -> dict[str, float]:
    return {
        "min_train_trades": MIN_TRAIN_TRADES,
        "min_reliable_train_trades": MIN_RELIABLE_TRAIN_TRADES,
        "min_validation_signals": MIN_VALIDATION_SIGNALS,
        "min_sharpe_filter": MIN_VALIDATION_SHARPE_FILTER,
        "min_sharpe_reliable": MIN_VALIDATION_SHARPE_RELIABLE,
        "max_drawdown_filter": MAX_DRAWDOWN_FILTER_PCT,
        "max_drawdown_reliable": MAX_DRAWDOWN_RELIABLE_PCT,
    }


def walk_forward_reliability_thresholds() -> dict[str, float]:
    return {
        "min_trade_count": MIN_VALIDATION_SIGNALS,
        "medium_trade_count": 12,
        "high_trade_count": MIN_TRAIN_TRADES,
        "min_profit_factor": 1.0,
        "medium_profit_factor": 1.15,
        "high_profit_factor": 1.3,
        "min_sharpe": MIN_VALIDATION_SHARPE_FILTER,
        "medium_sharpe": MIN_VALIDATION_SHARPE_RELIABLE,
        "high_sharpe": 0.75,
        "min_total_return_pct": 0.0,
        "medium_positive_window_ratio": 0.5,
        "high_positive_window_ratio": 0.6,
    }


def _rounded_gap(current: float, target: float) -> float:
    return round(target - current, 4)


def _improvement_item(
    *,
    metric: str,
    current: float,
    target: float,
    direction: str,
    label: str,
) -> dict[str, Any]:
    gap = _rounded_gap(current, target)
    return {
        "metric": metric,
        "current": round(current, 4),
        "target": round(target, 4),
        "gap": gap,
        "direction": direction,
        "summary": f"{label}: 현재 {round(current, 4)} → 목표 {round(target, 4)} ({gap:+.4f})",
    }


def assess_validation_reliability(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float | None = None,
) -> ValidationReliabilityAssessment:
    trade_count = max(0, int(trade_count or 0))
    validation_signals = max(0, int(validation_signals or 0))
    validation_sharpe = _to_float(validation_sharpe, 0.0)
    max_drawdown = None if max_drawdown_pct is None else _to_float(max_drawdown_pct, 0.0)

    is_reliable, reason = classify_optimization_reliability(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=_to_float(max_drawdown, 0.0) if max_drawdown is not None else 0.0,
    )

    if is_reliable:
        label = "high"
        passes_minimum_gate = True
    elif reason in BORDERLINE_REASONS:
        label = "medium"
        passes_minimum_gate = True
    elif reason in {"excessive_drawdown", "weak_validation_sharpe"}:
        label = "low"
        passes_minimum_gate = False
    else:
        label = "insufficient"
        passes_minimum_gate = False

    return ValidationReliabilityAssessment(
        label=label,
        reason=reason,
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=round(validation_sharpe, 4),
        max_drawdown_pct=max_drawdown,
        passes_minimum_gate=passes_minimum_gate,
        is_reliable=is_reliable,
    )


def explain_validation_reliability(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float | None = None,
) -> dict[str, Any]:
    assessment = assess_validation_reliability(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=max_drawdown_pct,
    )
    thresholds = reliability_thresholds()

    blockers: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []

    if assessment.trade_count < thresholds["min_train_trades"]:
        blockers.append(
            {
                "metric": "trade_count",
                "current": assessment.trade_count,
                "threshold": thresholds["min_train_trades"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"훈련 거래 수가 최소 기준보다 부족함 ({assessment.trade_count} < {int(thresholds['min_train_trades'])})",
            }
        )
        improvements.append(
            _improvement_item(
                metric="trade_count",
                current=float(assessment.trade_count),
                target=thresholds["min_train_trades"],
                direction="increase",
                label="최소 게이트 통과에 필요한 훈련 거래 수",
            )
        )
    elif assessment.trade_count < thresholds["min_reliable_train_trades"]:
        blockers.append(
            {
                "metric": "trade_count",
                "current": assessment.trade_count,
                "threshold": thresholds["min_reliable_train_trades"],
                "direction": "increase",
                "severity": "borderline",
                "summary": f"훈련 거래 수가 medium은 가능하지만 high 기준에는 부족함 ({assessment.trade_count} < {int(thresholds['min_reliable_train_trades'])})",
            }
        )

    if assessment.validation_signals < thresholds["min_validation_signals"]:
        blockers.append(
            {
                "metric": "validation_signals",
                "current": assessment.validation_signals,
                "threshold": thresholds["min_validation_signals"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"검증 신호 수가 최소 기준보다 부족함 ({assessment.validation_signals} < {int(thresholds['min_validation_signals'])})",
            }
        )
        improvements.append(
            _improvement_item(
                metric="validation_signals",
                current=float(assessment.validation_signals),
                target=thresholds["min_validation_signals"],
                direction="increase",
                label="최소 게이트 통과에 필요한 검증 신호 수",
            )
        )

    if assessment.validation_sharpe < thresholds["min_sharpe_filter"]:
        blockers.append(
            {
                "metric": "validation_sharpe",
                "current": assessment.validation_sharpe,
                "threshold": thresholds["min_sharpe_filter"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"검증 샤프가 최소 필터보다 낮음 ({assessment.validation_sharpe:.4f} < {thresholds['min_sharpe_filter']:.2f})",
            }
        )
        improvements.append(
            _improvement_item(
                metric="validation_sharpe",
                current=assessment.validation_sharpe,
                target=thresholds["min_sharpe_filter"],
                direction="increase",
                label="최소 게이트 통과에 필요한 검증 샤프",
            )
        )
    elif assessment.validation_sharpe < thresholds["min_sharpe_reliable"]:
        blockers.append(
            {
                "metric": "validation_sharpe",
                "current": assessment.validation_sharpe,
                "threshold": thresholds["min_sharpe_reliable"],
                "direction": "increase",
                "severity": "borderline",
                "summary": f"검증 샤프가 medium은 가능하지만 high 기준에는 부족함 ({assessment.validation_sharpe:.4f} < {thresholds['min_sharpe_reliable']:.2f})",
            }
        )

    if assessment.max_drawdown_pct is not None:
        drawdown = float(assessment.max_drawdown_pct)
        if drawdown < thresholds["max_drawdown_filter"]:
            blockers.append(
                {
                    "metric": "max_drawdown_pct",
                    "current": drawdown,
                    "threshold": thresholds["max_drawdown_filter"],
                    "direction": "reduce_loss",
                    "severity": "hard_gate",
                    "summary": f"최대 낙폭이 최소 허용 기준보다 나쁨 ({drawdown:.2f}% < {thresholds['max_drawdown_filter']:.2f}%)",
                }
            )
            improvements.append(
                _improvement_item(
                    metric="max_drawdown_pct",
                    current=drawdown,
                    target=thresholds["max_drawdown_filter"],
                    direction="reduce_loss",
                    label="최소 게이트 통과에 필요한 최대 낙폭",
                )
            )
        elif drawdown < thresholds["max_drawdown_reliable"]:
            blockers.append(
                {
                    "metric": "max_drawdown_pct",
                    "current": drawdown,
                    "threshold": thresholds["max_drawdown_reliable"],
                    "direction": "reduce_loss",
                    "severity": "borderline",
                    "summary": f"낙폭이 medium은 가능하지만 high 기준에는 부족함 ({drawdown:.2f}% < {thresholds['max_drawdown_reliable']:.2f}%)",
                }
            )

    if assessment.label in {"low", "insufficient"}:
        target_label = "medium"
    else:
        target_label = "high"

    target_adjustments: list[dict[str, Any]] = []
    trade_target = thresholds["min_train_trades"] if target_label == "medium" else thresholds["min_reliable_train_trades"]
    sharpe_target = thresholds["min_sharpe_filter"] if target_label == "medium" else thresholds["min_sharpe_reliable"]
    drawdown_target = thresholds["max_drawdown_filter"] if target_label == "medium" else thresholds["max_drawdown_reliable"]

    if assessment.trade_count < trade_target:
        target_adjustments.append(
            _improvement_item(
                metric="trade_count",
                current=float(assessment.trade_count),
                target=trade_target,
                direction="increase",
                label=f"{target_label} 달성에 필요한 훈련 거래 수",
            )
        )
    if assessment.validation_signals < thresholds["min_validation_signals"]:
        target_adjustments.append(
            _improvement_item(
                metric="validation_signals",
                current=float(assessment.validation_signals),
                target=thresholds["min_validation_signals"],
                direction="increase",
                label=f"{target_label} 달성에 필요한 검증 신호 수",
            )
        )
    if assessment.validation_sharpe < sharpe_target:
        target_adjustments.append(
            _improvement_item(
                metric="validation_sharpe",
                current=assessment.validation_sharpe,
                target=sharpe_target,
                direction="increase",
                label=f"{target_label} 달성에 필요한 검증 샤프",
            )
        )
    if assessment.max_drawdown_pct is not None and assessment.max_drawdown_pct < drawdown_target:
        target_adjustments.append(
            _improvement_item(
                metric="max_drawdown_pct",
                current=float(assessment.max_drawdown_pct),
                target=drawdown_target,
                direction="reduce_loss",
                label=f"{target_label} 달성에 필요한 최대 낙폭",
            )
        )

    summary_lines = [
        f"현재 판정: {assessment.label} ({assessment.reason})",
        f"훈련 거래 {assessment.trade_count}건 / 검증 신호 {assessment.validation_signals}건 / 검증 샤프 {assessment.validation_sharpe:.4f}",
    ]
    if assessment.max_drawdown_pct is not None:
        summary_lines.append(f"최대 낙폭 {assessment.max_drawdown_pct:.2f}%")
    if blockers:
        summary_lines.append(f"주요 차단 요소: {', '.join(str(item['metric']) for item in blockers[:3])}")

    return {
        "label": assessment.label,
        "reason": assessment.reason,
        "passes_minimum_gate": assessment.passes_minimum_gate,
        "is_reliable": assessment.is_reliable,
        "thresholds": thresholds,
        "summary_lines": summary_lines,
        "blockers": blockers,
        "minimum_gate_adjustments": improvements,
        "target_label": target_label,
        "target_adjustments": target_adjustments,
    }


def find_minimal_reliability_uplift(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float | None = None,
    target_label: str = "medium",
    max_adjusted_metrics: int = 4,
    max_trials: int = 2000,
) -> dict[str, Any]:
    assessment = assess_validation_reliability(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=max_drawdown_pct,
    )
    thresholds = reliability_thresholds()
    normalized_target = "high" if str(target_label or "medium").strip().lower() == "high" else "medium"

    if normalized_target == "high":
        required = {
            "trade_count": thresholds["min_reliable_train_trades"],
            "validation_signals": thresholds["min_validation_signals"],
            "validation_sharpe": thresholds["min_sharpe_reliable"],
            "max_drawdown_pct": thresholds["max_drawdown_reliable"],
        }
        target_reached = assessment.is_reliable
    else:
        required = {
            "trade_count": thresholds["min_train_trades"],
            "validation_signals": thresholds["min_validation_signals"],
            "validation_sharpe": thresholds["min_sharpe_filter"],
            "max_drawdown_pct": thresholds["max_drawdown_filter"],
        }
        target_reached = assessment.passes_minimum_gate

    current_values = {
        "trade_count": float(assessment.trade_count),
        "validation_signals": float(assessment.validation_signals),
        "validation_sharpe": float(assessment.validation_sharpe),
        "max_drawdown_pct": None if assessment.max_drawdown_pct is None else float(assessment.max_drawdown_pct),
    }
    changes: list[dict[str, Any]] = []
    for metric, required_value in required.items():
        current = current_values.get(metric)
        if current is None:
            continue
        if metric == "max_drawdown_pct":
            missing = current < required_value
        else:
            missing = current < required_value
        if not missing:
            continue
        changes.append(
            {
                "metric": metric,
                "from": round(float(current), 4),
                "to": round(float(required_value), 4),
                "delta": round(float(required_value) - float(current), 4),
            }
        )

    feasible = target_reached or len(changes) <= max_adjusted_metrics
    recommended_path = None if target_reached else {
        "cost": round(sum(abs(float(item.get("delta") or 0.0)) for item in changes), 4),
        "label": normalized_target,
        "reason": f"metric_uplift_to_{normalized_target}",
        "changes": changes,
    }
    alternatives = [] if target_reached else [
        {
            "cost": abs(float(item.get("delta") or 0.0)),
            "label": normalized_target,
            "reason": f"single_metric_uplift_{item.get('metric')}",
            "changes": [item],
        }
        for item in changes[:max(0, min(len(changes), max_trials, 4))]
    ]

    return {
        "target_label": normalized_target,
        "current": assessment.as_dict(),
        "target_reached": target_reached,
        "searched_candidates": min(max_trials, max(1, len(changes))),
        "feasible": feasible,
        "recommended_path": recommended_path,
        "alternatives": alternatives,
    }


def build_reliability_diagnostic(
    *,
    trade_count: int,
    validation_signals: int,
    validation_sharpe: float,
    max_drawdown_pct: float | None = None,
    target_label: str = "medium",
) -> dict[str, Any]:
    diagnostic = explain_validation_reliability(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=max_drawdown_pct,
    )
    assessment = assess_validation_reliability(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=max_drawdown_pct,
    )
    thresholds = reliability_thresholds()
    normalized_target = "high" if str(target_label or "medium").strip().lower() == "high" else "medium"

    if normalized_target == "high":
        target_thresholds = {
            "trade_count": thresholds["min_reliable_train_trades"],
            "validation_signals": thresholds["min_validation_signals"],
            "validation_sharpe": thresholds["min_sharpe_reliable"],
            "max_drawdown_pct": thresholds["max_drawdown_reliable"],
        }
        target_reached = assessment.is_reliable
    else:
        target_thresholds = {
            "trade_count": thresholds["min_train_trades"],
            "validation_signals": thresholds["min_validation_signals"],
            "validation_sharpe": thresholds["min_sharpe_filter"],
            "max_drawdown_pct": thresholds["max_drawdown_filter"],
        }
        target_reached = assessment.passes_minimum_gate

    def _gap_item(metric: str, current: float | None, required: float, direction: str, blocking: bool) -> dict[str, Any]:
        if current is None:
            gap = None
        elif direction == "reduce_loss":
            gap = round(required - current, 4)
        else:
            gap = round(required - current, 4)
        return {
            "metric": metric,
            "current": None if current is None else round(float(current), 4),
            "required": round(float(required), 4),
            "gap": gap,
            "direction": direction,
            "blocking": blocking,
        }

    metric_values = {
        "trade_count": float(assessment.trade_count),
        "validation_signals": float(assessment.validation_signals),
        "validation_sharpe": float(assessment.validation_sharpe),
        "max_drawdown_pct": None if assessment.max_drawdown_pct is None else float(assessment.max_drawdown_pct),
    }
    directions = {
        "trade_count": "increase",
        "validation_signals": "increase",
        "validation_sharpe": "increase",
        "max_drawdown_pct": "reduce_loss",
    }

    threshold_gaps: list[dict[str, Any]] = []
    blocking_factors: list[dict[str, Any]] = []
    uplift_changes: list[dict[str, Any]] = []
    for metric, required in target_thresholds.items():
        current = metric_values.get(metric)
        direction = directions[metric]
        if current is None:
            continue
        if direction == "reduce_loss":
            missing = current < required
        else:
            missing = current < required
        if not missing:
            continue
        item = _gap_item(metric, current, required, direction, True)
        threshold_gaps.append(item)
        blocking_factors.append(item)
        uplift_changes.append(
            {
                "metric": metric,
                "from": round(float(current), 4),
                "to": round(float(required), 4),
                "delta": round(float(required) - float(current), 4),
            }
        )

    uplift_search = find_minimal_reliability_uplift(
        trade_count=trade_count,
        validation_signals=validation_signals,
        validation_sharpe=validation_sharpe,
        max_drawdown_pct=max_drawdown_pct,
        target_label=normalized_target,
        max_adjusted_metrics=4,
        max_trials=2000,
    )

    payload = {
        "target_label": normalized_target,
        "current": assessment.as_dict(),
        "target_reached": target_reached,
        "blocking_factors": blocking_factors,
        "threshold_gaps": threshold_gaps,
        "summary_lines": diagnostic.get("summary_lines", []),
        "uplift_search": {
            "target_label": normalized_target,
            "already_satisfies_target": target_reached,
            "searched_candidates": uplift_search.get("searched_candidates", max(1, len(uplift_changes))),
            "feasible": uplift_search.get("feasible", bool(target_reached or uplift_changes)),
            "recommended_path": uplift_search.get("recommended_path"),
            "alternatives": uplift_search.get("alternatives", []),
        },
        "raw_diagnostic": diagnostic,
    }
    return payload


def classify_walk_forward_reliability(
    *,
    trade_count: int,
    profit_factor: float,
    sharpe: float,
    total_return_pct: float,
    positive_window_ratio: float,
) -> WalkForwardReliabilityAssessment:
    trade_count = max(0, int(trade_count or 0))
    profit_factor = _to_float(profit_factor, 0.0)
    sharpe = _to_float(sharpe, 0.0)
    total_return_pct = _to_float(total_return_pct, 0.0)
    positive_window_ratio = _to_float(positive_window_ratio, 0.0)

    label = "low"
    if trade_count < MIN_VALIDATION_SIGNALS:
        label = "insufficient"
    elif total_return_pct <= 0.0 or profit_factor < 1.0 or sharpe < MIN_VALIDATION_SHARPE_FILTER:
        label = "low"
    elif (
        trade_count >= MIN_TRAIN_TRADES
        and profit_factor >= 1.3
        and sharpe >= 0.75
        and positive_window_ratio >= 0.6
    ):
        label = "high"
    elif (
        trade_count >= 12
        and profit_factor >= 1.15
        and sharpe >= MIN_VALIDATION_SHARPE_RELIABLE
        and positive_window_ratio >= 0.5
    ):
        label = "medium"

    return WalkForwardReliabilityAssessment(
        label=label,
        trade_count=trade_count,
        profit_factor=round(profit_factor, 4),
        sharpe=round(sharpe, 4),
        total_return_pct=round(total_return_pct, 4),
        positive_window_ratio=round(positive_window_ratio, 4),
    )


def explain_walk_forward_reliability(
    *,
    trade_count: int,
    profit_factor: float,
    sharpe: float,
    total_return_pct: float,
    positive_window_ratio: float,
) -> dict[str, Any]:
    assessment = classify_walk_forward_reliability(
        trade_count=trade_count,
        profit_factor=profit_factor,
        sharpe=sharpe,
        total_return_pct=total_return_pct,
        positive_window_ratio=positive_window_ratio,
    )
    thresholds = walk_forward_reliability_thresholds()

    blockers: list[dict[str, Any]] = []
    strengths: list[str] = []

    if assessment.trade_count >= thresholds["medium_trade_count"]:
        strengths.append(f"표본 수는 medium 기준 통과 ({assessment.trade_count}건)")
    if assessment.profit_factor >= thresholds["medium_profit_factor"]:
        strengths.append(f"profit factor는 medium 기준 통과 ({assessment.profit_factor:.2f})")
    if assessment.sharpe >= thresholds["medium_sharpe"]:
        strengths.append(f"샤프는 medium 기준 통과 ({assessment.sharpe:.2f})")
    if positive_window_ratio >= thresholds["medium_positive_window_ratio"]:
        strengths.append(f"양수 윈도우 비율은 medium 기준 통과 ({positive_window_ratio:.2f})")
    if assessment.total_return_pct > thresholds["min_total_return_pct"]:
        strengths.append(f"OOS 수익률은 0% 초과 ({assessment.total_return_pct:.2f}%)")

    if assessment.trade_count < thresholds["min_trade_count"]:
        blockers.append(
            {
                "metric": "trade_count",
                "current": assessment.trade_count,
                "threshold": thresholds["min_trade_count"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"OOS 거래 수가 최소 기준보다 부족함 ({assessment.trade_count} < {int(thresholds['min_trade_count'])})",
            }
        )
    elif assessment.trade_count < thresholds["medium_trade_count"]:
        blockers.append(
            {
                "metric": "trade_count",
                "current": assessment.trade_count,
                "threshold": thresholds["medium_trade_count"],
                "direction": "increase",
                "severity": "medium_gap",
                "summary": f"거래 수가 low 게이트는 통과했지만 medium 기준에는 부족함 ({assessment.trade_count} < {int(thresholds['medium_trade_count'])})",
            }
        )

    if assessment.total_return_pct <= thresholds["min_total_return_pct"]:
        blockers.append(
            {
                "metric": "total_return_pct",
                "current": assessment.total_return_pct,
                "threshold": thresholds["min_total_return_pct"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"OOS 수익률이 0% 이하라서 low 판정이 유지됨 ({assessment.total_return_pct:.2f}%)",
            }
        )

    if assessment.profit_factor < thresholds["min_profit_factor"]:
        blockers.append(
            {
                "metric": "profit_factor",
                "current": assessment.profit_factor,
                "threshold": thresholds["min_profit_factor"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"profit factor가 1.0 미만이라 손익비가 깨짐 ({assessment.profit_factor:.2f})",
            }
        )
    elif assessment.profit_factor < thresholds["medium_profit_factor"]:
        blockers.append(
            {
                "metric": "profit_factor",
                "current": assessment.profit_factor,
                "threshold": thresholds["medium_profit_factor"],
                "direction": "increase",
                "severity": "medium_gap",
                "summary": f"profit factor가 medium 기준에는 부족함 ({assessment.profit_factor:.2f} < {thresholds['medium_profit_factor']:.2f})",
            }
        )

    if assessment.sharpe < thresholds["min_sharpe"]:
        blockers.append(
            {
                "metric": "sharpe",
                "current": assessment.sharpe,
                "threshold": thresholds["min_sharpe"],
                "direction": "increase",
                "severity": "hard_gate",
                "summary": f"샤프가 최소 기준보다 낮아 low 판정이 유지됨 ({assessment.sharpe:.2f} < {thresholds['min_sharpe']:.2f})",
            }
        )
    elif assessment.sharpe < thresholds["medium_sharpe"]:
        blockers.append(
            {
                "metric": "sharpe",
                "current": assessment.sharpe,
                "threshold": thresholds["medium_sharpe"],
                "direction": "increase",
                "severity": "medium_gap",
                "summary": f"샤프가 medium 기준에는 부족함 ({assessment.sharpe:.2f} < {thresholds['medium_sharpe']:.2f})",
            }
        )

    if positive_window_ratio < thresholds["medium_positive_window_ratio"]:
        blockers.append(
            {
                "metric": "positive_window_ratio",
                "current": round(positive_window_ratio, 4),
                "threshold": thresholds["medium_positive_window_ratio"],
                "direction": "increase",
                "severity": "medium_gap",
                "summary": f"양수 OOS 윈도우 비율이 medium 기준에는 부족함 ({positive_window_ratio:.2f} < {thresholds['medium_positive_window_ratio']:.2f})",
            }
        )

    target_adjustments: list[dict[str, Any]] = []
    for metric, current, target, direction, label in (
        ("trade_count", float(assessment.trade_count), thresholds["medium_trade_count"], "increase", "medium 달성에 필요한 OOS 거래 수"),
        ("profit_factor", assessment.profit_factor, thresholds["medium_profit_factor"], "increase", "medium 달성에 필요한 profit factor"),
        ("sharpe", assessment.sharpe, thresholds["medium_sharpe"], "increase", "medium 달성에 필요한 샤프"),
        ("positive_window_ratio", positive_window_ratio, thresholds["medium_positive_window_ratio"], "increase", "medium 달성에 필요한 양수 윈도우 비율"),
    ):
        if current < target:
            target_adjustments.append(
                _improvement_item(
                    metric=metric,
                    current=current,
                    target=target,
                    direction=direction,
                    label=label,
                )
            )
    if assessment.total_return_pct <= thresholds["min_total_return_pct"]:
        target_adjustments.append(
            _improvement_item(
                metric="total_return_pct",
                current=assessment.total_return_pct,
                target=0.01,
                direction="increase",
                label="medium 달성을 위해 필요한 양수 OOS 수익률",
            )
        )

    summary_lines = [
        f"현재 OOS 판정: {assessment.label}",
        f"거래 {assessment.trade_count}건 / PF {assessment.profit_factor:.2f} / 샤프 {assessment.sharpe:.2f} / 수익률 {assessment.total_return_pct:.2f}%",
        f"양수 윈도우 비율 {positive_window_ratio:.2f}",
    ]
    if blockers:
        summary_lines.append(f"medium 미달 핵심: {', '.join(str(item['metric']) for item in blockers[:4])}")

    return {
        "label": assessment.label,
        "thresholds": thresholds,
        "summary_lines": summary_lines,
        "strengths": strengths,
        "blockers": blockers,
        "target_label": "medium",
        "target_adjustments": target_adjustments,
    }
