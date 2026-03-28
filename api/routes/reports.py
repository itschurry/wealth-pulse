import time
from typing import Any

import api.cache as _cache
from api.helpers import _SUPPORTED_AUTO_TRADE_MARKETS
from api.routes.market import _build_market
from market_utils import resolve_market
from reporter.storage import load_latest_report, load_report
from reporter.storage import list_report_dates as _storage_list_dates


def _infer_recommendation_market(ticker: str, market: str = "", code: str = "", name: str = "") -> str:
    return resolve_market(code=code or ticker, name=name, market=market, ticker=ticker, scope="core")


def _list_report_dates() -> list[str]:
    dates = _storage_list_dates("analysis")
    return sorted(set(dates))


def _pick_date(requested: str | None = None) -> str | None:
    dates = _list_report_dates()
    if not dates:
        return None
    if requested and requested in dates:
        return requested
    return dates[-1]


def _previous_date(current: str | None = None) -> str | None:
    dates = _list_report_dates()
    if len(dates) < 2:
        return None
    if current and current in dates:
        index = dates.index(current)
        if index > 0:
            return dates[index - 1]
    return dates[-2]


def _load_report_json(suffix: str, date: str | None = None, latest: bool = True) -> dict:
    if latest:
        target_date = _pick_date(date)
        if not target_date:
            return {}
        return load_report(target_date, suffix) or {}
    if not date:
        return {}
    return load_report(date, suffix) or {}


def _get_cached_payload(cache_bucket: dict, loader, missing_payload: dict) -> dict:
    now = time.time()
    if cache_bucket["data"] is not None and now - cache_bucket["ts"] < _cache.REPORT_CACHE_TTL:
        return cache_bucket["data"]
    data = loader()
    if not data:
        return missing_payload
    cache_bucket["data"] = data
    cache_bucket["ts"] = now
    return data


def _get_cached_report(cache_bucket: dict, suffix: str, missing_payload: dict) -> dict:
    return _get_cached_payload(cache_bucket, lambda: load_latest_report(suffix), missing_payload)


def _get_analysis() -> dict:
    return _get_cached_report(
        _cache._analysis_cache,
        "analysis",
        {"error": "분석 결과가 없습니다. run_once.py를 먼저 실행하세요."},
    )


def _get_recommendations() -> dict:
    return _get_cached_report(
        _cache._recommendation_cache,
        "recommendations",
        {"error": "추천 결과가 없습니다. run_once.py를 먼저 실행하세요.", "recommendations": []},
    )


def _get_today_picks() -> dict:
    data = _get_cached_report(_cache._today_picks_cache, "today_picks", {})
    if not data:
        fallback = _fallback_today_picks()
        if fallback.get("picks"):
            return fallback
        return {"error": "오늘의 추천 결과가 없습니다.", "picks": [], "auto_candidates": []}
    return data


def _get_ai_signals() -> dict:
    return _get_cached_report(_cache._ai_signals_cache, "ai_signals", {"signals": []})


def _get_macro() -> dict:
    return _get_cached_report(_cache._macro_cache, "macro", {"error": "거시 지표 결과가 없습니다."})


def _get_market_context() -> dict:
    return _get_cached_report(
        _cache._market_context_cache,
        "market_context",
        {"error": "시장 컨텍스트 결과가 없습니다."},
    )


def _get_market_dashboard() -> dict:
    now = time.time()
    market = _cache._market_cache["data"]
    if market is None or now - _cache._market_cache["ts"] > _cache.CACHE_TTL:
        market = _build_market()
        _cache._market_cache["data"] = market
        _cache._market_cache["ts"] = now
    return {
        "market": market,
        "macro": _get_macro(),
        "context": _get_market_context(),
    }


def _ev_to_signal_label(expected_value: float) -> str:
    if expected_value > 1.5:
        return "추천"
    if expected_value > 0.2:
        return "중립"
    return "회피"


def _map_strategy_signal(item: dict[str, Any], rank: int) -> dict[str, Any]:
    ev_metrics = item.get("ev_metrics") if isinstance(item.get("ev_metrics"), dict) else {}
    expected_value = float(ev_metrics.get("expected_value") or 0.0)
    win_probability = float(ev_metrics.get("win_probability") or 0.5)
    reliability = str(ev_metrics.get("reliability") or "insufficient")
    calibration = ev_metrics.get("calibration") if isinstance(ev_metrics.get("calibration"), dict) else {}
    risk_inputs = item.get("risk_inputs") if isinstance(item.get("risk_inputs"), dict) else {}
    size_recommendation = item.get("size_recommendation") if isinstance(item.get("size_recommendation"), dict) else {}
    execution_realism = item.get("execution_realism") if isinstance(item.get("execution_realism"), dict) else {}
    reasoning = item.get("signal_reasoning") if isinstance(item.get("signal_reasoning"), dict) else {}

    score = max(0.0, min(100.0, 50.0 + (expected_value * 8.0)))
    confidence = max(1, min(99, int(round(win_probability * 100.0))))
    gate_status = "passed" if bool(item.get("entry_allowed")) else "blocked"
    reason_codes = [str(reason) for reason in (item.get("reason_codes") or []) if reason]
    candidate_reasons = [str(reason) for reason in (reasoning.get("candidate_reasons") or []) if reason]
    candidate_risks = [str(reason) for reason in (reasoning.get("candidate_risks") or []) if reason]

    if not candidate_reasons:
        candidate_reasons = [
            f"EV {expected_value:.2f}, 승률 {confidence}%, 전략 {item.get('strategy_type')}",
            f"슬리피지 {execution_realism.get('slippage_bps', 0)} bps",
        ]
    if not candidate_risks:
        candidate_risks = reason_codes[:]
    if not candidate_risks:
        candidate_risks = ["리스크 가드 이상 없음"]

    return {
        "rank": rank,
        "name": item.get("name"),
        "ticker": f"{item.get('code')}.{item.get('market')}",
        "code": item.get("code"),
        "market": item.get("market"),
        "sector": item.get("sector"),
        "signal": _ev_to_signal_label(expected_value),
        "score": round(score, 1),
        "confidence": confidence,
        "risk_level": "중간",
        "reasons": candidate_reasons[:5],
        "risks": candidate_risks[:5],
        "horizon": "short_term",
        "gate_status": gate_status,
        "gate_reasons": reason_codes[:5],
        "playbook_alignment": None,
        "ai_thesis": ((item.get("report_reasoning") or {}) if isinstance(item.get("report_reasoning"), dict) else {}).get("summary"),
        "strategy_type": item.get("strategy_type"),
        "expected_value": round(expected_value, 4),
        "win_probability": round(win_probability, 4),
        "expected_upside": ev_metrics.get("expected_upside"),
        "expected_downside": ev_metrics.get("expected_downside"),
        "size_recommendation": size_recommendation,
        "reliability": reliability,
        "validation_trades": int(calibration.get("sample_size") or 0),
        "validation_sharpe": calibration.get("validation_sharpe"),
        "strategy_reliability": reliability,
        "technical_snapshot": None,
        "execution_realism": execution_realism,
        "risk_inputs": risk_inputs,
    }


def _strategy_recommendations_payload() -> dict[str, Any]:
    from services.strategy_engine import build_signal_book

    signal_book = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={})
    rows = [
        _map_strategy_signal(item, idx + 1)
        for idx, item in enumerate(signal_book.get("signals", []))
    ]
    recommendations = [row for row in rows if row.get("gate_status") == "passed"][:60]
    rejected = [row for row in rows if row.get("gate_status") != "passed"][:80]
    signal_counts = {
        "추천": sum(1 for row in recommendations if row.get("signal") == "추천"),
        "중립": sum(1 for row in recommendations if row.get("signal") == "중립"),
        "회피": sum(1 for row in recommendations if row.get("signal") == "회피"),
    }
    return {
        "generated_at": signal_book.get("generated_at"),
        "strategy": "profit-max-strategy-engine-v2",
        "universe": "KOSPI+NASDAQ",
        "signal_counts": signal_counts,
        "recommendations": recommendations,
        "rejected_candidates": rejected,
        "risk_guard_state": signal_book.get("risk_guard_state"),
        "regime": signal_book.get("regime"),
        "risk_level": signal_book.get("risk_level"),
    }


def _strategy_today_picks_payload() -> dict[str, Any]:
    recommendation_payload = _strategy_recommendations_payload()
    approved = recommendation_payload.get("recommendations", [])
    picks = approved[:12]
    auto_candidates = approved[:100]
    return {
        "generated_at": recommendation_payload.get("generated_at"),
        "strategy": recommendation_payload.get("strategy"),
        "market_tone": recommendation_payload.get("regime"),
        "picks": picks,
        "auto_candidates": auto_candidates,
        "auto_candidate_limit": 100,
        "auto_candidate_total": len(auto_candidates),
        "auto_candidate_market_counts": {
            market: sum(1 for item in auto_candidates if str(item.get("market") or "").upper() == market)
            for market in sorted(_SUPPORTED_AUTO_TRADE_MARKETS)
        },
    }


def _fallback_today_picks(date: str | None = None) -> dict:
    recommendations = (
        _get_recommendations() if not date
        else _load_report_json("recommendations", date, latest=False)
    )
    if not recommendations.get("recommendations"):
        return {"picks": [], "auto_candidates": []}

    # Phase 5: 최적화 결과 로드 (신뢰도 정보 추가용)
    optimized_params = None
    try:
        from pathlib import Path
        from config.backtest_universe import LOGS_DIR
        opt_path = Path(__file__).parent.parent.parent / \
            "config" / "optimized_params.json"
        if opt_path.exists():
            import json
            optimized_params = json.loads(opt_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    all_candidates = []
    for item in recommendations.get("recommendations", []):
        ticker = (item.get("ticker") or "").split(".")[0]
        market = _infer_recommendation_market(
            str(item.get("ticker") or ""),
            str(item.get("market") or ""),
            str(item.get("code") or ticker),
            str(item.get("name") or ""),
        )

        # Phase 5: 최적화 결과에서 신뢰도 정보 추출
        code = item.get("code") or ticker
        opt_result = {}
        if optimized_params and optimized_params.get("per_symbol", {}).get(code):
            opt_result = optimized_params["per_symbol"][code]

        # 신뢰도 결정 (is_reliable 필드 기반)
        is_reliable = bool(opt_result.get("is_reliable", False))
        validation_trades = int(opt_result.get("validation_trades", 0))
        validation_sharpe = float(opt_result.get("validation_sharpe", 0.0))
        reliability_reason = str(opt_result.get(
            "reliability_reason", "unknown"))

        # 신뢰도 레벨 결정
        strategy_reliability = "insufficient"  # 기본값
        if is_reliable and validation_sharpe > 0.1 and validation_trades >= 10:
            strategy_reliability = "high"
        elif validation_trades >= 5 and validation_sharpe > 0.0:
            strategy_reliability = "medium"
        elif validation_trades > 0:
            strategy_reliability = "low"

        candidate = {
            "name": item.get("name"),
            "code": ticker,
            "market": market,
            "sector": item.get("sector"),
            "signal": item.get("signal"),
            "score": item.get("score"),
            "confidence": item.get("confidence", 55),
            "reasons": item.get("reasons", []),
            "risks": item.get("risks", []),
            "catalysts": item.get("reasons", [])[:2],
            "related_news": [],
            "theme_score": 0.0,
            "theme_hit_count": 0,
            "matched_themes": [],
            "keyword_gate_passed": False,
            "horizon": item.get("horizon", "short_term"),
            "gate_status": item.get("gate_status", "passed"),
            "gate_reasons": item.get("gate_reasons", []),
            "playbook_alignment": item.get("playbook_alignment"),
            "ai_thesis": item.get("ai_thesis"),
            # Phase 5 추가 필드
            "strategy_reliability": strategy_reliability,
            "validation_trades": validation_trades,
            "validation_sharpe": validation_sharpe,
            "is_reliable": is_reliable,
            "reliability_reason": reliability_reason,
        }
        all_candidates.append(candidate)

    picks = all_candidates[:8]
    auto_candidates = [
        item for item in all_candidates
        if str(item.get("market") or "").upper() in _SUPPORTED_AUTO_TRADE_MARKETS
    ][:100]

    return {
        "generated_at": recommendations.get("generated_at"),
        "date": recommendations.get("date"),
        "market_tone": "fallback",
        "strategy": "recommendation-fallback",
        "playbook_ref": recommendations.get("playbook_ref"),
        "picks": picks,
        "auto_candidates": auto_candidates,
        "auto_candidate_limit": 100,
        "auto_candidate_total": len(auto_candidates),
        "auto_candidate_market_counts": {
            market: sum(
                1 for item in auto_candidates
                if str(item.get("market") or "").upper() == market
            )
            for market in sorted(_SUPPORTED_AUTO_TRADE_MARKETS)
        },
    }


def _build_compare_payload(base_date: str | None = None, prev_date: str | None = None) -> dict:
    base_date = _pick_date(base_date)
    if not base_date:
        return {"error": "비교할 리포트가 없습니다."}

    prev_date = _previous_date(base_date) if prev_date is None else prev_date
    if not prev_date:
        return {"error": "전일 비교 데이터가 없습니다.", "base_date": base_date}

    base_analysis = _load_report_json("analysis", base_date, latest=False)
    prev_analysis = _load_report_json("analysis", prev_date, latest=False)
    base_recommendations = _load_report_json(
        "recommendations", base_date, latest=False)
    prev_recommendations = _load_report_json(
        "recommendations", prev_date, latest=False)
    base_context = _load_report_json("market_context", base_date, latest=False)
    prev_context = _load_report_json("market_context", prev_date, latest=False)
    base_today_picks = _load_report_json(
        "today_picks", base_date, latest=False) or _fallback_today_picks(base_date)
    prev_today_picks = _load_report_json(
        "today_picks", prev_date, latest=False) or _fallback_today_picks(prev_date)

    base_rec_map: dict = {}
    prev_rec_map: dict = {}
    for item in base_recommendations.get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        base_rec_map[key] = item
        base_rec_map[item.get("name")] = item
    for item in prev_recommendations.get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        prev_rec_map[key] = item
        prev_rec_map[item.get("name")] = item

    recommendation_changes = []
    for current in base_recommendations.get("recommendations", []):
        key = (current.get("ticker") or "").split(
            ".")[0] or current.get("name")
        previous = prev_rec_map.get(
            key) or prev_rec_map.get(current.get("name"))
        if not previous:
            continue
        if current.get("signal") != previous.get("signal") or current.get("score") != previous.get("score"):
            recommendation_changes.append({
                "name": current.get("name"),
                "ticker": current.get("ticker", ""),
                "current_signal": current.get("signal"),
                "previous_signal": previous.get("signal"),
                "score_diff": round(float(current.get("score", 0)) - float(previous.get("score", 0)), 1),
            })

    base_pick_map = {item.get("code") or item.get(
        "name"): item for item in base_today_picks.get("picks", [])}
    prev_pick_map = {item.get("code") or item.get(
        "name"): item for item in prev_today_picks.get("picks", [])}
    today_pick_changes = []
    for key, current in base_pick_map.items():
        previous = prev_pick_map.get(key)
        if not previous:
            today_pick_changes.append({
                "name": current.get("name"),
                "status": "new",
                "current_signal": current.get("signal"),
                "score_diff": current.get("score"),
            })
            continue
        if current.get("signal") != previous.get("signal") or current.get("score") != previous.get("score"):
            today_pick_changes.append({
                "name": current.get("name"),
                "status": "changed",
                "current_signal": current.get("signal"),
                "previous_signal": previous.get("signal"),
                "score_diff": round(float(current.get("score", 0)) - float(previous.get("score", 0)), 1),
            })

    base_ctx = base_context.get("context", {})
    prev_ctx = prev_context.get("context", {})
    context_changes = []
    for field in ("regime", "risk_level", "inflation_signal", "labor_signal", "policy_signal", "yield_curve_signal", "dollar_signal"):
        if base_ctx.get(field) != prev_ctx.get(field):
            context_changes.append({
                "field": field,
                "previous": prev_ctx.get(field),
                "current": base_ctx.get(field),
            })

    base_risks = set(base_ctx.get("risks", []))
    prev_risks = set(prev_ctx.get("risks", []))

    return {
        "base_date": base_date,
        "prev_date": prev_date,
        "summary_lines": {
            "base": base_analysis.get("summary_lines", []),
            "prev": prev_analysis.get("summary_lines", []),
        },
        "signal_counts": {
            "base": base_recommendations.get("signal_counts", {}),
            "prev": prev_recommendations.get("signal_counts", {}),
        },
        "recommendation_changes": sorted(
            recommendation_changes, key=lambda item: abs(item["score_diff"]), reverse=True
        )[:10],
        "today_pick_changes": sorted(
            today_pick_changes, key=lambda item: abs(item["score_diff"]), reverse=True
        )[:10],
        "context_changes": context_changes,
        "new_risks": sorted(base_risks - prev_risks),
        "resolved_risks": sorted(prev_risks - base_risks),
    }


def handle_reports() -> tuple[int, dict]:
    return 200, {"dates": _list_report_dates()}


def handle_analysis(date: str | None) -> tuple[int, dict]:
    try:
        data = (
            _get_analysis() if not date
            else _load_report_json("analysis", date, latest=False) or {"error": "해당 날짜 분석이 없습니다."}
        )
        return 200, data
    except Exception as e:
        return 500, {"error": str(e)}


def handle_recommendations(date: str | None) -> tuple[int, dict]:
    try:
        data = (
            _strategy_recommendations_payload() if not date
            else _load_report_json("recommendations", date, latest=False) or {"error": "해당 날짜 추천이 없습니다.", "recommendations": []}
        )
        return 200, data
    except Exception as e:
        return 500, {"error": str(e), "recommendations": []}


def handle_today_picks(date: str | None) -> tuple[int, dict]:
    try:
        if not date:
            data = _strategy_today_picks_payload()
        else:
            data = (
                _load_report_json("today_picks", date, latest=False)
                or _fallback_today_picks(date)
                or {"error": "해당 날짜 오늘의 추천이 없습니다.", "picks": []}
            )
        return 200, data
    except Exception as e:
        return 500, {"error": str(e), "picks": []}


def handle_compare(base_date: str | None, prev_date: str | None) -> tuple[int, dict]:
    try:
        return 200, _build_compare_payload(base_date, prev_date)
    except Exception as e:
        return 500, {"error": str(e)}


def handle_macro() -> tuple[int, dict]:
    try:
        return 200, _get_macro()
    except Exception as e:
        return 500, {"error": str(e)}


def handle_market_context(date: str | None) -> tuple[int, dict]:
    try:
        data = (
            _get_market_context() if not date
            else _load_report_json("market_context", date, latest=False) or {"error": "해당 날짜 시장 컨텍스트가 없습니다."}
        )
        return 200, data
    except Exception as e:
        return 500, {"error": str(e)}


def handle_market_dashboard() -> tuple[int, dict]:
    try:
        return 200, _get_market_dashboard()
    except Exception as e:
        return 500, {"error": str(e)}
