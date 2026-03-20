import datetime
import os
import threading
from pathlib import Path

import api.cache as _cache
from api.helpers import (
    _KST,
    _SUPPORTED_AUTO_TRADE_MARKETS,
    _get_kis_client,
    _now_iso,
    _send_paper_trade_notification,
)
from api.routes.market import _paper_fx_rate, _resolve_stock_quote
from api.routes.reports import _get_recommendations, _get_today_picks
from api.routes.watchlist import _compute_technical_snapshot
from analyzer.candidate_selector import (
    normalize_candidate_selection_config,
    select_market_candidates,
    serialize_candidate_selection_config,
)
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
from config.settings import LOGS_DIR
from market_utils import normalize_market, resolve_market

_DEFAULT_THEME_FOCUS = ["automotive", "robotics", "physical_ai"]
_ALLOWED_THEME_FOCUS = set(_DEFAULT_THEME_FOCUS)


def _get_paper_engine() -> PaperExecutionEngine:
    if _cache._paper_engine is None:
        state_path = Path(os.getenv("PAPER_TRADING_STATE_PATH", str(LOGS_DIR / "paper_account_state.json")))
        _cache._paper_engine = PaperExecutionEngine(
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
    return _cache._paper_engine


def _normalize_pick_market(market: str) -> str:
    return normalize_market(market)


def _infer_pick_market(code: str, market: str, name: str = "") -> str:
    return resolve_market(code=code, name=name, market=market, scope="core")


def _normalize_theme_focus(raw) -> list[str]:
    if not isinstance(raw, list):
        return list(_DEFAULT_THEME_FOCUS)
    normalized: list[str] = []
    for item in raw:
        key = str(item or "").strip().lower()
        if key in _ALLOWED_THEME_FOCUS and key not in normalized:
            normalized.append(key)
    return normalized or list(_DEFAULT_THEME_FOCUS)


def _parse_theme_gate_config(raw: dict | None = None) -> dict:
    payload = raw or {}
    try:
        min_score = float(payload.get("theme_min_score", 2.5))
    except (TypeError, ValueError):
        min_score = 2.5
    try:
        min_news = int(payload.get("theme_min_news", 1))
    except (TypeError, ValueError):
        min_news = 1
    try:
        priority_bonus = float(payload.get("theme_priority_bonus", 2.0))
    except (TypeError, ValueError):
        priority_bonus = 2.0
    return {
        "theme_gate_enabled": bool(payload.get("theme_gate_enabled", True)),
        "theme_min_score": max(0.0, min(30.0, min_score)),
        "theme_min_news": max(0, min(10, min_news)),
        "theme_priority_bonus": max(0.0, min(10.0, priority_bonus)),
        "theme_focus": _normalize_theme_focus(payload.get("theme_focus")),
    }


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
    return {
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
        "market_profiles": profiles,
    }


def _today_kst_str() -> str:
    return datetime.datetime.now(_KST).date().isoformat()


def _order_day(ts: str) -> str:
    try:
        return datetime.datetime.fromisoformat(ts).astimezone(_KST).date().isoformat()
    except Exception:
        return ""


def _position_holding_days(position: dict) -> int:
    entry_ts = str(position.get("entry_ts") or position.get("updated_at") or "")
    try:
        entry_date = datetime.datetime.fromisoformat(entry_ts).astimezone(_KST).date()
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
                profile_from_mapping(market, payload if isinstance(payload, dict) else {})
            ])[normalize_strategy_market(market)]
            for market, payload in raw_profiles.items()
            if normalize_strategy_market(market) in {"KOSPI", "NASDAQ"}
        }
        for market in selected_markets:
            profile_map.setdefault(
                market,
                serialize_strategy_profiles([default_strategy_profile(market)])[market],
            )
        return profile_map

    overrides: dict[str, object] = {}
    if "max_positions_per_market" in cfg:
        overrides["max_positions"] = int(cfg.get("max_positions_per_market") or 5)
    for key in ("max_holding_days", "rsi_min", "rsi_max", "volume_ratio_min", "signal_interval", "signal_range"):
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
    cfg["max_positions_per_market"] = int(primary.get("max_positions") or cfg.get("max_positions_per_market") or 5)
    cfg["signal_interval"] = str(primary.get("signal_interval") or "1d")
    cfg["signal_range"] = str(primary.get("signal_range") or "6mo")
    cfg["rsi_min"] = float(primary.get("rsi_min") or 45.0)
    cfg["rsi_max"] = float(primary.get("rsi_max") or 68.0)
    cfg["volume_ratio_min"] = float(primary.get("volume_ratio_min") or 1.2)
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
    return should_exit_from_snapshot(
        technicals,
        entry_price=float(position.get("avg_price_local") or 0.0) or None,
        holding_days=_position_holding_days(position),
        profile=_auto_trader_profile(cfg, market),
    )


def _collect_pick_candidates(market: str, cfg: dict) -> list[dict]:
    candidate_cfg = normalize_candidate_selection_config(
        {
            "min_score": cfg.get("min_score", 50.0),
            "include_neutral": cfg.get("include_neutral", True),
            **_parse_theme_gate_config(cfg),
        }
    )
    return select_market_candidates(
        market=market,
        cfg=candidate_cfg,
        today_picks=_get_today_picks(),
        recommendations=_get_recommendations(),
    )


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

    filter_cfg = {
        "min_score": min_score,
        "include_neutral": include_neutral,
        "theme_gate_enabled": theme_gate_enabled,
        "theme_min_score": theme_min_score,
        "theme_min_news": theme_min_news,
        "theme_priority_bonus": theme_priority_bonus,
        "theme_focus": theme_focus or list(_DEFAULT_THEME_FOCUS),
    }
    candidates = _collect_pick_candidates(target_market, filter_cfg)
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
            "skipped": [{"code": item.get("code"), "reason": "max_positions"} for item in candidates],
            "account": account,
        }

    available_cash = (
        float(account.get("cash_usd") or 0.0) if target_market == "NASDAQ"
        else float(account.get("cash_krw") or 0.0)
    )
    executed = []
    skipped = []
    remaining_slots = slots

    for item in candidates:
        if remaining_slots <= 0:
            skipped.append({"code": item.get("code"), "reason": "max_positions"})
            continue
        code = str(item.get("code") or "").upper()
        if code in held_codes:
            skipped.append({"code": code, "reason": "already_holding"})
            continue

        try:
            quote = _resolve_stock_quote(code, target_market)
            quote_price = float(quote.get("price") or 0.0)
        except Exception as exc:
            skipped.append({"code": code, "reason": f"quote_error: {exc}"})
            continue
        if quote_price <= 0:
            skipped.append({"code": code, "reason": "invalid_quote"})
            continue

        fx_rate = (_paper_fx_rate() or 1300.0) if target_market == "NASDAQ" else 1.0
        unit_price = quote_price if target_market == "NASDAQ" else (quote_price * fx_rate)
        budget_per_slot = available_cash / max(remaining_slots, 1)
        quantity = int((budget_per_slot * 0.995) // unit_price)
        if quantity <= 0:
            skipped.append({"code": code, "reason": "insufficient_cash"})
            continue

        order_result = engine.place_order(
            side="buy",
            code=code,
            market=target_market,
            quantity=quantity,
            order_type="market",
            limit_price=None,
        )
        if not order_result.get("ok"):
            skipped.append({"code": code, "reason": order_result.get("error") or "order_failed"})
            continue

        event = order_result.get("event") or {}
        executed.append({
            "code": code,
            "name": item.get("name"),
            "score": item.get("score"),
            "quantity": event.get("quantity"),
            "filled_price_local": event.get("filled_price_local"),
            "filled_price_krw": event.get("filled_price_krw"),
            "notional_krw": event.get("notional_krw"),
        })
        held_codes.add(code)
        remaining_slots -= 1
        refreshed = order_result.get("account") or {}
        available_cash = (
            float(refreshed.get("cash_usd") or available_cash)
            if target_market == "NASDAQ"
            else float(refreshed.get("cash_krw") or available_cash)
        )

    final_account = engine.get_account(refresh_quotes=True)
    message = ""
    if not candidates:
        message = "조건에 맞는 자동매수 후보가 없습니다. (점수 우선 + 테마 가점 모드) min_score 또는 데이터 갱신 상태를 확인해 보세요."
    return {
        "ok": True,
        "strategy": "today-picks-auto-buy-v1",
        "market": target_market,
        "max_positions": int(max_positions),
        "min_score": float(min_score),
        "executed": executed,
        "skipped": skipped,
        "candidate_count": len(candidates),
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

        return None, primary_error

    executed_buys: list[dict] = []
    executed_sells: list[dict] = []
    skipped: list[dict] = []
    markets = [m for m in cfg.get("markets", ["KOSPI", "NASDAQ"]) if m in {"KOSPI", "NASDAQ"}]
    candidate_counts_by_market: dict[str, int] = {market: 0 for market in markets}

    for market in markets:
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
            if _symbol_order_count(market, "sell", code) >= max_orders_per_symbol:
                continue
            technicals, tech_error = _load_technicals(code, market)
            if tech_error:
                skipped.append({"code": code, "market": market, "reason": f"technicals_error: {tech_error}"})
                continue
            if not technicals:
                continue
            reason = _should_exit_by_indicators(position, technicals, cfg, market)
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
                executed_sells.append({"code": code, "market": market, "reason": reason, "quantity": event.get("quantity")})
                orders = (result.get("account") or {}).get("orders", orders)
            else:
                skipped.append({"code": code, "market": market, "reason": result.get("error") or "sell_failed"})

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
        candidates = _collect_pick_candidates(market=market, cfg=cfg)
        candidate_counts_by_market[market] = len(candidates)
        for candidate in candidates:
            if slots <= 0 or buy_count >= daily_buy_limit:
                break
            code = str(candidate.get("code") or "").upper()
            if not code or code in held_codes:
                continue
            if _symbol_order_count(market, "buy", code) >= max_orders_per_symbol:
                continue
            technicals, tech_error = _load_technicals(code, market)
            if tech_error:
                skipped.append({"code": code, "market": market, "reason": f"technicals_error: {tech_error}"})
                continue
            if not technicals:
                skipped.append({"code": code, "market": market, "reason": "technicals_unavailable"})
                continue
            if not _should_enter_by_indicators(technicals, cfg, market):
                skipped.append({"code": code, "market": market, "reason": "entry_signal_not_matched"})
                continue
            quote = _resolve_stock_quote(code, market)
            price_local = float(quote.get("price") or 0.0)
            if price_local <= 0:
                skipped.append({"code": code, "market": market, "reason": "invalid_quote"})
                continue
            account = engine.get_account(refresh_quotes=False)
            available_cash = (
                float(account.get("cash_usd") or 0.0) if market == "NASDAQ"
                else float(account.get("cash_krw") or 0.0)
            )
            budget_per_slot = available_cash / max(slots, 1)
            quantity = int((budget_per_slot * 0.995) // price_local)
            if quantity <= 0:
                skipped.append({"code": code, "market": market, "reason": "insufficient_cash"})
                continue
            result = engine.place_order(
                side="buy",
                code=code,
                market=market,
                quantity=quantity,
                order_type="market",
            )
            if result.get("ok"):
                buy_count += 1
                slots -= 1
                held_codes.add(code)
                event = result.get("event") or {}
                executed_buys.append({
                    "code": code,
                    "market": market,
                    "quantity": event.get("quantity"),
                    "filled_price_local": event.get("filled_price_local"),
                })
                orders = (result.get("account") or {}).get("orders", orders)
            else:
                skipped.append({"code": code, "market": market, "reason": result.get("error") or "buy_failed"})

    skip_reason_counts: dict[str, int] = {}
    for item in skipped:
        reason = str(item.get("reason") or "unknown")
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

    market_stats: dict[str, dict] = {}
    for market in markets:
        market_stats[market] = {
            "candidate_count": int(candidate_counts_by_market.get(market, 0)),
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
        "skipped": skipped[:50],
        "account": final_account,
    }


def _auto_trader_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        with _cache._auto_trader_lock:
            cfg = dict(_cache._auto_trader_state.get("config") or _default_auto_trader_config())
        try:
            summary = _run_auto_trader_cycle(cfg)
            with _cache._auto_trader_lock:
                _cache._auto_trader_state["last_run_at"] = _now_iso()
                _cache._auto_trader_state["last_summary"] = summary
                _cache._auto_trader_state["last_error"] = ""
        except Exception as exc:
            with _cache._auto_trader_lock:
                _cache._auto_trader_state["last_run_at"] = _now_iso()
                _cache._auto_trader_state["last_error"] = str(exc)
                if "기간이 종료" in str(exc):
                    _cache._auto_trader_state["running"] = False
                    stop_event.set()
                    break
        interval = int((cfg.get("interval_seconds") or 300))
        interval = max(30, min(3600, interval))
        stop_event.wait(interval)


def _start_auto_trader(config: dict) -> dict:
    with _cache._auto_trader_lock:
        if (
            _cache._auto_trader_state.get("running")
            and _cache._auto_trader_thread
            and _cache._auto_trader_thread.is_alive()
        ):
            return {"ok": True, "running": True, "message": "이미 실행 중입니다.", "state": dict(_cache._auto_trader_state)}
        merged = _default_auto_trader_config()
        merged.update(config or {})
        merged["interval_seconds"] = max(30, min(3600, int(merged.get("interval_seconds") or 300)))
        merged["max_positions_per_market"] = max(1, min(20, int(merged.get("max_positions_per_market") or 5)))
        merged["daily_buy_limit"] = max(1, min(200, int(merged.get("daily_buy_limit") or 20)))
        merged["daily_sell_limit"] = max(1, min(200, int(merged.get("daily_sell_limit") or 20)))
        merged["max_orders_per_symbol_per_day"] = max(1, min(10, int(merged.get("max_orders_per_symbol_per_day") or 1)))
        merged["min_score"] = max(0.0, min(100.0, float(merged.get("min_score") or 50.0)))
        merged.update(_parse_theme_gate_config(merged))
        markets = merged.get("markets") or ["KOSPI", "NASDAQ"]
        if not isinstance(markets, list):
            markets = ["KOSPI", "NASDAQ"]
        merged["markets"] = [
            m for m in markets if normalize_strategy_market(m) in {"KOSPI", "NASDAQ"}
        ] or ["KOSPI", "NASDAQ"]
        merged = _sync_primary_strategy_fields(merged)

        _cache._auto_trader_stop_event = threading.Event()
        _cache._auto_trader_thread = threading.Thread(
            target=_auto_trader_loop, args=(_cache._auto_trader_stop_event,), daemon=True
        )
        _cache._auto_trader_state["running"] = True
        _cache._auto_trader_state["started_at"] = _now_iso()
        _cache._auto_trader_state["config"] = merged
        _cache._auto_trader_state["last_error"] = ""
        _cache._auto_trader_thread.start()
        return {"ok": True, "running": True, "state": dict(_cache._auto_trader_state)}


def _stop_auto_trader() -> dict:
    with _cache._auto_trader_lock:
        stop_event = _cache._auto_trader_stop_event
        thread = _cache._auto_trader_thread
        _cache._auto_trader_state["running"] = False
    if stop_event:
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=2.0)
    with _cache._auto_trader_lock:
        return {"ok": True, "running": False, "state": dict(_cache._auto_trader_state)}


def _auto_trader_status() -> dict:
    with _cache._auto_trader_lock:
        state = dict(_cache._auto_trader_state)
    if not state.get("config"):
        state["config"] = _default_auto_trader_config()
    if state.get("running") and not (_cache._auto_trader_thread and _cache._auto_trader_thread.is_alive()):
        state["running"] = False
        with _cache._auto_trader_lock:
            _cache._auto_trader_state["running"] = False
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
            limit_price = float(limit_price_raw) if limit_price_raw not in (None, "") else None
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
        initial_cash_krw = float(initial_cash_krw_raw) if initial_cash_krw_raw not in (None, "") else None
        initial_cash_usd = float(initial_cash_usd_raw) if initial_cash_usd_raw not in (None, "") else None
        paper_days = int(paper_days_raw) if paper_days_raw not in (None, "") else None
        engine = _get_paper_engine()
        return 200, {
            "ok": True,
            "account": engine.reset(
                initial_cash_krw=initial_cash_krw,
                initial_cash_usd=initial_cash_usd,
                paper_days=paper_days,
            ),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_paper_auto_invest(payload: dict) -> tuple[int, dict]:
    try:
        market = str(payload.get("market") or "NASDAQ").strip().upper()
        try:
            max_positions_raw = payload.get("max_positions")
            max_positions = int(5 if max_positions_raw in (None, "") else max_positions_raw)
        except (TypeError, ValueError):
            max_positions = 5
        try:
            min_score_raw = payload.get("min_score")
            min_score = float(50.0 if min_score_raw in (None, "") else min_score_raw)
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
