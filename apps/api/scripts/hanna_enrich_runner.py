from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.research import (  # noqa: E402
    handle_research_ingest_bulk,
    handle_research_scanner_enrich_targets,
    handle_research_status,
)


def _now_local() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()


def _bucket_now(now: dt.datetime | None = None) -> str:
    current = now or _now_local()
    return current.replace(second=0, microsecond=0).isoformat()


def _generated_now(now: dt.datetime | None = None) -> str:
    current = now or _now_local()
    return current.replace(second=0, microsecond=0).isoformat()


def _market_label(market: str) -> str:
    mapping = {
        "KOSPI": "국내 대형주",
        "KOSDAQ": "국내 성장주",
        "NASDAQ": "미국 기술주",
        "NYSE": "미국 대형주",
        "KR": "국내 시장",
        "US": "미국 시장",
    }
    return mapping.get(str(market or "").upper(), str(market or "시장"))


def _score_target(item: dict[str, Any]) -> tuple[float, dict[str, float], list[str], list[str], str]:
    snapshot_exists = bool(item.get("snapshot_exists"))
    snapshot_fresh = bool(item.get("snapshot_fresh"))
    rank_raw = item.get("candidate_rank")
    final_action = str(item.get("final_action") or "").strip().lower()
    market = str(item.get("market") or "").upper()
    strategy_name = str(item.get("strategy_name") or "").strip() or "scanner"
    name = str(item.get("name") or item.get("symbol") or "종목")

    try:
        rank = int(rank_raw) if rank_raw is not None else 999
    except (TypeError, ValueError):
        rank = 999

    freshness_score = 1.0 if not snapshot_exists else (0.25 if not snapshot_fresh else 0.85)
    rank_score = 1.0 if rank <= 3 else 0.8 if rank <= 10 else 0.6 if rank <= 20 else 0.45
    action_score = 1.0 if final_action == "review_for_entry" else 0.72 if final_action == "watch_only" else 0.4

    weighted = (freshness_score * 0.45) + (rank_score * 0.35) + (action_score * 0.20)
    research_score = round(max(0.05, min(0.95, weighted)), 2)

    warnings: list[str] = []
    tags: list[str] = []

    summary = (
        f"{name}는 {_market_label(market)} scanner 후보야. "
        f"전략 {strategy_name} 기준 우선 검토 대상이고, "
        f"현재 상태는 {'신규 research 필요' if not snapshot_exists else 'stale research 갱신 필요' if not snapshot_fresh else '운영 재점검'} 쪽으로 보는 게 맞아."
    )

    components = {
        "freshness_score": round(freshness_score, 2),
        "candidate_rank_score": round(rank_score, 2),
        "action_priority_score": round(action_score, 2),
    }
    return research_score, components, warnings, tags, summary


def _build_ingest_payload(items: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    now = _now_local()
    generated_at = _generated_now(now)
    bucket_ts = _bucket_now(now)
    normalized_items: list[dict[str, Any]] = []

    for item in items:
        symbol = str(item.get("symbol") or "").strip().upper()
        market = str(item.get("market") or "").strip().upper()
        if not symbol or not market:
            continue
        research_score, components, warnings, tags, summary = _score_target(item)
        normalized_items.append(
            {
                "symbol": symbol,
                "market": market,
                "bucket_ts": bucket_ts,
                "generated_at": generated_at,
                "research_score": research_score,
                "components": {"freshness_score": components.get("freshness_score", 0.5)},
                "warnings": warnings,
                "tags": tags,
                "summary": summary,
                "ttl_minutes": 180,
            }
        )

    return {
        "provider": provider,
        "schema_version": "v1",
        "run_id": f"hanna-enrich-{uuid.uuid4().hex[:12]}",
        "generated_at": generated_at,
        "items": normalized_items,
    }


def run(provider: str, markets: list[str], limit: int, mode: str) -> tuple[int, dict[str, Any]]:
    query: dict[str, list[str]] = {
        "provider": [provider],
        "limit": [str(limit)],
        "mode": [mode],
    }
    if markets:
        query["market"] = markets

    status_code, target_payload = handle_research_scanner_enrich_targets(query)
    if status_code != 200:
        return status_code, {
            "ok": False,
            "stage": "target_collection",
            "error": target_payload.get("error") or "target_collection_failed",
            "details": target_payload,
        }

    target_items = target_payload.get("items") if isinstance(target_payload, dict) else []
    if not isinstance(target_items, list):
        target_items = []

    if not target_items:
        _, provider_status = handle_research_status({"provider": [provider]})
        return 200, {
            "ok": True,
            "stage": "noop",
            "provider": provider,
            "markets": markets,
            "mode": mode,
            "selected_count": 0,
            "message": "No missing/stale research targets.",
            "provider_status": provider_status,
        }

    ingest_payload = _build_ingest_payload(target_items, provider)
    ingest_status, ingest_result = handle_research_ingest_bulk(ingest_payload)
    _, provider_status = handle_research_status({"provider": [provider]})

    result = {
        "ok": 200 <= ingest_status < 300,
        "stage": "ingested",
        "provider": provider,
        "markets": markets,
        "mode": mode,
        "selected_count": len(target_items),
        "targets": [
            {
                "symbol": item.get("symbol"),
                "market": item.get("market"),
                "strategy_name": item.get("strategy_name"),
                "candidate_rank": item.get("candidate_rank"),
                "final_action": item.get("final_action"),
            }
            for item in target_items
        ],
        "ingest": ingest_result,
        "provider_status": provider_status,
    }
    return ingest_status, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Hanna scanner enrich runner")
    parser.add_argument("--provider", default="openclaw")
    parser.add_argument("--market", action="append", default=[])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=["missing_or_stale", "missing_only", "stale_only"],
        default="missing_or_stale",
    )
    args = parser.parse_args()

    status_code, payload = run(
        provider=args.provider,
        markets=list(args.market),
        limit=max(1, int(args.limit)),
        mode=args.mode,
    )
    print(json.dumps({"status_code": status_code, **payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
