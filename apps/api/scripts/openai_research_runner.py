from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.research_source_enricher import build_research_source_pack
from services.openai_research_client import call_openai_research
from helpers import _ACTIVE_RESEARCH_MARKETS, _is_active_research_market


DEFAULT_API_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_RESEARCH_PROVIDER = "default"
MAX_AGENT_SIZE_INTENT_PCT = 40.0
ALLOWED_AGENT_RATINGS = {"strong_buy", "overweight", "hold", "underweight", "sell"}
ALLOWED_AGENT_ACTIONS = {"buy", "buy_watch", "hold", "reduce", "sell", "block"}
_QUOTE_FETCH_LOCK = threading.Lock()

_REQUIRED_OUTPUT_FIELDS = {
    "symbol": "string; target symbol/code",
    "market": "string; normalized market such as KOSPI, KOSDAQ, NASDAQ, NYSE",
    "confidence": "number 0..1",
    "rating": "one of strong_buy, overweight, hold, underweight, sell",
    "action": "one of buy, buy_watch, hold, reduce, sell, block",
    "summary": "short thesis in Korean",
    "bull_case": "array of strings",
    "bear_case": "array of strings",
    "catalysts": "array of strings",
    "risks": "array of strings",
    "invalidation_trigger": "object",
    "trade_plan": "object; size_intent_pct is only intent and will be clamped by risk guard",
    "technical_features": "object; include close_vs_sma20/close_vs_sma60/volume_ratio/rsi14 when available",
    "news_inputs": "array of cited news objects with title, source, url, published_at, summary; buy/buy_watch requires at least one trusted item from the last 72 hours",
    "evidence": "array of evidence objects with url or official source; required for buy/buy_watch and must not be blog/community/ad landing evidence",
    "data_quality": "object; has_recent_price, has_technical_features, has_news",
}


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _log(message: str, *, enabled: bool = True) -> None:
    if enabled:
        print(message, file=sys.stderr, flush=True)


def _api_base_url(base_url: str | None = None) -> str:
    return str(base_url or os.getenv("WEALTHPULSE_API_BASE_URL") or DEFAULT_API_BASE_URL).rstrip("/")


def _http_json(method: str, path: str, *, base_url: str | None = None, query: dict[str, list[str]] | None = None, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    url = f"{_api_base_url(base_url)}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query, doseq=True)}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.status), json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": body}
        return int(exc.code), parsed
    except Exception as exc:
        return 503, {"ok": False, "error": f"api_request_failed:{exc}"}


def _use_direct_routes(base_url: str | None = None) -> bool:
    """Opt into in-process route calls only for tests/debugging.

    Host-side research runs must use the live API HTTP surface so they hit the
    same Docker container, env, and mounted storage as production. Importing
    route handlers directly from the checkout can silently write to a different
    local path, so HTTP is the safe default.
    """
    text = str(base_url or "").strip().lower()
    env_value = str(os.getenv("WEALTHPULSE_RESEARCH_DIRECT_ROUTES") or "").strip().lower()
    return text in {"direct", "local"} or env_value in {"1", "true", "yes", "direct", "local"}


def handle_candidate_monitor_watchlist(query: dict[str, list[str]], *, base_url: str | None = None) -> tuple[int, dict[str, Any]]:
    if _use_direct_routes(base_url):
        from routes.candidate_monitor import handle_candidate_monitor_watchlist as route_handler  # type: ignore
        return route_handler(query)
    return _http_json("GET", "/api/monitor/watchlist", base_url=base_url, query=query)


def handle_research_ingest_bulk(payload: dict[str, Any], *, base_url: str | None = None) -> tuple[int, dict[str, Any]]:
    if _use_direct_routes(base_url):
        from routes.research import handle_research_ingest_bulk as route_handler  # type: ignore
        return route_handler(payload)
    return _http_json("POST", "/api/research/ingest/bulk", base_url=base_url, payload=payload)


def handle_research_run_status_save(payload: dict[str, Any], *, base_url: str | None = None) -> tuple[int, dict[str, Any]]:
    if _use_direct_routes(base_url):
        from routes.research import handle_research_run_status_save as route_handler  # type: ignore
        return route_handler(payload)
    return _http_json("POST", "/api/research/run-status", base_url=base_url, payload=payload)


def _market_query(markets: list[str], *, limit: int, mode: str) -> dict[str, list[str]]:
    query: dict[str, list[str]] = {
        "refresh": ["1"],
        "limit": [str(max(1, int(limit)))],
        "mode": [mode],
    }
    if markets:
        query["market"] = list(markets)
    return query


def _trim_dict(payload: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    return {key: source.get(key) for key in keys if source.get(key) not in (None, "", [], {})}


def _quote_enriched_target(target: dict[str, Any]) -> dict[str, Any]:
    row = dict(target)
    raw_technical = row.get("technical_snapshot")
    technical: dict[str, Any] = dict(raw_technical) if isinstance(raw_technical, dict) else {}
    if technical.get("current_price") not in (None, "") and technical.get("quote_fetched_at"):
        return row
    if str(os.getenv("WEALTHPULSE_RESEARCH_FETCH_QUOTES") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return row

    symbol = str(row.get("symbol") or row.get("code") or "").strip().upper()
    market = str(row.get("market") or "").strip().upper()
    if not symbol or not market:
        return row

    with _QUOTE_FETCH_LOCK:
        status, quote = _http_json(
            "GET",
            f"/api/stock/{parse.quote(symbol)}",
            query={"market": [market]},
        )
    if status != 200:
        raise RuntimeError(f"quote_fetch_failed:{symbol}:{status}:{quote.get('error') or quote}")
    current_price = quote.get("price")
    if current_price not in (None, ""):
        row["current_price"] = current_price
        row["price"] = current_price
        technical["current_price"] = current_price
        technical["close"] = current_price
    if quote.get("change_pct") not in (None, ""):
        technical["change_pct"] = quote.get("change_pct")
    technical["quote_source"] = str(quote.get("source") or "KIS")
    technical["quote_fetched_at"] = str(quote.get("fetched_at") or "")
    technical["freshness"] = "fresh"
    technical["quote_is_stale"] = bool(quote.get("is_stale", False))
    row["technical_snapshot"] = technical
    return row


def _compact_target(target: dict[str, Any]) -> dict[str, Any]:
    target = _quote_enriched_target(target)
    technical = _trim_dict(
        target.get("technical_snapshot"),
        (
            "current_price",
            "close",
            "change_pct",
            "volume_ratio",
            "rsi14",
            "atr14_pct",
            "close_vs_sma20",
            "close_vs_sma60",
            "quote_source",
            "quote_fetched_at",
        ),
    )
    criteria = _trim_dict(
        target.get("selection_criteria"),
        ("trading_value", "change_pct", "news_surge_score", "source_ranks"),
    )
    payload = {
        "symbol": target.get("symbol") or target.get("code"),
        "market": target.get("market"),
        "name": target.get("name"),
        "sector": target.get("sector"),
        "score": target.get("score"),
        "candidate_rank": target.get("candidate_rank"),
        "slot_type": target.get("slot_type"),
        "candidate_source": target.get("candidate_source"),
        "candidate_sources": target.get("candidate_sources"),
        "selection_reason": target.get("selection_reason") or target.get("reason"),
        "monitor_priority": target.get("monitor_priority") or target.get("priority"),
        "bluechip": target.get("bluechip"),
        "bluechip_reason": target.get("bluechip_reason"),
        "allocation_mode": target.get("allocation_mode"),
        "snapshot_research_score": target.get("snapshot_research_score"),
        "research_status": target.get("research_status"),
        "validation_grade": target.get("validation_grade"),
        "technical_snapshot": technical,
        "selection_criteria": criteria,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def build_feature_pack(target: dict[str, Any]) -> dict[str, Any]:
    source_pack = target.get("source_pack") if isinstance(target.get("source_pack"), dict) else build_research_source_pack(target)
    return {
        "target": _compact_target(target),
        "source_inputs": source_pack,
        "contract": {
            "schema": "Research Snapshot v2 agent analysis JSON",
            "required_fields": _REQUIRED_OUTPUT_FIELDS,
            "allowed_ratings": sorted(ALLOWED_AGENT_RATINGS),
            "allowed_actions": sorted(ALLOWED_AGENT_ACTIONS),
            "safety": {
                "do_not_place_orders": True,
                "order_execution_owner": "WealthPulse deterministic runtime and risk guard",
                "size_intent_max_pct_before_runtime_clamp": MAX_AGENT_SIZE_INTENT_PCT,
            },
        },
    }


def build_research_prompt(target: dict[str, Any]) -> str:
    feature_pack = build_feature_pack(target)
    return (
        "You are the OpenAI research analyst for WealthPulse.\n"
        "Analyze the candidate using the provided feature pack and source_inputs.\n"
        "Return ONLY one JSON object, no markdown, no code fence, no commentary.\n"
        "The JSON must satisfy the Research Snapshot v2 agent analysis contract.\n"
        "Do not place orders, do not call brokers, and do not claim execution. WealthPulse runtime and risk guard decide all orders.\n"
        "Use source_inputs.news_inputs as the primary news evidence. Do not invent news.\n"
        "If source_inputs.news_inputs is empty, set news_inputs=[] and data_quality.has_news=false, then use hold/reduce/sell/block only.\n"
        "Use source_inputs.evidence as official evidence where relevant.\n"
        "For buy/buy_watch, news_inputs must include title, source, url, published_at, summary. Missing URL, missing published_at, stale news, or untrusted source means hold.\n"
        "For buy/buy_watch, evidence must include URL or official data source. Feature-pack metadata alone never justifies buy/buy_watch.\n"
        "Allowed source labels: naver-openapi, google-news-rss, dart, opendart, krx, kind, company_ir, company_newsroom, sec, nasdaq, nyse.\n"
        "Blogs, communities, ad landing pages, anonymous claims, and URL-free evidence are not valid buy evidence.\n"
        "Keep trade_plan.size_intent_pct as intent only; risk guard will clamp and recalculate actual size.\n\n"
        "Feature pack:\n"
        f"{_json_dumps(feature_pack)}"
    )


def build_agent_research_ingest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from services.research_agent_payload import build_agent_research_ingest_payload as service_builder  # type: ignore
    return service_builder(payload)


def _merge_analysis_with_target(analysis: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    merged = dict(analysis)
    merged.pop("components", None)
    merged.setdefault("symbol", target.get("symbol") or target.get("code"))
    merged.setdefault("market", target.get("market"))
    merged.setdefault("candidate_source", "openai_research")
    source_pack = target.get("source_pack") if isinstance(target.get("source_pack"), dict) else {}
    source_news = source_pack.get("news_inputs") if isinstance(source_pack.get("news_inputs"), list) else []
    source_evidence = source_pack.get("evidence") if isinstance(source_pack.get("evidence"), list) else []
    if source_news:
        merged["news_inputs"] = [*source_news, *[item for item in (merged.get("news_inputs") or []) if isinstance(item, dict)]]
    if source_evidence:
        merged["evidence"] = [*source_evidence, *[item for item in (merged.get("evidence") or []) if isinstance(item, dict)]]
    if not isinstance(merged.get("technical_features"), dict) or not merged.get("technical_features"):
        technical = target.get("technical_snapshot") if isinstance(target.get("technical_snapshot"), dict) else {}
        if not technical:
            source_pack = target.get("source_pack") if isinstance(target.get("source_pack"), dict) else {}
            technical = source_pack.get("technical_features") if isinstance(source_pack.get("technical_features"), dict) else {}
        merged["technical_features"] = _trim_dict(
            technical,
            ("current_price", "close", "change_pct", "volume_ratio", "rsi14", "atr14_pct", "close_vs_sma20", "close_vs_sma60", "source", "fetched_at"),
        )
    data_quality = dict(merged.get("data_quality")) if isinstance(merged.get("data_quality"), dict) else {}
    data_quality.setdefault("analysis_mode", "agent_research")
    data_quality.setdefault("target_source", "candidate_monitor")
    data_quality["has_news"] = bool(merged.get("news_inputs"))
    data_quality["has_recent_price"] = bool(
        data_quality.get("has_recent_price")
        or (isinstance(merged.get("technical_features"), dict) and (merged["technical_features"].get("current_price") not in (None, "") or merged["technical_features"].get("close") not in (None, "")))
        or (isinstance(target.get("technical_snapshot"), dict) and target["technical_snapshot"].get("current_price") not in (None, ""))
        or target.get("current_price") not in (None, "")
        or target.get("price") not in (None, "")
    )
    data_quality["has_technical_features"] = bool(data_quality.get("has_technical_features") or merged.get("technical_features"))
    merged["data_quality"] = data_quality
    return merged


def run(
    *,
    markets: list[str],
    limit: int,
    mode: str,
    dry_run: bool = False,
    timeout: int = 300,
    concurrency: int = 3,
    api_base_url: str | None = None,
    progress: bool = True,
) -> tuple[int, dict[str, Any]]:
    started_monotonic = time.monotonic()
    inactive_markets = [
        str(market or "").strip().upper()
        for market in markets
        if str(market or "").strip() and not _is_active_research_market(str(market or ""))
    ]
    if inactive_markets:
        return 400, {
            "ok": False,
            "stage": "market_scope",
            "error": "inactive_research_market",
            "markets": markets,
            "inactive_markets": inactive_markets,
            "active_research_markets": sorted(_ACTIVE_RESEARCH_MARKETS),
        }
    query = _market_query(markets, limit=limit, mode=mode)
    _log(f"[research] collect targets markets={markets or ['KOSPI']} limit={limit} mode={mode}", enabled=progress)
    status_code, target_payload = handle_candidate_monitor_watchlist(query, base_url=api_base_url)
    if status_code != 200:
        _log(f"[research] target collection failed status={status_code}", enabled=progress)
        return status_code, {
            "ok": False,
            "stage": "target_collection",
            "error": target_payload.get("error") if isinstance(target_payload, dict) else "target_collection_failed",
            "details": target_payload,
        }

    target_items = target_payload.get("pending_items") if isinstance(target_payload, dict) else []
    if not isinstance(target_items, list):
        target_items = []
    target_items = [item for item in target_items if isinstance(item, dict)]
    if not target_items:
        _log("[research] no pending targets", enabled=progress)
        return 200, {
            "ok": True,
            "stage": "noop",
            "markets": markets,
            "mode": mode,
            "selected_count": 0,
            "message": "No pending monitor-slot research targets.",
        }

    enriched_targets: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []
    for target in target_items:
        enriched_target = dict(target)
        enriched_target["source_pack"] = build_research_source_pack(enriched_target)
        enriched_targets.append(enriched_target)
        prompt_rows.append(
            {
                "symbol": enriched_target.get("symbol") or enriched_target.get("code"),
                "market": enriched_target.get("market"),
                "prompt": build_research_prompt(enriched_target),
                "source_pack": enriched_target["source_pack"],
            }
        )
    _log(f"[research] selected targets={len(target_items)}", enabled=progress)
    if dry_run:
        _log("[research] dry-run only; research agent is not called", enabled=progress)
        return 200, {
            "ok": True,
            "stage": "dry_run",
            "markets": markets,
            "mode": mode,
            "selected_count": len(target_items),
            "prompts": prompt_rows,
        }

    analyses: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    ingest_results: list[dict[str, Any]] = []
    total = len(prompt_rows)
    command_preview = "openai responses"
    worker_count = max(1, min(int(concurrency or 1), total))
    _log(f"[research] provider=openai command={command_preview} timeout={max(1, int(timeout))}s concurrency={worker_count}", enabled=progress)

    def _process_one(index: int, target: dict[str, Any], prompt_row: dict[str, Any]) -> dict[str, Any]:
        symbol = str(prompt_row.get("symbol") or "")
        market = str(prompt_row.get("market") or "")
        try:
            _log(f"[research] {index}/{total} start {market}:{symbol}", enabled=progress)
            feature_pack = build_feature_pack(target)
            raw_analysis = call_openai_research(feature_pack, timeout=timeout)
            analysis = _merge_analysis_with_target(raw_analysis, target)
            ingest_payload = build_agent_research_ingest_payload({"items": [analysis]})
            ingest_status, ingest_result = handle_research_ingest_bulk(ingest_payload, base_url=api_base_url)
            accepted = int(ingest_result.get("accepted") or 0) if isinstance(ingest_result, dict) else 0
            ingest_row = {
                "symbol": symbol,
                "market": market,
                "status_code": ingest_status,
                "accepted": accepted,
                "result": ingest_result,
            }
            if not (200 <= ingest_status < 300) or accepted <= 0:
                raise RuntimeError(f"ingest_failed:{ingest_status}:accepted={accepted}")
            _log(f"[research] {index}/{total} ok {market}:{symbol} ingest_status={ingest_status} accepted={accepted}", enabled=progress)
            return {"ok": True, "analysis": analysis, "ingest_result": ingest_row, "symbol": symbol, "market": market}
        except Exception as exc:
            _log(f"[research] {index}/{total} failed {market}:{symbol} error={exc}", enabled=progress)
            return {"ok": False, "error": {"symbol": symbol, "market": market, "error": str(exc)}, "symbol": symbol, "market": market}

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_process_one, index, target, prompt_row)
            for index, (target, prompt_row) in enumerate(zip(enriched_targets, prompt_rows), start=1)
        ]
        for future in as_completed(futures):
            result = future.result()
            if result.get("ok"):
                analysis = result.get("analysis")
                if isinstance(analysis, dict):
                    analyses.append(analysis)
                ingest = result.get("ingest_result")
                if isinstance(ingest, dict):
                    ingest_results.append(ingest)
            else:
                error_row = result.get("error")
                if isinstance(error_row, dict):
                    errors.append(error_row)

    run_status_payload = {
        "provider": DEFAULT_RESEARCH_PROVIDER,
        "agent_provider": "openai",
        "selected_count": len(target_items),
        "success_count": len(analyses),
        "failure_count": len(errors),
        "partial_failure": bool(analyses and errors),
        "errors": errors,
        "duration_seconds": round(time.monotonic() - started_monotonic, 2),
        "avg_seconds_per_success": round((time.monotonic() - started_monotonic) / max(1, len(analyses)), 2) if analyses else None,
        "concurrency": worker_count,
    }
    handle_research_run_status_save(run_status_payload, base_url=api_base_url)

    if not analyses:
        _log(f"[research] all OpenAI calls or ingests failed errors={len(errors)}", enabled=progress)
        return 502, {
            "ok": False,
            "stage": "agent_failed",
            "markets": markets,
            "mode": mode,
            "selected_count": len(target_items),
            "duration_seconds": run_status_payload["duration_seconds"],
            "avg_seconds_per_success": run_status_payload["avg_seconds_per_success"],
            "concurrency": worker_count,
            "errors": errors,
            "ingest_results": ingest_results,
        }

    if errors:
        return 207, {
            "ok": False,
            "stage": "partial_failure",
            "markets": markets,
            "mode": mode,
            "selected_count": len(target_items),
            "agent_success_count": len(analyses),
            "agent_error_count": len(errors),
            "accepted_count": sum(int(item.get("accepted") or 0) for item in ingest_results),
            "duration_seconds": run_status_payload["duration_seconds"],
            "avg_seconds_per_success": run_status_payload["avg_seconds_per_success"],
            "concurrency": worker_count,
            "partial_failure": True,
            "errors": errors,
            "ingest_results": ingest_results,
        }

    return 200, {
        "ok": True,
        "stage": "ingested_incremental",
        "markets": markets,
        "mode": mode,
        "selected_count": len(target_items),
        "agent_success_count": len(analyses),
        "agent_error_count": len(errors),
        "accepted_count": sum(int(item.get("accepted") or 0) for item in ingest_results),
        "duration_seconds": run_status_payload["duration_seconds"],
        "avg_seconds_per_success": run_status_payload["avg_seconds_per_success"],
        "concurrency": worker_count,
        "errors": errors,
        "ingest_results": ingest_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run WealthPulse research analysis for pending monitor targets")
    parser.add_argument("--market", action="append", default=[])
    parser.add_argument("--limit", type=int, default=9)
    parser.add_argument("--mode", choices=["missing_or_stale", "missing_only", "stale_only", "all"], default="missing_or_stale")
    parser.add_argument("--dry-run", action="store_true", help="Collect targets and print prompts without calling the research agent")
    parser.add_argument("--api-base-url", default=None, help="WealthPulse API base URL for host-side execution, default: env WEALTHPULSE_API_BASE_URL or http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--no-progress", action="store_true", help="Do not print progress logs to stderr")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    status_code, payload = run(
        markets=list(args.market),
        limit=max(1, int(args.limit)),
        mode=args.mode,
        dry_run=bool(args.dry_run),
        timeout=max(1, int(args.timeout)),
        concurrency=max(1, int(args.concurrency)),
        api_base_url=args.api_base_url,
        progress=not bool(args.no_progress),
    )
    print(json.dumps({"status_code": status_code, **payload}, ensure_ascii=False, indent=2))
    if status_code == 207 or payload.get("partial_failure"):
        return 2
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
