from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def get_cached_payload(
    cache_bucket: dict[str, Any],
    loader: Callable[[], dict[str, Any] | None],
    missing_payload: dict[str, Any],
    *,
    ttl: float,
) -> dict[str, Any]:
    now = time.time()
    cached = cache_bucket.get("data")
    cached_at = float(cache_bucket.get("ts", 0.0) or 0.0)
    if cached is not None and now - cached_at < ttl:
        return cached

    data = loader() or {}
    if not data:
        return missing_payload

    cache_bucket["data"] = data
    cache_bucket["ts"] = now
    return data
