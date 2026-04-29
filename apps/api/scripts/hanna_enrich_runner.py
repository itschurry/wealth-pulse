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

from routes.candidate_monitor import handle_candidate_monitor_watchlist  # noqa: E402
from routes.research import handle_research_ingest_bulk, handle_research_status  # noqa: E402
from services.research_store import DEFAULT_RESEARCH_PROVIDER  # noqa: E402


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
    tags: list[str] = ["deterministic_fallback"]

    summary = (
        f"{name}는 {_market_label(market)} scanner 후보야. "
        f"전략 {strategy_name} 기준 우선 검토 대상이고, "
        f"현재 상태는 {'신규 research 필요' if not snapshot_exists else 'stale research 갱신 필요' if not snapshot_fresh else '운영 재점검'} 쪽으로 보는 게 맞아. "
        "이 스냅샷은 Hermes/LLM 분석이 아니라 deterministic scanner fallback이므로 뉴스·정성 분석 전 확정 매수 근거로 쓰면 안 돼."
    )

    components = {
        "freshness_score": round(freshness_score, 2),
        "candidate_rank_score": round(rank_score, 2),
        "action_priority_score": round(action_score, 2),
    }
    return research_score, components, warnings, tags, summary


def _coerce_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_scanner_score(value: Any) -> float | None:
    score = _coerce_float(value)
    if score is None:
        return None
    if score > 1.0:
        score = score / 100.0
    return round(max(0.0, min(1.0, score)), 4)


def _risk_inputs(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("risk_inputs")
    return dict(raw) if isinstance(raw, dict) else {}


def _build_technical_features(item: dict[str, Any]) -> dict[str, Any]:
    rank = _coerce_int(item.get("candidate_rank"), 999)
    risk_inputs = _risk_inputs(item)
    features: dict[str, Any] = {
        "source": "candidate_monitor",
        "strategy_name": str(item.get("strategy_name") or "scanner").strip() or "scanner",
        "candidate_rank": rank,
        "final_action": str(item.get("final_action") or "").strip().lower(),
        "signal_state": str(item.get("signal_state") or "").strip().lower(),
    }
    scanner_score = _normalize_scanner_score(item.get("score"))
    if scanner_score is not None:
        features["scanner_score"] = scanner_score
    for source_key, target_key in (("stop_loss_pct", "stop_loss_pct"), ("take_profit_pct", "take_profit_pct")):
        numeric = _coerce_float(risk_inputs.get(source_key))
        if numeric is not None:
            features[target_key] = numeric
    return features


def _agent_rating_action(item: dict[str, Any], research_score: float) -> tuple[str, str]:
    final_action = str(item.get("final_action") or "").strip().lower()
    signal_state = str(item.get("signal_state") or "").strip().lower()
    rank = _coerce_int(item.get("candidate_rank"), 999) or 999
    if final_action == "review_for_entry" and signal_state == "entry" and rank <= 10 and research_score >= 0.65:
        return "overweight", "buy_watch"
    if final_action in {"blocked", "do_not_touch"}:
        return "underweight", "block"
    return "hold", "hold"


def _build_v2_agent_fields(item: dict[str, Any], research_score: float, summary: str) -> dict[str, Any]:
    technical_features = _build_technical_features(item)
    rating, action = _agent_rating_action(item, research_score)
    final_action = technical_features.get("final_action") or "unknown"
    signal_state = technical_features.get("signal_state") or "unknown"
    rank = technical_features.get("candidate_rank")
    strategy_name = technical_features.get("strategy_name")
    snapshot_exists = bool(item.get("snapshot_exists"))
    snapshot_fresh = bool(item.get("snapshot_fresh"))
    research_context = "new_research" if not snapshot_exists else "fresh_recheck" if snapshot_fresh else "stale_recheck"

    return {
        "confidence": research_score,
        "time_horizon_days": 3,
        "rating": rating,
        "action": action,
        "candidate_source": "candidate_monitor_scanner",
        "bull_case": [
            f"candidate monitor rank {rank} / strategy {strategy_name}",
            f"runtime final_action={final_action}, signal_state={signal_state}",
        ],
        "bear_case": [
            "뉴스·실적·거시 이벤트를 Hermes/LLM이 아직 독립 검증하지 않았다.",
            "deterministic scanner fallback은 가격/랭크 기반 우선순위일 뿐 확정 매수 판단이 아니다.",
        ],
        "catalysts": ["candidate_monitor_priority", research_context],
        "risks": [
            "Hermes/LLM 뉴스·차트 종합 분석 전에는 자동매수 확정 근거로 부족하다.",
            "스캐너 점수는 시장 급변, 공시, 장중 유동성 악화를 반영하지 못할 수 있다.",
        ],
        "invalidation_trigger": {
            "type": "runtime_recheck",
            "condition": "final_action changes away from review_for_entry or signal_state loses entry alignment",
        },
        "trade_plan": {
            "intent": "watchlist_enrich",
            "entry": "risk_guard_and_runtime_only",
            "sizing": "deterministic_risk_guard_clamped",
            "notes": "Fallback v2 contract; real Hermes analysis should replace this snapshot before agent-primary live use.",
        },
        "technical_features": technical_features,
        "news_inputs": [],
        "evidence": [
            {
                "type": "scanner_snapshot",
                "source": "candidate_monitor",
                "summary": summary,
                "final_action": final_action,
                "signal_state": signal_state,
                "candidate_rank": rank,
            }
        ],
        "data_quality": {
            "has_recent_price": True,
            "has_technical_features": True,
            "has_news": False,
            "research_context": research_context,
            "analysis_mode": "deterministic_fallback",
        },
    }


def _build_ingest_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
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
                "components": components,
                "warnings": warnings,
                "tags": tags,
                "summary": summary,
                "ttl_minutes": 180,
                **_build_v2_agent_fields(item, research_score, summary),
            }
        )

    return {
        "provider": DEFAULT_RESEARCH_PROVIDER,
        "schema_version": "v2",
        "run_id": f"hanna-enrich-{uuid.uuid4().hex[:12]}",
        "generated_at": generated_at,
        "items": normalized_items,
    }


def run(markets: list[str], limit: int, mode: str) -> tuple[int, dict[str, Any]]:
    query: dict[str, list[str]] = {
        "refresh": ["1"],
        "limit": [str(limit)],
        "mode": [mode],
    }
    if markets:
        query["market"] = markets

    status_code, target_payload = handle_candidate_monitor_watchlist(query)
    if status_code != 200:
        return status_code, {
            "ok": False,
            "stage": "target_collection",
            "error": target_payload.get("error") or "target_collection_failed",
            "details": target_payload,
        }

    target_items = target_payload.get("pending_items") if isinstance(target_payload, dict) else []
    if not isinstance(target_items, list):
        target_items = []

    if not target_items:
        _, provider_status = handle_research_status({})
        return 200, {
            "ok": True,
            "stage": "noop",
            "provider": DEFAULT_RESEARCH_PROVIDER,
            "markets": markets,
            "mode": mode,
            "selected_count": 0,
            "message": "No pending monitor-slot research targets.",
            "provider_status": provider_status,
        }

    ingest_payload = _build_ingest_payload(target_items)
    ingest_status, ingest_result = handle_research_ingest_bulk(ingest_payload)
    _, provider_status = handle_research_status({})

    result = {
        "ok": 200 <= ingest_status < 300,
        "stage": "ingested",
        "provider": DEFAULT_RESEARCH_PROVIDER,
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
    parser.add_argument("--market", action="append", default=[])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=["missing_or_stale", "missing_only", "stale_only"],
        default="missing_or_stale",
    )
    args = parser.parse_args()

    status_code, payload = run(
        markets=list(args.market),
        limit=max(1, int(args.limit)),
        mode=args.mode,
    )
    print(json.dumps({"status_code": status_code, **payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
