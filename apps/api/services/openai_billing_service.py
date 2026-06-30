from __future__ import annotations

from datetime import UTC, datetime
import json
import os
import urllib.parse
import urllib.request
import urllib.error
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import OPENAI_ADMIN_KEY


OPENAI_USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"
OPENAI_COSTS_URL = "https://api.openai.com/v1/organization/costs"
KST = ZoneInfo("Asia/Seoul")


def _admin_key() -> str:
    key = str(os.getenv("OPENAI_ADMIN_KEY") or OPENAI_ADMIN_KEY or "").strip()
    if not key:
        raise RuntimeError("OPENAI_ADMIN_KEY_required")
    return key


def _month_bounds() -> tuple[int, int, int, str]:
    now = datetime.now(KST)
    start = datetime(now.year, now.month, 1, tzinfo=KST)
    start_time = int(start.timestamp())
    end_time = int(now.timestamp())
    query_end_time = max(end_time, start_time + 86400)
    return start_time, end_time, query_end_time, start.date().isoformat()


def _get_json(url: str, params: dict[str, str | int], *, timeout: int = 20) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        method="GET",
        headers={
            "Authorization": f"Bearer {_admin_key()}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"openai_billing_http_{exc.code}:{body}") from None
    if not isinstance(parsed, dict):
        raise RuntimeError("openai_billing_response_invalid")
    return parsed


def _sum_usage(data: dict[str, Any]) -> dict[str, int]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
    }
    for bucket in data.get("data") or []:
        if not isinstance(bucket, dict):
            continue
        for result in bucket.get("results") or []:
            if not isinstance(result, dict):
                continue
            input_tokens = int(result.get("input_tokens") or 0)
            output_tokens = int(result.get("output_tokens") or 0)
            totals["input_tokens"] += input_tokens
            totals["output_tokens"] += output_tokens
            totals["total_tokens"] += input_tokens + output_tokens
            totals["requests"] += int(result.get("num_model_requests") or 0)
    return totals


def _sum_costs(data: dict[str, Any]) -> tuple[float, str]:
    total = 0.0
    currency = "usd"
    for bucket in data.get("data") or []:
        if not isinstance(bucket, dict):
            continue
        for result in bucket.get("results") or []:
            if not isinstance(result, dict):
                continue
            amount = result.get("amount")
            if not isinstance(amount, dict):
                continue
            total += float(amount.get("value") or 0)
            currency = str(amount.get("currency") or currency).lower()
    return total, currency


def get_openai_billing_summary() -> dict[str, Any]:
    start_time, end_time, query_end_time, month_start = _month_bounds()
    common_params = {
        "start_time": start_time,
        "end_time": query_end_time,
        "bucket_width": "1d",
        "limit": 31,
    }
    usage = _get_json(OPENAI_USAGE_URL, common_params)
    costs = _get_json(OPENAI_COSTS_URL, common_params)
    usage_totals = _sum_usage(usage)
    cost_total, currency = _sum_costs(costs)
    return {
        "ok": True,
        "period": "month_to_date",
        "timezone": "Asia/Seoul",
        "month_start": month_start,
        "end_time": datetime.fromtimestamp(end_time, tz=KST).isoformat(),
        "cost": {
            "amount": round(cost_total, 6),
            "currency": currency,
        },
        "usage": usage_totals,
    }
