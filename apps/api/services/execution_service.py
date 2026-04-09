import datetime
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover - fallback for lightweight test envs
    logger = logging.getLogger(__name__)
from helpers import (
    _KST,
    _SUPPORTED_AUTO_TRADE_MARKETS,
    _now_iso,
)
from analyzer.technical_snapshot import fetch_technical_snapshot as _compute_technical_snapshot
from services.market_data_service import get_paper_fx_rate as _paper_fx_rate, resolve_stock_quote as _resolve_stock_quote
from analyzer.shared_strategy import (
    build_strategy_profile,
    default_strategy_profile,
    default_strategy_profiles,
    normalize_strategy_market,
    profile_from_mapping,
    serialize_strategy_profiles,
    should_enter_from_snapshot,
    should_exit_from_snapshot,
)
from broker.execution_engine import EngineConfig, PaperExecutionEngine
from config.market_calendar import is_market_open
from config.settings import LOGS_DIR
from market_utils import normalize_market, resolve_market
from services.notification_service import get_notification_service
from services.optimized_params_store import (
    RUNTIME_OPTIMIZED_PARAMS_PATH as STORE_RUNTIME_OPTIMIZED_PARAMS_PATH,
    SEARCH_OPTIMIZED_PARAMS_PATH as STORE_SEARCH_OPTIMIZED_PARAMS_PATH,
    load_execution_optimized_params,
)
from services.paper_runtime_store import (
    append_account_snapshot,
    append_engine_cycle,
    append_execution_events,
    append_order_event,
    append_signal_snapshots,
    clear_account_snapshots,
    clear_engine_cycles,
    clear_execution_events,
    clear_order_events,
    clear_signal_snapshots,
    load_engine_state,
    read_account_snapshots,
    read_engine_cycles,
    read_execution_events,
    read_order_events,
    read_signal_snapshots,
    save_engine_state,
)
from services.execution_lifecycle import build_execution_events, normalize_execution_reason, summarize_execution_events
from services.order_decision_service import summarize_order_decision
from services.trade_workflow import (
    build_workflow_summary,
    enrich_order_payload,
    enrich_signal_payload,
)
from services.reliability_service import assess_validation_reliability
from services.reliability_policy import overlay_policy_metadata, should_apply_symbol_overlay
from services.signal_service import (
    collect_pick_candidates as _signal_collect_pick_candidates,
    normalize_theme_focus as _signal_normalize_theme_focus,
    parse_theme_gate_config as _signal_parse_theme_gate_config,
)
from services.strategy_engine import build_signal_book, select_entry_candidates

from broker.kis_client import KISClient
from broker.execution_engine import (
    EngineConfig,
    LiveBrokerExecutionEngine,
    PaperExecutionEngine,
)
from config.settings import LOGS_DIR


_DEFAULT_THEME_FOCUS = ["automotive", "robotics", "physical_ai"]
_ALLOWED_THEME_FOCUS = set(_DEFAULT_THEME_FOCUS)

_OPTIMIZED_PARAMS_PATH = STORE_SEARCH_OPTIMIZED_PARAMS_PATH
_RUNTIME_OPTIMIZED_PARAMS_PATH = STORE_RUNTIME_OPTIMIZED_PARAMS_PATH
_OPTIMIZED_PARAMS_MAX_AGE_DAYS = 30
_OPTIMIZABLE_KEYS = {
    "stop_loss_pct",
    "take_profit_pct",
    "max_holding_days",
    "rsi_min",
    "rsi_max",
    "volume_ratio_min",
    "adx_min",
    "mfi_min",
    "mfi_max",
    "bb_pct_min",
    "bb_pct_max",
    "stoch_k_min",
    "stoch_k_max",
}

_paper_engine: PaperExecutionEngine | None = None
_auto_trader_lock = threading.Lock()
_auto_trader_stop_event: threading.Event | None = None
_auto_trader_thread: threading.Thread | None = None
_auto_trader_state_loaded = False
_last_daily_loss_notified_day = ""
_auto_trader_state: dict[str, Any] = {
    "engine_state": "stopped",
    "running": False,
    "started_at": "",
    "paused_at": "",
    "stopped_at": "",
    "last_run_at": "",
    "next_run_at": "",
    "last_success_at": "",
    "last_error": "",
    "last_error_at": "",
    "last_summary": {},
    "current_config": {},
    "config": {},
    "latest_cycle_id": "",
    "validation_policy": {},
    "optimized_params": {},
}
_live_engine: LiveBrokerExecutionEngine | None = None


def _mask_chat_id(chat_id: str) -> str:
    value = str(chat_id or "").strip()
    if len(value) <= 4:
        return value
    return f"{value[:2]}***{value[-2:]}"


def _today_order_counts(account: dict) -> dict[str, int]:
    today = _today_kst_str()
    orders = account.get("orders", [])
    counts = {
        "buy": 0,
        "sell": 0,
        "failed": 0,
    }
    for order in orders:
        if _order_day(str(order.get("ts") or "")) != today:
            continue
        side = str(order.get("side") or "").lower()
        if side in {"buy", "sell"}:
            counts[side] += 1
    recent_failures = read_order_events(limit=300)
    for item in recent_failures:
        if str(item.get("timestamp") or "").startswith(today) and not bool(item.get("success")):
            counts["failed"] += 1
    return counts


def _order_failure_summary() -> dict[str, Any]:
    today = _today_kst_str()
    failures = [
        item for item in read_order_events(limit=300)
        if str(item.get("timestamp") or "").startswith(today) and not bool(item.get("success"))
    ]
    if not failures:
        return {
            "today_failed": 0,
            "insufficient_cash_failed": 0,
            "repeated_insufficient_cash": [],
            "top_reason": "",
            "top_reason_count": 0,
            "latest_failure_reason": "",
            "latest_failure_at": "",
            "cooldown_recommended": False,
        }

    reason_counts: dict[str, int] = {}
    insufficient_symbol_counts: dict[str, dict[str, Any]] = {}
    insufficient_cash_failed = 0

    for item in failures:
        reason = str(item.get("failure_reason")
                     or "order_failed").strip() or "order_failed"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if "현금이 부족" not in reason:
            continue
        insufficient_cash_failed += 1
        market = str(item.get("market") or "").upper()
        code = str(item.get("code") or "").upper()
        key = f"{market}:{code}"
        bucket = insufficient_symbol_counts.get(key) or {
            "market": market,
            "code": code,
            "count": 0,
            "last_at": "",
            "reason": reason,
        }
        bucket["count"] = int(bucket.get("count") or 0) + 1
        bucket["last_at"] = str(item.get("timestamp")
                                or bucket.get("last_at") or "")
        bucket["reason"] = reason
        insufficient_symbol_counts[key] = bucket

    latest_failure = failures[0]
    top_reason, top_reason_count = max(
        reason_counts.items(), key=lambda entry: entry[1])
    repeated_insufficient_cash = sorted(
        [item for item in insufficient_symbol_counts.values() if int(
            item.get("count") or 0) >= 2],
        key=lambda item: int(item.get("count") or 0),
        reverse=True,
    )[:5]

    return {
        "today_failed": len(failures),
        "insufficient_cash_failed": insufficient_cash_failed,
        "repeated_insufficient_cash": repeated_insufficient_cash,
        "top_reason": top_reason,
        "top_reason_count": top_reason_count,
        "latest_failure_reason": str(latest_failure.get("failure_reason") or ""),
        "latest_failure_at": str(latest_failure.get("timestamp") or ""),
        "cooldown_recommended": len(repeated_insufficient_cash) > 0,
    }


def _today_realized_pnl(account: dict) -> float:
    today = _today_kst_str()
    realized = 0.0
    for order in account.get("orders", []):
        if _order_day(str(order.get("ts") or "")) != today:
            continue
        if str(order.get("side") or "").lower() != "sell":
            continue
        realized += _to_float(order.get("realized_pnl_krw"), 0.0)
    return round(realized, 2)


def _next_run_at(interval_seconds: int) -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc).astimezone()
        + datetime.timedelta(seconds=max(30, min(3600, interval_seconds)))
    ).isoformat(timespec="seconds")


def _default_validation_policy() -> dict[str, Any]:
    return {
        "validation_gate_enabled": True,
        "validation_min_trades": 8,
        "validation_min_sharpe": 0.2,
        "validation_block_on_low_reliability": True,
        "validation_require_optimized_reliability": True,
    }


def _optimized_params_status() -> dict[str, Any]:
    return {
        "version": "strategy_registry",
        "optimized_at": "",
        "is_stale": False,
        "source": "strategy_registry",
        "effective_source": "strategy_registry",
        "search_version": "",
        "search_optimized_at": "",
        "search_source": "",
        "runtime_candidate_id": "",
        "runtime_applied_at": "",
        "runtime_source": "",
        "global_overlay_source": "strategy_registry",
        "overlay_policy": overlay_policy_metadata(),
    }


def _persist_auto_trader_state_locked() -> None:
    snapshot = dict(_auto_trader_state)
    snapshot["running"] = snapshot.get("engine_state") == "running"
    snapshot["config"] = dict(snapshot.get("current_config") or {})
    save_engine_state(snapshot)


def _hydrate_auto_trader_state() -> None:
    global _auto_trader_state_loaded, _auto_trader_state
    if _auto_trader_state_loaded:
        return
    loaded = load_engine_state(default={})
    merged = dict(_auto_trader_state)
    merged.update(loaded if isinstance(loaded, dict) else {})
    config = merged.get("current_config") or merged.get(
        "config") or _default_auto_trader_config()
    if not isinstance(config, dict):
        config = _default_auto_trader_config()
    merged["current_config"] = _sync_primary_strategy_fields(dict(config))
    merged["config"] = dict(merged["current_config"])

    engine_state = str(merged.get("engine_state") or "stopped").lower()
    if engine_state in {"running", "paused"}:
        # 프로세스 재시작 시 자동 재개하지 않고 안전 정지로 복구한다.
        engine_state = "stopped"
        merged["running"] = False
        if not merged.get("last_error"):
            merged["last_error"] = "서버 재시작으로 엔진 상태를 stopped로 복구했습니다."
            merged["last_error_at"] = _now_iso()
    merged["engine_state"] = engine_state
    merged["running"] = engine_state == "running"

    policy = _default_validation_policy()
    policy.update({
        key: merged["current_config"].get(key)
        for key in policy.keys()
        if key in merged["current_config"]
    })
    merged["validation_policy"] = policy
    merged["optimized_params"] = _optimized_params_status()
    _auto_trader_state = merged
    _auto_trader_state_loaded = True
    _persist_auto_trader_state_locked()


def _build_status_payload(state: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    today_counts = _today_order_counts(account)
    running = state.get("engine_state") == "running"
    payload_state = dict(state)
    payload_state["running"] = running
    payload_state["config"] = dict(state.get("current_config") or {})
    payload_state["today_order_counts"] = today_counts
    payload_state["order_failure_summary"] = _order_failure_summary()
    payload_state["today_realized_pnl"] = _today_realized_pnl(account)
    payload_state["current_equity"] = round(
        _to_float(account.get("equity_krw"), 0.0), 2)
    payload_state["workflow_summary"] = build_workflow_summary(
        read_signal_snapshots(limit=120),
        read_order_events(limit=120),
    )
    payload_state["execution_lifecycle_summary"] = summarize_execution_events(
        read_execution_events(limit=400),
    )
    return {
        "ok": True,
        "state": payload_state,
        "account": account,
    }


def _resolve_validation_snapshot(signal: dict[str, Any]) -> dict[str, Any]:
    ev = signal.get("ev_metrics") if isinstance(
        signal.get("ev_metrics"), dict) else {}
    reasoning = signal.get("signal_reasoning") if isinstance(
        signal.get("signal_reasoning"), dict) else {}
    calibration = reasoning.get("calibration") if isinstance(
        reasoning.get("calibration"), dict) else {}
    validation_snapshot = signal.get("validation_snapshot") if isinstance(
        signal.get("validation_snapshot"), dict) else {}
    reliability_detail = ev.get("reliability_detail") if isinstance(
        ev.get("reliability_detail"), dict) else {}

    trade_count = int(
        validation_snapshot.get("trade_count")
        or calibration.get("trade_count")
        or signal.get("trade_count")
        or signal.get("validation_trades")
        or 0
    )
    trades = int(
        validation_snapshot.get("validation_trades")
        or calibration.get("sample_size")
        or signal.get("validation_trades")
        or 0
    )
    sharpe = _to_float(
        validation_snapshot.get("validation_sharpe")
        or calibration.get("validation_sharpe")
        or signal.get("validation_sharpe"),
        0.0,
    )
    max_drawdown_pct = validation_snapshot.get("max_drawdown_pct")
    if max_drawdown_pct is None:
        max_drawdown_pct = calibration.get("max_drawdown_pct")
    if max_drawdown_pct is None:
        max_drawdown_pct = signal.get("max_drawdown_pct")

    assessment = assess_validation_reliability(
        trade_count=trade_count if trade_count > 0 else trades,
        validation_signals=trades,
        validation_sharpe=sharpe,
        max_drawdown_pct=_to_float(
            max_drawdown_pct, 0.0) if max_drawdown_pct is not None else None,
    )
    return {
        "trade_count": trade_count if trade_count > 0 else trades,
        "trades": trades,
        "sharpe": round(sharpe, 4),
        "max_drawdown_pct": None if max_drawdown_pct is None else round(_to_float(max_drawdown_pct, 0.0), 4),
        "reliability": str(
            validation_snapshot.get("strategy_reliability")
            or reliability_detail.get("label")
            or assessment.label
        ),
        "reliability_reason": str(
            validation_snapshot.get("reliability_reason")
            or reliability_detail.get("reason")
            or assessment.reason
        ),
        "passes_minimum_gate": bool(
            validation_snapshot.get("passes_minimum_gate", reliability_detail.get(
                "passes_minimum_gate", assessment.passes_minimum_gate))
        ),
        "optimized_reliable": bool(
            validation_snapshot.get("is_reliable", reliability_detail.get(
                "is_reliable", assessment.is_reliable))
        ),
        "source": str(validation_snapshot.get("validation_source") or "signal"),
    }


def _optimized_validation_baseline(optimized: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(optimized, dict):
        return {}
    baseline = optimized.get("validation_baseline")
    return baseline if isinstance(baseline, dict) else {}


def _apply_validation_gate(signal: dict[str, Any], cfg: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    snapshot = _resolve_validation_snapshot(signal)
    if not bool(cfg.get("validation_gate_enabled", True)):
        return True, [], {
            "enabled": False,
            **snapshot,
        }

    code = str(signal.get("code") or "").upper()
    optimized = _load_optimized_params() or {}
    per_symbol = optimized.get("per_symbol", {}) if isinstance(
        optimized, dict) else {}
    raw_symbol_payload = per_symbol.get(
        code, {}) if isinstance(per_symbol, dict) else {}
    symbol_payload = raw_symbol_payload if isinstance(raw_symbol_payload, dict) and should_apply_symbol_overlay(
        is_reliable=bool(raw_symbol_payload.get("is_reliable", False)),
        reliability_reason=str(raw_symbol_payload.get("reliability_reason") or ""),
    ) else {}
    global_baseline = _optimized_validation_baseline(optimized)
    optimized_validation_payload = symbol_payload if symbol_payload else global_baseline
    validation_source = "signal"

    if optimized_validation_payload:
        trade_count = int(
            optimized_validation_payload.get("trade_count")
            or snapshot.get("trade_count")
            or optimized_validation_payload.get("validation_trades")
            or 0
        )
        trades = int(
            optimized_validation_payload.get("validation_trades")
            or snapshot.get("trades")
            or trade_count
            or 0
        )
        sharpe = _to_float(
            optimized_validation_payload.get("validation_sharpe"),
            snapshot.get("sharpe", 0.0),
        )
        max_drawdown_pct = optimized_validation_payload.get(
            "max_drawdown_pct", snapshot.get("max_drawdown_pct")
        )
        assessment = assess_validation_reliability(
            trade_count=trade_count if trade_count > 0 else trades,
            validation_signals=trades,
            validation_sharpe=sharpe,
            max_drawdown_pct=_to_float(
                max_drawdown_pct, 0.0) if max_drawdown_pct is not None else None,
        )
        snapshot = {
            "trade_count": trade_count if trade_count > 0 else trades,
            "trades": trades,
            "sharpe": round(sharpe, 4),
            "max_drawdown_pct": None if max_drawdown_pct is None else round(_to_float(max_drawdown_pct, 0.0), 4),
            "reliability": str(
                optimized_validation_payload.get("strategy_reliability")
                or optimized_validation_payload.get("reliability")
                or assessment.label
            ),
            "reliability_reason": str(
                optimized_validation_payload.get("reliability_reason")
                or assessment.reason
            ),
            "passes_minimum_gate": bool(
                optimized_validation_payload.get(
                    "passes_minimum_gate", assessment.passes_minimum_gate)
            ),
            "optimized_reliable": bool(
                optimized_validation_payload.get(
                    "is_reliable", assessment.is_reliable)
            ),
        }
        validation_source = "symbol" if symbol_payload else "global"

    reasons: list[str] = []
    if int(snapshot.get("trades") or 0) < int(cfg.get("validation_min_trades", 8)):
        reasons.append("validation_trades_low")
    if float(snapshot.get("sharpe") or 0.0) < float(cfg.get("validation_min_sharpe", 0.2)):
        reasons.append("validation_sharpe_low")
    if bool(cfg.get("validation_block_on_low_reliability", True)) and str(snapshot.get("reliability") or "insufficient") in {"low", "insufficient"}:
        reasons.append("validation_reliability_low")
    if bool(cfg.get("validation_require_optimized_reliability", True)) and optimized_validation_payload and not bool(snapshot.get("passes_minimum_gate")):
        reasons.append("optimized_validation_failed")

    return len(reasons) == 0, reasons, {
        "enabled": True,
        "source": validation_source,
        **snapshot,
    }


def _notification_order_hook(event: dict[str, Any], _account: dict[str, Any]) -> None:
    get_notification_service().notify_order_filled(event)


def _record_execution_order(payload: dict[str, Any]) -> dict[str, Any]:
    order_payload = enrich_order_payload(payload)
    order_payload["order_id"] = order_payload.get("order_id") or order_payload.get("trace_id") or str(uuid.uuid4())
    order_payload["trace_id"] = order_payload.get("trace_id") or order_payload["order_id"]
    order_payload["reason_code"] = normalize_execution_reason(
        order_payload.get("reason_code") or order_payload.get("failure_reason"),
        order_type=str(order_payload.get("order_type") or ""),
    )
    append_order_event(order_payload)
    append_execution_events(build_execution_events(order_payload))
    return order_payload


def _load_optimized_params() -> dict | None:
    """실행 경로에서는 quant-ops/runtime로 승인된 payload만 사용한다."""
    try:
        data = load_execution_optimized_params()
        if not data:
            return None
        optimized_at = datetime.datetime.fromisoformat(
            data.get("optimized_at", "2000-01-01"))
        age_days = (datetime.datetime.now(datetime.timezone.utc)
                    - optimized_at.astimezone(datetime.timezone.utc)).days
        if age_days > _OPTIMIZED_PARAMS_MAX_AGE_DAYS:
            logger.warning("최적화 파라미터가 {}일 지났습니다. 재실행 권장.", age_days)
        return data
    except Exception as exc:
        logger.warning("optimized_params payload 로드 실패: {}", exc)
        return None


def _get_symbol_optimized_params(code: str) -> dict:
    """per_symbol에서 해당 종목의 신뢰할 수 있는 파라미터를 반환한다. 없으면 빈 dict."""
    optimized = _load_optimized_params()
    if not optimized:
        return {}
    symbol_data = optimized.get("per_symbol", {}).get(code, {})
    if not should_apply_symbol_overlay(
        is_reliable=bool(symbol_data.get("is_reliable", False)),
        reliability_reason=str(symbol_data.get("reliability_reason") or ""),
    ):
        return {}
    return {
        k: symbol_data[k]
        for k in (
            "stop_loss_pct",
            "take_profit_pct",
            "max_holding_days",
            "rsi_min",
            "rsi_max",
            "volume_ratio_min",
            "adx_min",
            "mfi_min",
            "mfi_max",
            "bb_pct_min",
            "bb_pct_max",
            "stoch_k_min",
            "stoch_k_max",
        )
        if k in symbol_data
    }


def _get_paper_engine() -> PaperExecutionEngine:
    global _paper_engine
    if _paper_engine is None:
        state_path = Path(os.getenv("PAPER_TRADING_STATE_PATH",
                          str(LOGS_DIR / "paper_account_state.json")))
        _paper_engine = PaperExecutionEngine(
            config=EngineConfig(
                state_path=state_path,
                default_initial_cash_krw=10_000_000.0,
                default_initial_cash_usd=10_000.0,
                default_paper_days=7,
                order_notifier=_notification_order_hook,
            ),
            quote_provider=_resolve_stock_quote,
            fx_provider=_paper_fx_rate,
        )
    return _paper_engine


def _get_live_engine() -> LiveBrokerExecutionEngine:
    """KISClient가 연결된 실거래 엔진을 반환한다 (싱글턴).

    실거래 전환 시: get_execution_engine()에서 이 함수를 호출하도록 분기 추가.
    """
    global _live_engine
    if _live_engine is None:
        kis = KISClient.from_env()
        _live_engine = LiveBrokerExecutionEngine(
            kis_client=kis,
            quote_provider=_resolve_stock_quote,   # 기존 quote provider 재사용
            fx_provider=_paper_fx_rate,            # 기존 fx provider 재사용
            config=EngineConfig(
                state_path=LOGS_DIR / "live_account_state.json",  # paper와 분리
            ),
        )
    return _live_engine


# ── 엔진 선택 함수 (기존 get_execution_engine 또는 유사 함수 교체) ────────────

def get_execution_engine(mode: str = "paper") -> PaperExecutionEngine | LiveBrokerExecutionEngine:
    """실행 모드에 따라 엔진을 반환한다.

    mode:
      'paper' - 내부 가상계좌 (현재 운영 중, 기본값)
      'live'  - KIS 실거래 주문 (실거래 전환 시 사용)

    전환 방법:
      .env 또는 API 파라미터로 EXECUTION_MODE=live 설정 후 이 함수에 전달.
      절대로 코드를 직접 수정하지 말고 이 함수의 mode 인자로만 제어할 것.
    """
    if mode == "live":
        return _get_live_engine()
    return _get_paper_engine()  # 기존 함수 그대로 유지


def _normalize_pick_market(market: str) -> str:
    return normalize_market(market)


def _infer_pick_market(code: str, market: str, name: str = "") -> str:
    return resolve_market(code=code, name=name, market=market, scope="core")


def _parse_seed_positions(raw) -> list[dict]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("seed_positions는 배열이어야 합니다.")
    parsed: list[dict] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"seed_positions[{idx}] 형식이 올바르지 않습니다.")
        market = str(item.get("market") or "").strip().upper()
        code = str(item.get("code") or "").strip().upper()
        name = str(item.get("name") or "").strip()
        try:
            quantity = int(item.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0
        avg_price_raw = item.get("avg_price_local")
        try:
            avg_price_local = float(
                avg_price_raw) if avg_price_raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            avg_price_local = 0.0

        if market not in {"KOSPI", "NASDAQ"}:
            raise ValueError(
                f"seed_positions[{idx}] market은 KOSPI/NASDAQ만 허용합니다.")
        if not code:
            raise ValueError(f"seed_positions[{idx}] code가 필요합니다.")
        if quantity <= 0:
            raise ValueError(f"seed_positions[{idx}] quantity는 1 이상이어야 합니다.")
        if avg_price_local <= 0:
            raise ValueError(
                f"seed_positions[{idx}] avg_price_local은 0보다 커야 합니다.")

        parsed.append({
            "market": market,
            "code": code,
            "name": name,
            "quantity": quantity,
            "avg_price_local": avg_price_local,
        })
    return parsed


def _normalize_theme_focus(raw) -> list[str]:
    return _signal_normalize_theme_focus(raw)


def _parse_theme_gate_config(raw: dict | None = None) -> dict:
    return _signal_parse_theme_gate_config(raw)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_theme_news_count(item: dict) -> int:
    if not isinstance(item, dict):
        return 0
    explicit = item.get("theme_news_count")
    if isinstance(explicit, (int, float)):
        return int(explicit)
    related_news = item.get("related_news", [])
    if not isinstance(related_news, list):
        return 0
    count = 0
    for news in related_news:
        if not isinstance(news, dict):
            continue
        score = _to_float(news.get("theme_score"), default=0.0)
        themes = news.get("matched_themes", [])
        if score > 0 or (isinstance(themes, list) and len(themes) > 0):
            count += 1
    return count


def _passes_theme_gate(item: dict, cfg: dict) -> bool:
    if not bool(cfg.get("theme_gate_enabled", True)):
        return False
    if _to_float(item.get("theme_score"), default=0.0) < float(cfg.get("theme_min_score", 2.5)):
        return False
    if _pick_theme_news_count(item) < int(cfg.get("theme_min_news", 1)):
        return False
    return True


def _default_auto_trader_config() -> dict:
    profiles = {
        profile.market: serialize_strategy_profiles([profile])[profile.market]
        for profile in default_strategy_profiles(["KOSPI", "NASDAQ"])
    }
    primary = profiles["KOSPI"]
    base = {
        "interval_seconds": 300,
        "markets": ["KOSPI", "NASDAQ"],
        "max_positions_per_market": int(primary["max_positions"]),
        "min_score": 50.0,
        "include_neutral": True,
        "theme_gate_enabled": True,
        "theme_min_score": 2.5,
        "theme_min_news": 1,
        "theme_priority_bonus": 2.0,
        "theme_focus": list(_DEFAULT_THEME_FOCUS),
        "daily_buy_limit": 100,
        "daily_sell_limit": 100,
        "max_orders_per_symbol_per_day": 3,
        "rsi_min": primary["rsi_min"],
        "rsi_max": primary["rsi_max"],
        "volume_ratio_min": primary["volume_ratio_min"],
        "signal_interval": primary["signal_interval"],
        "signal_range": primary["signal_range"],
        "stop_loss_pct": primary["stop_loss_pct"],
        "take_profit_pct": primary["take_profit_pct"],
        "max_holding_days": primary["max_holding_days"],
        "risk_per_trade_pct": 0.35,
        "daily_loss_limit_pct": 2.0,
        "max_consecutive_loss": 3,
        "cooldown_minutes": 120,
        "max_symbol_weight_pct": 20.0,
        "max_sector_weight_pct": 35.0,
        "max_market_exposure_pct": 70.0,
        "block_buy_in_risk_off": True,
        "block_buy_when_risk_high": True,
        "validation_gate_enabled": True,
        "validation_min_trades": 8,
        "validation_min_sharpe": 0.2,
        "validation_block_on_low_reliability": True,
        "validation_require_optimized_reliability": True,
        "min_avg_volume": 100000,
        "min_avg_notional_krw": 50000000,
        "slippage_bps_base": 8.0,
        "market_profiles": profiles,
    }
    return base


def _today_kst_str() -> str:
    return datetime.datetime.now(_KST).date().isoformat()


def _order_day(ts: str) -> str:
    try:
        return datetime.datetime.fromisoformat(ts).astimezone(_KST).date().isoformat()
    except Exception:
        return ""


def _position_holding_days(position: dict) -> int:
    entry_ts = str(position.get("entry_ts")
                   or position.get("updated_at") or "")
    try:
        entry_date = datetime.datetime.fromisoformat(
            entry_ts).astimezone(_KST).date()
    except Exception:
        return 0
    return max(0, (datetime.datetime.now(_KST).date() - entry_date).days)


def _auto_trader_profile_map(cfg: dict, markets: list[str] | None = None) -> dict[str, dict]:
    selected_markets = [
        normalize_strategy_market(market)
        for market in (markets or cfg.get("markets") or ["KOSPI", "NASDAQ"])
        if normalize_strategy_market(market) in {"KOSPI", "NASDAQ"}
    ] or ["KOSPI", "NASDAQ"]
    raw_profiles = cfg.get("market_profiles")
    if isinstance(raw_profiles, dict) and raw_profiles:
        profile_map = {
            normalize_strategy_market(market): serialize_strategy_profiles([
                profile_from_mapping(
                    market, payload if isinstance(payload, dict) else {})
            ])[normalize_strategy_market(market)]
            for market, payload in raw_profiles.items()
            if normalize_strategy_market(market) in {"KOSPI", "NASDAQ"}
        }
        for market in selected_markets:
            profile_map.setdefault(
                market,
                serialize_strategy_profiles(
                    [default_strategy_profile(market)])[market],
            )
        return profile_map

    overrides: dict[str, object] = {}
    if "max_positions_per_market" in cfg:
        overrides["max_positions"] = int(
            cfg.get("max_positions_per_market") or 5)
    for key in (
        "max_holding_days",
        "rsi_min",
        "rsi_max",
        "volume_ratio_min",
        "adx_min",
        "mfi_min",
        "mfi_max",
        "bb_pct_min",
        "bb_pct_max",
        "stoch_k_min",
        "stoch_k_max",
        "signal_interval",
        "signal_range",
    ):
        if key in cfg and cfg.get(key) not in (None, ""):
            overrides[key] = cfg.get(key)
    for key in ("stop_loss_pct", "take_profit_pct"):
        if key in cfg:
            overrides[key] = cfg.get(key)

    return {
        profile.market: serialize_strategy_profiles([
            build_strategy_profile(profile.market, **overrides)
        ])[profile.market]
        for profile in default_strategy_profiles(selected_markets)
    }


def _auto_trader_profile(cfg: dict, market: str):
    profile_map = _auto_trader_profile_map(cfg, [market])
    normalized = normalize_strategy_market(market)
    return profile_from_mapping(normalized, profile_map.get(normalized))


def _sync_primary_strategy_fields(cfg: dict) -> dict:
    markets = [
        normalize_strategy_market(market)
        for market in (cfg.get("markets") or ["KOSPI", "NASDAQ"])
        if normalize_strategy_market(market) in {"KOSPI", "NASDAQ"}
    ] or ["KOSPI", "NASDAQ"]
    profile_map = _auto_trader_profile_map(cfg, markets)
    primary = profile_map.get(markets[0]) or next(iter(profile_map.values()))
    cfg["market_profiles"] = profile_map
    cfg["max_positions_per_market"] = int(primary.get(
        "max_positions") or cfg.get("max_positions_per_market") or 5)
    cfg["signal_interval"] = str(primary.get("signal_interval") or "1d")
    cfg["signal_range"] = str(primary.get("signal_range") or "6mo")
    cfg["rsi_min"] = float(primary.get("rsi_min") or 45.0)
    cfg["rsi_max"] = float(primary.get("rsi_max") or 68.0)
    cfg["volume_ratio_min"] = float(primary.get("volume_ratio_min") or 1.2)
    cfg["adx_min"] = primary.get("adx_min")
    cfg["mfi_min"] = primary.get("mfi_min")
    cfg["mfi_max"] = primary.get("mfi_max")
    cfg["bb_pct_min"] = primary.get("bb_pct_min")
    cfg["bb_pct_max"] = primary.get("bb_pct_max")
    cfg["stoch_k_min"] = primary.get("stoch_k_min")
    cfg["stoch_k_max"] = primary.get("stoch_k_max")
    cfg["stop_loss_pct"] = primary.get("stop_loss_pct")
    cfg["take_profit_pct"] = primary.get("take_profit_pct")
    cfg["max_holding_days"] = int(primary.get("max_holding_days") or 30)
    return cfg


def _apply_quant_candidate_patch(cfg: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(cfg or _default_auto_trader_config())
    patch = candidate.get("patch") if isinstance(
        candidate.get("patch"), dict) else {}
    settings = candidate.get("settings") if isinstance(
        candidate.get("settings"), dict) else {}
    decision = candidate.get("decision") if isinstance(candidate.get("decision"), dict) else {}

    # Determine which market this candidate was optimized for.
    # Patch values are market-specific and must not bleed into other markets.
    base_query = candidate.get("base_query") if isinstance(candidate.get("base_query"), dict) else {}
    candidate_market = normalize_strategy_market(str(base_query.get("market_scope") or ""))

    profile_map = merged.get("market_profiles") if isinstance(
        merged.get("market_profiles"), dict) else _auto_trader_profile_map(merged)
    next_profile_map: dict[str, dict[str, Any]] = {}
    for market, payload in profile_map.items():
        current_payload = dict(payload) if isinstance(payload, dict) else {}
        # Apply patch only to the market this candidate was validated for.
        # If candidate_market is unknown, apply to all (safe fallback).
        if not candidate_market or normalize_strategy_market(market) == candidate_market:
            for key, value in patch.items():
                if key in _OPTIMIZABLE_KEYS and value not in (None, ""):
                    current_payload[key] = value
        next_profile_map[market] = current_payload
    merged["market_profiles"] = next_profile_map

    if settings.get("minTrades") not in (None, ""):
        merged["validation_min_trades"] = max(
            0, min(200, int(settings.get("minTrades") or 0)))
    if settings.get("walkForward") is not None:
        merged["validation_gate_enabled"] = bool(
            merged.get("validation_gate_enabled", True))

    if str(decision.get("status") or "") == "limited_adopt":
        base_risk = float(merged.get("risk_per_trade_pct") or 0.35)
        merged["risk_per_trade_pct"] = min(base_risk * 0.5, 0.2)
        merged["max_positions_per_market"] = min(int(merged.get("max_positions_per_market") or 5), 2)
        merged["max_symbol_weight_pct"] = min(float(merged.get("max_symbol_weight_pct") or 20.0), 10.0)
        merged["max_market_exposure_pct"] = min(float(merged.get("max_market_exposure_pct") or 70.0), 35.0)
        merged["validation_require_optimized_reliability"] = True
        merged["quant_candidate_approval_level"] = str(decision.get("approval_level") or "probationary")
    else:
        merged["quant_candidate_approval_level"] = str(decision.get("approval_level") or "full")
    merged = _sync_primary_strategy_fields(merged)
    return merged


def _should_enter_by_indicators(technicals: dict, cfg: dict, market: str) -> bool:
    if not isinstance(technicals, dict):
        return False
    return should_enter_from_snapshot(technicals, _auto_trader_profile(cfg, market))


def _should_exit_by_indicators(position: dict, technicals: dict, cfg: dict, market: str) -> str | None:
    if not isinstance(technicals, dict):
        return None
    return should_exit_from_snapshot(
        technicals,
        entry_price=float(position.get("avg_price_local") or 0.0) or None,
        holding_days=_position_holding_days(position),
        profile=_auto_trader_profile(cfg, market),
    )


def _collect_pick_candidates(market: str, cfg: dict) -> list[dict]:
    return _signal_collect_pick_candidates(market=market, cfg=cfg)


def _auto_invest_picks(
    *,
    market: str = "NASDAQ",
    max_positions: int = 5,
    min_score: float = 50.0,
    include_neutral: bool = False,
    theme_gate_enabled: bool = True,
    theme_min_score: float = 2.5,
    theme_min_news: int = 1,
    theme_priority_bonus: float = 2.0,
    theme_focus: list[str] | None = None,
) -> dict:
    target_market = _normalize_pick_market(market)
    if target_market not in _SUPPORTED_AUTO_TRADE_MARKETS:
        return {"ok": False, "error": "market은 NASDAQ/KOSPI만 허용합니다."}

    calendar_market = "KR" if target_market == "KOSPI" else "US"
    if not is_market_open(calendar_market):
        return {"ok": False, "error": f"{target_market} 정규장 시간이 아닙니다. 장중에만 거래가 가능합니다."}

    filter_cfg = _default_auto_trader_config()
    filter_cfg.update({
        "min_score": min_score,
        "include_neutral": include_neutral,
        "theme_gate_enabled": theme_gate_enabled,
        "theme_min_score": theme_min_score,
        "theme_min_news": theme_min_news,
        "theme_priority_bonus": theme_priority_bonus,
        "theme_focus": theme_focus or list(_DEFAULT_THEME_FOCUS),
        "markets": [target_market],
        "max_positions_per_market": int(max_positions),
    })

    engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))
    account = engine.get_account(refresh_quotes=True)
    held_codes = {
        str(position.get("code") or "").upper()
        for position in account.get("positions", [])
        if str(position.get("market") or "").upper() == target_market
    }
    market_position_count = sum(
        1
        for position in account.get("positions", [])
        if str(position.get("market") or "").upper() == target_market
    )
    slots = max(0, int(max_positions) - market_position_count)
    if slots <= 0:
        return {
            "ok": True,
            "message": "이미 최대 포지션 수를 보유 중입니다.",
            "executed": [],
            "skipped": [],
            "account": account,
        }

    entry_candidates = select_entry_candidates(
        market=target_market,
        cfg=filter_cfg,
        account=account,
        max_count=max(20, slots * 6),
    )

    executed = []
    skipped = []
    remaining_slots = slots

    for item in entry_candidates:
        if remaining_slots <= 0:
            skipped.append({"code": item.get("code"),
                           "reason": "max_positions"})
            continue

        code = str(item.get("code") or "").upper()
        if code in held_codes:
            skipped.append({"code": code, "reason": "already_holding"})
            continue

        size_recommendation = item.get("size_recommendation") if isinstance(
            item.get("size_recommendation"), dict) else {}
        quantity = int(size_recommendation.get("quantity") or 0)
        if quantity <= 0:
            skipped.append(
                {"code": code, "reason": size_recommendation.get("reason") or "size_zero"})
            continue

        risk_inputs = item.get("risk_inputs") if isinstance(
            item.get("risk_inputs"), dict) else {}
        stop_loss_pct = risk_inputs.get("stop_loss_pct")
        take_profit_pct = risk_inputs.get("take_profit_pct")

        order_result = engine.place_order(
            side="buy",
            code=code,
            market=target_market,
            quantity=quantity,
            order_type="market",
            limit_price=None,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        if not order_result.get("ok"):
            skipped.append(
                {"code": code, "reason": order_result.get("error") or "order_failed"})
            continue

        event = order_result.get("event") or {}
        ev_metrics = item.get("ev_metrics") if isinstance(
            item.get("ev_metrics"), dict) else {}
        executed.append({
            "code": code,
            "name": item.get("name"),
            "strategy_type": item.get("strategy_type"),
            "expected_value": ev_metrics.get("expected_value"),
            "quantity": event.get("quantity"),
            "filled_price_local": event.get("filled_price_local"),
            "filled_price_krw": event.get("filled_price_krw"),
            "notional_krw": event.get("notional_krw"),
        })
        held_codes.add(code)
        remaining_slots -= 1

    final_account = engine.get_account(refresh_quotes=True)
    message = ""
    if not entry_candidates:
        message = "EV 및 리스크 가드를 통과한 자동매수 후보가 없습니다."
    return {
        "ok": True,
        "strategy": "ev-ranked-auto-buy-v2",
        "market": target_market,
        "max_positions": int(max_positions),
        "min_score": float(min_score),
        "executed": executed,
        "skipped": skipped,
        "candidate_count": len(entry_candidates),
        "include_neutral": include_neutral,
        "theme_gate_enabled": bool(theme_gate_enabled),
        "theme_min_score": float(theme_min_score),
        "theme_min_news": int(theme_min_news),
        "theme_priority_bonus": float(theme_priority_bonus),
        "theme_focus": _normalize_theme_focus(theme_focus),
        "message": message,
        "account": final_account,
    }


def _run_auto_trader_cycle(cfg: dict) -> dict:
    global _last_daily_loss_notified_day
    engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))
    notifier = get_notification_service()
    cycle_id = f"cycle-{datetime.datetime.now(_KST).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started_at = _now_iso()
    account = engine.get_account(refresh_quotes=True)
    if int(account.get("days_left") or 0) <= 0:
        raise RuntimeError("모의투자 기간이 종료되어 자동매매를 중지합니다.")

    orders = account.get("orders", [])
    today = _today_kst_str()
    daily_buy_limit = int(cfg.get("daily_buy_limit", 20))
    daily_sell_limit = int(cfg.get("daily_sell_limit", 20))
    max_orders_per_symbol = int(cfg.get("max_orders_per_symbol_per_day", 1))

    def _count_orders(market: str, side: str) -> int:
        return sum(
            1 for order in orders
            if str(order.get("market") or "").upper() == market
            and str(order.get("side") or "").lower() == side
            and _order_day(str(order.get("ts") or "")) == today
        )

    def _symbol_order_count(market: str, side: str, code: str) -> int:
        return sum(
            1 for order in orders
            if str(order.get("market") or "").upper() == market
            and str(order.get("side") or "").lower() == side
            and str(order.get("code") or "").upper() == code
            and _order_day(str(order.get("ts") or "")) == today
        )

    def _load_technicals(code: str, market: str) -> tuple[dict | None, str | None]:
        primary_error: str | None = None
        profile = _auto_trader_profile(cfg, market)
        try:
            technicals = _compute_technical_snapshot(
                code,
                market,
                range_=profile.signal_range,
                interval=profile.signal_interval,
            )
        except Exception as exc:
            technicals = None
            primary_error = str(exc)
        if technicals:
            return technicals, None

        if profile.signal_interval != "1d" or profile.signal_range != "6mo":
            try:
                fallback = _compute_technical_snapshot(
                    code,
                    market,
                    range_="6mo",
                    interval="1d",
                )
            except Exception as exc:
                if primary_error:
                    return None, f"{primary_error}; fallback={exc}"
                return None, str(exc)
            if fallback:
                return fallback, None

        return None, primary_error or "data_insufficient_or_api_error"

    executed_buys: list[dict] = []
    executed_sells: list[dict] = []
    skipped: list[dict] = []
    blocked_reason_counts: dict[str, int] = {}
    closed_markets: list[str] = []
    markets = [m for m in cfg.get("markets", ["KOSPI", "NASDAQ"]) if m in {
        "KOSPI", "NASDAQ"}]
    candidate_counts_by_market: dict[str, int] = {
        market: 0 for market in markets}
    signal_snapshots: list[dict[str, Any]] = []
    blocked_counts_by_market: dict[str, int] = {
        market: 0 for market in markets}
    risk_guard_state: dict[str, Any] = {}

    _MARKET_TO_CALENDAR = {"KOSPI": "KR", "NASDAQ": "US"}

    for market in markets:
        calendar_market = _MARKET_TO_CALENDAR.get(market, market)
        if not is_market_open(calendar_market):
            closed_markets.append(market)
            candidate_counts_by_market[market] = 0
            skipped.append({
                "market": market,
                "reason": "market_closed",
            })
            continue

        account = engine.get_account(refresh_quotes=True)
        market_positions = [
            position for position in account.get("positions", [])
            if str(position.get("market") or "").upper() == market
        ]

        sell_count = _count_orders(market, "sell")
        for position in market_positions:
            if sell_count >= daily_sell_limit:
                break
            code = str(position.get("code") or "").upper()
            pos_name = str(position.get("name") or code)
            if _symbol_order_count(market, "sell", code) >= max_orders_per_symbol:
                continue
            technicals, tech_error = _load_technicals(code, market)
            if tech_error:
                skipped.append({"code": code, "name": pos_name, "market": market,
                               "reason": f"technicals_error: {tech_error}"})
                continue
            if not technicals:
                continue
            reason = _should_exit_by_indicators(
                position, technicals, cfg, market)
            if not reason:
                continue
            result = engine.place_order(
                side="sell",
                code=code,
                market=market,
                quantity=int(position.get("quantity") or 0),
                order_type="market",
            )
            if result.get("ok"):
                sell_count += 1
                event = result.get("event") or {}
                executed_sells.append(
                    {"code": code, "market": market, "reason": reason, "quantity": event.get("quantity")})
                _record_execution_order({
                    "timestamp": event.get("ts") or _now_iso(),
                    "success": True,
                    "side": "sell",
                    "code": code,
                    "market": market,
                    "quantity": event.get("quantity"),
                    "order_type": "market",
                    "submitted_at": started_at,
                    "filled_at": event.get("ts"),
                    "filled_price_local": event.get("filled_price_local"),
                    "filled_price_krw": event.get("filled_price_krw"),
                    "notional_krw": event.get("notional_krw"),
                    "failure_reason": "",
                    "reason_code": "",
                    "message": "",
                    "originating_cycle_id": cycle_id,
                    "originating_signal_key": f"{market}:{code}",
                    "quote_source": event.get("quote_source"),
                    "quote_fetched_at": event.get("quote_fetched_at"),
                    "quote_is_stale": event.get("quote_is_stale"),
                })
                orders = (result.get("account") or {}).get("orders", orders)
            else:
                failure_reason = result.get("error") or "sell_failed"
                skipped.append({"code": code, "market": market,
                               "reason": failure_reason})
                _record_execution_order({
                    "timestamp": _now_iso(),
                    "success": False,
                    "side": "sell",
                    "code": code,
                    "market": market,
                    "quantity": int(position.get("quantity") or 0),
                    "order_type": "market",
                    "submitted_at": _now_iso(),
                    "filled_at": "",
                    "filled_price_local": None,
                    "filled_price_krw": None,
                    "notional_krw": None,
                    "failure_reason": failure_reason,
                    "reason_code": failure_reason,
                    "message": failure_reason,
                    "originating_cycle_id": cycle_id,
                    "originating_signal_key": f"{market}:{code}",
                })
                notifier.notify_order_failure({
                    "code": code,
                    "market": market,
                    "side": "sell",
                    "failure_reason": failure_reason,
                    "originating_cycle_id": cycle_id,
                })

        account = engine.get_account(refresh_quotes=True)
        held_codes = {
            str(position.get("code") or "").upper()
            for position in account.get("positions", [])
            if str(position.get("market") or "").upper() == market
        }
        market_position_count = len(held_codes)
        profile = _auto_trader_profile(cfg, market)
        max_positions = int(profile.max_positions)
        slots = max(0, max_positions - market_position_count)
        if slots <= 0:
            candidate_counts_by_market[market] = 0
            skipped.append({
                "market": market,
                "reason": "max_positions_reached",
            })
            continue
        buy_count = _count_orders(market, "buy")
        signal_book = build_signal_book(
            markets=[market], cfg=cfg, account=account)
        risk_guard_state = signal_book.get(
            "risk_guard_state", risk_guard_state)
        market_signals = signal_book.get("signals", []) if isinstance(
            signal_book.get("signals"), list) else []
        effective_candidates: list[dict[str, Any]] = []
        blocked_count = 0
        for signal in market_signals:
            if not isinstance(signal, dict):
                continue
            candidate = dict(signal)
            signal_state = str(candidate.get("signal_state") or "")
            risk_check = candidate.get("risk_check") if isinstance(candidate.get("risk_check"), dict) else {}
            decision = summarize_order_decision(candidate)
            entry_allowed = decision["orderable"]
            reason_code = decision["reason_code"]
            merged_reasons = list(candidate.get("reason_codes") or []) or ([reason_code] if reason_code else [])
            if decision["action"] == "block":
                blocked_count += 1
                for reason in merged_reasons:
                    key = str(reason or "unknown")
                    blocked_reason_counts[key] = blocked_reason_counts.get(key, 0) + 1
                _record_execution_order({
                    "timestamp": _now_iso(),
                    "success": False,
                    "side": "buy",
                    "code": candidate.get("code"),
                    "market": candidate.get("market") or market,
                    "strategy_id": candidate.get("strategy_id"),
                    "strategy_name": candidate.get("strategy_name"),
                    "quantity": decision["order_quantity"],
                    "order_type": "screened",
                    "submitted_at": started_at,
                    "filled_at": "",
                    "filled_price_local": None,
                    "filled_price_krw": None,
                    "notional_krw": None,
                    "failure_reason": reason_code,
                    "reason_code": reason_code,
                    "message": (
                        str(risk_check.get("message") or "")
                        if str(risk_check.get("reason_code") or "") not in ("", "ok")
                        else ""
                    ) or reason_code or "screened",
                    "originating_cycle_id": cycle_id,
                    "originating_signal_key": f"{market}:{candidate.get('code')}",
                })
            candidate["entry_allowed"] = entry_allowed
            candidate["reason_codes"] = merged_reasons
            if entry_allowed:
                effective_candidates.append(candidate)

            ev_metrics = candidate.get("ev_metrics") if isinstance(
                candidate.get("ev_metrics"), dict) else {}
            size_reco = candidate.get("size_recommendation") if isinstance(
                candidate.get("size_recommendation"), dict) else {}
            realism = candidate.get("execution_realism") if isinstance(
                candidate.get("execution_realism"), dict) else {}
            report_reasoning = candidate.get("report_reasoning") if isinstance(
                candidate.get("report_reasoning"), dict) else {}
            signal_snapshots.append(enrich_signal_payload({
                "timestamp": started_at,
                "cycle_id": cycle_id,
                "signal_id": f"{cycle_id}:{market}:{candidate.get('code')}",
                "code": candidate.get("code"),
                "name": candidate.get("name"),
                "market": candidate.get("market") or market,
                "strategy_id": candidate.get("strategy_id"),
                "strategy_name": candidate.get("strategy_name"),
                "strategy_type": candidate.get("strategy_type"),
                "signal_state": signal_state,
                "score": candidate.get("score"),
                "confidence": ev_metrics.get("win_probability"),
                "expected_value": ev_metrics.get("expected_value"),
                "entry_allowed": entry_allowed,
                "reason_codes": merged_reasons,
                "size_recommendation": size_reco,
                "liquidity_gate_status": realism.get("liquidity_gate_status"),
                "slippage_bps": realism.get("slippage_bps"),
                "risk_reason_code": risk_check.get("reason_code"),
                "risk_message": risk_check.get("message"),
                "ai_reasoning_summary": report_reasoning.get("summary") or "",
                "candidate_source": candidate.get("candidate_source"),
                "candidate_source_label": candidate.get("candidate_source_label"),
                "candidate_source_detail": candidate.get("candidate_source_detail"),
                "candidate_source_tier": candidate.get("candidate_source_tier"),
                "candidate_source_priority": candidate.get("candidate_source_priority"),
                "candidate_runtime_source_mode": candidate.get("candidate_runtime_source_mode"),
                "candidate_research_source": candidate.get("candidate_research_source"),
                "research_status": candidate.get("research_status"),
                "research_unavailable": candidate.get("research_unavailable"),
                "research_score": candidate.get("research_score"),
                "final_action": candidate.get("final_action"),
                "final_action_snapshot": candidate.get("final_action_snapshot"),
                "layer_events": candidate.get("layer_events"),
                "source": "strategy_engine",
                "fetched_at": signal_book.get("generated_at") or started_at,
                "is_stale": False,
                "risk_check": risk_check,
            }))

        blocked_counts_by_market[market] = blocked_count
        candidate_counts_by_market[market] = len(market_signals)
        for candidate in effective_candidates:
            if slots <= 0 or buy_count >= daily_buy_limit:
                break
            code = str(candidate.get("code") or "").upper()
            cand_name = str(candidate.get("name") or code)
            if not code or code in held_codes:
                continue
            if _symbol_order_count(market, "buy", code) >= max_orders_per_symbol:
                continue

            size_recommendation = candidate.get("size_recommendation") if isinstance(
                candidate.get("size_recommendation"), dict) else {}
            quantity = int(size_recommendation.get("quantity") or 0)
            if quantity <= 0:
                skipped.append({
                    "code": code,
                    "name": cand_name,
                    "market": market,
                    "reason": size_recommendation.get("reason") or "size_zero",
                })
                continue

            risk_inputs = candidate.get("risk_inputs") if isinstance(
                candidate.get("risk_inputs"), dict) else {}
            stop_loss_pct = risk_inputs.get("stop_loss_pct")
            take_profit_pct = risk_inputs.get("take_profit_pct")

            result = engine.place_order(
                side="buy",
                code=code,
                market=market,
                quantity=quantity,
                order_type="market",
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
            )
            if result.get("ok"):
                buy_count += 1
                slots -= 1
                held_codes.add(code)
                event = result.get("event") or {}
                ev_metrics = candidate.get("ev_metrics") if isinstance(
                    candidate.get("ev_metrics"), dict) else {}
                executed_buys.append({
                    "code": code,
                    "name": cand_name,
                    "market": market,
                    "strategy_type": candidate.get("strategy_type"),
                    "expected_value": ev_metrics.get("expected_value"),
                    "quantity": event.get("quantity"),
                    "filled_price_local": event.get("filled_price_local"),
                })
                _record_execution_order({
                    "timestamp": event.get("ts") or _now_iso(),
                    "success": True,
                    "side": "buy",
                    "code": code,
                    "market": market,
                    "strategy_id": candidate.get("strategy_id"),
                    "strategy_name": candidate.get("strategy_name"),
                    "quantity": event.get("quantity"),
                    "order_type": "market",
                    "submitted_at": started_at,
                    "filled_at": event.get("ts"),
                    "filled_price_local": event.get("filled_price_local"),
                    "filled_price_krw": event.get("filled_price_krw"),
                    "notional_krw": event.get("notional_krw"),
                    "failure_reason": "",
                    "reason_code": "",
                    "message": "",
                    "originating_cycle_id": cycle_id,
                    "originating_signal_key": f"{market}:{code}",
                    "quote_source": event.get("quote_source"),
                    "quote_fetched_at": event.get("quote_fetched_at"),
                    "quote_is_stale": event.get("quote_is_stale"),
                })
                orders = (result.get("account") or {}).get("orders", orders)
            else:
                failure_reason = result.get("error") or "buy_failed"
                skipped.append({"code": code, "name": cand_name, "market": market,
                               "reason": failure_reason})
                _record_execution_order({
                    "timestamp": _now_iso(),
                    "success": False,
                    "side": "buy",
                    "code": code,
                    "market": market,
                    "strategy_id": candidate.get("strategy_id"),
                    "strategy_name": candidate.get("strategy_name"),
                    "quantity": quantity,
                    "order_type": "market",
                    "submitted_at": _now_iso(),
                    "filled_at": "",
                    "filled_price_local": None,
                    "filled_price_krw": None,
                    "notional_krw": None,
                    "failure_reason": failure_reason,
                    "reason_code": failure_reason,
                    "message": failure_reason,
                    "originating_cycle_id": cycle_id,
                    "originating_signal_key": f"{market}:{code}",
                })
                notifier.notify_order_failure({
                    "code": code,
                    "market": market,
                    "side": "buy",
                    "failure_reason": failure_reason,
                    "originating_cycle_id": cycle_id,
                })

    skip_reason_counts: dict[str, int] = {}
    for item in skipped:
        reason = str(item.get("reason") or "unknown")
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

    market_stats: dict[str, dict] = {}
    for market in markets:
        market_stats[market] = {
            "candidate_count": int(candidate_counts_by_market.get(market, 0)),
            "market_closed": market in closed_markets,
            "executed_buy_count": sum(
                1 for item in executed_buys
                if str(item.get("market") or "").upper() == market
            ),
            "executed_sell_count": sum(
                1 for item in executed_sells
                if str(item.get("market") or "").upper() == market
            ),
            "blocked_count": int(blocked_counts_by_market.get(market, 0)),
            "skipped_count": sum(
                1 for item in skipped
                if str(item.get("market") or "").upper() == market
            ),
        }

    final_account = engine.get_account(refresh_quotes=True)
    unrealized_pnl = sum(
        _to_float(position.get("unrealized_pnl_krw"), 0.0)
        for position in final_account.get("positions", [])
        if isinstance(position, dict)
    )
    finished_at = _now_iso()
    summary = {
        "ok": True,
        "cycle_id": cycle_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "ran_at": finished_at,
        "executed_buy_count": len(executed_buys),
        "executed_sell_count": len(executed_sells),
        "executed_buys": executed_buys,
        "executed_sells": executed_sells,
        "candidate_counts_by_market": candidate_counts_by_market,
        "blocked_reason_counts": blocked_reason_counts,
        "skip_reason_counts": skip_reason_counts,
        "market_stats": market_stats,
        "closed_markets": closed_markets,
        "risk_guard_state": risk_guard_state,
        "validation_gate_summary": {
            "enabled": False,
            "min_trades": 0,
            "min_sharpe": 0.0,
            "blocked_reason_counts": blocked_reason_counts,
            "blocked_count_by_market": blocked_counts_by_market,
        },
        "pnl_snapshot": {
            "realized_today": _today_realized_pnl(final_account),
            "unrealized": round(unrealized_pnl, 2),
            "equity_krw": round(_to_float(final_account.get("equity_krw"), 0.0), 2),
        },
        "skipped": skipped[:50],
        "error": "",
        "account": final_account,
    }
    append_signal_snapshots(signal_snapshots)
    append_engine_cycle(summary)
    append_account_snapshot({
        "timestamp": finished_at,
        "cycle_id": cycle_id,
        "cash_krw": final_account.get("cash_krw"),
        "cash_usd": final_account.get("cash_usd"),
        "equity_krw": final_account.get("equity_krw"),
        "realized_pnl_today": _today_realized_pnl(final_account),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "open_positions_count": len(final_account.get("positions", [])),
        "total_orders_today": _today_order_counts(final_account).get("buy", 0) + _today_order_counts(final_account).get("sell", 0),
        "days_left": final_account.get("days_left"),
        "engine_state": _auto_trader_state.get("engine_state"),
    })
    if isinstance(risk_guard_state, dict) and not bool(risk_guard_state.get("entry_allowed", True)):
        reasons = [str(item) for item in risk_guard_state.get("reasons", [])]
        if "daily_loss_limit_reached" in reasons:
            today = _today_kst_str()
            if _last_daily_loss_notified_day != today:
                _last_daily_loss_notified_day = today
                notifier.notify_daily_loss_limit({
                    "daily_loss_left": risk_guard_state.get("daily_loss_left"),
                    "reason": "daily_loss_limit_reached",
                })
    return summary


def _auto_trader_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        _hydrate_auto_trader_state()
        with _auto_trader_lock:
            cfg = dict(_auto_trader_state.get(
                "current_config") or _default_auto_trader_config())
            engine_state = str(_auto_trader_state.get(
                "engine_state") or "stopped")
        if engine_state == "paused":
            stop_event.wait(1.0)
            continue
        if engine_state != "running":
            stop_event.set()
            break
        try:
            summary = _run_auto_trader_cycle(cfg)
            with _auto_trader_lock:
                _auto_trader_state["last_run_at"] = _now_iso()
                _auto_trader_state["last_success_at"] = _auto_trader_state["last_run_at"]
                _auto_trader_state["last_summary"] = summary
                _auto_trader_state["last_error"] = ""
                _auto_trader_state["last_error_at"] = ""
                _auto_trader_state["latest_cycle_id"] = summary.get(
                    "cycle_id") or ""
                _auto_trader_state["next_run_at"] = _next_run_at(
                    int(cfg.get("interval_seconds") or 300))
                _auto_trader_state["optimized_params"] = _optimized_params_status(
                )
                _persist_auto_trader_state_locked()
        except Exception as exc:
            logger.warning("auto trader cycle 실패: {}", exc)
            notifier = get_notification_service()
            with _auto_trader_lock:
                _auto_trader_state["last_run_at"] = _now_iso()
                _auto_trader_state["last_error_at"] = _auto_trader_state["last_run_at"]
                _auto_trader_state["last_error"] = str(exc)
                _auto_trader_state["engine_state"] = "error"
                _auto_trader_state["running"] = False
                _persist_auto_trader_state_locked()
                notifier.notify_engine_error(
                    error=str(exc),
                    cycle_id=str(_auto_trader_state.get(
                        "latest_cycle_id") or ""),
                )
            append_engine_cycle({
                "ok": False,
                "cycle_id": str(_auto_trader_state.get("latest_cycle_id") or ""),
                "started_at": _now_iso(),
                "finished_at": _now_iso(),
                "error": str(exc),
            })
            stop_event.set()
            break
        interval = int((cfg.get("interval_seconds") or 300))
        interval = max(30, min(3600, interval))
        with _auto_trader_lock:
            _auto_trader_state["next_run_at"] = _next_run_at(interval)
            _persist_auto_trader_state_locked()
        stop_event.wait(interval)


def _start_auto_trader(config: dict) -> dict:
    global _auto_trader_stop_event, _auto_trader_thread
    _hydrate_auto_trader_state()
    with _auto_trader_lock:
        current_state = str(_auto_trader_state.get(
            "engine_state") or "stopped")
        if current_state in {"running", "paused"} and _auto_trader_thread and _auto_trader_thread.is_alive():
            return _build_status_payload(dict(_auto_trader_state), _get_paper_engine().get_account(refresh_quotes=False))
        merged = _default_auto_trader_config()
        merged.update(config or {})
        merged["interval_seconds"] = max(
            30, min(3600, int(merged.get("interval_seconds") or 300)))
        merged["max_positions_per_market"] = max(
            1, min(20, int(merged.get("max_positions_per_market") or 5)))
        merged["daily_buy_limit"] = max(
            1, min(200, int(merged.get("daily_buy_limit") or 20)))
        merged["daily_sell_limit"] = max(
            1, min(200, int(merged.get("daily_sell_limit") or 20)))
        merged["max_orders_per_symbol_per_day"] = max(
            1, min(10, int(merged.get("max_orders_per_symbol_per_day") or 1)))
        merged["min_score"] = max(
            0.0, min(100.0, float(merged.get("min_score") or 50.0)))
        merged["risk_per_trade_pct"] = max(
            0.05, min(5.0, float(merged.get("risk_per_trade_pct") or 0.35)))
        merged["daily_loss_limit_pct"] = max(
            0.1, min(20.0, float(merged.get("daily_loss_limit_pct") or 2.0)))
        merged["max_consecutive_loss"] = max(
            1, min(20, int(merged.get("max_consecutive_loss") or 3)))
        merged["cooldown_minutes"] = max(
            5, min(1440, int(merged.get("cooldown_minutes") or 120)))
        merged["max_symbol_weight_pct"] = max(
            1.0, min(100.0, float(merged.get("max_symbol_weight_pct") or 20.0)))
        merged["max_sector_weight_pct"] = max(
            1.0, min(100.0, float(merged.get("max_sector_weight_pct") or 35.0)))
        merged["max_market_exposure_pct"] = max(
            1.0, min(100.0, float(merged.get("max_market_exposure_pct") or 70.0)))
        merged["min_avg_volume"] = max(
            0.0, float(merged.get("min_avg_volume") or 100000))
        merged["min_avg_notional_krw"] = max(
            0.0, float(merged.get("min_avg_notional_krw") or 50000000))
        merged["slippage_bps_base"] = max(
            1.0, min(80.0, float(merged.get("slippage_bps_base") or 8.0)))
        merged["validation_gate_enabled"] = bool(
            merged.get("validation_gate_enabled", True))
        merged["validation_min_trades"] = max(
            0, min(200, int(merged.get("validation_min_trades") or 8)))
        merged["validation_min_sharpe"] = max(
            -5.0, min(10.0, float(merged.get("validation_min_sharpe") or 0.2)))
        merged["validation_block_on_low_reliability"] = bool(
            merged.get("validation_block_on_low_reliability", True))
        merged["validation_require_optimized_reliability"] = bool(
            merged.get("validation_require_optimized_reliability", True))
        merged.update(_parse_theme_gate_config(merged))
        markets = merged.get("markets") or ["KOSPI", "NASDAQ"]
        if not isinstance(markets, list):
            markets = ["KOSPI", "NASDAQ"]
        merged["markets"] = [
            m for m in markets if normalize_strategy_market(m) in {"KOSPI", "NASDAQ"}
        ] or ["KOSPI", "NASDAQ"]
        merged = _sync_primary_strategy_fields(merged)

        _auto_trader_stop_event = threading.Event()
        _auto_trader_thread = threading.Thread(
            target=_auto_trader_loop, args=(
                _auto_trader_stop_event,), daemon=True
        )
        _auto_trader_state["engine_state"] = "running"
        _auto_trader_state["running"] = True
        _auto_trader_state["started_at"] = _now_iso()
        _auto_trader_state["paused_at"] = ""
        _auto_trader_state["stopped_at"] = ""
        _auto_trader_state["next_run_at"] = _next_run_at(
            int(merged.get("interval_seconds") or 300))
        _auto_trader_state["current_config"] = merged
        _auto_trader_state["config"] = dict(merged)
        _auto_trader_state["validation_policy"] = {
            key: merged.get(key)
            for key in _default_validation_policy().keys()
        }
        _auto_trader_state["optimized_params"] = _optimized_params_status()
        _auto_trader_state["last_error"] = ""
        _auto_trader_state["last_error_at"] = ""
        _persist_auto_trader_state_locked()
        _auto_trader_thread.start()
        get_notification_service().notify_engine_started(merged)
        account = _get_paper_engine().get_account(refresh_quotes=False)
        return _build_status_payload(dict(_auto_trader_state), account)


def _stop_auto_trader() -> dict:
    global _auto_trader_stop_event, _auto_trader_thread
    _hydrate_auto_trader_state()
    with _auto_trader_lock:
        stop_event = _auto_trader_stop_event
        thread = _auto_trader_thread
        _auto_trader_state["engine_state"] = "stopped"
        _auto_trader_state["running"] = False
        _auto_trader_state["stopped_at"] = _now_iso()
        _auto_trader_state["next_run_at"] = ""
        _persist_auto_trader_state_locked()
    if stop_event:
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=2.0)
    with _auto_trader_lock:
        state = dict(_auto_trader_state)
    get_notification_service().notify_engine_stopped({"reason": "manual_stop"})
    return _build_status_payload(state, _get_paper_engine().get_account(refresh_quotes=False))


def _pause_auto_trader() -> dict:
    _hydrate_auto_trader_state()
    with _auto_trader_lock:
        if str(_auto_trader_state.get("engine_state") or "") != "running":
            return _build_status_payload(dict(_auto_trader_state), _get_paper_engine().get_account(refresh_quotes=False))
        _auto_trader_state["engine_state"] = "paused"
        _auto_trader_state["running"] = False
        _auto_trader_state["paused_at"] = _now_iso()
        _auto_trader_state["next_run_at"] = ""
        _persist_auto_trader_state_locked()
        state = dict(_auto_trader_state)
    get_notification_service().notify_engine_paused()
    return _build_status_payload(state, _get_paper_engine().get_account(refresh_quotes=False))


def _resume_auto_trader() -> dict:
    _hydrate_auto_trader_state()
    start_cfg: dict[str, Any] | None = None
    with _auto_trader_lock:
        if str(_auto_trader_state.get("engine_state") or "") == "running":
            return _build_status_payload(dict(_auto_trader_state), _get_paper_engine().get_account(refresh_quotes=False))
        if _auto_trader_thread is None or not _auto_trader_thread.is_alive():
            # 정지된 스레드는 재시작 시 start 흐름을 재사용한다.
            start_cfg = dict(_auto_trader_state.get(
                "current_config") or _default_auto_trader_config())
        else:
            _auto_trader_state["engine_state"] = "running"
            _auto_trader_state["running"] = True
            _auto_trader_state["paused_at"] = ""
            _auto_trader_state["next_run_at"] = _next_run_at(int(
                (_auto_trader_state.get("current_config") or {}).get("interval_seconds") or 300))
            _persist_auto_trader_state_locked()
            state = dict(_auto_trader_state)
    if start_cfg is not None:
        return _start_auto_trader(start_cfg)
    get_notification_service().notify_engine_resumed()
    return _build_status_payload(state, _get_paper_engine().get_account(refresh_quotes=False))


def _auto_trader_status() -> dict:
    _hydrate_auto_trader_state()
    with _auto_trader_lock:
        state = dict(_auto_trader_state)
    if not state.get("current_config"):
        state["current_config"] = _default_auto_trader_config()
    if str(state.get("engine_state") or "") in {"running", "paused"} and not (_auto_trader_thread and _auto_trader_thread.is_alive()):
        state["engine_state"] = "stopped"
        state["running"] = False
        with _auto_trader_lock:
            _auto_trader_state["engine_state"] = "stopped"
            _auto_trader_state["running"] = False
            _persist_auto_trader_state_locked()
    engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))
    account = engine.get_account(refresh_quotes=False)
    return _build_status_payload(state, account)


def apply_quant_candidate_runtime_config(candidate: dict[str, Any]) -> dict[str, Any]:
    _hydrate_auto_trader_state()
    with _auto_trader_lock:
        base_cfg = dict(_auto_trader_state.get("current_config")
                        or _default_auto_trader_config())
        merged = _apply_quant_candidate_patch(base_cfg, candidate)
        _auto_trader_state["current_config"] = merged
        _auto_trader_state["config"] = dict(merged)
        _auto_trader_state["validation_policy"] = {
            key: merged.get(key)
            for key in _default_validation_policy().keys()
        }
        _auto_trader_state["optimized_params"] = _optimized_params_status()
        _persist_auto_trader_state_locked()
        state = dict(_auto_trader_state)
    account = _get_paper_engine().get_account(refresh_quotes=False)
    return _build_status_payload(state, account)


def handle_paper_account(refresh_quotes: bool) -> tuple[int, dict]:
    try:
        engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))
        return 200, engine.get_account(refresh_quotes=refresh_quotes)
    except Exception as exc:
        return 500, {"error": str(exc)}


def handle_paper_order(payload: dict) -> tuple[int, dict]:
    try:
        _hydrate_auto_trader_state()
        side = str(payload.get("side") or "").strip().lower()
        code = str(payload.get("code") or "").strip().upper()
        market = str(payload.get("market") or "").strip().upper()
        try:
            quantity = int(payload.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0
        order_type = str(payload.get("order_type") or "market").strip().lower()
        limit_price_raw = payload.get("limit_price")
        try:
            limit_price = float(limit_price_raw) if limit_price_raw not in (
                None, "") else None
        except (TypeError, ValueError):
            limit_price = None
        engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))
        result = engine.place_order(
            side=side,
            code=code,
            market=market,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        if result.get("ok"):
            event = result.get("event") or {}
            _record_execution_order({
                "timestamp": event.get("ts") or _now_iso(),
                "success": True,
                "side": side,
                "code": code,
                "market": market,
                "quantity": event.get("quantity"),
                "order_type": order_type,
                "submitted_at": _now_iso(),
                "filled_at": event.get("ts"),
                "filled_price_local": event.get("filled_price_local"),
                "filled_price_krw": event.get("filled_price_krw"),
                "notional_krw": event.get("notional_krw"),
                "failure_reason": "",
                "reason_code": "",
                "message": "",
                "originating_cycle_id": "",
                "originating_signal_key": f"{market}:{code}",
                "quote_source": event.get("quote_source"),
                "quote_fetched_at": event.get("quote_fetched_at"),
                "quote_is_stale": event.get("quote_is_stale"),
            })
            account = result.get("account") if isinstance(result.get(
                "account"), dict) else engine.get_account(refresh_quotes=False)
            unrealized = sum(
                _to_float(item.get("unrealized_pnl_krw"), 0.0)
                for item in account.get("positions", [])
                if isinstance(item, dict)
            )
            append_account_snapshot({
                "timestamp": _now_iso(),
                "cycle_id": "",
                "cash_krw": account.get("cash_krw"),
                "cash_usd": account.get("cash_usd"),
                "equity_krw": account.get("equity_krw"),
                "realized_pnl_today": _today_realized_pnl(account),
                "unrealized_pnl": round(unrealized, 2),
                "open_positions_count": len(account.get("positions", [])),
                "total_orders_today": _today_order_counts(account).get("buy", 0) + _today_order_counts(account).get("sell", 0),
                "days_left": account.get("days_left"),
                "engine_state": _auto_trader_state.get("engine_state"),
            })
        else:
            reason = str(result.get("error") or "order_failed")
            _record_execution_order({
                "timestamp": _now_iso(),
                "success": False,
                "side": side,
                "code": code,
                "market": market,
                "quantity": quantity,
                "order_type": order_type,
                "submitted_at": _now_iso(),
                "filled_at": "",
                "filled_price_local": None,
                "filled_price_krw": None,
                "notional_krw": None,
                "failure_reason": reason,
                "reason_code": reason,
                "message": reason,
                "originating_cycle_id": "",
                "originating_signal_key": f"{market}:{code}",
            })
            get_notification_service().notify_order_failure({
                "code": code,
                "market": market,
                "side": side,
                "failure_reason": reason,
                "originating_cycle_id": "",
            })
        status = 200 if result.get("ok") else 400
        return status, result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_reset(payload: dict) -> tuple[int, dict]:
    try:
        _hydrate_auto_trader_state()
        initial_cash_krw_raw = payload.get("initial_cash_krw")
        initial_cash_usd_raw = payload.get("initial_cash_usd")
        paper_days_raw = payload.get("paper_days")
        seed_positions = _parse_seed_positions(payload.get("seed_positions"))
        initial_cash_krw = float(
            initial_cash_krw_raw) if initial_cash_krw_raw not in (None, "") else None
        initial_cash_usd = float(
            initial_cash_usd_raw) if initial_cash_usd_raw not in (None, "") else None
        paper_days = int(paper_days_raw) if paper_days_raw not in (
            None, "") else None
        engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))
        account = engine.reset(
            initial_cash_krw=initial_cash_krw,
            initial_cash_usd=initial_cash_usd,
            paper_days=paper_days,
            seed_positions=seed_positions,
        )
        _append_paper_reset_snapshot(account)
        return 200, {
            "ok": True,
            "account": account,
        }
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_auto_invest(payload: dict) -> tuple[int, dict]:
    try:
        market = str(payload.get("market") or "NASDAQ").strip().upper()
        try:
            max_positions_raw = payload.get("max_positions")
            max_positions = int(5 if max_positions_raw in (
                None, "") else max_positions_raw)
        except (TypeError, ValueError):
            max_positions = 5
        try:
            min_score_raw = payload.get("min_score")
            min_score = float(50.0 if min_score_raw in (
                None, "") else min_score_raw)
        except (TypeError, ValueError):
            min_score = 50.0
        include_neutral = bool(payload.get("include_neutral") is True)
        theme_cfg = _parse_theme_gate_config(payload)
        max_positions = max(1, min(20, max_positions))
        min_score = max(0.0, min(100.0, min_score))
        result = _auto_invest_picks(
            market=market,
            max_positions=max_positions,
            min_score=min_score,
            include_neutral=include_neutral,
            theme_gate_enabled=theme_cfg["theme_gate_enabled"],
            theme_min_score=theme_cfg["theme_min_score"],
            theme_min_news=theme_cfg["theme_min_news"],
            theme_priority_bonus=theme_cfg["theme_priority_bonus"],
            theme_focus=theme_cfg["theme_focus"],
        )
        status = 200 if result.get("ok") else 400
        return status, result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_engine_start(payload: dict) -> tuple[int, dict]:
    try:
        return 200, _start_auto_trader(payload)
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_engine_stop() -> tuple[int, dict]:
    try:
        return 200, _stop_auto_trader()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_engine_pause() -> tuple[int, dict]:
    try:
        return 200, _pause_auto_trader()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_engine_resume() -> tuple[int, dict]:
    try:
        return 200, _resume_auto_trader()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_engine_status() -> tuple[int, dict]:
    try:
        return 200, _auto_trader_status()
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_engine_cycles(limit: int = 50) -> tuple[int, dict]:
    try:
        rows = read_engine_cycles(limit=limit)
        return 200, {"ok": True, "cycles": rows, "count": len(rows)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_order_events(limit: int = 100) -> tuple[int, dict]:
    try:
        rows = [enrich_order_payload(item) for item in read_order_events(limit=limit)]
        execution_events = read_execution_events(limit=limit * 4)
        return 200, {
            "ok": True,
            "orders": rows,
            "execution_events": execution_events,
            "execution_summary": summarize_execution_events(execution_events),
            "count": len(rows),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_account_history(limit: int = 100) -> tuple[int, dict]:
    try:
        rows = read_account_snapshots(limit=limit)
        return 200, {"ok": True, "history": rows, "count": len(rows)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def _coerce_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "t", "yes", "on"}
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return bool(raw)
    return bool(raw) if raw != "" else default


def _coerce_optional_float(raw: object) -> float | None:
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value


def _coerce_optional_int(raw: object) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value


def _append_paper_reset_snapshot(account: dict[str, Any]) -> None:
    append_account_snapshot({
        "timestamp": _now_iso(),
        "cycle_id": "",
        "cash_krw": account.get("cash_krw"),
        "cash_usd": account.get("cash_usd"),
        "equity_krw": account.get("equity_krw"),
        "realized_pnl_today": _today_realized_pnl(account),
        "unrealized_pnl": 0.0,
        "open_positions_count": len(account.get("positions", [])),
        "total_orders_today": _today_order_counts(account).get("buy", 0) + _today_order_counts(account).get("sell", 0),
        "days_left": account.get("days_left"),
        "engine_state": _auto_trader_state.get("engine_state"),
    })


def handle_paper_history_clear(payload: dict) -> tuple[int, dict]:
    try:
        clear_all = _coerce_bool(payload.get("clear_all"), True)
        clear_orders = clear_all or _coerce_bool(payload.get("clear_orders"), False)
        clear_signals = clear_all or _coerce_bool(payload.get("clear_signals"), False)
        clear_accounts = clear_all or _coerce_bool(payload.get("clear_accounts"), False)
        clear_cycles = clear_all or _coerce_bool(payload.get("clear_cycles"), False)
        reset_account = (
            _coerce_bool(payload.get("reset_account"), False)
            or _coerce_bool(payload.get("clear_account_state"), False)
            or _coerce_bool(payload.get("hard_reset"), False)
        )
        if reset_account:
            clear_accounts = True

        if reset_account:
            _hydrate_auto_trader_state()
            engine = get_execution_engine(os.getenv("EXECUTION_MODE", "paper"))

        removed_orders = clear_order_events() if clear_orders else 0
        removed_execution_events = clear_execution_events() if clear_orders else 0
        removed_signals = clear_signal_snapshots() if clear_signals else 0
        removed_accounts = clear_account_snapshots() if clear_accounts else 0
        removed_cycles = clear_engine_cycles() if clear_cycles else 0
        reset_account_data: dict[str, Any] | None = None
        if reset_account:
            account = engine.reset(
                initial_cash_krw=_coerce_optional_float(payload.get("initial_cash_krw")),
                initial_cash_usd=_coerce_optional_float(payload.get("initial_cash_usd")),
                paper_days=_coerce_optional_int(payload.get("paper_days")),
                seed_positions=_parse_seed_positions(payload.get("seed_positions")),
            )
            _append_paper_reset_snapshot(account)
            reset_account_data = account

        return 200, {
            "ok": True,
            "account_reset": reset_account,
            "clear_count": {
                "order_events": removed_orders,
                "execution_events": removed_execution_events,
                "signal_snapshots": removed_signals,
                "account_snapshots": removed_accounts,
                "engine_cycles": removed_cycles,
            },
            **({"account": reset_account_data} if reset_account_data is not None else {}),
        }
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_signal_snapshots(limit: int = 200) -> tuple[int, dict]:
    try:
        rows = [enrich_signal_payload(item) for item in read_signal_snapshots(limit=limit)]
        return 200, {"ok": True, "snapshots": rows, "count": len(rows)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_workflow(limit: int = 120) -> tuple[int, dict]:
    try:
        signals = read_signal_snapshots(limit=limit)
        orders = read_order_events(limit=limit)
        summary = build_workflow_summary(signals, orders)
        execution_events = read_execution_events(limit=limit * 4)
        return 200, {
            "ok": True,
            "workflow": summary,
            "execution_lifecycle": summarize_execution_events(execution_events),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


class ExecutionService:
    def paper_account(self, refresh_quotes: bool) -> tuple[int, dict]:
        return handle_paper_account(refresh_quotes)

    def paper_order(self, payload: dict) -> tuple[int, dict]:
        return handle_paper_order(payload)

    def paper_reset(self, payload: dict) -> tuple[int, dict]:
        return handle_paper_reset(payload)

    def paper_auto_invest(self, payload: dict) -> tuple[int, dict]:
        return handle_paper_auto_invest(payload)

    def paper_engine_start(self, payload: dict) -> tuple[int, dict]:
        return handle_paper_engine_start(payload)

    def paper_engine_stop(self) -> tuple[int, dict]:
        return handle_paper_engine_stop()

    def paper_engine_pause(self) -> tuple[int, dict]:
        return handle_paper_engine_pause()

    def paper_engine_resume(self) -> tuple[int, dict]:
        return handle_paper_engine_resume()

    def paper_engine_status(self) -> tuple[int, dict]:
        return handle_paper_engine_status()

    def paper_engine_cycles(self, limit: int = 50) -> tuple[int, dict]:
        return handle_paper_engine_cycles(limit)

    def paper_orders(self, limit: int = 100) -> tuple[int, dict]:
        return handle_paper_order_events(limit)

    def paper_account_history(self, limit: int = 100) -> tuple[int, dict]:
        return handle_paper_account_history(limit)

    def paper_history_clear(self, payload: dict) -> tuple[int, dict]:
        return handle_paper_history_clear(payload)

    def signal_snapshots(self, limit: int = 200) -> tuple[int, dict]:
        return handle_signal_snapshots(limit)

    def paper_workflow(self, limit: int = 120) -> tuple[int, dict]:
        return handle_paper_workflow(limit)


_execution_service: ExecutionService | None = None


def get_execution_service() -> ExecutionService:
    global _execution_service
    if _execution_service is None:
        _execution_service = ExecutionService()
    _hydrate_auto_trader_state()
    return _execution_service
