"""Strategy type selection and allocator weights."""

from __future__ import annotations

from typing import Any


def _text_blob(candidate: dict[str, Any]) -> str:
    values = [
        str(candidate.get("name") or ""),
        str(candidate.get("sector") or ""),
        str(candidate.get("signal") or ""),
        " ".join(str(item) for item in (candidate.get("reasons") or []) if item),
        " ".join(str(item) for item in (candidate.get("risks") or []) if item),
        " ".join(str(item) for item in (candidate.get("matched_themes") or []) if item),
    ]
    return " ".join(values).lower()


def determine_strategy_type(candidate: dict[str, Any]) -> str:
    blob = _text_blob(candidate)
    technicals = candidate.get("technical_snapshot") if isinstance(candidate.get("technical_snapshot"), dict) else {}

    if any(keyword in blob for keyword in ("fomc", "cpi", "고용", "실적", "이벤트", "공시", "정책")):
        return "event-driven"
    if float(candidate.get("theme_score") or 0.0) >= 3.0 or any(keyword in blob for keyword in ("theme", "robot", "ai", "자동차", "로봇")):
        return "news-theme momentum"

    if technicals:
        if bool(technicals.get("breakout_20d")) or (float(technicals.get("volume_ratio") or 0.0) >= 1.4 and str(technicals.get("trend") or "") == "bullish"):
            return "breakout"
        if float(technicals.get("rsi14") or 50.0) <= 38.0:
            return "mean-reversion"
        if str(technicals.get("trend") or "") == "bullish":
            return "pullback"

    signal = str(candidate.get("signal") or "")
    if signal == "추천":
        return "pullback"
    return "mean-reversion"


def allocator_weight(
    *,
    strategy_type: str,
    regime: str,
    market: str,
    sector: str,
) -> dict[str, Any]:
    regime_key = str(regime or "neutral").lower()

    by_regime = {
        "risk_on": {
            "breakout": 1.0,
            "news-theme momentum": 0.95,
            "event-driven": 0.75,
            "pullback": 0.7,
            "mean-reversion": 0.45,
        },
        "neutral": {
            "breakout": 0.8,
            "news-theme momentum": 0.75,
            "event-driven": 0.7,
            "pullback": 0.85,
            "mean-reversion": 0.8,
        },
        "risk_off": {
            "breakout": 0.35,
            "news-theme momentum": 0.3,
            "event-driven": 0.85,
            "pullback": 0.9,
            "mean-reversion": 0.95,
        },
    }

    weight = by_regime.get(regime_key, by_regime["neutral"]).get(strategy_type, 0.5)

    market_upper = str(market or "").upper()
    sector_lower = str(sector or "").lower()
    if market_upper == "NASDAQ" and strategy_type in {"breakout", "news-theme momentum"}:
        weight += 0.05
    if sector_lower in {"반도체", "로봇", "플랫폼"} and strategy_type == "news-theme momentum":
        weight += 0.05

    weight = max(0.0, min(1.2, weight))
    enabled = weight >= 0.45

    return {
        "enabled": enabled,
        "weight": round(weight, 4),
        "reason": f"regime={regime_key}, strategy={strategy_type}",
    }
