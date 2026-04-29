from __future__ import annotations

from typing import Any, Iterable, Mapping


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


def build_market_regime_snapshot(
    snapshots: Iterable[Mapping[str, Any] | None],
    *,
    market: str | None = None,
) -> dict[str, Any]:
    rows = [row for row in snapshots if isinstance(row, Mapping)]
    if not rows:
        return {"market": str(market or ""), "source": "empty_market_regime_snapshot"}

    def first_numeric(row: Mapping[str, Any], *keys: str) -> float | None:
        for key in keys:
            parsed = _to_float(row.get(key))
            if parsed is not None:
                return parsed
        return None

    def avg(*keys: str) -> float | None:
        values: list[float] = []
        for row in rows:
            parsed = first_numeric(row, *keys)
            if parsed is not None:
                values.append(parsed)
        return (sum(values) / len(values)) if values else None

    def avg_ratio(numerator_keys: tuple[str, ...], denominator_keys: tuple[str, ...]) -> float | None:
        values: list[float] = []
        for row in rows:
            numerator = first_numeric(row, *numerator_keys)
            denominator = first_numeric(row, *denominator_keys)
            if numerator is None or denominator is None or denominator == 0:
                continue
            values.append(numerator / denominator)
        return (sum(values) / len(values)) if values else None

    close_keys = ("close", "current_price", "trade_price")
    current_price_keys = ("current_price", "close", "trade_price")
    trade_price_keys = ("trade_price", "close", "current_price")
    sma20_keys = ("sma20",)
    sma60_keys = ("sma60",)

    close_sma20_ratio = avg_ratio(close_keys, sma20_keys)
    close_sma60_ratio = avg_ratio(close_keys, sma60_keys)
    current_sma60_ratio = avg_ratio(current_price_keys, sma60_keys)
    trade_sma60_ratio = avg_ratio(trade_price_keys, sma60_keys)
    sma20_sma60_ratio = avg_ratio(sma20_keys, sma60_keys)

    # Market-wide regime must not be biased by absolute share prices.  Use a
    # normalized 100-point SMA60 base when ratio inputs are available, then let
    # detect_market_regime() consume the same close/sma20/sma60 shape as before.
    normalized_close = close_sma60_ratio * 100.0 if close_sma60_ratio is not None else avg(*close_keys)
    normalized_current_price = current_sma60_ratio * 100.0 if current_sma60_ratio is not None else avg(*current_price_keys)
    normalized_trade_price = trade_sma60_ratio * 100.0 if trade_sma60_ratio is not None else avg(*trade_price_keys)
    normalized_sma20 = sma20_sma60_ratio * 100.0 if sma20_sma60_ratio is not None else avg(*sma20_keys)
    normalized_sma60 = 100.0 if (close_sma60_ratio is not None or sma20_sma60_ratio is not None) else avg(*sma60_keys)

    return {
        "market": str(market or ""),
        "source": "market_regime_aggregate",
        "sample_count": len(rows),
        "price_basis": "normalized_ratio" if normalized_sma60 == 100.0 else "raw_average",
        "close": normalized_close,
        "current_price": normalized_current_price,
        "trade_price": normalized_trade_price,
        "sma20": normalized_sma20,
        "sma60": normalized_sma60,
        "close_sma20_ratio": close_sma20_ratio,
        "close_sma60_ratio": close_sma60_ratio,
        "sma20_sma60_ratio": sma20_sma60_ratio,
        "volume_ratio": avg("volume_ratio"),
        "rsi14": avg("rsi14"),
        "atr14_pct": avg("atr14_pct"),
    }
