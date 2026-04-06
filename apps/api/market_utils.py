"""Shared market resolution helpers for domestic and US equities."""
from __future__ import annotations

import re
from functools import lru_cache

from config.company_catalog import CompanyCatalogEntry, get_company_catalog

_NUMERIC_CODE_PATTERN = re.compile(r"\d{4,6}")
_ASCII_SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")

_MARKET_ALIASES = {
    "KOSPI": "KOSPI",
    "KRX": "KOSPI",
    "KR": "KOSPI",
    "KOREA": "KOSPI",
    "KOSDAQ": "KOSDAQ",
    "KQ": "KOSDAQ",
    "KOSDAQ GLOBAL": "KOSDAQ",
    "코스닥": "KOSDAQ",
    "NASDAQ": "NASDAQ",
    "NAS": "NASDAQ",
    "NYSE": "NYSE",
    "AMEX": "AMEX",
    "US": "NASDAQ",
    "USA": "NASDAQ",
}

_US_MARKETS = {"NASDAQ", "NYSE", "AMEX"}
_DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ"}


def normalize_text(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").strip().lower())


def normalize_market(market: str) -> str:
    normalized = str(market or "").strip().upper()
    if not normalized:
        return ""
    return _MARKET_ALIASES.get(normalized, normalized)


def split_ticker(value: str) -> tuple[str, str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return "", ""
    if "." not in raw:
        return raw, ""
    base, suffix = raw.split(".", 1)
    return base.strip(), suffix.strip()


def normalize_code(value: str) -> str:
    code, _ = split_ticker(value)
    return code


def infer_market_from_ticker(value: str) -> str:
    code, suffix = split_ticker(value)
    if not code:
        return ""
    if suffix == "KS":
        return "KOSPI"
    if suffix == "KQ":
        return "KOSDAQ"
    if suffix in {"O", "Q"}:
        return "NASDAQ"
    if suffix == "N":
        return "NYSE"
    return ""


@lru_cache(maxsize=4)
def _catalog(scope: str) -> tuple[CompanyCatalogEntry, ...]:
    normalized_scope = str(scope or "live").strip().lower()
    if normalized_scope not in {"core", "live"}:
        normalized_scope = "live"
    return tuple(get_company_catalog(scope=normalized_scope))


def lookup_company_listing(
    *,
    code: str = "",
    name: str = "",
    market: str = "",
    ticker: str = "",
    scope: str = "live",
) -> dict | None:
    normalized_market = normalize_market(market)
    normalized_code = normalize_code(code or ticker)
    normalized_name = normalize_text(name)
    if not normalized_name and normalized_code and not _NUMERIC_CODE_PATTERN.fullmatch(normalized_code):
        normalized_name = normalize_text(normalized_code)

    entries = _catalog(scope)

    def _market_matches(entry_market: str) -> bool:
        return not normalized_market or normalize_market(entry_market) == normalized_market

    if normalized_code:
        for entry in entries:
            if not _market_matches(entry.market):
                continue
            if normalize_code(entry.code) == normalized_code:
                return {
                    "name": entry.name,
                    "code": entry.code,
                    "market": normalize_market(entry.market),
                    "sector": entry.sector,
                    "aliases": entry.aliases,
                }

    if normalized_name:
        for entry in entries:
            if not _market_matches(entry.market):
                continue
            if normalize_text(entry.name) == normalized_name:
                return {
                    "name": entry.name,
                    "code": entry.code,
                    "market": normalize_market(entry.market),
                    "sector": entry.sector,
                    "aliases": entry.aliases,
                }
            if any(normalize_text(alias) == normalized_name for alias in entry.aliases):
                return {
                    "name": entry.name,
                    "code": entry.code,
                    "market": normalize_market(entry.market),
                    "sector": entry.sector,
                    "aliases": entry.aliases,
                }

    return None


def resolve_market(
    *,
    code: str = "",
    name: str = "",
    market: str = "",
    ticker: str = "",
    scope: str = "live",
) -> str:
    normalized_market = normalize_market(market)
    catalog_match = lookup_company_listing(code=code, name=name, market=normalized_market, ticker=ticker, scope=scope)
    if catalog_match:
        catalog_market = str(catalog_match.get("market") or "")
        if not normalized_market:
            return catalog_market
        if normalized_market == catalog_market:
            return normalized_market
        if normalized_market in _US_MARKETS and catalog_market in _US_MARKETS:
            return normalized_market
        return catalog_market

    if normalized_market:
        return normalized_market

    ticker_market = infer_market_from_ticker(ticker or code)
    if ticker_market:
        return ticker_market

    normalized_code = normalize_code(code or ticker)
    if not normalized_code:
        return ""
    if _NUMERIC_CODE_PATTERN.fullmatch(normalized_code):
        return "KOSPI"
    if _ASCII_SYMBOL_PATTERN.fullmatch(normalized_code):
        return ""
    return ""


def resolve_quote_market(
    *,
    code: str = "",
    name: str = "",
    market: str = "",
    ticker: str = "",
    scope: str = "live",
) -> str:
    resolved_market = resolve_market(code=code, name=name, market=market, ticker=ticker, scope=scope)
    if resolved_market in _DOMESTIC_MARKETS:
        return "KOSPI"
    if resolved_market in _US_MARKETS:
        return "NASDAQ"
    return ""


def is_domestic_market(market: str) -> bool:
    return normalize_market(market) in _DOMESTIC_MARKETS


def is_us_market(market: str) -> bool:
    return normalize_market(market) in _US_MARKETS
