"""Runtime strategy-engine compatibility layer for live signal book construction."""

from __future__ import annotations

from typing import Any

try:
    from domains.report.market_context_service import get_market_context
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from apps.api.domains.report.market_context_service import get_market_context
from helpers import _now_iso
from services.risk_guard_service import build_risk_guard_state as _build_account_risk_guard_state
from services.live_layers import build_layer_c_snapshot, build_layer_d_snapshot, build_layer_e_snapshot, build_layer_events
from services.market_data_service import resolve_stock_quote
from services.optimized_params_store import load_execution_optimized_params
from services.reliability_policy import should_apply_symbol_overlay
from services.candidate_monitor_service import list_market_watchlists
from services.research_store import DEFAULT_RESEARCH_PROVIDER, load_latest_research_snapshot
from services.signal_service import collect_pick_candidates
from services.sizing_service import recommend_position_size
from services.trade_workflow import enrich_signal_payload


DEFAULT_SIGNAL_MARKETS = ("KOSPI", "NASDAQ")


def _context_snapshot() -> tuple[str, str]:
    try:
        payload = get_market_context()
    except Exception:
        payload = {}
    context = payload.get("context") if isinstance(payload, dict) else {}
    context = context if isinstance(context, dict) else {}
    regime = str(context.get("regime") or "neutral").lower()
    risk_level = str(context.get("risk_level") or "중간")
    return regime, risk_level


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _snapshot_is_fresh(symbol: str, market: str) -> tuple[bool, dict[str, Any]]:
    snapshot = load_latest_research_snapshot(symbol, market, provider=DEFAULT_RESEARCH_PROVIDER)
    if not isinstance(snapshot, dict):
        return False, {}
    freshness = str(
        snapshot.get("freshness")
        or (snapshot.get("freshness_detail") if isinstance(snapshot.get("freshness_detail"), dict) else {}).get("status")
        or "missing"
    ).strip().lower()
    return freshness in {"fresh", "healthy", "derived"}, snapshot


def _with_live_technical_snapshot(candidate: dict[str, Any], market: str) -> dict[str, Any]:
    row = dict(candidate)
    code = str(row.get("code") or row.get("symbol") or "").strip().upper()
    if not code:
        return row

    technical = dict(row.get("technical_snapshot")) if isinstance(row.get("technical_snapshot"), dict) else {}
    try:
        quote = resolve_stock_quote(code, market)
    except Exception as exc:
        technical["quote_error"] = str(exc)
        row["technical_snapshot"] = technical
        return row
    current_price = quote.get("price")
    if current_price not in (None, ""):
        row["current_price"] = current_price
        row["price"] = current_price
        row["last_price_local"] = current_price
        technical["current_price"] = current_price
        technical["close"] = current_price
    if quote.get("change_pct") not in (None, ""):
        technical["change_pct"] = quote.get("change_pct")
    technical["quote_source"] = str(quote.get("source") or "KIS")
    technical["quote_fetched_at"] = str(quote.get("fetched_at") or _now_iso())
    technical["freshness"] = "fresh"
    technical["quote_is_stale"] = bool(quote.get("is_stale", False))

    row["technical_snapshot"] = technical
    return row


def _monitor_active_slot_candidates(market: str, *, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_market = str(market or "").strip().upper() or "KOSPI"
    min_score = _to_float(cfg.get("min_score"), 50.0)
    watchlists = list_market_watchlists([normalized_market], refresh=False)
    watchlist = watchlists[0] if watchlists else {}
    active_slots = watchlist.get("active_slots") if isinstance(watchlist, dict) and isinstance(watchlist.get("active_slots"), list) else []
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(active_slots, start=1):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("symbol") or "").strip().upper()
        if not code:
            continue
        fresh, snapshot = _snapshot_is_fresh(code, normalized_market)
        score = max(
            _to_float(item.get("score"), 0.0),
            _to_float(item.get("snapshot_research_score"), 0.0) * 100.0,
            _to_float(snapshot.get("research_score"), 0.0) * 100.0,
        )
        slot_type = str(item.get("slot_type") or "active").strip().lower()
        row = {
            **item,
            "code": code,
            "symbol": code,
            "market": normalized_market,
            "name": item.get("name") or code,
            "sector": item.get("sector") or "미분류",
            "score": round(score, 2),
            "candidate_rank": item.get("candidate_rank") or index,
            "candidate_source": str(item.get("candidate_source") or slot_type or "monitor_active_slot"),
            "candidate_source_label": "active-slot",
            "candidate_source_detail": str(item.get("reason") or item.get("selection_reason") or slot_type or "monitor_active_slot"),
            "candidate_source_tier": "tier_1" if fresh else "tier_3",
            "candidate_source_priority": 85 if fresh else 35,
            "candidate_runtime_source_mode": "monitor_active_slots",
            "candidate_source_mode": "monitor_active_slots",
            "candidate_research_source": DEFAULT_RESEARCH_PROVIDER,
            "signal_state": "entry" if fresh and score >= min_score else "watch",
            "final_action": "review_for_entry" if fresh and score >= min_score else "watch_only",
            "gate_status": "passed" if fresh else "research_missing_or_stale",
            "gate_reasons": [] if fresh else ["research_missing_or_stale"],
            "reasons": [
                "monitor_active_slot",
                f"slot_type:{slot_type}",
                f"research:{'fresh' if fresh else 'missing_or_stale'}",
            ],
        }
        candidates.append(_with_live_technical_snapshot(row, normalized_market))
    candidates.sort(
        key=lambda row: (
            int(row.get("candidate_source_priority") or 0),
            _to_float(row.get("score"), 0.0),
            -int(row.get("candidate_rank") or 999999),
        ),
        reverse=True,
    )
    return candidates[: max(1, int(cfg.get("candidate_pool_limit") or 40))]


def _load_optimized_params() -> dict[str, Any] | None:
    payload = load_execution_optimized_params()
    return payload if isinstance(payload, dict) else None


def determine_strategy_type(candidate: dict[str, Any]) -> str:
    return str(candidate.get("strategy_type") or candidate.get("source") or "quant").strip() or "quant"


def allocator_weight(*, candidate: dict[str, Any], cfg: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    return {"enabled": True, "weight": 1.0}


def build_risk_guard_state(*, candidate: dict[str, Any], cfg: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    config = cfg or {}
    config = config if isinstance(config, dict) else {}
    account_payload = account or {}
    account_payload = account_payload if isinstance(account_payload, dict) else {}
    regime, risk_level = _context_snapshot()
    try:
        normalized_cfg = {
            "daily_loss_limit_pct": _normalize_threshold(config.get("daily_loss_limit_pct"), 2.0),
            "max_symbol_weight_pct": _normalize_threshold(config.get("max_symbol_weight_pct", 20.0), 20.0),
            "max_sector_weight_pct": _normalize_threshold(config.get("max_sector_weight_pct", 35.0), 35.0),
            "max_market_exposure_pct": _normalize_threshold(config.get("max_market_exposure_pct", 70.0), 70.0),
            "block_buy_in_risk_off": bool(config.get("block_buy_in_risk_off", True)),
            "block_buy_when_risk_high": bool(config.get("block_buy_when_risk_high", True)),
            "max_consecutive_loss": max(1, int(config.get("max_consecutive_loss") or 3)),
            "cooldown_minutes": max(5, int(config.get("cooldown_minutes") or 120)),
        }
        return _build_account_risk_guard_state(
            account=account_payload,
            cfg=normalized_cfg,
            regime=regime,
            risk_level=risk_level,
        )
    except Exception:
        return {"entry_allowed": True, "reasons": []}


def _normalize_threshold(value: Any, default: float) -> float:
    normalized = _to_float(value, default)
    if 0 < normalized <= 1:
        normalized = normalized * 100.0
    return max(0.0, normalized)


def compute_ev_metrics(*, candidate: dict[str, Any], validation_snapshot: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    reliability = str(validation_snapshot.get("strategy_reliability") or "insufficient")
    return {
        "expected_value": round(_to_float(candidate.get("score"), 0.0) / 100.0, 4),
        "reliability": reliability,
        "reliability_detail": {
            "label": reliability,
            "reason": str(validation_snapshot.get("reliability_reason") or "validation_snapshot"),
            "passes_minimum_gate": bool(validation_snapshot.get("passes_minimum_gate")),
            "is_reliable": bool(validation_snapshot.get("is_reliable")),
        },
        "calibration": {},
    }


def _validation_snapshot_for_candidate(candidate: dict[str, Any], optimized_payload: dict[str, Any] | None) -> dict[str, Any]:
    base_snapshot = candidate.get("validation_snapshot") if isinstance(candidate.get("validation_snapshot"), dict) else {}
    code = str(candidate.get("code") or "").upper()
    optimized_payload = optimized_payload if isinstance(optimized_payload, dict) else {}
    per_symbol = optimized_payload.get("per_symbol") if isinstance(optimized_payload.get("per_symbol"), dict) else {}
    global_baseline = optimized_payload.get("validation_baseline") if isinstance(optimized_payload.get("validation_baseline"), dict) else {}
    symbol_payload = per_symbol.get(code) if isinstance(per_symbol.get(code), dict) else {}

    use_symbol = bool(symbol_payload) and should_apply_symbol_overlay(
        is_reliable=bool(symbol_payload.get("is_reliable", False)),
        reliability_reason=str(symbol_payload.get("reliability_reason") or ""),
    )
    overlay = symbol_payload if use_symbol else global_baseline
    source = "symbol" if use_symbol else "global" if overlay else str(base_snapshot.get("validation_source") or "signal")

    trade_count = overlay.get("trade_count") if overlay else base_snapshot.get("trade_count")
    validation_trades = overlay.get("validation_trades") if overlay else base_snapshot.get("validation_trades")
    if trade_count in (None, ""):
        trade_count = validation_trades or 0
    if validation_trades in (None, ""):
        validation_trades = trade_count or 0

    result = {
        **base_snapshot,
        "validation_source": source,
        "trade_count": int(trade_count or 0),
        "validation_trades": int(validation_trades or 0),
        "validation_sharpe": _to_float((overlay or {}).get("validation_sharpe"), _to_float(base_snapshot.get("validation_sharpe"), 0.0)),
        "max_drawdown_pct": (overlay or {}).get("max_drawdown_pct", base_snapshot.get("max_drawdown_pct")),
        "strategy_reliability": str((overlay or {}).get("strategy_reliability") or base_snapshot.get("strategy_reliability") or "insufficient"),
        "reliability_reason": str((overlay or {}).get("reliability_reason") or base_snapshot.get("reliability_reason") or "validation_snapshot"),
        "passes_minimum_gate": bool((overlay or {}).get("passes_minimum_gate", base_snapshot.get("passes_minimum_gate", False))),
        "is_reliable": bool((overlay or {}).get("is_reliable", base_snapshot.get("is_reliable", False))),
        "composite_score": (overlay or {}).get("composite_score", base_snapshot.get("composite_score")),
    }
    freshness = "derived"
    grade = "D" if int(result.get("validation_trades") or 0) <= 0 and int(result.get("trade_count") or 0) <= 0 else "A" if str(result.get("strategy_reliability") or "") == "high" else "B" if str(result.get("strategy_reliability") or "") == "medium" else "C"
    exclusion_reason = "validation evidence unavailable" if grade == "D" else None
    result["freshness"] = freshness
    result["freshness_detail"] = {
        "status": freshness,
        "is_stale": False,
        "reason": "runtime_validation_overlay",
    }
    result["validation"] = {
        "grade": grade,
        "source": source,
        "source_count": 1,
        "reason": str(result.get("reliability_reason") or "validation_snapshot"),
        "notes": [f"reliability:{str(result.get('strategy_reliability') or 'insufficient')}", f"validation_trades:{int(result.get('validation_trades') or 0)}"],
        "exclusion_reason": exclusion_reason,
    }
    return result


def _risk_inputs_for_candidate(candidate: dict[str, Any], optimized_payload: dict[str, Any] | None, cfg: dict[str, Any]) -> dict[str, Any]:
    code = str(candidate.get("code") or "").upper()
    optimized_payload = optimized_payload if isinstance(optimized_payload, dict) else {}
    per_symbol = optimized_payload.get("per_symbol") if isinstance(optimized_payload.get("per_symbol"), dict) else {}
    global_baseline = optimized_payload.get("validation_baseline") if isinstance(optimized_payload.get("validation_baseline"), dict) else {}
    symbol_payload = per_symbol.get(code) if isinstance(per_symbol.get(code), dict) else {}

    use_symbol = bool(symbol_payload) and should_apply_symbol_overlay(
        is_reliable=bool(symbol_payload.get("is_reliable", False)),
        reliability_reason=str(symbol_payload.get("reliability_reason") or ""),
    )
    overlay = symbol_payload if use_symbol else global_baseline

    stop_loss_pct = overlay.get("stop_loss_pct") if isinstance(overlay, dict) else None
    if stop_loss_pct in (None, ""):
        stop_loss_pct = candidate.get("stop_loss_pct")
    if stop_loss_pct in (None, ""):
        stop_loss_pct = cfg.get("stop_loss_pct", 5.0)

    take_profit_pct = overlay.get("take_profit_pct") if isinstance(overlay, dict) else None
    if take_profit_pct in (None, ""):
        take_profit_pct = candidate.get("take_profit_pct")
    if take_profit_pct in (None, ""):
        take_profit_pct = cfg.get("take_profit_pct")

    result = {"stop_loss_pct": _to_float(stop_loss_pct, 5.0)}
    tp = _to_float(take_profit_pct)
    if tp is not None:
        result["take_profit_pct"] = tp
    return result


def _build_signal_from_candidate(
    *,
    candidate: dict[str, Any],
    market: str,
    cfg: dict[str, Any],
    account: dict[str, Any],
    optimized_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    validation_snapshot = _validation_snapshot_for_candidate(candidate, optimized_payload)
    risk_inputs = _risk_inputs_for_candidate(candidate, optimized_payload, cfg)
    risk_guard_state = build_risk_guard_state(candidate=candidate, cfg=cfg, account=account)
    ev_metrics = compute_ev_metrics(candidate=candidate, validation_snapshot=validation_snapshot, cfg=cfg)
    normalized_market = str(candidate.get("market") or market).upper()
    technical_snapshot = candidate.get("technical_snapshot") if isinstance(candidate.get("technical_snapshot"), dict) else {}
    reasons = [str(item) for item in (candidate.get("reasons") or []) if str(item)]
    signal_state = str(candidate.get("signal_state") or "entry")
    timestamp = _now_iso()
    decision_quant_score = max(
        _to_float(candidate.get("score"), 0.0),
        max(0.0, min(100.0, _to_float(ev_metrics.get("expected_value"), 0.0) * 100.0)),
    )

    size_recommendation = recommend_position_size(
        account=account,
        market=normalized_market,
        unit_price_local=_to_float(
            candidate.get("price"),
            _to_float(technical_snapshot.get("current_price"), 0.0),
        ),
        stop_loss_pct=_to_float(risk_inputs.get("stop_loss_pct"), 5.0),
        expected_value=_to_float(ev_metrics.get("expected_value"), 0.0),
        reliability=str(ev_metrics.get("reliability") or validation_snapshot.get("strategy_reliability") or "insufficient"),
        risk_guard_state=risk_guard_state,
        cfg=cfg,
        symbol_key=f"{normalized_market}:{str(candidate.get('code') or '').upper()}",
        sector=str(candidate.get("sector") or "미분류"),
    )
    gate_passed = str(candidate.get("gate_status") or "passed") == "passed"
    entry_allowed = bool(risk_guard_state.get("entry_allowed", True)) and gate_passed
    risk_check = {
        "passed": gate_passed,
        "reason_code": "ok" if gate_passed else str(candidate.get("gate_status") or "blocked"),
        "message": ", ".join([str(item) for item in (candidate.get("gate_reasons") or []) if str(item)]) or "candidate_policy",
        "checks": [],
    }

    layer_c = build_layer_c_snapshot(
        symbol=str(candidate.get("code") or "").upper(),
        market=normalized_market,
        timestamp=timestamp,
        strategy={
            "strategy_id": determine_strategy_type(candidate),
            "market": normalized_market,
            "universe_rule": candidate.get("candidate_source_detail") or candidate.get("source") or "runtime_candidate_pool",
        },
        score=decision_quant_score,
        reasons=reasons,
        technical_snapshot=technical_snapshot,
    )
    layer_d = build_layer_d_snapshot(
        risk_check=risk_check,
        size_recommendation=size_recommendation,
        risk_guard_state=risk_guard_state,
        research=layer_c,
    )
    layer_e = build_layer_e_snapshot(
        signal_state=signal_state,
        quant_score=decision_quant_score,
        research=layer_c,
        risk=layer_d,
        timestamp=timestamp,
        source_context={"strategy_id": determine_strategy_type(candidate), "symbol": str(candidate.get("code") or "").upper(), "market": normalized_market},
    )
    layer_events = build_layer_events(
        layer_a={"layer": "A", "market": normalized_market, "source": "strategy_engine_candidate_pool"},
        layer_b={
            "layer": "B",
            "quant_score": round(decision_quant_score / 100.0, 4),
            "signal_state": signal_state,
            "quant_tags": reasons,
            "technical_snapshot": {
                "current_price": technical_snapshot.get("current_price") or technical_snapshot.get("close"),
                "volume_ratio": technical_snapshot.get("volume_ratio"),
                "rsi14": technical_snapshot.get("rsi14"),
                "atr14_pct": technical_snapshot.get("atr14_pct"),
            },
        },
        layer_c=layer_c,
        layer_d=layer_d,
        layer_e=layer_e,
    )

    return enrich_signal_payload({
        **candidate,
        "market": normalized_market,
        "signal_state": signal_state,
        "entry_intent": True,
        "exit_intent": False,
        "entry_allowed": entry_allowed and layer_e.get("final_action") == "review_for_entry",
        "validation_snapshot": validation_snapshot,
        "risk_inputs": risk_inputs,
        "risk_guard_state": risk_guard_state,
        "strategy_type": determine_strategy_type(candidate),
        "strategy_role": "auxiliary",
        "candidate_primary_source": "common_candidate_pool",
        "allocation": allocator_weight(candidate=candidate, cfg=cfg, account=account),
        "ev_metrics": ev_metrics,
        "size_recommendation": size_recommendation,
        "execution_realism": {
            "liquidity_gate_status": "ok" if entry_allowed else "blocked",
            **(candidate.get("execution_realism") if isinstance(candidate.get("execution_realism"), dict) else {}),
        },
        "candidate_source_mode": str(candidate.get("candidate_source_mode") or candidate.get("candidate_source") or candidate.get("candidate_runtime_source_mode") or "runtime_candidates"),
        "candidate_runtime_source_mode": str(candidate.get("candidate_runtime_source_mode") or candidate.get("candidate_source") or "runtime_candidates"),
        "candidate_research_source": layer_c.get("provider"),
        "research_status": layer_c.get("provider_status"),
        "research_unavailable": layer_c.get("research_unavailable"),
        "research_score": layer_c.get("research_score"),
        "final_action": layer_e.get("final_action"),
        "final_action_snapshot": layer_e,
        "layer_c": layer_c,
        "layer_d": layer_d,
        "layer_e": layer_e,
        "layer_events": layer_events,
        "fetched_at": timestamp,
    })


def build_signal_book(
    *,
    markets: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or {}
    account = account or {}
    normalized_markets = [str(item or "").strip().upper() for item in (markets or []) if str(item or "").strip()]
    if not normalized_markets:
        normalized_markets = list(DEFAULT_SIGNAL_MARKETS)
    optimized_payload = _load_optimized_params()
    regime, risk_level = _context_snapshot()
    signals: list[dict[str, Any]] = []
    risk_guard_state: dict[str, Any] = {}

    for market in normalized_markets:
        candidates = collect_pick_candidates(market=market, cfg=cfg)
        monitor_candidates = _monitor_active_slot_candidates(market, cfg=cfg)
        if monitor_candidates:
            by_symbol = {
                str(item.get("code") or item.get("symbol") or "").strip().upper(): item
                for item in candidates
                if isinstance(item, dict) and str(item.get("code") or item.get("symbol") or "").strip()
            }
            for item in monitor_candidates:
                symbol = str(item.get("code") or item.get("symbol") or "").strip().upper()
                if symbol and symbol not in by_symbol:
                    by_symbol[symbol] = item
            candidates = list(by_symbol.values())
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            signal = _build_signal_from_candidate(
                candidate=candidate,
                market=market,
                cfg=cfg,
                account=account,
                optimized_payload=optimized_payload,
            )
            signals.append(signal)
            if not risk_guard_state and isinstance(signal.get("risk_guard_state"), dict):
                risk_guard_state = dict(signal.get("risk_guard_state") or {})

    payload = {
        "generated_at": _now_iso(),
        "signals": signals,
        "count": len(signals),
        "blocked_count": sum(1 for item in signals if str(item.get("signal_state") or "") == "entry" and not bool(item.get("entry_allowed"))),
        "entry_allowed_count": sum(1 for item in signals if bool(item.get("entry_allowed"))),
        "risk_guard_state": risk_guard_state,
        "scanner": [],
        "regime": regime,
        "risk_level": risk_level,
        "candidate_generation_mode": "common_candidate_pool",
        "strategy_role": "auxiliary",
        "markets": normalized_markets,
    }
    if isinstance(payload.get("risk_guard_state"), dict):
        payload["risk_guard_state"].setdefault("regime", regime)
        payload["risk_guard_state"].setdefault("risk_level", risk_level)
    return payload


def select_entry_candidates(
    *,
    market: str,
    cfg: dict[str, Any],
    account: dict[str, Any],
    max_count: int,
) -> list[dict[str, Any]]:
    book = build_signal_book(markets=[market], cfg=cfg, account=account)
    allowed = [
        item for item in book.get("signals", [])
        if isinstance(item, dict)
        and str(item.get("market") or "").upper() == str(market or "").upper()
        and str(item.get("signal_state") or "") == "entry"
        and bool(item.get("entry_allowed"))
    ]
    return allowed[: max(0, int(max_count))]
