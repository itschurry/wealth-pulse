import datetime
import json
import os
import threading
from pathlib import Path

from api.helpers import (
    _KST,
    _SUPPORTED_AUTO_TRADE_MARKETS,
    _now_iso,
    _send_paper_trade_notification,
)
from api.routes.market import _paper_fx_rate, _resolve_stock_quote
from api.routes.watchlist import _compute_technical_snapshot
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
from services.signal_service import (
    collect_pick_candidates as _signal_collect_pick_candidates,
    normalize_theme_focus as _signal_normalize_theme_focus,
    parse_theme_gate_config as _signal_parse_theme_gate_config,
)
from services.strategy_engine import select_entry_candidates

_DEFAULT_THEME_FOCUS = ["automotive", "robotics", "physical_ai"]
_ALLOWED_THEME_FOCUS = set(_DEFAULT_THEME_FOCUS)

_OPTIMIZED_PARAMS_PATH = Path(
    __file__).resolve().parent.parent / "config" / "optimized_params.json"
_OPTIMIZED_PARAMS_MAX_AGE_DAYS = 30

_paper_engine: PaperExecutionEngine | None = None
_auto_trader_lock = threading.Lock()
_auto_trader_stop_event: threading.Event | None = None
_auto_trader_thread: threading.Thread | None = None
_auto_trader_state: dict = {
    "running": False,
    "started_at": "",
    "last_run_at": "",
    "last_error": "",
    "last_summary": {},
    "config": {},
}


def _load_optimized_params() -> dict | None:
    """config/optimized_params.json을 읽어 반환한다.
    파일이 없거나 30일 이상 오래된 경우 None 반환.
    """
    if not _OPTIMIZED_PARAMS_PATH.exists():
        return None
    try:
        data = json.loads(_OPTIMIZED_PARAMS_PATH.read_text(encoding="utf-8"))
        optimized_at = datetime.datetime.fromisoformat(
            data.get("optimized_at", "2000-01-01"))
        age_days = (datetime.datetime.now(datetime.timezone.utc)
                    - optimized_at.astimezone(datetime.timezone.utc)).days
        if age_days > _OPTIMIZED_PARAMS_MAX_AGE_DAYS:
            from loguru import logger
            logger.warning("최적화 파라미터가 {}일 지났습니다. 재실행 권장.", age_days)
        return data
    except Exception as exc:
        from loguru import logger
        logger.warning("optimized_params.json 로드 실패: {}", exc)
        return None


def _get_symbol_optimized_params(code: str) -> dict:
    """per_symbol에서 해당 종목의 신뢰할 수 있는 파라미터를 반환한다. 없으면 빈 dict."""
    optimized = _load_optimized_params()
    if not optimized:
        return {}
    symbol_data = optimized.get("per_symbol", {}).get(code, {})
    if not symbol_data.get("is_reliable", False):
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
                order_notifier=_send_paper_trade_notification,
            ),
            quote_provider=_resolve_stock_quote,
            fx_provider=_paper_fx_rate,
        )
    return _paper_engine


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
        "min_avg_volume": 100000,
        "min_avg_notional_krw": 50000000,
        "slippage_bps_base": 8.0,
        "market_profiles": profiles,
    }
    # 몬테카를로 최적화 결과 오버레이
    optimized = _load_optimized_params()
    if optimized:
        global_params = optimized.get("global_params", {})
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
        for key in _OPTIMIZABLE_KEYS:
            if key in global_params and global_params[key] is not None:
                base[key] = global_params[key]
                for market_key in ("KOSPI", "NASDAQ"):
                    if market_key in base["market_profiles"]:
                        base["market_profiles"][market_key][key] = global_params[key]
        from loguru import logger
        logger.info("몬테카를로 최적 파라미터 적용: {}", global_params)
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


def _should_enter_by_indicators(technicals: dict, cfg: dict, market: str) -> bool:
    if not isinstance(technicals, dict):
        return False
    return should_enter_from_snapshot(technicals, _auto_trader_profile(cfg, market))


def _should_exit_by_indicators(position: dict, technicals: dict, cfg: dict, market: str) -> str | None:
    if not isinstance(technicals, dict):
        return None
    code = str(position.get("code") or "").upper()
    symbol_params = _get_symbol_optimized_params(code)
    effective_cfg = {**cfg, **symbol_params} if symbol_params else cfg
    return should_exit_from_snapshot(
        technicals,
        entry_price=float(position.get("avg_price_local") or 0.0) or None,
        holding_days=_position_holding_days(position),
        profile=_auto_trader_profile(effective_cfg, market),
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

    engine = _get_paper_engine()
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
            skipped.append({"code": item.get("code"), "reason": "max_positions"})
            continue

        code = str(item.get("code") or "").upper()
        if code in held_codes:
            skipped.append({"code": code, "reason": "already_holding"})
            continue

        size_recommendation = item.get("size_recommendation") if isinstance(item.get("size_recommendation"), dict) else {}
        quantity = int(size_recommendation.get("quantity") or 0)
        if quantity <= 0:
            skipped.append({"code": code, "reason": size_recommendation.get("reason") or "size_zero"})
            continue

        risk_inputs = item.get("risk_inputs") if isinstance(item.get("risk_inputs"), dict) else {}
        stop_loss_pct = risk_inputs.get("stop_loss_pct")

        order_result = engine.place_order(
            side="buy",
            code=code,
            market=target_market,
            quantity=quantity,
            order_type="market",
            limit_price=None,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=None,
        )
        if not order_result.get("ok"):
            skipped.append({"code": code, "reason": order_result.get("error") or "order_failed"})
            continue

        event = order_result.get("event") or {}
        ev_metrics = item.get("ev_metrics") if isinstance(item.get("ev_metrics"), dict) else {}
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
    engine = _get_paper_engine()
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
    closed_markets: list[str] = []
    markets = [m for m in cfg.get("markets", ["KOSPI", "NASDAQ"]) if m in {
        "KOSPI", "NASDAQ"}]
    candidate_counts_by_market: dict[str, int] = {
        market: 0 for market in markets}

    _MARKET_TO_CALENDAR = {"KOSPI": "KR", "NASDAQ": "US"}

    for market in markets:
        calendar_market = _MARKET_TO_CALENDAR.get(market, market)
        if not is_market_open(calendar_market):
            closed_markets.append(market)
            candidate_counts_by_market[market] = 0
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
                orders = (result.get("account") or {}).get("orders", orders)
            else:
                skipped.append({"code": code, "market": market,
                               "reason": result.get("error") or "sell_failed"})

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
            continue
        buy_count = _count_orders(market, "buy")
        entry_candidates = select_entry_candidates(
            market=market,
            cfg=cfg,
            account=account,
            max_count=max(20, slots * 6),
        )
        candidate_counts_by_market[market] = len(entry_candidates)
        for candidate in entry_candidates:
            if slots <= 0 or buy_count >= daily_buy_limit:
                break
            code = str(candidate.get("code") or "").upper()
            cand_name = str(candidate.get("name") or code)
            if not code or code in held_codes:
                continue
            if _symbol_order_count(market, "buy", code) >= max_orders_per_symbol:
                continue

            size_recommendation = candidate.get("size_recommendation") if isinstance(candidate.get("size_recommendation"), dict) else {}
            quantity = int(size_recommendation.get("quantity") or 0)
            if quantity <= 0:
                skipped.append({
                    "code": code,
                    "name": cand_name,
                    "market": market,
                    "reason": size_recommendation.get("reason") or "size_zero",
                })
                continue

            risk_inputs = candidate.get("risk_inputs") if isinstance(candidate.get("risk_inputs"), dict) else {}
            stop_loss_pct = risk_inputs.get("stop_loss_pct")

            result = engine.place_order(
                side="buy",
                code=code,
                market=market,
                quantity=quantity,
                order_type="market",
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=None,
            )
            if result.get("ok"):
                buy_count += 1
                slots -= 1
                held_codes.add(code)
                event = result.get("event") or {}
                ev_metrics = candidate.get("ev_metrics") if isinstance(candidate.get("ev_metrics"), dict) else {}
                executed_buys.append({
                    "code": code,
                    "name": cand_name,
                    "market": market,
                    "strategy_type": candidate.get("strategy_type"),
                    "expected_value": ev_metrics.get("expected_value"),
                    "quantity": event.get("quantity"),
                    "filled_price_local": event.get("filled_price_local"),
                })
                orders = (result.get("account") or {}).get("orders", orders)
            else:
                skipped.append({"code": code, "name": cand_name, "market": market,
                               "reason": result.get("error") or "buy_failed"})

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
            "skipped_count": sum(
                1 for item in skipped
                if str(item.get("market") or "").upper() == market
            ),
        }

    final_account = engine.get_account(refresh_quotes=True)
    return {
        "ok": True,
        "ran_at": _now_iso(),
        "executed_buy_count": len(executed_buys),
        "executed_sell_count": len(executed_sells),
        "executed_buys": executed_buys,
        "executed_sells": executed_sells,
        "candidate_counts_by_market": candidate_counts_by_market,
        "skip_reason_counts": skip_reason_counts,
        "market_stats": market_stats,
        "closed_markets": closed_markets,
        "skipped": skipped[:50],
        "account": final_account,
    }


def _auto_trader_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        with _auto_trader_lock:
            cfg = dict(_auto_trader_state.get(
                "config") or _default_auto_trader_config())
        try:
            summary = _run_auto_trader_cycle(cfg)
            with _auto_trader_lock:
                _auto_trader_state["last_run_at"] = _now_iso()
                _auto_trader_state["last_summary"] = summary
                _auto_trader_state["last_error"] = ""
        except Exception as exc:
            with _auto_trader_lock:
                _auto_trader_state["last_run_at"] = _now_iso()
                _auto_trader_state["last_error"] = str(exc)
                if "기간이 종료" in str(exc):
                    _auto_trader_state["running"] = False
                    stop_event.set()
                    break
        interval = int((cfg.get("interval_seconds") or 300))
        interval = max(30, min(3600, interval))
        stop_event.wait(interval)


def _start_auto_trader(config: dict) -> dict:
    global _auto_trader_stop_event, _auto_trader_thread
    with _auto_trader_lock:
        if (
            _auto_trader_state.get("running")
            and _auto_trader_thread
            and _auto_trader_thread.is_alive()
        ):
            return {"ok": True, "running": True, "message": "이미 실행 중입니다.", "state": dict(_auto_trader_state)}
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
        _auto_trader_state["running"] = True
        _auto_trader_state["started_at"] = _now_iso()
        _auto_trader_state["config"] = merged
        _auto_trader_state["last_error"] = ""
        _auto_trader_thread.start()
        return {"ok": True, "running": True, "state": dict(_auto_trader_state)}


def _stop_auto_trader() -> dict:
    global _auto_trader_stop_event, _auto_trader_thread
    with _auto_trader_lock:
        stop_event = _auto_trader_stop_event
        thread = _auto_trader_thread
        _auto_trader_state["running"] = False
    if stop_event:
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=2.0)
    with _auto_trader_lock:
        return {"ok": True, "running": False, "state": dict(_auto_trader_state)}


def _auto_trader_status() -> dict:
    with _auto_trader_lock:
        state = dict(_auto_trader_state)
    if not state.get("config"):
        state["config"] = _default_auto_trader_config()
    if state.get("running") and not (_auto_trader_thread and _auto_trader_thread.is_alive()):
        state["running"] = False
        with _auto_trader_lock:
            _auto_trader_state["running"] = False
    engine = _get_paper_engine()
    account = engine.get_account(refresh_quotes=False)
    return {"ok": True, "state": state, "account": account}


def handle_paper_account(refresh_quotes: bool) -> tuple[int, dict]:
    try:
        engine = _get_paper_engine()
        return 200, engine.get_account(refresh_quotes=refresh_quotes)
    except Exception as exc:
        return 500, {"error": str(exc)}


def handle_paper_order(payload: dict) -> tuple[int, dict]:
    try:
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
        engine = _get_paper_engine()
        result = engine.place_order(
            side=side,
            code=code,
            market=market,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        status = 200 if result.get("ok") else 400
        return status, result
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_reset(payload: dict) -> tuple[int, dict]:
    try:
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
        engine = _get_paper_engine()
        return 200, {
            "ok": True,
            "account": engine.reset(
                initial_cash_krw=initial_cash_krw,
                initial_cash_usd=initial_cash_usd,
                paper_days=paper_days,
                seed_positions=seed_positions,
            ),
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


def handle_paper_engine_status() -> tuple[int, dict]:
    try:
        return 200, _auto_trader_status()
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

    def paper_engine_status(self) -> tuple[int, dict]:
        return handle_paper_engine_status()


_execution_service: ExecutionService | None = None


def get_execution_service() -> ExecutionService:
    global _execution_service
    if _execution_service is None:
        _execution_service = ExecutionService()
    return _execution_service
