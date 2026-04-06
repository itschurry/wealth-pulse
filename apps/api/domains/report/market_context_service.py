from __future__ import annotations

try:
    import cache as _cache
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from apps.api import cache as _cache

try:
    from services.report_cache import get_cached_payload
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from apps.api.services.report_cache import get_cached_payload


def get_market_context() -> dict:
    return get_cached_payload(
        _cache._market_context_cache,
        lambda: _storage_load_latest_report("market_context"),
        {"error": "시장 컨텍스트 결과가 없습니다."},
        ttl=_cache.REPORT_CACHE_TTL,
    )


def _storage_load_latest_report(key: str) -> dict | None:
    try:
        from reporter.storage import load_latest_report
    except ModuleNotFoundError:  # pragma: no cover - package import fallback
        from apps.api.reporter.storage import load_latest_report

    return load_latest_report(key)
