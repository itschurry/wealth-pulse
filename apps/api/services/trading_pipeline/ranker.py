from __future__ import annotations

from typing import Any, Mapping

from .store import utc_now_iso


def _monitor_priority(candidate: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
    scanner_score = float(candidate.get("scanner_score") or 0)
    reasons = set(candidate.get("reason_codes") or [])
    tech = candidate.get("technical_snapshot") or {}
    trading_value = float(tech.get("trading_value") or 0)
    change_pct = float(tech.get("change_pct") or 0)

    realtime_bonus = 20.0 if "realtime_mover" in reasons else 0.0
    liquidity_bonus = min(18.0, trading_value / 10_000_000_000.0)
    momentum_bonus = min(16.0, max(0.0, change_pct) * 2.0)
    scanner_component = min(42.0, scanner_score * 0.42)

    breakdown = {
        "scanner_score": round(scanner_component, 4),
        "realtime_mover": realtime_bonus,
        "liquidity": round(liquidity_bonus, 4),
        "momentum": round(momentum_bonus, 4),
    }
    return round(sum(breakdown.values()), 4), breakdown


def rank_candidates(
    scan_snapshot: Mapping[str, Any],
    *,
    max_candidates: int = 100,
    active_limit: int = 30,
) -> dict[str, Any]:
    ranked: list[dict[str, Any]] = []
    for candidate in scan_snapshot.get("candidates") or []:
        priority, breakdown = _monitor_priority(candidate)
        item = dict(candidate)
        item["monitor_priority"] = priority
        item["monitor_priority_breakdown"] = breakdown
        item["candidate_source"] = "market_scanner"
        item["candidate_sources"] = sorted(set(candidate.get("reason_codes") or ["market_scanner"]))
        item["selection_reason"] = item["candidate_sources"][0]
        ranked.append(item)

    ranked.sort(key=lambda item: float(item.get("monitor_priority") or 0), reverse=True)
    selected = ranked[: max(1, int(max_candidates))]
    active = selected[: max(1, int(active_limit))]
    for index, candidate in enumerate(selected, start=1):
        candidate["candidate_rank"] = index
        candidate["active_slot"] = index <= len(active)

    return {
        "schema_version": "trading_pipeline.rank.v1",
        "market": scan_snapshot.get("market"),
        "generated_at": utc_now_iso(),
        "scan_generated_at": scan_snapshot.get("generated_at"),
        "candidate_count": len(selected),
        "active_slot_count": len(active),
        "candidates": selected,
        "active_slots": active,
    }
