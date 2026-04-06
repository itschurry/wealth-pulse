from __future__ import annotations

from typing import Any, Mapping


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_market_regime(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"regime": "sideways", "risk_level": "balanced", "confidence": 0.2}

    close = _to_float(snapshot.get("close") or snapshot.get("current_price") or snapshot.get("trade_price"))
    sma20 = _to_float(snapshot.get("sma20"))
    sma60 = _to_float(snapshot.get("sma60"))
    volume_ratio = _to_float(snapshot.get("volume_ratio"))
    rsi14 = _to_float(snapshot.get("rsi14"))
    atr14_pct = _to_float(snapshot.get("atr14_pct"))

    if close is None or sma20 is None or sma60 is None:
        return {"regime": "sideways", "risk_level": "balanced", "confidence": 0.25}

    if atr14_pct is not None and atr14_pct >= 7.0:
        return {"regime": "risk_off", "risk_level": "high", "confidence": 0.75}
    if close < sma60 and ((volume_ratio is not None and volume_ratio < 0.9) or (rsi14 is not None and rsi14 < 42.0)):
        return {"regime": "bear", "risk_level": "high", "confidence": 0.8}
    if close > sma20 > sma60 and (rsi14 is None or rsi14 >= 52.0) and (volume_ratio is None or volume_ratio >= 1.0):
        return {"regime": "bull", "risk_level": "balanced", "confidence": 0.85}
    return {"regime": "sideways", "risk_level": "balanced", "confidence": 0.6}
