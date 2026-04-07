"""
Market data utility functions.

routes/market.py 에서 서비스 계층이 직접 의존하던 함수들을 추출한 모듈.
routes 계층 → services 계층의 역방향 임포트를 제거하기 위해 만들어졌다.
"""
from __future__ import annotations

import datetime
import re
import urllib.request
from typing import Any

import cache as _cache
from broker.kis_client import KISConfigError
from helpers import _HEADERS, _get_kis_client
from market_utils import lookup_company_listing, normalize_market, resolve_quote_market


def _usd_krw_fetch() -> float | None:
    """네이버 마켓인덱스에서 USD/KRW 환율을 스크래핑한다."""
    try:
        req = urllib.request.Request("https://finance.naver.com/marketindex/", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=4) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        m = re.search(r'class="value"[^>]*>(1[,\d]+\.\d{2})', text)
        if m:
            return float(m.group(1).replace(",", ""))
    except Exception:
        pass
    return None


def get_paper_fx_rate() -> float | None:
    """현재 USD/KRW 환율을 반환한다. 시장 캐시 우선, 폴백으로 네이버 스크래핑."""
    try:
        if _cache._market_cache["data"] is not None:
            usd_krw = _cache._market_cache["data"].get("usd_krw")
            if isinstance(usd_krw, (int, float)) and usd_krw > 0:
                return float(usd_krw)
        value = _usd_krw_fetch()
        return float(value) if value and value > 0 else None
    except Exception:
        return None


def _normalize_quote_market(code: str, market: str) -> str:
    return resolve_quote_market(code=code, market=market, scope="core")


def _overseas_exchange_candidates(market: str) -> list[str]:
    normalized = (market or "").strip().upper()
    if normalized in {"NYSE", "AMEX", "NASDAQ"}:
        ordered = [normalized, "NASDAQ", "NYSE", "AMEX"]
    elif normalized in {"NAS", "US", "USA", ""}:
        ordered = ["NASDAQ", "NYSE", "AMEX"]
    else:
        ordered = ["NASDAQ", "NYSE", "AMEX"]
    deduped: list[str] = []
    for item in ordered:
        if item not in deduped:
            deduped.append(item)
    return deduped


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
    if normalized_market not in {"KOSPI", "NASDAQ"}:
        raise ValueError("market could not be resolved; provide a valid market or use a known stock code")

    client = _get_kis_client()
    if client is None:
        raise KISConfigError("KIS가 설정되지 않았거나 비활성 상태입니다.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

    if normalized_market == "KOSPI":
        kis_price = client.get_domestic_price(resolved_code)
        return {
            "code": resolved_code,
            "name": kis_price.get("name") or resolved_name,
            "price": kis_price.get("price"),
            "change_pct": kis_price.get("change_pct"),
            "market": normalize_market(resolved_market) or "KOSPI",
            "source": "KIS",
            "fetched_at": now_iso,
            "is_stale": False,
        }

    last_exc: Exception | None = None
    kis_price = None
    resolved_exchange = normalize_market(resolved_market) or "NASDAQ"
    for exchange in _overseas_exchange_candidates(resolved_exchange):
        try:
            kis_price = client.get_overseas_price(resolved_code, exchange=exchange)
            resolved_exchange = exchange
            break
        except Exception as exc:
            last_exc = exc
            continue
    if kis_price is None:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("해외 현재가 조회에 실패했습니다.")

    return {
        "code": resolved_code,
        "name": kis_price.get("name") or resolved_name,
        "price": kis_price.get("price"),
        "change_pct": kis_price.get("change_pct"),
        "market": resolved_exchange,
        "source": "KIS",
        "fetched_at": now_iso,
        "is_stale": False,
    }
