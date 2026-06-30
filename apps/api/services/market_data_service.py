"""
Market data utility functions.

routes/market.py 에서 서비스 계층이 직접 의존하던 함수들을 추출한 모듈.
routes 계층 → services 계층의 역방향 임포트를 제거하기 위해 만들어졌다.
"""
from __future__ import annotations

import datetime
from typing import Any

from broker.kis_client import KISConfigError
from helpers import _get_kis_client
from market_utils import lookup_company_listing, normalize_market, resolve_quote_market


def get_usd_krw_rate() -> float | None:
    return 1.0


def _normalize_quote_market(code: str, market: str) -> str:
    return resolve_quote_market(code=code, market=market, scope="core")


def resolve_stock_quote(code: str, market: str = "") -> dict[str, Any]:
    """종목 코드와 시장으로 KIS를 통해 실시간 주가 정보를 조회한다."""
    normalized_input = code.split(".")[0].strip().upper()
    if not normalized_input:
        raise ValueError("code required")

    listing = lookup_company_listing(code=normalized_input, name=normalized_input, scope="core")
    if not listing:
        listing = lookup_company_listing(code=normalized_input, name=normalized_input, scope="live")
    resolved_code = str((listing or {}).get("code") or normalized_input).strip().upper()
    resolved_name = str((listing or {}).get("name") or normalized_input).strip()
    resolved_market = str((listing or {}).get("market") or market or "").strip()
    normalized_market = _normalize_quote_market(resolved_code, resolved_market)
    if normalized_market != "KOSPI":
        raise ValueError("market could not be resolved; provide a valid market or use a known stock code")

    client = _get_kis_client()
    if client is None:
        raise KISConfigError("KIS가 설정되지 않았거나 비활성 상태입니다.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

    kis_price = client.get_domestic_price(resolved_code)
    price = kis_price.get("price")
    volume = kis_price.get("volume")
    trading_value = None
    if price not in (None, "") and volume not in (None, ""):
        trading_value = float(price) * float(volume)
    return {
        "code": resolved_code,
        "name": kis_price.get("name") or resolved_name,
        "price": price,
        "change_pct": kis_price.get("change_pct"),
        "volume": volume,
        "trading_value": trading_value,
        "market": normalize_market(resolved_market) or "KOSPI",
        "source": "KIS",
        "fetched_at": now_iso,
        "is_stale": False,
    }
