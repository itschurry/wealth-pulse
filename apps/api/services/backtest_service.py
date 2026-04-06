"""Backtest validation service."""

from __future__ import annotations

import json
import os
from pathlib import Path

import cache as _cache
from analyzer.candidate_selector import (
    normalize_candidate_selection_config,
    serialize_candidate_selection_config,
)
from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest
from analyzer.shared_strategy import (
    build_strategy_profile,
    default_strategy_profile,
    serialize_strategy_profiles,
)
from schemas.strategy_metadata import portfolio_defaults
from config.settings import REPORT_OUTPUT_DIR

_OPTIMIZED_PARAMS_PATH = Path(__file__).resolve().parent.parent / "config" / "optimized_params.json"


class BacktestService:
    @staticmethod
    def _parse_candidate_selection_config(
        query: dict[str, list[str]],
        *,
        enabled: bool,
        parse_float,
        parse_int,
        parse_bool,
    ):
        if not enabled:
            # Keep indicator-only backtests independent from report/theme/news knobs.
            return normalize_candidate_selection_config({})
        return normalize_candidate_selection_config(
            {
                "min_score": parse_float("min_score", 50.0, 0.0, 100.0),
                "include_neutral": parse_bool("include_neutral", True),
                "theme_gate_enabled": parse_bool("theme_gate_enabled", True),
                "theme_min_score": parse_float("theme_min_score", 2.5, 0.0, 30.0),
                "theme_min_news": parse_int("theme_min_news", 1, 0, 10),
                "theme_priority_bonus": parse_float("theme_priority_bonus", 2.0, 0.0, 10.0),
            }
        )

    def parse_config(self, query: dict[str, list[str]]) -> BacktestConfig:
        def _parse_json(name: str) -> dict[str, object]:
            raw = (query.get(name, ["{}"])[0] or "{}").strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}

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

        strategy_kind = (query.get("strategy_kind", ["trend_following"])[0] or "trend_following").strip().lower()
        if strategy_kind not in {"trend_following", "mean_reversion", "defensive"}:
            strategy_kind = "trend_following"
        regime_mode = (query.get("regime_mode", ["auto"])[0] or "auto").strip().lower()
        if regime_mode not in {"auto", "manual"}:
            regime_mode = "auto"
        risk_profile = (query.get("risk_profile", ["balanced"])[0] or "balanced").strip().lower()
        if risk_profile not in {"conservative", "balanced", "aggressive"}:
            risk_profile = "balanced"
        strategy_params_payload = _parse_json("strategy_params")
        portfolio_constraints_payload = _parse_json("portfolio_constraints")
        portfolio_defaults_payload = portfolio_defaults(market_scope)

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
            default_profile = default_strategy_profile(
                market,
                strategy_kind=strategy_kind,
                risk_profile=risk_profile,
                regime_mode=regime_mode,
            )
            portfolio_initial_cash = portfolio_constraints_payload.get("initial_cash", portfolio_defaults_payload.get("initial_cash", initial_default))
            portfolio_max_positions = portfolio_constraints_payload.get("max_positions", query.get("max_positions", [default_profile.max_positions])[0])
            portfolio_holding_days = portfolio_constraints_payload.get("max_holding_days", query.get("max_holding_days", [default_profile.max_holding_days])[0])
            param_stop_loss = strategy_params_payload.get("stop_loss_pct", query.get("stop_loss_pct", [default_profile.stop_loss_pct])[0] if "stop_loss_pct" in query or default_profile.stop_loss_pct is not None else None)
            param_take_profit = strategy_params_payload.get("take_profit_pct", query.get("take_profit_pct", [default_profile.take_profit_pct])[0] if "take_profit_pct" in query or default_profile.take_profit_pct is not None else None)
            market_profiles.append(
                build_strategy_profile(
                    market,
                    strategy_kind=strategy_kind,
                    risk_profile=risk_profile,
                    regime_mode=regime_mode,
                    max_positions=max(1, min(20, int(float(portfolio_max_positions)))),
                    max_holding_days=max(1, min(180, int(float(portfolio_holding_days)))),
                    rsi_min=_parse_float("rsi_min", float(strategy_params_payload.get("rsi_min", default_profile.rsi_min)), 10.0, 90.0),
                    rsi_max=_parse_float("rsi_max", float(strategy_params_payload.get("rsi_max", default_profile.rsi_max)), 10.0, 90.0),
                    volume_ratio_min=_parse_float("volume_ratio_min", float(strategy_params_payload.get("volume_ratio_min", default_profile.volume_ratio_min)), 0.5, 5.0),
                    stop_loss_pct=(
                        None if param_stop_loss in (None, "") else max(1.0, min(50.0, float(param_stop_loss)))
                    ),
                    take_profit_pct=(
                        None if param_take_profit in (None, "") else max(1.0, min(100.0, float(param_take_profit)))
                    ),
                    adx_min=(
                        strategy_params_payload.get("adx_min", _parse_optional_float("adx_min", 5.0, 40.0) if "adx_min" in query else default_profile.adx_min)
                    ),
                    mfi_min=(
                        strategy_params_payload.get("mfi_min", _parse_optional_float("mfi_min", 0.0, 100.0) if "mfi_min" in query else default_profile.mfi_min)
                    ),
                    mfi_max=(
                        strategy_params_payload.get("mfi_max", _parse_optional_float("mfi_max", 0.0, 100.0) if "mfi_max" in query else default_profile.mfi_max)
                    ),
                    bb_pct_min=(
                        strategy_params_payload.get("bb_pct_min", _parse_optional_float("bb_pct_min", 0.0, 1.0) if "bb_pct_min" in query else default_profile.bb_pct_min)
                    ),
                    bb_pct_max=(
                        strategy_params_payload.get("bb_pct_max", _parse_optional_float("bb_pct_max", 0.0, 1.0) if "bb_pct_max" in query else default_profile.bb_pct_max)
                    ),
                    stoch_k_min=(
                        strategy_params_payload.get("stoch_k_min", _parse_optional_float("stoch_k_min", 0.0, 100.0) if "stoch_k_min" in query else default_profile.stoch_k_min)
                    ),
                    stoch_k_max=(
                        strategy_params_payload.get("stoch_k_max", _parse_optional_float("stoch_k_max", 0.0, 100.0) if "stoch_k_max" in query else default_profile.stoch_k_max)
                    ),
                    trade_suppression_threshold=(
                        strategy_params_payload.get("trade_suppression_threshold", default_profile.trade_suppression_threshold)
                    ),
                )
            )
        primary_profile = market_profiles[0]
        # Historical report/news candidate filtering must be explicitly enabled.
        candidate_selection_enabled = _parse_bool("candidate_selection_enabled", False)
        candidate_selection = self._parse_candidate_selection_config(
            query,
            enabled=candidate_selection_enabled,
            parse_float=_parse_float,
            parse_int=_parse_int,
            parse_bool=_parse_bool,
        )

        selected_symbols_raw = (query.get("symbols", [""])[0] or query.get("symbol", [""])[0] or "").strip()
        selected_symbols = tuple(
            symbol.strip().upper()
            for symbol in selected_symbols_raw.split(",")
            if symbol.strip()
        )

        return BacktestConfig(
            initial_cash=max(
                initial_minimum,
                min(
                    initial_maximum,
                    float(portfolio_constraints_payload.get("initial_cash", _parse_float("initial_cash", initial_default, initial_minimum, initial_maximum))),
                ),
            ),
            base_currency=base_currency,
            max_positions=primary_profile.max_positions,
            max_holding_days=primary_profile.max_holding_days,
            lookback_days=_parse_int("lookback_days", 1095, 180, 1825),
            markets=markets,
            selected_symbols=selected_symbols,
            strategy_kind=strategy_kind,
            regime_mode=regime_mode,
            risk_profile=risk_profile,
            portfolio_constraints={
                "market_scope": market_scope,
                "initial_cash": float(portfolio_constraints_payload.get("initial_cash", _parse_float("initial_cash", initial_default, initial_minimum, initial_maximum))),
                "max_positions": primary_profile.max_positions,
                "max_holding_days": primary_profile.max_holding_days,
            },
            strategy_params={
                "rsi_min": primary_profile.rsi_min,
                "rsi_max": primary_profile.rsi_max,
                "volume_ratio_min": primary_profile.volume_ratio_min,
                "stop_loss_pct": primary_profile.stop_loss_pct,
                "take_profit_pct": primary_profile.take_profit_pct,
                "adx_min": primary_profile.adx_min,
                "mfi_min": primary_profile.mfi_min,
                "mfi_max": primary_profile.mfi_max,
                "bb_pct_min": primary_profile.bb_pct_min,
                "bb_pct_max": primary_profile.bb_pct_max,
                "stoch_k_min": primary_profile.stoch_k_min,
                "stoch_k_max": primary_profile.stoch_k_max,
                "trade_suppression_threshold": primary_profile.trade_suppression_threshold,
            },
            rsi_min=primary_profile.rsi_min,
            rsi_max=primary_profile.rsi_max,
            volume_ratio_min=primary_profile.volume_ratio_min,
            stop_loss_pct=primary_profile.stop_loss_pct,
            take_profit_pct=primary_profile.take_profit_pct,
            market_profiles=tuple(market_profiles),
            candidate_selection_enabled=candidate_selection_enabled,
            candidate_selection=candidate_selection,
        )

    def run(self, config: BacktestConfig) -> dict:
        cache_key = self._config_cache_key(config)
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

    @staticmethod
    def _coerce_query_str(query: dict[str, list[str]], name: str, default: str = "") -> str:
        value = query.get(name, [default])[0]
        return str(value).strip() if value is not None else default.strip()

    @staticmethod
    def _coerce_query_int(
        query: dict[str, list[str]],
        name: str,
        default: int,
        minimum: int,
        maximum: int | None = None,
    ) -> int:
        raw = query.get(name, [str(default)])[0]
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        if maximum is None:
            return max(minimum, value)
        return max(minimum, min(maximum, value))

    def _build_optimization_payload(self, query: dict[str, list[str]]) -> dict[str, object]:
        strategy_params = {}
        raw_strategy_params = self._coerce_query_str(query, "strategy_params", "{}")
        try:
            parsed = json.loads(raw_strategy_params) if raw_strategy_params else {}
            strategy_params = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            strategy_params = {}
        portfolio_constraints = {}
        raw_portfolio_constraints = self._coerce_query_str(query, "portfolio_constraints", "{}")
        try:
            parsed = json.loads(raw_portfolio_constraints) if raw_portfolio_constraints else {}
            portfolio_constraints = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            portfolio_constraints = {}
        query_payload = {
            "market_scope": self._coerce_query_str(query, "market_scope", "kospi"),
            "lookback_days": self._coerce_query_int(query, "lookback_days", 1095, 180),
            "strategy_kind": self._coerce_query_str(query, "strategy_kind", "trend_following"),
            "regime_mode": self._coerce_query_str(query, "regime_mode", "auto"),
            "risk_profile": self._coerce_query_str(query, "risk_profile", "balanced"),
            "portfolio_constraints": portfolio_constraints,
            "strategy_params": strategy_params,
        }
        settings_payload = {
            "trainingDays": self._coerce_query_int(query, "training_days", 180, 30),
            "validationDays": self._coerce_query_int(query, "validation_days", 60, 20),
            "objective": self._coerce_query_str(query, "objective", "수익 우선"),
        }
        return {"query": query_payload, "settings": settings_payload}

    def run_with_optional_optimization(self, query: dict[str, list[str]], *, auto_optimize: bool = False) -> dict:
        config = self.parse_config(query)
        result = self.run(config)
        if not auto_optimize:
            return result

        if not _OPTIMIZED_PARAMS_PATH.exists():
            try:
                from routes.optimization import handle_run_optimization

                payload = self._build_optimization_payload(query)
                _, optimization_payload = handle_run_optimization(payload)
                if isinstance(result, dict):
                    result["optimization"] = optimization_payload
            except Exception:
                pass
        return result

    def get_latest_kospi(self) -> dict:
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

    def _config_cache_key(self, config: BacktestConfig) -> str:
        candidate_selection_payload = {"enabled": config.candidate_selection_enabled}
        if config.candidate_selection_enabled:
            candidate_selection_payload.update(serialize_candidate_selection_config(config.candidate_selection))
        return json.dumps(
            {
                "initial_cash": config.initial_cash,
                "base_currency": config.base_currency,
                "lookback_days": config.lookback_days,
                "markets": list(config.markets),
                "selected_symbols": list(config.selected_symbols),
                "market_profiles": serialize_strategy_profiles(config.market_profiles),
                "candidate_selection": candidate_selection_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


_service: BacktestService | None = None


def get_backtest_service() -> BacktestService:
    global _service
    if _service is None:
        _service = BacktestService()
    return _service


# Backward-compatible function used by tests/importers.
def parse_backtest_config(query: dict[str, list[str]]) -> BacktestConfig:
    return get_backtest_service().parse_config(query)
