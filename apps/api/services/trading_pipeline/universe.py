from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from market_utils import normalize_market

from .store import utc_now_iso


@dataclass(frozen=True)
class UniverseConfig:
    market: str = "KOSPI"
    max_symbols: int = 200
    min_price_krw: float = 1000.0
    min_trading_value_krw: float = 5_000_000_000.0


REQUIRED_COLUMNS = ("Code", "Name", "Close", "Volume", "Amount", "Marcap")
CHANGE_RATIO_COLUMNS = ("ChagesRatio", "ChangesRatio")


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


def _load_stock_listing(market: str) -> list[dict[str, Any]]:
    import FinanceDataReader as fdr

    listing = fdr.StockListing(market.upper())
    missing = [column for column in REQUIRED_COLUMNS if column not in listing.columns]
    change_column = next((column for column in CHANGE_RATIO_COLUMNS if column in listing.columns), "")
    if not change_column:
        missing.append("ChagesRatio")
    if missing:
        raise ValueError(f"FinanceDataReader listing is missing columns: {', '.join(missing)}")
    return listing.loc[:, [*REQUIRED_COLUMNS, change_column]].to_dict(orient="records")


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
    rows = list(source_rows) if source_rows is not None else _load_stock_listing(cfg.market)
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
                "source": "finance_data_reader",
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
