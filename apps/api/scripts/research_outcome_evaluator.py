from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.market_data_service import resolve_stock_quote
from services.research_outcome_store import evaluate_snapshot_outcome
from services.research_store import list_latest_research_snapshots


def _price_from_quote(quote: dict[str, Any]) -> float:
    value = quote.get("price")
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise ValueError("quote_price_invalid") from None
    if price <= 0:
        raise ValueError("quote_price_invalid")
    return price


def run(*, limit: int = 200, dry_run: bool = False) -> dict[str, Any]:
    snapshots = list_latest_research_snapshots(limit=limit)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "selected_count": len(snapshots),
            "evaluated_count": 0,
            "error_count": 0,
            "errors": [],
            "items": [
                {
                    "symbol": item.get("symbol"),
                    "market": item.get("market"),
                    "run_id": item.get("run_id"),
                    "generated_at": item.get("generated_at"),
                }
                for item in snapshots[:20]
            ],
        }
    evaluated: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for snapshot in snapshots:
        symbol = str(snapshot.get("symbol") or "").upper()
        market = str(snapshot.get("market") or "").upper()
        if not symbol or not market:
            continue
        try:
            quote = resolve_stock_quote(symbol, market)
            current_price = _price_from_quote(quote)
            evaluated.append(evaluate_snapshot_outcome(snapshot, current_price=current_price))
        except Exception as exc:
            errors.append({"symbol": symbol, "market": market, "error": str(exc)})
    return {
        "ok": not errors,
        "selected_count": len(snapshots),
        "evaluated_count": len(evaluated),
        "error_count": len(errors),
        "errors": errors[:20],
        "items": evaluated[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate OpenAI research outcomes")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(limit=max(1, int(args.limit)), dry_run=bool(args.dry_run))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
