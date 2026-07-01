from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Iterable, Mapping
import urllib.parse
import urllib.request

from market_utils import normalize_market

from .store import utc_now_iso


@dataclass(frozen=True)
class UniverseConfig:
    market: str = "KOSPI"
    max_symbols: int = 200
    min_price_krw: float = 1000.0
    min_trading_value_krw: float = 5_000_000_000.0


NAVER_PAGE_SIZE = 100
NAVER_SORT_TYPES = ("marketValue", "up")


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else text


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _parse_number(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A":
        return None
    cleaned = text.replace(",", "").replace("%", "").replace("+", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _naver_rows_for_sort(market: str, sort_type: str, *, target_count: int) -> list[dict[str, Any]]:
    pages = max(1, math.ceil(max(1, int(target_count)) / NAVER_PAGE_SIZE))
    rows: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        params = urllib.parse.urlencode({"page": page, "pageSize": NAVER_PAGE_SIZE})
        url = f"https://m.stock.naver.com/api/stocks/{sort_type}/{market}?{params}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 WealthPulse market scanner",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        stocks = payload.get("stocks")
        if not isinstance(stocks, list):
            raise ValueError(f"Naver stock list payload is missing stocks: {sort_type}")
        rows.extend(item for item in stocks if isinstance(item, dict))
        if len(stocks) < NAVER_PAGE_SIZE:
            break
    return rows


def _load_stock_listing(market: str, *, max_symbols: int) -> list[dict[str, Any]]:
    normalized_market = normalize_market(market)
    if normalized_market not in {"KOSPI", "KOSDAQ"}:
        raise ValueError(f"unsupported_dynamic_universe_market:{normalized_market}")

    target_count = max(100, int(max_symbols))
    by_code: dict[str, dict[str, Any]] = {}
    for sort_type in NAVER_SORT_TYPES:
        for row in _naver_rows_for_sort(normalized_market, sort_type, target_count=target_count):
            if str(row.get("stockEndType") or "").strip().lower() != "stock":
                continue
            code = str(row.get("itemCode") or "").strip()
            if len(code) != 6 or not code.isdigit():
                continue
            close = _parse_number(row.get("closePrice"))
            volume = _parse_number(row.get("accumulatedTradingVolume"))
            amount_raw = _parse_number(row.get("accumulatedTradingValueRaw"))
            amount = amount_raw if amount_raw is not None else (_parse_number(row.get("accumulatedTradingValue")) or 0) * 1_000_000.0
            change_pct = _parse_number(row.get("fluctuationsRatio"))
            market_cap_raw = _parse_number(row.get("marketValueRaw"))
            market_cap = market_cap_raw if market_cap_raw is not None else (_parse_number(row.get("marketValue")) or 0) * 100_000_000.0
            if close is None or volume is None or amount is None or change_pct is None or market_cap is None:
                continue
            current = {
                "Code": code,
                "Name": str(row.get("stockName") or code),
                "Close": close,
                "Volume": volume,
                "Amount": amount,
                "ChagesRatio": change_pct,
                "Marcap": market_cap,
                "Source": "naver_mobile_stock",
                "LocalTradedAt": str(row.get("localTradedAt") or ""),
            }
            previous = by_code.get(code)
            if previous is None or float(current["Amount"] or 0) > float(previous.get("Amount") or 0):
                by_code[code] = current
    if not by_code:
        raise ValueError(f"Naver stock list returned no usable symbols: {normalized_market}")
    return list(by_code.values())


def _normalize_source_rows(source_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in source_rows]



def build_dynamic_universe(
    *,
    market: str = "KOSPI",
    max_symbols: int = 200,
    min_price_krw: float = 1000.0,
    min_trading_value_krw: float = 5_000_000_000.0,
    source_rows: Iterable[Mapping[str, Any]] | None = None,
    force_symbols: Iterable[str] | None = None,
) -> dict[str, Any]:
    cfg = UniverseConfig(
        market=normalize_market(market),
        max_symbols=max(1, int(max_symbols)),
        min_price_krw=float(min_price_krw),
        min_trading_value_krw=float(min_trading_value_krw),
    )
    rows = _normalize_source_rows(source_rows) if source_rows is not None else _load_stock_listing(cfg.market, max_symbols=cfg.max_symbols)
    force_set = {normalize_symbol(symbol) for symbol in (force_symbols or []) if normalize_symbol(symbol)}

    symbols: list[dict[str, Any]] = []
    for row in rows:
        code = normalize_symbol(row.get("Code"))
        if not code:
            continue
        close = _to_float(row.get("Close"))
        volume = _to_float(row.get("Volume"))
        amount = _to_float(row.get("Amount"))
        change_pct = _to_float(row.get("ChagesRatio") if row.get("ChagesRatio") is not None else row.get("ChangesRatio"))
        market_cap = _to_float(row.get("Marcap"))
        if close is None or volume is None or amount is None or change_pct is None or market_cap is None:
            continue

        forced = code in force_set
        if not forced and close < cfg.min_price_krw:
            continue
        if not forced and amount < cfg.min_trading_value_krw:
            continue

        symbols.append(
            {
                "symbol": code,
                "code": code,
                "name": str(row.get("Name") or code),
                "market": cfg.market,
                "close": close,
                "current_price": close,
                "volume": volume,
                "trading_value": amount,
                "change_pct": change_pct,
                "market_cap": market_cap,
                "forced": forced,
                "source": str(row.get("Source") or row.get("source") or "provided_listing"),
                "quote_fetched_at": str(row.get("LocalTradedAt") or row.get("quote_fetched_at") or ""),
            }
        )

    symbols.sort(
        key=lambda item: (
            bool(item.get("forced")),
            float(item.get("trading_value") or 0),
            float(item.get("market_cap") or 0),
        ),
        reverse=True,
    )
    selected = symbols[: cfg.max_symbols]

    return {
        "schema_version": "trading_pipeline.universe.v1",
        "market": cfg.market,
        "generated_at": utc_now_iso(),
        "config": {
            "max_symbols": cfg.max_symbols,
            "min_price_krw": cfg.min_price_krw,
            "min_trading_value_krw": cfg.min_trading_value_krw,
            "forced_symbols": sorted(force_set),
        },
        "symbol_count": len(selected),
        "symbols": selected,
    }
