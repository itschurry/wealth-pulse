from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_AGENT_COMMAND = "hermes --oneshot"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_RESEARCH_PROVIDER = "default"
DEFAULT_AGENT_TTL_MINUTES = 180
MAX_AGENT_SIZE_INTENT_PCT = 5.0
ALLOWED_AGENT_RATINGS = {"strong_buy", "overweight", "hold", "underweight", "sell"}
ALLOWED_AGENT_ACTIONS = {"buy", "buy_watch", "hold", "reduce", "sell", "block"}
BUY_RATINGS = {"strong_buy", "overweight"}
BUY_ACTIONS = {"buy", "buy_watch"}

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
    "news_inputs": "array of cited news/source objects; empty only for non-buy neutral calls",
    "evidence": "array of evidence objects; required for buy/buy_watch",
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

    Host-side Hermes runs must use the live API HTTP surface so they hit the
    same Docker container, env, and mounted storage as production. Importing
    route handlers directly from the checkout can silently write to a different
    local path, so HTTP is the safe default.
    """
    text = str(base_url or "").strip().lower()
    env_value = str(os.getenv("WEALTHPULSE_HERMES_DIRECT_ROUTES") or "").strip().lower()
    return text in {"direct", "local"} or env_value in {"1", "true", "yes", "direct", "local"}


def handle_candidate_monitor_watchlist(query: dict[str, list[str]], *, base_url: str | None = None) -> tuple[int, dict[str, Any]]:
    if _use_direct_routes(base_url):
        try:
            from routes.candidate_monitor import handle_candidate_monitor_watchlist as route_handler  # type: ignore
            return route_handler(query)
        except Exception:
            pass
    return _http_json("GET", "/api/monitor/watchlist", base_url=base_url, query=query)


def handle_research_ingest_bulk(payload: dict[str, Any], *, base_url: str | None = None) -> tuple[int, dict[str, Any]]:
    if _use_direct_routes(base_url):
        try:
            from routes.research import handle_research_ingest_bulk as route_handler  # type: ignore
            return route_handler(payload)
        except Exception:
            pass
    return _http_json("POST", "/api/research/ingest/bulk", base_url=base_url, payload=payload)


def _market_query(markets: list[str], *, limit: int, mode: str) -> dict[str, list[str]]:
    query: dict[str, list[str]] = {
        "refresh": ["1"],
        "limit": [str(max(1, int(limit)))],
        "mode": [mode],
    }
    if markets:
        query["market"] = list(markets)
    return query


def build_feature_pack(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": dict(target),
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
        "You are the Hermes research analyst for WealthPulse.\n"
        "Analyze the candidate using the provided feature pack and any explicitly sourced news/tool evidence you can cite.\n"
        "Return ONLY one JSON object, no markdown, no code fence, no commentary.\n"
        "The JSON must satisfy the Research Snapshot v2 agent analysis contract.\n"
        "Do not place orders, do not call brokers, and do not claim execution. WealthPulse runtime and risk guard decide all orders.\n"
        "Do not invent news. If no current sourced news is available, set news_inputs=[] and data_quality.has_news=false.\n"
        "For buy/buy_watch, include technical_features and evidence. If evidence is weak, use hold or buy_watch rather than buy.\n"
        "Keep trade_plan.size_intent_pct as intent only; risk guard will clamp and recalculate actual size.\n\n"
        "Feature pack:\n"
        f"{_json_dumps(feature_pack)}"
    )


def parse_agent_json(output: str) -> dict[str, Any]:
    text = str(output or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("agent_output_json_missing") from None
        try:
            parsed = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("agent_output_json_invalid") from exc
    if not isinstance(parsed, dict):
        raise ValueError("agent_output_must_be_object")
    return parsed


def _command_list(agent_command: list[str] | str | None) -> list[str]:
    if isinstance(agent_command, list):
        return [str(part) for part in agent_command if str(part)]
    command_text = str(agent_command or os.getenv("WEALTHPULSE_HERMES_RESEARCH_COMMAND") or DEFAULT_AGENT_COMMAND).strip()
    return shlex.split(command_text)


def _command_with_prompt(command: list[str], prompt: str) -> list[str]:
    if any("{prompt}" in part for part in command):
        return [part.replace("{prompt}", prompt) for part in command]
    return [*command, prompt]


def call_hermes_agent(
    prompt: str,
    *,
    agent_command: list[str] | str | None = None,
    timeout: int = 300,
) -> str:
    command = _command_list(agent_command)
    if not command:
        raise ValueError("agent_command_required")
    timeout_seconds = max(1, int(timeout))
    try:
        completed = subprocess.run(
            _command_with_prompt(command, prompt),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = str(exc.stderr or "").strip()
        raise RuntimeError(f"hermes_agent_timeout:{timeout_seconds}s:{stderr[:500]}") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"hermes_agent_failed:{completed.returncode}:{completed.stderr.strip()[:500]}")
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("hermes_agent_empty_output")
    return output


def _now_local() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()


def _minute_iso(value: Any | None = None) -> str:
    if value is None or value == "":
        parsed = _now_local()
    else:
        parsed = dt.datetime.fromisoformat(str(value).strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone().replace(second=0, microsecond=0).isoformat()


def _as_score(value: Any, *, field: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}_invalid") from None
    if score > 1.0:
        score = score / 100.0
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{field}_out_of_range")
    return round(score, 4)


def _text(value: Any, *, field: str, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field}_required")
    return text


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_market(market: Any) -> str:
    text = str(market or "").strip().upper()
    aliases = {"KR": "KOSPI", "KOREA": "KOSPI", "US": "NASDAQ", "USA": "NASDAQ"}
    return aliases.get(text, text)


def build_agent_research_ingest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from services.research_agent_payload import build_agent_research_ingest_payload as service_builder  # type: ignore
    return service_builder(payload)
def _merge_analysis_with_target(analysis: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    merged = dict(analysis)
    merged.setdefault("symbol", target.get("symbol") or target.get("code"))
    merged.setdefault("market", target.get("market"))
    merged.setdefault("candidate_source", "hermes_agent")
    data_quality = dict(merged.get("data_quality")) if isinstance(merged.get("data_quality"), dict) else {}
    data_quality.setdefault("analysis_mode", "agent_research")
    data_quality.setdefault("target_source", "candidate_monitor")
    merged["data_quality"] = data_quality
    return merged


def run(
    *,
    markets: list[str],
    limit: int,
    mode: str,
    dry_run: bool = False,
    agent_command: list[str] | str | None = None,
    timeout: int = 300,
    api_base_url: str | None = None,
    progress: bool = True,
) -> tuple[int, dict[str, Any]]:
    query = _market_query(markets, limit=limit, mode=mode)
    _log(f"[hermes] collect targets markets={markets or ['KOSPI']} limit={limit} mode={mode}", enabled=progress)
    status_code, target_payload = handle_candidate_monitor_watchlist(query, base_url=api_base_url)
    if status_code != 200:
        _log(f"[hermes] target collection failed status={status_code}", enabled=progress)
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
        _log("[hermes] no pending targets", enabled=progress)
        return 200, {
            "ok": True,
            "stage": "noop",
            "markets": markets,
            "mode": mode,
            "selected_count": 0,
            "message": "No pending monitor-slot research targets.",
        }

    prompt_rows = [
        {
            "symbol": target.get("symbol") or target.get("code"),
            "market": target.get("market"),
            "prompt": build_research_prompt(target),
        }
        for target in target_items
    ]
    _log(f"[hermes] selected targets={len(target_items)}", enabled=progress)
    if dry_run:
        _log("[hermes] dry-run only; Hermes is not called", enabled=progress)
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
    command_preview = " ".join(shlex.quote(part) for part in _command_list(agent_command))
    _log(f"[hermes] command={command_preview} timeout={max(1, int(timeout))}s", enabled=progress)
    for index, (target, prompt_row) in enumerate(zip(target_items, prompt_rows), start=1):
        symbol = str(prompt_row.get("symbol") or "")
        market = str(prompt_row.get("market") or "")
        try:
            _log(f"[hermes] {index}/{total} start {market}:{symbol}", enabled=progress)
            raw_output = call_hermes_agent(prompt_row["prompt"], agent_command=agent_command, timeout=timeout)
            analysis = _merge_analysis_with_target(parse_agent_json(raw_output), target)
            ingest_payload = build_agent_research_ingest_payload({"items": [analysis]})
            ingest_status, ingest_result = handle_research_ingest_bulk(ingest_payload, base_url=api_base_url)
            accepted = int(ingest_result.get("accepted") or 0) if isinstance(ingest_result, dict) else 0
            ingest_results.append({
                "symbol": symbol,
                "market": market,
                "status_code": ingest_status,
                "accepted": accepted,
                "result": ingest_result,
            })
            if not (200 <= ingest_status < 300) or accepted <= 0:
                raise RuntimeError(f"ingest_failed:{ingest_status}:accepted={accepted}")
            analyses.append(analysis)
            _log(f"[hermes] {index}/{total} ok {market}:{symbol} ingest_status={ingest_status} accepted={accepted}", enabled=progress)
        except Exception as exc:
            errors.append({"symbol": symbol, "market": market, "error": str(exc)})
            _log(f"[hermes] {index}/{total} failed {market}:{symbol} error={exc}", enabled=progress)

    if not analyses:
        _log(f"[hermes] all Hermes calls or ingests failed errors={len(errors)}", enabled=progress)
        return 502, {
            "ok": False,
            "stage": "agent_failed",
            "markets": markets,
            "mode": mode,
            "selected_count": len(target_items),
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
        "errors": errors,
        "ingest_results": ingest_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Hermes research analysis for WealthPulse pending monitor targets")
    parser.add_argument("--market", action="append", default=[])
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--mode", choices=["missing_or_stale", "missing_only", "stale_only"], default="missing_or_stale")
    parser.add_argument("--dry-run", action="store_true", help="Collect targets and print prompts without calling Hermes")
    parser.add_argument("--agent-command", default=None, help="Command prefix used to call Hermes, default: env WEALTHPULSE_HERMES_RESEARCH_COMMAND or 'hermes --oneshot'")
    parser.add_argument("--api-base-url", default=None, help="WealthPulse API base URL for host-side execution, default: env WEALTHPULSE_API_BASE_URL or http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-progress", action="store_true", help="Do not print progress logs to stderr")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    status_code, payload = run(
        markets=list(args.market),
        limit=max(1, int(args.limit)),
        mode=args.mode,
        dry_run=bool(args.dry_run),
        agent_command=args.agent_command,
        timeout=max(1, int(args.timeout)),
        api_base_url=args.api_base_url,
        progress=not bool(args.no_progress),
    )
    print(json.dumps({"status_code": status_code, **payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
