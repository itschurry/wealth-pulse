from __future__ import annotations

from typing import Any, Mapping

from .store import utc_now_iso

REALTIME_MOVER_CHANGE_PCT = 2.0
REALTIME_MOVER_TRADING_VALUE = 50_000_000_000.0


def _rank(values: list[dict[str, Any]], field: str) -> dict[str, int]:
    ordered = sorted(values, key=lambda item: float(item.get(field) or 0), reverse=True)
    return {str(item["symbol"]): index + 1 for index, item in enumerate(ordered)}


def _score_symbol(row: Mapping[str, Any], ranks: Mapping[str, dict[str, int]]) -> tuple[float, dict[str, float], list[str]]:
    symbol = str(row["symbol"])
    amount = float(row.get("trading_value") or 0)
    change_pct = float(row.get("change_pct") or 0)
    volume = float(row.get("volume") or 0)

    amount_rank = ranks["trading_value"][symbol]
    change_rank = ranks["change_pct"][symbol]
    volume_rank = ranks["volume"][symbol]

    amount_score = max(0.0, 35.0 - amount_rank * 0.25)
    change_score = max(0.0, 25.0 - change_rank * 0.20)
    volume_score = max(0.0, 15.0 - volume_rank * 0.10)
    mover_score = 18.0 if change_pct >= REALTIME_MOVER_CHANGE_PCT or amount >= REALTIME_MOVER_TRADING_VALUE else 0.0
    forced_score = 7.0 if row.get("forced") else 0.0

    reasons = ["market_scanner"]
    if mover_score:
        reasons.append("realtime_mover")
    if amount_rank <= 30:
        reasons.append("trading_value_top")
    if change_rank <= 30:
        reasons.append("change_rate_top")
    if volume_rank <= 30 and volume > 0:
        reasons.append("volume_top")
    if row.get("forced"):
        reasons.append("forced_symbol")

    breakdown = {
        "trading_value_rank": float(amount_rank),
        "trading_value": round(amount_score, 4),
        "change_rank": float(change_rank),
        "change_rate": round(change_score, 4),
        "volume_rank": float(volume_rank),
        "volume": round(volume_score, 4),
        "realtime_mover": mover_score,
        "forced_symbol": forced_score,
    }
    return round(sum(value for key, value in breakdown.items() if not key.endswith("_rank")), 4), breakdown, reasons


def scan_universe(universe: Mapping[str, Any], *, max_candidates: int = 120) -> dict[str, Any]:
    rows = list(universe.get("symbols") or [])
    if not rows:
        return {
            "schema_version": "trading_pipeline.scan.v1",
            "market": universe.get("market"),
            "generated_at": utc_now_iso(),
            "candidate_count": 0,
            "candidates": [],
        }

    ranks = {
        "trading_value": _rank(rows, "trading_value"),
        "change_pct": _rank(rows, "change_pct"),
        "volume": _rank(rows, "volume"),
    }
    candidates: list[dict[str, Any]] = []
    for row in rows:
        score, breakdown, reasons = _score_symbol(row, ranks)
        candidates.append(
            {
                "symbol": row["symbol"],
                "code": row["symbol"],
                "name": row.get("name") or row["symbol"],
                "market": row.get("market") or universe.get("market"),
                "scanner_score": score,
                "scanner_score_breakdown": breakdown,
                "reason_codes": reasons,
                "technical_snapshot": {
                    "current_price": row.get("current_price"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "trading_value": row.get("trading_value"),
                    "change_pct": row.get("change_pct"),
                    "market_cap": row.get("market_cap"),
                    "source": row.get("source"),
                    "fetched_at": universe.get("generated_at"),
                    "quote_fetched_at": row.get("quote_fetched_at"),
                },
            }
        )

    candidates.sort(key=lambda item: float(item.get("scanner_score") or 0), reverse=True)
    selected = candidates[: max(1, int(max_candidates))]
    for index, candidate in enumerate(selected, start=1):
        candidate["scanner_rank"] = index

    return {
        "schema_version": "trading_pipeline.scan.v1",
        "market": universe.get("market"),
        "generated_at": utc_now_iso(),
        "universe_generated_at": universe.get("generated_at"),
        "candidate_count": len(selected),
        "candidates": selected,
    }
