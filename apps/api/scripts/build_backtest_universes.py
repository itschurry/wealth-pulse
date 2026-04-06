#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve()
_API_ROOT = _SCRIPT_PATH.parents[1]
_REPO_ROOT = _API_ROOT.parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

import FinanceDataReader as fdr  # type: ignore[import-not-found]

OUTPUT_DIR = _API_ROOT / "config" / "universes"

SP100_TICKERS = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AMAT", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK.B", "C",
    "CAT", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS", "CVX",
    "DE", "DHR", "DIS", "DUK", "EMR", "FDX", "GD", "GE", "GEV", "GILD",
    "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU", "ISRG",
    "JNJ", "JPM", "KO", "LIN", "LLY", "LMT", "LOW", "LRCX", "MA", "MCD",
    "MDLZ", "MDT", "META", "MMM", "MO", "MRK", "MS", "MSFT", "MU", "NEE",
    "NFLX", "NKE", "NOW", "NVDA", "ORCL", "PEP", "PFE", "PG", "PLTR", "PM",
    "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TMO", "TMUS", "TSLA",
    "TXN", "UBER", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT", "XOM",
]


def _write_json(path: Path, payload: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def build_kospi100() -> list[dict]:
    df = fdr.StockListing("KRX-MARCAP")
    code_col = "Code" if "Code" in df.columns else "Symbol"
    name_col = "Name"
    market_col = "Market" if "Market" in df.columns else "MarketId"
    marcap_col = "Marcap"

    filtered = df
    if market_col in df.columns:
        filtered = df[df[market_col].astype(str).isin(["KOSPI", "STK"])]

    top = filtered.sort_values(marcap_col, ascending=False).head(100)
    rows = [
        {
            "code": str(row[code_col]).strip().upper(),
            "name": str(row[name_col]).strip(),
            "market": "KOSPI",
        }
        for _, row in top.iterrows()
        if str(row[code_col]).strip()
    ]
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if row["code"] in seen:
            continue
        seen.add(row["code"])
        deduped.append(row)
    return deduped[:100]


def build_sp100() -> list[dict]:
    sp500 = fdr.StockListing("S&P500")
    nasdaq = fdr.StockListing("NASDAQ")
    nyse = fdr.StockListing("NYSE")

    def _rows_to_map(df, market_name: str) -> dict[str, dict]:
        mapping: dict[str, dict] = {}
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol") or row.get("Code") or "").strip().upper()
            if not symbol:
                continue
            mapping[symbol] = {
                "code": symbol,
                "name": str(row.get("Name") or symbol).strip() or symbol,
                "market": market_name,
            }
        return mapping

    sp500_map = _rows_to_map(sp500, "US")
    nasdaq_map = _rows_to_map(nasdaq, "NASDAQ")
    nyse_map = _rows_to_map(nyse, "NYSE")

    rows: list[dict] = []
    for ticker in SP100_TICKERS:
        item = nasdaq_map.get(ticker) or nyse_map.get(ticker) or sp500_map.get(ticker)
        if item is None and ticker == "BRK.B":
            item = nasdaq_map.get("BRK-B") or nyse_map.get("BRK-B") or sp500_map.get("BRK-B")
            if item:
                item = {**item, "code": "BRK.B"}
        if item is None:
            rows.append({"code": ticker, "name": ticker, "market": "US"})
        else:
            rows.append(item)
    return rows


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    kospi100 = build_kospi100()
    sp100 = build_sp100()
    _write_json(OUTPUT_DIR / "kospi100.json", kospi100)
    _write_json(OUTPUT_DIR / "sp100.json", sp100)
    print(f"kospi100={len(kospi100)} -> {OUTPUT_DIR / 'kospi100.json'}")
    print(f"sp100={len(sp100)} -> {OUTPUT_DIR / 'sp100.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
