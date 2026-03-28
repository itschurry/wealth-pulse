"""Statistical EV calibration service.

EV is computed in percentage terms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EVPrior:
    win_probability: float
    expected_upside_pct: float
    expected_downside_pct: float
    expected_holding_days: int


_STRATEGY_PRIORS: dict[str, EVPrior] = {
    "breakout": EVPrior(0.53, 9.0, 4.8, 14),
    "pullback": EVPrior(0.56, 6.5, 3.9, 11),
    "event-driven": EVPrior(0.51, 11.0, 6.2, 8),
    "news-theme momentum": EVPrior(0.52, 10.0, 5.8, 10),
    "mean-reversion": EVPrior(0.57, 5.8, 3.5, 12),
}

_REGIME_BONUS: dict[str, dict[str, float]] = {
    "risk_on": {
        "breakout": 0.03,
        "news-theme momentum": 0.02,
        "event-driven": 0.01,
    },
    "risk_off": {
        "mean-reversion": 0.03,
        "pullback": 0.02,
        "breakout": -0.03,
        "news-theme momentum": -0.03,
    },
}


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _strategy_prior(strategy_type: str) -> EVPrior:
    return _STRATEGY_PRIORS.get(strategy_type, _STRATEGY_PRIORS["pullback"])


def _reliability(validation_trades: int, validation_sharpe: float) -> str:
    if validation_trades >= 25 and validation_sharpe >= 0.45:
        return "high"
    if validation_trades >= 12 and validation_sharpe >= 0.2:
        return "medium"
    if validation_trades >= 5 and validation_sharpe > 0:
        return "low"
    return "insufficient"


def compute_ev_metrics(
    *,
    strategy_type: str,
    regime: str,
    score: float,
    confidence: float,
    validation_trades: int = 0,
    validation_sharpe: float = 0.0,
    market: str = "",
    sector: str = "",
) -> dict[str, Any]:
    prior = _strategy_prior(strategy_type)

    score_adj = (score - 50.0) / 220.0
    conf_adj = (confidence - 50.0) / 260.0
    sharpe_adj = _clamp(validation_sharpe * 0.04, -0.08, 0.08)
    regime_adj = _REGIME_BONUS.get(regime, {}).get(strategy_type, 0.0)

    sample_size = max(0, int(validation_trades))
    shrinkage_weight = _clamp(sample_size / 30.0, 0.0, 1.0)

    raw_win_prob = prior.win_probability + score_adj + conf_adj + sharpe_adj + regime_adj
    win_probability = (raw_win_prob * shrinkage_weight) + (prior.win_probability * (1.0 - shrinkage_weight))
    win_probability = _clamp(win_probability, 0.05, 0.95)

    expected_upside_pct = prior.expected_upside_pct * (1.0 + _clamp((score - 50.0) / 120.0, -0.25, 0.35))
    expected_upside_pct *= (1.0 + _clamp(validation_sharpe / 8.0, -0.2, 0.25))

    downside_multiplier = 1.0 - _clamp((confidence - 50.0) / 160.0, -0.2, 0.25)
    if regime == "risk_off":
        downside_multiplier *= 1.15
    expected_downside_pct = prior.expected_downside_pct * downside_multiplier

    expected_holding_days = max(2, int(round(prior.expected_holding_days * (1.0 - regime_adj * 0.7))))
    expected_value = (win_probability * expected_upside_pct) - ((1.0 - win_probability) * expected_downside_pct)

    reliability = _reliability(sample_size, validation_sharpe)

    return {
        "win_probability": round(win_probability, 4),
        "expected_upside": round(expected_upside_pct, 4),
        "expected_downside": round(expected_downside_pct, 4),
        "expected_holding_days": expected_holding_days,
        "expected_value": round(expected_value, 4),
        "confidence": round(_clamp(confidence, 0.0, 100.0), 2),
        "reliability": reliability,
        "calibration": {
            "sample_size": sample_size,
            "validation_sharpe": round(validation_sharpe, 4),
            "shrinkage_weight": round(shrinkage_weight, 4),
            "market": market,
            "sector": sector,
            "regime": regime,
            "strategy_type": strategy_type,
        },
    }
