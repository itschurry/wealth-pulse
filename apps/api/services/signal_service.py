"""Signal/candidate service extracted from API routes."""

from __future__ import annotations

from analyzer.candidate_selector import (
    normalize_candidate_selection_config,
    select_market_candidates,
)
from api.routes.reports import _get_recommendations, _get_today_picks

DEFAULT_THEME_FOCUS = ["automotive", "robotics", "physical_ai"]
_ALLOWED_THEME_FOCUS = set(DEFAULT_THEME_FOCUS)


def normalize_theme_focus(raw) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_THEME_FOCUS)
    normalized: list[str] = []
    for item in raw:
        key = str(item or "").strip().lower()
        if key in _ALLOWED_THEME_FOCUS and key not in normalized:
            normalized.append(key)
    return normalized or list(DEFAULT_THEME_FOCUS)


def parse_theme_gate_config(raw: dict | None = None) -> dict:
    payload = raw or {}
    try:
        min_score = float(payload.get("theme_min_score", 2.5))
    except (TypeError, ValueError):
        min_score = 2.5
    try:
        min_news = int(payload.get("theme_min_news", 1))
    except (TypeError, ValueError):
        min_news = 1
    try:
        priority_bonus = float(payload.get("theme_priority_bonus", 2.0))
    except (TypeError, ValueError):
        priority_bonus = 2.0
    return {
        "theme_gate_enabled": bool(payload.get("theme_gate_enabled", True)),
        "theme_min_score": max(0.0, min(30.0, min_score)),
        "theme_min_news": max(0, min(10, min_news)),
        "theme_priority_bonus": max(0.0, min(10.0, priority_bonus)),
        "theme_focus": normalize_theme_focus(payload.get("theme_focus")),
    }


def collect_pick_candidates(market: str, cfg: dict) -> list[dict]:
    candidate_cfg = normalize_candidate_selection_config(
        {
            "min_score": cfg.get("min_score", 50.0),
            "include_neutral": cfg.get("include_neutral", True),
            **parse_theme_gate_config(cfg),
        }
    )
    return select_market_candidates(
        market=market,
        cfg=candidate_cfg,
        today_picks=_get_today_picks(),
        recommendations=_get_recommendations(),
    )
