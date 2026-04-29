from __future__ import annotations

import datetime
from typing import Any

from analyzer.shared_strategy import profile_from_mapping
from helpers import _KST
from analyzer.technical_snapshot import fetch_technical_snapshot as _compute_technical_snapshot
from services.live_layers import (
    build_layer_a_snapshot,
    build_layer_b_snapshot,
    build_layer_c_snapshot,
    build_layer_d_snapshot,
    build_layer_e_snapshot,
    build_layer_events,
)
from services.live_risk_engine import build_strategy_risk_state, evaluate_entry_risk
from services.paper_runtime_store import load_strategy_scan, save_strategy_scan
from services.regime_service import build_market_regime_snapshot
from services.sizing_service import recommend_position_size
from services.strategy_selector import resolve_strategy
from services.strategy_registry import list_strategies
from services.universe_builder import get_universe_snapshot
from services.trade_workflow import enrich_signal_payload
from market_utils import normalize_market


_SIGNAL_STATE_PRIORITY = {"exit": 3, "entry": 2, "watch": 1}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_scan_cycle_seconds(raw: Any) -> int:
    value = str(raw or "5m").strip().lower()
    if value.endswith("s"):
        try:
            return max(10, int(value[:-1]))
        except ValueError:
            return 300
    if value.endswith("m"):
        try:
            return max(10, int(value[:-1]) * 60)
        except ValueError:
            return 300
    if value.endswith("h"):
        try:
            return max(300, int(value[:-1]) * 3600)
        except ValueError:
            return 300
    return 300


def _seconds_since(timestamp: str) -> float | None:
    try:
        parsed = datetime.datetime.fromisoformat(str(timestamp))
    except Exception:
        return None
    delta = datetime.datetime.now(datetime.timezone.utc) - parsed.astimezone(datetime.timezone.utc)
    return delta.total_seconds()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _position_holding_days(position: dict[str, Any]) -> int:
    entry_ts = str(position.get("entry_ts") or position.get("updated_at") or "")
    try:
        entry_date = datetime.datetime.fromisoformat(entry_ts).astimezone(_KST).date()
    except Exception:
        return 0
    return max(0, (datetime.datetime.now(_KST).date() - entry_date).days)


def _normalize_score(raw: Any) -> float:
    return round(max(0.0, min(100.0, _to_float(raw, 0.0))), 2)


def _build_reasoning(snapshot: dict[str, Any], *, signal_state: str, exit_reason: str | None = None) -> list[str]:
    reasons: list[str] = []
    volume_ratio = _to_float(snapshot.get("volume_ratio"), 0.0)
    rsi14 = _to_float(snapshot.get("rsi14"), 0.0)
    if volume_ratio > 0:
        reasons.append(f"volume_ratio:{round(volume_ratio, 2)}")
    if rsi14 > 0:
        reasons.append(f"rsi14:{round(rsi14, 2)}")
    if _to_float(snapshot.get("macd_hist"), 0.0) > 0:
        reasons.append("macd_positive")
    if signal_state == "entry":
        reasons.append("entry_signal_detected")
    elif signal_state == "exit":
        reasons.append(str(exit_reason or "exit_signal_detected"))
    else:
        reasons.append("watch_candidate")
    return reasons


def _profile(strategy: dict[str, Any]):
    market = str(strategy.get("market") or "KOSPI")
    params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
    return profile_from_mapping(market, params)


def _top_n(strategy: dict[str, Any]) -> int:
    params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
    return max(1, min(20, int(params.get("candidate_top_n") or 8)))


def _scan_limit(strategy: dict[str, Any]) -> int:
    params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
    return max(5, min(80, int(params.get("scan_limit") or 30)))


def _symbol_sort_key(symbol: dict[str, Any]) -> tuple[float, float, str]:
    liquidity = max(
        _to_float(symbol.get("trading_value"), 0.0),
        _to_float(symbol.get("market_cap"), 0.0),
        _to_float(symbol.get("volume_avg20"), 0.0),
        _to_float(symbol.get("volume"), 0.0),
    )
    priority = _to_float(symbol.get("priority") or symbol.get("rank"), 999999.0)
    return (-liquidity, priority, str(symbol.get("code") or ""))


def scan_strategy(
    strategy: dict[str, Any],
    *,
    account: dict[str, Any] | None = None,
    refresh: bool = False,
    include_watch: bool = True,
) -> dict[str, Any]:
    strategy_id = str(strategy.get("strategy_id") or "").strip()
    if not strategy_id:
        raise ValueError("strategy_id is required")

    previous = load_strategy_scan(strategy_id)
    scan_cycle_seconds = _parse_scan_cycle_seconds(strategy.get("scan_cycle"))
    if not refresh and previous:
        elapsed = _seconds_since(str(previous.get("last_scan_at") or previous.get("scanned_at") or ""))
        if elapsed is not None and elapsed < scan_cycle_seconds:
            return previous

    market = str(strategy.get("market") or "KOSPI").upper()
    if not bool(strategy.get("enabled")):
        snapshot = {
            "strategy_id": strategy_id,
            "strategy_name": strategy.get("name"),
            "approval_status": strategy.get("approval_status"),
            "enabled": bool(strategy.get("enabled")),
            "market": market,
            "universe_rule": strategy.get("universe_rule"),
            "scan_cycle": strategy.get("scan_cycle"),
            "last_scan_at": str(previous.get("last_scan_at") or previous.get("scanned_at") or ""),
            "next_scan_at": "",
            "candidate_count": 0,
            "scanned_symbol_count": 0,
            "universe_symbol_count": int((previous.get("universe_symbol_count") if isinstance(previous, dict) else 0) or 0),
            "scan_duration_ms": 0,
            "top_candidates": [],
            "status": "inactive",
        }
        save_strategy_scan(strategy_id, snapshot)
        return snapshot

    started = datetime.datetime.now(datetime.timezone.utc)
    market = normalize_market(market)
    if not market:
        market = "KOSPI"

    universe = get_universe_snapshot(
        str(strategy.get("universe_rule") or "kospi"),
        market=market,
        refresh=refresh,
    )
    profile = _profile(strategy)
    account_payload = account or {"positions": [], "orders": [], "equity_krw": 0.0, "fx_rate": 1300.0, "cash_krw": 0.0, "cash_usd": 0.0}
    positions = account_payload.get("positions", []) if isinstance(account_payload.get("positions"), list) else []
    position_map = {
        f"{str(item.get('market') or '').upper()}:{str(item.get('code') or '').upper()}": item
        for item in positions
        if isinstance(item, dict)
    }
    candidates: list[dict[str, Any]] = []

    symbols_pool = sorted(
        [item for item in list(universe.get("symbols") or []) if isinstance(item, dict)],
        key=_symbol_sort_key,
    )
    scanned_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for symbol in symbols_pool[:_scan_limit(strategy)]:
        if not isinstance(symbol, dict):
            continue
        code = str(symbol.get("code") or "").upper()
        if not code:
            continue
        technical_snapshot = _compute_technical_snapshot(
            code,
            market,
            range_=str(profile.signal_range),
            interval=str(profile.signal_interval),
        )
        if not isinstance(technical_snapshot, dict):
            continue
        scanned_rows.append((symbol, technical_snapshot))

    market_regime_snapshot = build_market_regime_snapshot(
        [snapshot for _, snapshot in scanned_rows],
        market=market,
    )
    market_selection = resolve_strategy(profile, market_regime_snapshot, regime_snapshot=market_regime_snapshot)
    regime = str(market_selection.get("regime") or "neutral")
    risk_level = str(market_selection.get("risk_level") or "중간")
    base_risk_state = build_strategy_risk_state(
        account=account_payload,
        strategy=strategy,
        regime=regime,
        risk_level=risk_level,
    )

    for symbol, technical_snapshot in scanned_rows:
        code = str(symbol.get("code") or "").upper()
        position = position_map.get(f"{market}:{code}")
        selection = resolve_strategy(profile, technical_snapshot, regime_snapshot=market_regime_snapshot)
        strategy_impl = selection["strategy"]
        resolved_profile = selection["profile"]
        candidate_regime = str(selection.get("regime") or regime)
        candidate_risk_level = str(selection.get("risk_level") or risk_level)
        entry_signal = bool(strategy_impl.should_enter(
            technical_snapshot,
            resolved_profile,
            {"regime": candidate_regime},
        ))
        exit_reason = None
        if position is not None:
            exit_reason = strategy_impl.should_exit(
                technical_snapshot,
                {
                    "entry_price": _to_float(position.get("avg_price_local"), 0.0) or None,
                    "holding_days": _position_holding_days(position),
                },
                resolved_profile,
                {"regime": candidate_regime},
            )

        signal_state = "watch"
        if exit_reason:
            signal_state = "exit"
        elif entry_signal:
            signal_state = "entry"
        elif not include_watch:
            continue

        current_price = _to_float(technical_snapshot.get("current_price") or technical_snapshot.get("close"), 0.0)
        score = _normalize_score(strategy_impl.score(
            technical_snapshot,
            resolved_profile,
            {"regime": candidate_regime},
        ))
        reasons = _build_reasoning(technical_snapshot, signal_state=signal_state, exit_reason=exit_reason)
        confidence = round(max(40.0, min(92.0, 45.0 + (score / 2.0))), 2)
        candidate = {
            "signal_id": f"{strategy_id}:{market}:{code}",
            "strategy_id": strategy_id,
            "strategy_name": strategy.get("name"),
            "strategy_version": strategy.get("version"),
            "strategy_type": strategy_id,
            "market": market,
            "code": code,
            "name": symbol.get("name") or code,
            "sector": symbol.get("sector") or "미분류",
            "scan_cycle": strategy.get("scan_cycle"),
            "universe_rule": strategy.get("universe_rule"),
            "approval_status": strategy.get("approval_status"),
            "signal_state": signal_state,
            "resolved_strategy_kind": selection.get("strategy_kind"),
            "regime": candidate_regime,
            "risk_level": candidate_risk_level,
            "regime_confidence": selection.get("regime_confidence"),
            "entry_intent": signal_state == "entry",
            "exit_intent": signal_state == "exit",
            "current_price": current_price,
            "price": current_price,
            "score": score,
            "quant_score": round(score / 100.0, 4),
            "confidence": confidence,
            "reasons": reasons,
            "reason_codes": [],
            "technical_snapshot": technical_snapshot,
            "candidate_source": "live_scanner",
            "candidate_source_label": "scanner",
            "candidate_source_detail": str(strategy.get("universe_rule") or ""),
            "candidate_source_tier": "tier_1",
            "candidate_source_priority": 100,
            "candidate_runtime_source_mode": "live_scanner",
            "candidate_research_source": "research_snapshot_store",
            "report_reasoning": {
                "summary": ", ".join(reasons[:3]),
                "gate_status": signal_state,
                "gate_reasons": reasons,
            },
            "ev_metrics": {
                "expected_value": round((score - 48.0) / 12.0, 2),
                "win_probability": round(min(0.92, max(0.38, confidence / 100.0)), 4),
                "reliability": "high" if bool(strategy.get("enabled")) else "medium",
            },
            "validation_snapshot": {
                "validation_source": "strategy_registry",
                "validation_trades": 0,
                "trade_count": 0,
                "validation_sharpe": None,
                "strategy_reliability": "approved" if bool(strategy.get("enabled")) else "draft",
                "freshness": "derived",
                "freshness_detail": {
                    "status": "derived",
                    "is_stale": False,
                    "reason": "strategy_registry_snapshot",
                },
                "validation": {
                    "grade": "D",
                    "source": "strategy_registry",
                    "source_count": 1,
                    "reason": "validation_snapshot_missing",
                    "notes": ["validation_trades:0"],
                    "exclusion_reason": "validation evidence unavailable",
                },
            },
            "execution_realism": {
                "liquidity_gate_status": "pending",
                "slippage_bps": None,
            },
            "size_recommendation": {"quantity": 0, "reason": "signal_only"},
            "risk_inputs": {
                "stop_loss_pct": resolved_profile.stop_loss_pct or 5.0,
                **({"take_profit_pct": float(resolved_profile.take_profit_pct)} if getattr(resolved_profile, "take_profit_pct", None) is not None else {}),
            },
            "risk_check": {"passed": signal_state != "entry", "reason_code": "ok", "message": "scan_only", "checks": []},
            "entry_allowed": signal_state != "entry",
            "risk_guard_state": base_risk_state,
            "last_scanned_at": _now_iso(),
        }

        if signal_state == "entry":
            risk_pre = evaluate_entry_risk(
                account=account_payload,
                strategy=strategy,
                candidate=candidate,
                regime=candidate_regime,
                risk_level=candidate_risk_level,
            )
            candidate["risk_check"] = risk_pre
            candidate["execution_realism"]["liquidity_gate_status"] = "passed" if risk_pre.get("passed") else str(risk_pre.get("reason_code") or "blocked")
            if risk_pre.get("passed"):
                stop_loss_pct = _to_float(resolved_profile.stop_loss_pct, 5.0) or 5.0
                size_reco = recommend_position_size(
                    account=account_payload,
                    market=market,
                    unit_price_local=current_price,
                    stop_loss_pct=stop_loss_pct,
                    expected_value=_to_float(candidate["ev_metrics"].get("expected_value"), 0.0),
                    reliability=str(candidate["ev_metrics"].get("reliability") or "medium"),
                    risk_guard_state=base_risk_state,
                    cfg={"risk_per_trade_pct": 0.35},
                    symbol_key=f"{market}:{code}",
                    sector=str(candidate.get("sector") or "미분류"),
                )
                candidate["size_recommendation"] = size_reco
                risk_final = evaluate_entry_risk(
                    account=account_payload,
                    strategy=strategy,
                    candidate=candidate,
                    desired_quantity=int(size_reco.get("quantity") or 0),
                    regime=candidate_regime,
                    risk_level=candidate_risk_level,
                )
                candidate["risk_check"] = risk_final
                candidate["entry_allowed"] = bool(risk_final.get("passed"))
                if not candidate["entry_allowed"]:
                    candidate["reason_codes"] = [str(risk_final.get("reason_code") or "risk_guard_blocked")]
                    candidate["execution_realism"]["liquidity_gate_status"] = str(risk_final.get("reason_code") or "blocked")
            else:
                candidate["entry_allowed"] = False
                candidate["reason_codes"] = [str(risk_pre.get("reason_code") or "risk_guard_blocked")]
        else:
            candidate["entry_allowed"] = False

        layer_a = build_layer_a_snapshot(strategy=strategy, universe=universe, symbol=symbol, scan_time=candidate["last_scanned_at"])
        layer_b = build_layer_b_snapshot(strategy=strategy, score=score, signal_state=signal_state, reasons=reasons, technical_snapshot=technical_snapshot)
        layer_c = build_layer_c_snapshot(
            symbol=code,
            market=market,
            timestamp=candidate["last_scanned_at"],
            strategy=strategy,
            score=score,
            reasons=reasons,
            technical_snapshot=technical_snapshot,
        )
        if layer_c.get("warnings"):
            candidate["reason_codes"] = list(dict.fromkeys([
                *candidate["reason_codes"],
                *[f"research_warning:{item}" for item in (layer_c.get("warnings") or []) if str(item)],
            ]))
        layer_d = build_layer_d_snapshot(
            risk_check=candidate["risk_check"],
            size_recommendation=candidate["size_recommendation"],
            risk_guard_state=base_risk_state,
            research=layer_c,
        )
        layer_e = build_layer_e_snapshot(
            signal_state=signal_state,
            quant_score=score,
            research=layer_c,
            risk=layer_d,
            timestamp=candidate["last_scanned_at"],
            source_context={"strategy_id": strategy_id, "symbol": code, "market": market},
        )
        candidate["research_score"] = layer_c.get("research_score")
        candidate["research_status"] = layer_c.get("provider_status")
        candidate["research_unavailable"] = layer_c.get("research_unavailable")
        candidate["final_action"] = layer_e.get("final_action")
        candidate["final_action_snapshot"] = layer_e
        candidate["layer_a"] = layer_a
        candidate["layer_b"] = layer_b
        candidate["layer_c"] = layer_c
        candidate["layer_d"] = layer_d
        candidate["layer_e"] = layer_e
        candidate["layer_events"] = build_layer_events(layer_a=layer_a, layer_b=layer_b, layer_c=layer_c, layer_d=layer_d, layer_e=layer_e)
        candidate["entry_allowed"] = layer_e.get("final_action") == "review_for_entry"

        candidates.append(enrich_signal_payload(candidate))

    candidates.sort(
        key=lambda item: (
            _SIGNAL_STATE_PRIORITY.get(str(item.get("signal_state") or "watch"), 0),
            _to_float(item.get("score"), 0.0),
            str(item.get("code") or ""),
        ),
        reverse=True,
    )
    top_candidates = candidates[:_top_n(strategy)]
    for index, item in enumerate(top_candidates, start=1):
        item["candidate_rank"] = index

    finished = datetime.datetime.now(datetime.timezone.utc)
    snapshot = {
        "strategy_id": strategy_id,
        "strategy_name": strategy.get("name"),
        "approval_status": strategy.get("approval_status"),
        "enabled": bool(strategy.get("enabled")),
        "market": market,
        "universe_rule": strategy.get("universe_rule"),
        "scan_cycle": strategy.get("scan_cycle"),
        "last_scan_at": _now_iso(),
        "next_scan_at": (finished + datetime.timedelta(seconds=scan_cycle_seconds)).astimezone().isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "scanned_symbol_count": len(scanned_rows),
        "universe_symbol_count": int(universe.get("symbol_count") or 0),
        "market_regime": {
            "regime": regime,
            "risk_level": risk_level,
            "confidence": market_selection.get("regime_confidence"),
            "sample_count": market_regime_snapshot.get("sample_count"),
        },
        "scan_duration_ms": round((finished - started).total_seconds() * 1000.0, 2),
        "top_candidates": top_candidates,
        "status": "running",
    }
    save_strategy_scan(strategy_id, snapshot)
    return snapshot


def scan_live_strategies(
    *,
    markets: list[str] | None = None,
    account: dict[str, Any] | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    normalized_markets = {str(item or "").upper() for item in (markets or []) if str(item or "").strip()}
    rows = []
    for strategy in list_strategies():
        if normalized_markets and str(strategy.get("market") or "").upper() not in normalized_markets:
            continue
        rows.append(scan_strategy(strategy, account=account, refresh=refresh))
    rows.sort(key=lambda item: (not bool(item.get("enabled")), str(item.get("strategy_id") or "")))
    return rows


def build_live_signal_book(
    *,
    markets: list[str] | None = None,
    account: dict[str, Any] | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    scans = scan_live_strategies(markets=markets, account=account, refresh=refresh)
    signals: list[dict[str, Any]] = []
    blocked_count = 0
    risk_guard_state: dict[str, Any] = {}
    for scan in scans:
        top_candidates = scan.get("top_candidates", []) if isinstance(scan.get("top_candidates"), list) else []
        signals.extend(item for item in top_candidates if isinstance(item, dict))
        for item in top_candidates:
            if isinstance(item, dict) and item.get("signal_state") == "entry" and not bool(item.get("entry_allowed")):
                blocked_count += 1
        if not risk_guard_state and top_candidates:
            first = top_candidates[0]
            if isinstance(first, dict):
                risk_guard_state = first.get("risk_guard_state") if isinstance(first.get("risk_guard_state"), dict) else {}

    signals.sort(
        key=lambda item: (
            _SIGNAL_STATE_PRIORITY.get(str(item.get("signal_state") or "watch"), 0),
            _to_float(item.get("score"), 0.0),
            str(item.get("strategy_id") or ""),
            str(item.get("code") or ""),
        ),
        reverse=True,
    )
    entry_allowed_count = sum(1 for item in signals if bool(item.get("entry_allowed")))
    return {
        "generated_at": _now_iso(),
        "signals": signals,
        "count": len(signals),
        "blocked_count": blocked_count,
        "entry_allowed_count": entry_allowed_count,
        "risk_guard_state": risk_guard_state,
        "scanner": scans,
    }
