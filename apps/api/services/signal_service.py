"""Signal/candidate service extracted from API routes."""

from __future__ import annotations

from typing import Any, Literal

from analyzer.candidate_selector import (
    normalize_candidate_selection_config,
    select_market_candidates,
)
from market_utils import lookup_company_listing, normalize_market, resolve_market
from routes.reports import _get_recommendations, _get_today_picks
from services.optimized_params_store import load_execution_optimized_params

DEFAULT_THEME_FOCUS = ["automotive", "robotics", "physical_ai"]
_ALLOWED_THEME_FOCUS = set(DEFAULT_THEME_FOCUS)
_RUNTIME_CANDIDATE_SOURCE_MODES = {"quant_only", "hybrid"}
RuntimeCandidateSourceMode = Literal["quant_only", "hybrid"]


try:
    from analyzer.technical_snapshot import fetch_technical_snapshot as _fetch_technical_snapshot_impl
except Exception:  # pragma: no cover - optional dependency in lightweight tests
    _fetch_technical_snapshot_impl = None



def fetch_technical_snapshot(code: str, market: str) -> dict[str, Any] | None:
    if _fetch_technical_snapshot_impl is None:
        return None
    try:
        return _fetch_technical_snapshot_impl(code, market)
    except Exception:
        return None



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


def normalize_runtime_candidate_source_mode(raw: Any) -> RuntimeCandidateSourceMode:
    mode = str(raw or "quant_only").strip().lower()
    if mode not in _RUNTIME_CANDIDATE_SOURCE_MODES:
        return "quant_only"
    return mode  # type: ignore[return-value]


def _research_candidate_config(cfg: dict | None) -> dict[str, Any]:
    payload = cfg or {}
    return {
        "min_score": payload.get("min_score", 50.0),
        "include_neutral": payload.get("include_neutral", True),
        "allow_recommendation_fallback": bool(payload.get("allow_recommendation_fallback", False)),
        **parse_theme_gate_config(payload),
    }


def collect_research_candidates(market: str, cfg: dict | None = None) -> list[dict]:
    candidate_cfg = normalize_candidate_selection_config(_research_candidate_config(cfg))
    return select_market_candidates(
        market=market,
        cfg=candidate_cfg,
        today_picks=_get_today_picks(),
        recommendations=_get_recommendations(),
    )


def _quant_candidate_score(payload: dict[str, Any]) -> float:
    composite = payload.get("composite_score")
    if isinstance(composite, (int, float)):
        return max(0.0, min(100.0, float(composite)))
    sharpe = payload.get("validation_sharpe")
    if isinstance(sharpe, (int, float)):
        return max(0.0, min(100.0, 50.0 + (float(sharpe) * 20.0)))
    trades = payload.get("validation_trades") or payload.get("trade_count")
    if isinstance(trades, (int, float)):
        return max(0.0, min(100.0, 40.0 + min(40.0, float(trades))))
    return 50.0


def _quant_candidate_confidence(payload: dict[str, Any]) -> float:
    if bool(payload.get("is_reliable")):
        return 80.0
    reliability = str(payload.get("strategy_reliability") or "").lower()
    if reliability == "high":
        return 80.0
    if reliability == "medium":
        return 65.0
    if reliability == "low":
        return 45.0
    return 50.0


def _merge_runtime_technical_snapshot(item: dict[str, Any], fetched: dict[str, Any] | None) -> dict[str, Any]:
    existing = item.get("technical_snapshot") if isinstance(item.get("technical_snapshot"), dict) else {}
    snapshot = dict(fetched or {})
    snapshot.update({key: value for key, value in existing.items() if value not in (None, "")})

    if snapshot.get("current_price") in (None, ""):
        for key in ("last_price_local", "current_price", "price"):
            value = item.get(key)
            if value not in (None, ""):
                snapshot["current_price"] = value
                break
    return snapshot



def _runtime_source_meta(source: str, *, research_source: Any = None, mode: RuntimeCandidateSourceMode = "hybrid") -> dict[str, Any]:
    normalized = str(source or "unknown").strip().lower()
    research_source_value = str(research_source or "").strip().lower() or None

    if normalized == "hybrid":
        return {
            "source": "hybrid",
            "source_label": "hybrid",
            "source_detail": "quant + research",
            "source_tier": "tier_1",
            "source_priority": 100,
            "runtime_candidate_source_mode": mode,
            "research_source": research_source_value,
        }
    if normalized == "quant_runtime":
        return {
            "source": "quant_runtime",
            "source_label": "quant",
            "source_detail": "runtime quant overlay",
            "source_tier": "tier_1",
            "source_priority": 90,
            "runtime_candidate_source_mode": mode,
            "research_source": research_source_value,
        }
    return {
        "source": normalized or "research",
        "source_label": "research",
        "source_detail": research_source_value or normalized or "research",
        "source_tier": "tier_2",
        "source_priority": 70,
        "runtime_candidate_source_mode": mode,
        "research_source": research_source_value or normalized or None,
    }


def _build_quant_runtime_candidate(
    *,
    code: str,
    item: dict[str, Any],
    item_market: str,
    listing: dict[str, Any],
    runtime_source_mode: RuntimeCandidateSourceMode,
) -> dict[str, Any]:
    fetched_snapshot = fetch_technical_snapshot(code, item_market)
    technical_snapshot = _merge_runtime_technical_snapshot(item, fetched_snapshot)
    score = _quant_candidate_score(item)
    sharpe = item.get("validation_sharpe")
    trade_count = item.get("validation_trades") or item.get("trade_count") or 0
    reliability = str(item.get("strategy_reliability") or ("high" if item.get("is_reliable") else "insufficient"))
    current_price = technical_snapshot.get("current_price")
    volume_avg20 = technical_snapshot.get("volume_avg20")
    reasons = [
        f"quant_runtime:{reliability}",
        f"validation_trades:{trade_count}",
    ]
    if sharpe not in (None, ""):
        reasons.append(f"validation_sharpe:{sharpe}")
    if current_price not in (None, ""):
        reasons.append(f"current_price:{current_price}")
    if volume_avg20 not in (None, ""):
        reasons.append(f"volume_avg20:{volume_avg20}")

    return {
        "code": code,
        "name": listing.get("name") or code,
        "market": normalize_market(item_market),
        "sector": listing.get("sector") or item.get("sector") or "미분류",
        "score": round(score, 2),
        "priority_score": round(score, 2),
        "signal": "BUY",
        "confidence": _quant_candidate_confidence(item),
        "gate_status": "passed",
        "gate_reasons": [],
        "theme_score": 0.0,
        "matched_themes": [],
        "keyword_gate_passed": False,
        "related_news": [],
        "theme_news_count": 0,
        "reasons": reasons,
        "risks": [],
        "ai_thesis": str(item.get("ai_thesis") or "runtime quant validated candidate").strip(),
        "price": item.get("price") if item.get("price") not in (None, "") else current_price,
        "current_price": item.get("current_price") if item.get("current_price") not in (None, "") else current_price,
        "last_price_local": item.get("last_price_local") if item.get("last_price_local") not in (None, "") else current_price,
        "technical_snapshot": technical_snapshot,
        "validation_snapshot": {
            "validation_source": "quant_runtime",
            "trade_count": int(item.get("trade_count") or item.get("validation_trades") or 0),
            "validation_trades": int(item.get("validation_trades") or item.get("trade_count") or 0),
            "validation_sharpe": float(item.get("validation_sharpe") or 0.0),
            "max_drawdown_pct": item.get("max_drawdown_pct"),
            "strategy_reliability": reliability,
            "reliability_reason": str(item.get("reliability_reason") or "runtime_overlay"),
            "passes_minimum_gate": bool(item.get("validation_trades") or item.get("trade_count")),
            "is_reliable": bool(item.get("is_reliable", reliability in {"high", "medium"})),
            "composite_score": item.get("composite_score"),
        },
        **_runtime_source_meta("quant_runtime", mode=runtime_source_mode),
    }



def collect_quant_runtime_candidates(market: str, cfg: dict | None = None) -> list[dict]:
    payload = load_execution_optimized_params() or {}
    per_symbol = payload.get("per_symbol") if isinstance(payload.get("per_symbol"), dict) else {}
    normalized_market = normalize_market(market)
    if not per_symbol or not normalized_market:
        return []

    raw_cfg = cfg or {}
    runtime_source_mode = normalize_runtime_candidate_source_mode(raw_cfg.get("runtime_candidate_source_mode"))
    try:
        min_quant_score = float(raw_cfg.get("quant_min_score", 0.0))
    except (TypeError, ValueError):
        min_quant_score = 0.0

    candidates: list[dict[str, Any]] = []
    for raw_code, raw_item in per_symbol.items():
        code = str(raw_code or "").strip().upper()
        item = raw_item if isinstance(raw_item, dict) else {}
        if not code:
            continue
        item_market = resolve_market(code=code, market=str(item.get("market") or ""), scope="core")
        if normalize_market(item_market) != normalized_market:
            continue
        listing = lookup_company_listing(code=code, market=item_market, scope="core") or {}
        score = _quant_candidate_score(item)
        if score < min_quant_score:
            continue
        candidates.append(
            _build_quant_runtime_candidate(
                code=code,
                item=item,
                item_market=item_market,
                listing=listing,
                runtime_source_mode=runtime_source_mode,
            )
        )

    return sorted(
        candidates,
        key=lambda item: (float(item.get("priority_score") or 0.0), float(item.get("score") or 0.0), str(item.get("code") or "")),
        reverse=True,
    )


def collect_runtime_candidates(market: str, cfg: dict | None = None) -> list[dict]:
    payload = cfg or {}
    mode = normalize_runtime_candidate_source_mode(payload.get("runtime_candidate_source_mode"))
    if mode == "quant_only":
        return collect_quant_runtime_candidates(market, payload)

    quant_candidates = collect_quant_runtime_candidates(market, payload)
    research_candidates = collect_research_candidates(market, payload)
    merged: dict[str, dict[str, Any]] = {}
    for item in quant_candidates:
        code = str(item.get("code") or "").upper()
        if code:
            merged[code] = dict(item)
    for item in research_candidates:
        code = str(item.get("code") or "").upper()
        if not code:
            continue
        if code in merged:
            combined = dict(merged[code])
            combined.update(_runtime_source_meta("hybrid", research_source=item.get("source"), mode=mode))
            combined["research_candidate"] = dict(item)
            combined["priority_score"] = round(max(float(combined.get("priority_score") or 0.0), float(item.get("priority_score") or 0.0)), 2)
            if not combined.get("technical_snapshot") and item.get("technical_snapshot"):
                combined["technical_snapshot"] = item.get("technical_snapshot")
            if not combined.get("ai_thesis") and item.get("ai_thesis"):
                combined["ai_thesis"] = item.get("ai_thesis")
            combined["reasons"] = list(dict.fromkeys([*(combined.get("reasons") or []), *(item.get("reasons") or []), "hybrid_candidate:quant+research"]))
            merged[code] = combined
            continue
        merged[code] = {
            **dict(item),
            **_runtime_source_meta(item.get("source") or "research", research_source=item.get("source"), mode=mode),
        }
    return sorted(
        merged.values(),
        key=lambda item: (float(item.get("priority_score") or 0.0), float(item.get("score") or 0.0), str(item.get("code") or "")),
        reverse=True,
    )


def collect_pick_candidates(market: str, cfg: dict) -> list[dict]:
    return collect_runtime_candidates(market=market, cfg=cfg)
