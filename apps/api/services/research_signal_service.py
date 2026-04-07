"""
Research/AI 신호 데이터 접근 서비스.

routes/reports.py 에서 서비스 계층이 직접 의존하던 캐시 읽기 함수들을 추출한 모듈.
routes 계층 → services 계층의 역방향 임포트를 제거하기 위해 만들어졌다.
"""
from __future__ import annotations

from typing import Any

import cache as _cache
from services.report_cache import get_cached_payload


def _load_latest_report(key: str) -> dict[str, Any] | None:
    try:
        from reporter.storage import load_latest_report
        return load_latest_report(key)
    except Exception:
        return None


def _get_cached_report(cache_bucket: dict, suffix: str, missing_payload: dict[str, Any]) -> dict[str, Any]:
    return get_cached_payload(
        cache_bucket,
        lambda: _load_latest_report(suffix),
        missing_payload,
        ttl=_cache.REPORT_CACHE_TTL,
    )


def get_recommendations() -> dict[str, Any]:
    """LLM 추천 결과를 반환한다. 캐시 히트 시 캐시값, 없으면 저장소에서 로드."""
    return _get_cached_report(
        _cache._recommendation_cache,
        "recommendations",
        {"error": "추천 결과가 없습니다. run_once.py를 먼저 실행하세요.", "recommendations": []},
    )


def get_today_picks() -> dict[str, Any]:
    """오늘의 추천 종목을 반환한다. 캐시 히트 시 캐시값, 없으면 저장소에서 로드."""
    return _get_cached_report(
        _cache._today_picks_cache,
        "today_picks",
        {"error": "오늘의 추천 결과가 없습니다.", "picks": [], "auto_candidates": []},
    )
