import json
import os

import api.cache as _cache
from analyzer.candidate_selector import (
    normalize_candidate_selection_config,
    serialize_candidate_selection_config,
)
from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest
from analyzer.shared_strategy import (
    build_strategy_profile,
    default_strategy_profile,
    default_strategy_profiles,
    serialize_strategy_profiles,
)
from config.settings import REPORT_OUTPUT_DIR


def _config_cache_key(config: BacktestConfig) -> str:
    return json.dumps(
        {
            "initial_cash": config.initial_cash,
            "base_currency": config.base_currency,
            "lookback_days": config.lookback_days,
            "markets": list(config.markets),
            "market_profiles": serialize_strategy_profiles(config.market_profiles),
            "candidate_selection": {
                "enabled": config.candidate_selection_enabled,
                **serialize_candidate_selection_config(config.candidate_selection),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _parse_backtest_config(query: dict[str, list[str]]) -> BacktestConfig:
    market_scope = (query.get("market_scope", ["kospi"])[0] or "kospi").strip().lower()
    if market_scope == "all":
        markets = ("KOSPI", "NASDAQ")
        base_currency = "KRW"
        initial_default = 10_000_000.0
        initial_minimum = 1_000_000.0
        initial_maximum = 500_000_000.0
    elif market_scope == "nasdaq":
        markets = ("NASDAQ",)
        base_currency = "USD"
        initial_default = 10_000.0
        initial_minimum = 1_000.0
        initial_maximum = 5_000_000.0
    else:
        markets = ("KOSPI",)
        base_currency = "KRW"
        initial_default = 10_000_000.0
        initial_minimum = 1_000_000.0
        initial_maximum = 500_000_000.0

    def _parse_int(name: str, default: int, minimum: int, maximum: int) -> int:
        raw = query.get(name, [str(default)])[0]
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _parse_float(name: str, default: float, minimum: float, maximum: float) -> float:
        raw = query.get(name, [str(default)])[0]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _parse_optional_float(name: str, minimum: float, maximum: float) -> float | None:
        raw = (query.get(name, [""])[0] or "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(minimum, min(maximum, value))

    def _parse_bool(name: str, default: bool) -> bool:
        raw = (query.get(name, [str(default)])[0] or "").strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
        return default

    market_profiles = []
    for market in markets:
        default_profile = default_strategy_profile(market)
        market_profiles.append(
            build_strategy_profile(
                market,
                max_positions=_parse_int("max_positions", default_profile.max_positions, 1, 20),
                max_holding_days=_parse_int("max_holding_days", default_profile.max_holding_days, 5, 180),
                rsi_min=_parse_float("rsi_min", default_profile.rsi_min, 10.0, 90.0),
                rsi_max=_parse_float("rsi_max", default_profile.rsi_max, 10.0, 90.0),
                volume_ratio_min=_parse_float("volume_ratio_min", default_profile.volume_ratio_min, 0.5, 5.0),
                stop_loss_pct=(
                    _parse_optional_float("stop_loss_pct", 1.0, 50.0)
                    if "stop_loss_pct" in query else default_profile.stop_loss_pct
                ),
                take_profit_pct=(
                    _parse_optional_float("take_profit_pct", 1.0, 100.0)
                    if "take_profit_pct" in query else default_profile.take_profit_pct
                ),
            )
        )
    primary_profile = market_profiles[0]
    candidate_selection_enabled = _parse_bool("candidate_selection_enabled", True)
    candidate_selection = normalize_candidate_selection_config(
        {
            "min_score": _parse_float("min_score", 50.0, 0.0, 100.0),
            "include_neutral": _parse_bool("include_neutral", True),
            "theme_gate_enabled": _parse_bool("theme_gate_enabled", True),
            "theme_min_score": _parse_float("theme_min_score", 2.5, 0.0, 30.0),
            "theme_min_news": _parse_int("theme_min_news", 1, 0, 10),
            "theme_priority_bonus": _parse_float("theme_priority_bonus", 2.0, 0.0, 10.0),
        }
    )

    return BacktestConfig(
        initial_cash=_parse_float("initial_cash", initial_default, initial_minimum, initial_maximum),
        base_currency=base_currency,
        max_positions=primary_profile.max_positions,
        max_holding_days=primary_profile.max_holding_days,
        lookback_days=_parse_int("lookback_days", 1095, 180, 1825),
        markets=markets,
        rsi_min=primary_profile.rsi_min,
        rsi_max=primary_profile.rsi_max,
        volume_ratio_min=primary_profile.volume_ratio_min,
        stop_loss_pct=primary_profile.stop_loss_pct,
        take_profit_pct=primary_profile.take_profit_pct,
        market_profiles=tuple(market_profiles),
        candidate_selection_enabled=candidate_selection_enabled,
        candidate_selection=candidate_selection,
    )


def _run_backtest(config: BacktestConfig) -> dict:
    cache_key = _config_cache_key(config)
    cached = _cache._backtest_run_cache.get(cache_key)
    if cached:
        return cached

    result = run_kospi_backtest(config)
    _cache._backtest_run_cache[cache_key] = result
    if len(_cache._backtest_run_cache) > 12:
        oldest_key = next(iter(_cache._backtest_run_cache))
        if oldest_key != cache_key:
            _cache._backtest_run_cache.pop(oldest_key, None)
    return result


def _get_kospi_backtest() -> dict:
    path = os.path.join(str(REPORT_OUTPUT_DIR), "kospi_backtest_latest.json")
    if not os.path.exists(path):
        return {"error": "백테스트 결과가 없습니다. scripts/run_kospi_backtest.py를 먼저 실행하세요."}

    mtime = os.path.getmtime(path)
    if _cache._backtest_cache["data"] is not None and mtime == _cache._backtest_cache["mtime"]:
        return _cache._backtest_cache["data"]

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    _cache._backtest_cache["data"] = data
    _cache._backtest_cache["mtime"] = mtime
    return data


def handle_backtest_run(query: dict) -> tuple[int, dict]:
    try:
        config = _parse_backtest_config(query)
        return 200, _run_backtest(config)
    except Exception as e:
        return 500, {"error": str(e)}


def handle_kospi_backtest() -> tuple[int, dict]:
    try:
        return 200, _get_kospi_backtest()
    except Exception as e:
        return 500, {"error": str(e)}
