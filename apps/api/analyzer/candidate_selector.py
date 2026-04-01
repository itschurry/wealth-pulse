"""Shared candidate selection helpers for auto-trading and backtests."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from analyzer.shared_strategy import normalize_strategy_market


@dataclass(frozen=True)
class CandidateSelectionConfig:
    min_score: float = 50.0
    include_neutral: bool = True
    theme_gate_enabled: bool = True
    theme_min_score: float = 2.5
    theme_min_news: int = 1
    theme_priority_bonus: float = 2.0
    allow_recommendation_fallback: bool = True


def normalize_candidate_selection_config(raw: Mapping[str, Any] | None = None) -> CandidateSelectionConfig:
    payload = raw or {}
    try:
        min_score = float(payload.get("min_score", 50.0))
    except (TypeError, ValueError):
        min_score = 50.0
    try:
        theme_min_score = float(payload.get("theme_min_score", 2.5))
    except (TypeError, ValueError):
        theme_min_score = 2.5
    try:
        theme_min_news = int(payload.get("theme_min_news", 1))
    except (TypeError, ValueError):
        theme_min_news = 1
    try:
        theme_priority_bonus = float(payload.get("theme_priority_bonus", 2.0))
    except (TypeError, ValueError):
        theme_priority_bonus = 2.0
    return CandidateSelectionConfig(
        min_score=max(0.0, min(100.0, min_score)),
        include_neutral=bool(payload.get("include_neutral", True)),
        theme_gate_enabled=bool(payload.get("theme_gate_enabled", True)),
        theme_min_score=max(0.0, min(30.0, theme_min_score)),
        theme_min_news=max(0, min(10, theme_min_news)),
        theme_priority_bonus=max(0.0, min(10.0, theme_priority_bonus)),
        allow_recommendation_fallback=bool(payload.get("allow_recommendation_fallback", True)),
    )


def serialize_candidate_selection_config(cfg: CandidateSelectionConfig) -> dict[str, Any]:
    return asdict(cfg)


def select_market_candidates(
    *,
    market: str,
    cfg: CandidateSelectionConfig,
    today_picks: Mapping[str, Any] | None = None,
    recommendations: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates, _ = _select_market_candidates_with_source(
        market=market,
        cfg=cfg,
        today_picks=today_picks,
        recommendations=recommendations,
    )
    return candidates


def _select_market_candidates_with_source(
    *,
    market: str,
    cfg: CandidateSelectionConfig,
    today_picks: Mapping[str, Any] | None = None,
    recommendations: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    normalized_market = normalize_strategy_market(market)
    allowed_signals = {"추천", "buy", "BUY"}
    if cfg.include_neutral:
        allowed_signals.update({"중립", "hold", "HOLD"})

    picks_payload = today_picks if isinstance(today_picks, Mapping) else {}
    raw_picks = picks_payload.get("auto_candidates")
    if not isinstance(raw_picks, list) or not raw_picks:
        raw_picks = picks_payload.get("picks", [])
    prepared = _prepare_today_pick_candidates(raw_picks, normalized_market, allowed_signals, cfg)
    if prepared:
        return _sort_candidates(prepared, cfg), "today_picks"

    if cfg.allow_recommendation_fallback:
        recommendation_payload = recommendations if isinstance(recommendations, Mapping) else {}
        raw_recommendations = recommendation_payload.get("recommendations", [])
        prepared = _prepare_recommendation_candidates(raw_recommendations, normalized_market, allowed_signals, cfg)
        if prepared:
            return _sort_candidates(prepared, cfg), "recommendations"
    if today_picks:
        return [], "today_picks"
    if recommendations:
        return [], "recommendations"
    return [], "none"


def load_historical_candidates(
    *,
    date: str,
    market: str,
    cfg: CandidateSelectionConfig,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    if report_dir is None:
        # Production path: read from SQLite DB.
        today_picks = _load_report_sqlite(date, "today_picks")
        recommendations = _load_report_sqlite(date, "recommendations")
    else:
        # Test / override path: read from JSON files in the given directory.
        today_picks = _load_report_json(report_dir, date, "today_picks")
        recommendations = _load_report_json(report_dir, date, "recommendations")
    candidates, source = _select_market_candidates_with_source(
        market=market,
        cfg=cfg,
        today_picks=today_picks,
        recommendations=recommendations,
    )
    return {
        "date": date,
        "market": normalize_strategy_market(market),
        "source": source,
        "codes": {
            str(item.get("code") or "").split(".")[0].strip().upper()
            for item in candidates
            if str(item.get("code") or "").strip()
        },
        "candidates": candidates,
        "has_report": source != "none",
    }


def _prepare_today_pick_candidates(
    items: list[Any],
    market: str,
    allowed_signals: set[str],
    cfg: CandidateSelectionConfig,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "").strip().upper()
        if not code:
            continue
        item_market = normalize_strategy_market(str(item.get("market") or ""))
        signal = str(item.get("signal") or "")
        score = _to_float(item.get("score"), default=0.0)
        gate_status = str(item.get("gate_status") or "passed")
        if item_market != market or signal not in allowed_signals or score < cfg.min_score or gate_status == "blocked":
            continue
        prepared.append(
            {
                "code": code,
                "name": item.get("name") or code,
                "market": item_market,
                "sector": item.get("sector"),
                "score": score,
                "signal": signal,
                "confidence": item.get("confidence"),
                "gate_status": gate_status,
                "gate_reasons": item.get("gate_reasons", []),
                "theme_score": _to_float(item.get("theme_score"), default=0.0),
                "matched_themes": item.get("matched_themes", []),
                "keyword_gate_passed": bool(item.get("keyword_gate_passed", False)),
                "related_news": item.get("related_news", []),
                "theme_news_count": _pick_theme_news_count(item),
                "reasons": item.get("reasons", []),
                "risks": item.get("risks", []),
                "ai_thesis": item.get("ai_thesis") or item.get("summary"),
                "price": item.get("price"),
                "current_price": item.get("current_price"),
                "last_price_local": item.get("last_price_local"),
                "technical_snapshot": item.get("technical_snapshot"),
                "technical_view": item.get("technical_view"),
                "setup_quality": item.get("setup_quality"),
                "source": "today_picks",
            }
        )
    return prepared


def _prepare_recommendation_candidates(
    items: list[Any],
    market: str,
    allowed_signals: set[str],
    cfg: CandidateSelectionConfig,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        code = ticker.split(".")[0] or str(item.get("code") or "").strip().upper()
        if not code:
            continue
        item_market = normalize_strategy_market(str(item.get("market") or ""))
        signal = str(item.get("signal") or "")
        score = _to_float(item.get("score"), default=0.0)
        gate_status = str(item.get("gate_status") or "passed")
        if item_market != market or signal not in allowed_signals or score < cfg.min_score or gate_status == "blocked":
            continue
        prepared.append(
            {
                "code": code,
                "name": item.get("name") or code,
                "market": item_market,
                "sector": item.get("sector"),
                "score": score,
                "signal": signal,
                "confidence": item.get("confidence"),
                "gate_status": gate_status,
                "gate_reasons": item.get("gate_reasons", []),
                "theme_score": _to_float(item.get("theme_score"), default=0.0),
                "matched_themes": item.get("matched_themes", []),
                "keyword_gate_passed": bool(item.get("keyword_gate_passed", False)),
                "related_news": item.get("related_news", []),
                "theme_news_count": _pick_theme_news_count(item),
                "reasons": item.get("reasons", []),
                "risks": item.get("risks", []),
                "ai_thesis": item.get("ai_thesis") or item.get("summary"),
                "price": item.get("price"),
                "current_price": item.get("current_price"),
                "last_price_local": item.get("last_price_local"),
                "technical_snapshot": item.get("technical_snapshot"),
                "technical_view": item.get("technical_view"),
                "setup_quality": item.get("setup_quality"),
                "source": "recommendations",
            }
        )
    return prepared


def _sort_candidates(items: list[dict[str, Any]], cfg: CandidateSelectionConfig) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for item in items:
        base_score = float(item.get("score") or 0.0)
        priority_score = base_score
        if cfg.theme_gate_enabled and _passes_theme_gate(item, cfg):
            priority_score += cfg.theme_priority_bonus
        candidate = dict(item)
        candidate["priority_score"] = round(priority_score, 2)
        prepared.append(candidate)
    return sorted(
        prepared,
        key=lambda item: (float(item.get("priority_score") or 0.0), float(item.get("score") or 0.0)),
        reverse=True,
    )


def _passes_theme_gate(item: Mapping[str, Any], cfg: CandidateSelectionConfig) -> bool:
    if not cfg.theme_gate_enabled:
        return False
    if _to_float(item.get("theme_score"), default=0.0) < cfg.theme_min_score:
        return False
    if _pick_theme_news_count(item) < cfg.theme_min_news:
        return False
    return True


def _pick_theme_news_count(item: Mapping[str, Any]) -> int:
    explicit = item.get("theme_news_count")
    if isinstance(explicit, (int, float)):
        return int(explicit)
    related_news = item.get("related_news", [])
    if not isinstance(related_news, list):
        return 0
    count = 0
    for news in related_news:
        if not isinstance(news, Mapping):
            continue
        score = _to_float(news.get("theme_score"), default=0.0)
        themes = news.get("matched_themes", [])
        if score > 0 or (isinstance(themes, list) and len(themes) > 0):
            count += 1
    return count


def _load_report_sqlite(date: str, key: str) -> dict[str, Any]:
    """SQLite DB에서 리포트를 로드한다. 없거나 오류 시 빈 dict 반환."""
    try:
        from reporter.storage import load_report
        return load_report(date, key) or {}
    except Exception:
        return {}


def _load_report_json(report_root: Path, date: str, suffix: str) -> dict[str, Any]:
    """JSON 파일에서 리포트를 로드한다 (테스트용 경로 지원)."""
    path = report_root / f"{date}_{suffix}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
