from __future__ import annotations

from typing import Any

from services.reliability_service import assess_validation_reliability


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_validation_snapshot(signal: dict[str, Any]) -> dict[str, Any]:
    ev = signal.get("ev_metrics") if isinstance(signal.get("ev_metrics"), dict) else {}
    reasoning = signal.get("signal_reasoning") if isinstance(signal.get("signal_reasoning"), dict) else {}
    calibration = reasoning.get("calibration") if isinstance(reasoning.get("calibration"), dict) else {}
    validation_snapshot = signal.get("validation_snapshot") if isinstance(signal.get("validation_snapshot"), dict) else {}
    reliability_detail = ev.get("reliability_detail") if isinstance(ev.get("reliability_detail"), dict) else {}

    trade_count = int(
        validation_snapshot.get("trade_count")
        or calibration.get("trade_count")
        or signal.get("trade_count")
        or signal.get("validation_trades")
        or 0
    )
    trades = int(
        validation_snapshot.get("validation_trades")
        or calibration.get("sample_size")
        or signal.get("validation_trades")
        or 0
    )
    sharpe = _to_float(
        validation_snapshot.get("validation_sharpe")
        or calibration.get("validation_sharpe")
        or signal.get("validation_sharpe"),
        0.0,
    )
    max_drawdown_pct = validation_snapshot.get("max_drawdown_pct")
    if max_drawdown_pct is None:
        max_drawdown_pct = calibration.get("max_drawdown_pct")
    if max_drawdown_pct is None:
        max_drawdown_pct = signal.get("max_drawdown_pct")

    assessment = assess_validation_reliability(
        trade_count=trade_count if trade_count > 0 else trades,
        validation_signals=trades,
        validation_sharpe=sharpe,
        max_drawdown_pct=_to_float(max_drawdown_pct, 0.0) if max_drawdown_pct is not None else None,
    )
    return {
        "trade_count": trade_count if trade_count > 0 else trades,
        "trades": trades,
        "sharpe": round(sharpe, 4),
        "max_drawdown_pct": None if max_drawdown_pct is None else round(_to_float(max_drawdown_pct, 0.0), 4),
        "reliability": str(
            validation_snapshot.get("strategy_reliability")
            or reliability_detail.get("label")
            or assessment.label
        ),
        "reliability_reason": str(
            validation_snapshot.get("reliability_reason")
            or reliability_detail.get("reason")
            or assessment.reason
        ),
        "passes_minimum_gate": bool(
            validation_snapshot.get(
                "passes_minimum_gate",
                reliability_detail.get("passes_minimum_gate", assessment.passes_minimum_gate),
            )
        ),
        "validation_reliable": bool(
            validation_snapshot.get("is_reliable", reliability_detail.get("is_reliable", assessment.is_reliable))
        ),
        "source": str(validation_snapshot.get("validation_source") or "signal"),
    }


def apply_validation_gate(signal: dict[str, Any], cfg: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    snapshot = resolve_validation_snapshot(signal)
    if not bool(cfg.get("validation_gate_enabled", True)):
        return True, [], {
            "enabled": False,
            **snapshot,
        }

    reasons: list[str] = []
    if int(snapshot.get("trades") or 0) < int(cfg.get("validation_min_trades", 8)):
        reasons.append("validation_trades_low")
    if float(snapshot.get("sharpe") or 0.0) < float(cfg.get("validation_min_sharpe", 0.2)):
        reasons.append("validation_sharpe_low")
    if bool(cfg.get("validation_block_on_low_reliability", True)) and str(
        snapshot.get("reliability") or "insufficient"
    ) in {"low", "insufficient"}:
        reasons.append("validation_reliability_low")

    return len(reasons) == 0, reasons, {
        "enabled": True,
        "source": "signal",
        **snapshot,
    }
