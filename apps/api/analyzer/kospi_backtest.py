"""KOSPI100 + S&P100 가상 매매 백테스트 엔진."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import sqrt
from typing import Any

from analyzer.candidate_selector import (
    CandidateSelectionConfig,
    load_historical_candidates,
    serialize_candidate_selection_config,
)
from broker.kis_client import KISClient
from config.backtest_universe import get_kospi100_universe, get_sp100_universe
from analyzer.shared_strategy import (
    StrategyProfile,
    build_strategy_profile,
    entry_score_from_snapshot,
    normalize_strategy_market,
    profiles_by_market,
    serialize_strategy_profiles,
    should_enter_from_snapshot,
    should_exit_from_snapshot,
)


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 10_000_000.0
    base_currency: str = "KRW"
    max_positions: int = 5
    buy_fee_rate: float = 0.00015
    sell_fee_rate: float = 0.00015
    max_holding_days: int = 15
    lookback_days: int = 1095
    markets: tuple[str, ...] = ("KOSPI",)
    rsi_min: float = 45.0
    rsi_max: float = 62.0
    volume_ratio_min: float = 1.2
    stop_loss_pct: float | None = 5.0
    take_profit_pct: float | None = None
    market_profiles: tuple[StrategyProfile, ...] = ()
    candidate_selection_enabled: bool = True
    candidate_selection: CandidateSelectionConfig = field(
        default_factory=CandidateSelectionConfig)


def run_kospi_backtest(config: BacktestConfig | None = None) -> dict[str, Any]:
    cfg = config or BacktestConfig()
    base_currency = (cfg.base_currency or "KRW").upper()
    market_profiles = _resolve_backtest_profiles(cfg)
    candidate_cache: dict[str, dict[str, dict[str, Any]]] = {}
    universe = _get_backtest_universe(cfg.markets)
    histories = _load_histories(universe, cfg.lookback_days, base_currency)

    available_histories = {
        code: rows for code, rows in histories.items() if len(rows) >= 80
    }
    if not available_histories:
        raise RuntimeError("백테스트에 사용할 KOSPI100/S&P100 히스토리를 불러오지 못했습니다.")

    all_dates = sorted(
        {
            row["date"]
            for rows in available_histories.values()
            for row in rows
            if row.get("close") is not None
        }
    )
    row_maps = {
        code: {row["date"]: row for row in rows}
        for code, rows in available_histories.items()
    }

    cash = cfg.initial_cash
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []

    for current_date in all_dates:
        # 1) 매도 조건 확인
        for code in list(positions):
            row = row_maps[code].get(current_date)
            if row and row.get("trade_price") is not None:
                positions[code]["last_trade_price"] = float(row["trade_price"])
            if not row or row.get("close") is None:
                continue

            holding = positions[code]
            holding_days = (current_date - holding["entry_date"]).days
            profile = market_profiles.get(
                normalize_strategy_market(holding["market"]))
            if profile is None:
                continue
            exit_reason = should_exit_from_snapshot(
                row,
                entry_price=holding.get("entry_price"),
                holding_days=holding_days,
                profile=profile,
            )
            if not exit_reason:
                continue

            exit_price = float(row["trade_price"])
            gross_value = exit_price * holding["shares"]
            fee = gross_value * cfg.sell_fee_rate
            cash += gross_value - fee
            pnl = (exit_price - holding["entry_price"]) * \
                holding["shares"] - holding["buy_fee"] - fee
            pnl_pct = (
                (exit_price / holding["entry_price"]) - 1) * 100 if holding["entry_price"] else 0.0
            trades.append(
                {
                    "code": code,
                    "market": holding["market"],
                    "name": holding["name"],
                    "entry_date": holding["entry_date"].isoformat(),
                    "exit_date": current_date.isoformat(),
                    "entry_price": round(holding["entry_price"], 2),
                    "exit_price": round(exit_price, 2),
                    "shares": holding["shares"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "holding_days": holding_days,
                    "reason": exit_reason,
                }
            )
            del positions[code]

        # 2) 매수 후보 선정
        market_slots = _available_market_slots(market_profiles, positions)
        total_slots = sum(max(0, value) for value in market_slots.values())
        if total_slots > 0 and cash > 0:
            candidates = []
            for code, rows in row_maps.items():
                if code in positions:
                    continue
                row = rows.get(current_date)
                if not row:
                    continue
                market = normalize_strategy_market(
                    str(row.get("market") or ""))
                profile = market_profiles.get(market)
                if profile is None or market_slots.get(market, 0) <= 0:
                    continue
                candidate_info = _historical_candidate_info(
                    candidate_cache, current_date.isoformat(), market, cfg)
                if candidate_info["has_report"] and str(row.get("code") or "").strip().upper() not in candidate_info["codes"]:
                    continue
                if not should_enter_from_snapshot(row, profile):
                    continue
                candidates.append(
                    (code, entry_score_from_snapshot(row, profile), row, profile))

            candidates.sort(key=lambda item: item[1], reverse=True)
            for code, _, row, profile in candidates:
                market = normalize_strategy_market(
                    str(row.get("market") or ""))
                if market_slots.get(market, 0) <= 0:
                    continue
                remaining_slots = sum(max(0, value)
                                      for value in market_slots.values())
                if remaining_slots <= 0:
                    break
                budget = cash / remaining_slots
                price = float(row["trade_price"])
                if price <= 0:
                    continue
                shares = int(budget // price)
                if shares < 1:
                    continue
                gross_cost = shares * price
                fee = gross_cost * cfg.buy_fee_rate
                total_cost = gross_cost + fee
                if total_cost > cash:
                    continue
                cash -= total_cost
                positions[code] = {
                    "name": row["name"],
                    "market": row["market"],
                    "market_key": market,
                    "shares": shares,
                    "entry_price": float(row["trade_price"]),
                    "last_trade_price": float(row["trade_price"]),
                    "entry_date": current_date,
                    "buy_fee": fee,
                }
                market_slots[market] = max(0, market_slots.get(market, 0) - 1)

        market_value = 0.0
        open_positions = []
        for code, holding in positions.items():
            row = row_maps[code].get(current_date)
            price = float(row["trade_price"]) if row and row.get(
                "trade_price") is not None else float(holding["last_trade_price"])
            value = price * holding["shares"]
            market_value += value
            open_positions.append(
                {
                    "code": code,
                    "market": holding["market"],
                    "name": holding["name"],
                    "shares": holding["shares"],
                    "price": round(price, 2),
                    "value": round(value, 2),
                }
            )

        equity_curve.append(
            {
                "date": current_date.isoformat(),
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "equity": round(cash + market_value, 2),
                "positions": open_positions,
            }
        )

    final_equity = equity_curve[-1]["equity"] if equity_curve else cfg.initial_cash
    metrics = _compute_metrics(cfg.initial_cash, equity_curve, trades)
    universe_label = _universe_label(cfg.markets)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe": universe_label,
        "strategy": "trend-momentum-volume-v4-shared-daily",
        "config": {
            "initial_cash": cfg.initial_cash,
            "base_currency": base_currency,
            "buy_fee_rate": cfg.buy_fee_rate,
            "sell_fee_rate": cfg.sell_fee_rate,
            "lookback_days": cfg.lookback_days,
            "markets": list(cfg.markets),
            "market_profiles": serialize_strategy_profiles(market_profiles),
            "candidate_selection": {
                "enabled": cfg.candidate_selection_enabled,
                **serialize_candidate_selection_config(cfg.candidate_selection),
                **_candidate_coverage_summary(candidate_cache),
            },
            **_single_market_profile_config(market_profiles),
        },
        "symbols": [
            {"code": code, "name": rows[-1]["name"],
                "market": rows[-1]["market"]}
            for code, rows in available_histories.items()
        ],
        "metrics": {
            **metrics,
            "final_equity": round(final_equity, 2),
        },
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _historical_candidate_info(
    cache: dict[str, dict[str, dict[str, Any]]],
    date: str,
    market: str,
    cfg: BacktestConfig,
) -> dict[str, Any]:
    day_cache = cache.setdefault(date, {})
    normalized_market = normalize_strategy_market(market)
    if normalized_market not in day_cache:
        if not cfg.candidate_selection_enabled:
            day_cache[normalized_market] = {
                "date": date,
                "market": normalized_market,
                "source": "disabled",
                "codes": set(),
                "candidates": [],
                "has_report": False,
            }
        else:
            day_cache[normalized_market] = load_historical_candidates(
                date=date,
                market=normalized_market,
                cfg=cfg.candidate_selection,
            )
    return day_cache[normalized_market]


def _candidate_coverage_summary(cache: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    total_market_dates = 0
    covered_market_dates = 0
    source_counts: dict[str, int] = {}
    for day_cache in cache.values():
        for candidate_info in day_cache.values():
            total_market_dates += 1
            if candidate_info.get("has_report"):
                covered_market_dates += 1
            source = str(candidate_info.get("source") or "none")
            source_counts[source] = source_counts.get(source, 0) + 1
    coverage_pct = (covered_market_dates / total_market_dates *
                    100) if total_market_dates else 0.0
    return {
        "report_coverage_pct": round(coverage_pct, 2),
        "covered_market_dates": covered_market_dates,
        "total_market_dates": total_market_dates,
        "source_counts": source_counts,
        "fallback_mode": "indicator_only_when_reports_missing",
    }


def _universe_label(markets: tuple[str, ...]) -> str:
    labels = []
    for market in markets:
        if market == "KOSPI":
            labels.append("KOSPI100")
        elif market == "NASDAQ":
            labels.append("S&P100")
        else:
            labels.append(market)
    return " + ".join(labels)


def _resolve_backtest_profiles(cfg: BacktestConfig) -> dict[str, StrategyProfile]:
    if cfg.market_profiles:
        return profiles_by_market(cfg.market_profiles, cfg.markets)
    return {
        normalize_strategy_market(market): build_strategy_profile(
            market,
            max_positions=cfg.max_positions,
            max_holding_days=cfg.max_holding_days,
            rsi_min=cfg.rsi_min,
            rsi_max=cfg.rsi_max,
            volume_ratio_min=cfg.volume_ratio_min,
            stop_loss_pct=cfg.stop_loss_pct,
            take_profit_pct=cfg.take_profit_pct,
            adx_min=getattr(cfg, "adx_min", None),
            mfi_min=getattr(cfg, "mfi_min", None),
            mfi_max=getattr(cfg, "mfi_max", None),
            bb_pct_min=getattr(cfg, "bb_pct_min", None),
            bb_pct_max=getattr(cfg, "bb_pct_max", None),
            stoch_k_min=getattr(cfg, "stoch_k_min", None),
            stoch_k_max=getattr(cfg, "stoch_k_max", None),
        )
        for market in cfg.markets
    }


def _single_market_profile_config(market_profiles: dict[str, StrategyProfile]) -> dict[str, Any]:
    if len(market_profiles) != 1:
        return {}
    profile = next(iter(market_profiles.values()))
    return {
        "max_positions": profile.max_positions,
        "max_holding_days": profile.max_holding_days,
        "rsi_min": profile.rsi_min,
        "rsi_max": profile.rsi_max,
        "volume_ratio_min": profile.volume_ratio_min,
        "stop_loss_pct": profile.stop_loss_pct,
        "take_profit_pct": profile.take_profit_pct,
        "adx_min": profile.adx_min,
        "mfi_min": profile.mfi_min,
        "mfi_max": profile.mfi_max,
        "bb_pct_min": profile.bb_pct_min,
        "bb_pct_max": profile.bb_pct_max,
        "stoch_k_min": profile.stoch_k_min,
        "stoch_k_max": profile.stoch_k_max,
    }


def _available_market_slots(
    market_profiles: dict[str, StrategyProfile],
    positions: dict[str, dict[str, Any]],
) -> dict[str, int]:
    counts = {market: 0 for market in market_profiles}
    for holding in positions.values():
        market = normalize_strategy_market(
            str(holding.get("market") or holding.get("market_key") or ""))
        if market in counts:
            counts[market] += 1
    return {
        market: max(0, profile.max_positions - counts.get(market, 0))
        for market, profile in market_profiles.items()
    }


def _get_backtest_universe(markets: tuple[str, ...]) -> list[tuple[str, str, str]]:
    universe = []
    allowed_markets = set(markets)
    if "KOSPI" in allowed_markets:
        for entry in get_kospi100_universe():
            universe.append((entry["code"], entry["name"], entry["market"]))
    if "NASDAQ" in allowed_markets:
        for entry in get_sp100_universe():
            universe.append((entry["code"], entry["name"], entry["market"]))
    return universe


def _load_histories(
    universe: list[tuple[str, str, str]],
    lookback_days: int,
    base_currency: str,
) -> dict[str, list[dict[str, Any]]]:
    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).date()
    histories: dict[str, list[dict[str, Any]]] = {}

    def _load_one(entry: tuple[str, str, str]) -> tuple[str, list[dict[str, Any]]]:
        code, name, market = entry
        if market == "KOSPI":
            rows = _fetch_kis_daily_history(code, name, market, cutoff_date)
        else:
            rows = _fetch_kis_overseas_daily_history(code, name, market, cutoff_date)
        return f"{market}:{code}", rows

    max_workers = 8
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_load_one, entry) for entry in universe]
        for future in as_completed(futures):
            code, rows = future.result()
            if len(rows) < 80:
                continue
            histories[code] = rows
    return histories


def _get_kis_client() -> KISClient | None:
    global _kis_client, _kis_unavailable

    if _kis_unavailable:
        return None
    if _kis_client is not None:
        return _kis_client
    if not KISClient.is_configured():
        _kis_unavailable = True
        return None
    try:
        _kis_client = KISClient.from_env(timeout=8.0)
        return _kis_client
    except Exception:
        _kis_unavailable = True
        return None


def _fetch_kis_daily_history(
    code: str,
    name: str,
    market: str,
    cutoff_date,
) -> list[dict[str, Any]]:
    client = _get_kis_client()
    if client is None:
        return []

    try:
        raw_rows = client.get_domestic_daily_history(
            code,
            start_date=cutoff_date.strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
    except Exception:
        return []

    parsed_rows = []
    for item in raw_rows:
        try:
            date = datetime.strptime(str(item["date"]), "%Y%m%d").date()
            close = float(item["close"])
            volume = float(item["volume"] or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if date < cutoff_date:
            continue
        parsed_rows.append((date, close, volume))

    if len(parsed_rows) < 80:
        return []

    parsed_rows.sort(key=lambda item: item[0])

    rows = []
    valid_closes: list[float] = []
    valid_volumes: list[float] = []
    for date, close, volume in parsed_rows:
        valid_closes.append(close)
        valid_volumes.append(volume)
        sma20 = sum(valid_closes[-20:]) / \
            20 if len(valid_closes) >= 20 else None
        sma60 = sum(valid_closes[-60:]) / \
            60 if len(valid_closes) >= 60 else None
        volume_avg20 = sum(valid_volumes[-20:]) / \
            20 if len(valid_volumes) >= 20 else None
        volume_ratio = (volume / volume_avg20) if volume_avg20 else None
        rsi14 = _rsi(valid_closes, 14)
        ema12 = _ema(valid_closes, 12)
        ema26 = _ema(valid_closes, 26)
        macd_series = [fast - slow for fast,
                       slow in zip(ema12[-len(ema26):], ema26)]
        signal_series = _ema(macd_series, 9)
        macd = macd_series[-1] if macd_series else None
        macd_signal = signal_series[-1] if signal_series else None
        macd_hist = (
            (macd - macd_signal)
            if macd is not None and macd_signal is not None
            else None
        )
        rows.append(
            {
                "date": date,
                "code": code,
                "name": name,
                "market": market,
                "currency": "KRW",
                "close": close,
                "trade_price": close,
                "volume": volume,
                "sma20": sma20,
                "sma60": sma60,
                "volume_ratio": volume_ratio,
                "rsi14": rsi14,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_hist": macd_hist,
            }
        )
    return rows


def _fetch_kis_overseas_daily_history(
    code: str,
    name: str,
    market: str,
    cutoff_date,
) -> list[dict[str, Any]]:
    """KIS API로 해외(NASDAQ 등) 일봉 히스토리를 가져온다."""
    client = _get_kis_client()
    if client is None:
        return []

    try:
        raw_rows = client.get_overseas_daily_history(
            code,
            exchange=market,
            start_date=cutoff_date.strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
    except Exception:
        return []

    parsed_rows = []
    for item in raw_rows:
        try:
            date = datetime.strptime(str(item["date"]), "%Y%m%d").date()
            close = float(item["close"])
            volume = float(item.get("volume") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if date < cutoff_date:
            continue
        parsed_rows.append((date, close, volume))

    if len(parsed_rows) < 80:
        return []

    parsed_rows.sort(key=lambda x: x[0])

    rows = []
    valid_closes: list[float] = []
    valid_volumes: list[float] = []
    for date, close, volume in parsed_rows:
        valid_closes.append(close)
        valid_volumes.append(volume)
        sma20 = sum(valid_closes[-20:]) / 20 if len(valid_closes) >= 20 else None
        sma60 = sum(valid_closes[-60:]) / 60 if len(valid_closes) >= 60 else None
        volume_avg20 = sum(valid_volumes[-20:]) / 20 if len(valid_volumes) >= 20 else None
        volume_ratio = (volume / volume_avg20) if volume_avg20 else None
        rsi14 = _rsi(valid_closes, 14)
        ema12 = _ema(valid_closes, 12)
        ema26 = _ema(valid_closes, 26)
        macd_series = [fast - slow for fast, slow in zip(ema12[-len(ema26):], ema26)]
        signal_series = _ema(macd_series, 9)
        macd = macd_series[-1] if macd_series else None
        macd_signal = signal_series[-1] if signal_series else None
        macd_hist = (
            (macd - macd_signal)
            if macd is not None and macd_signal is not None
            else None
        )
        rows.append(
            {
                "date": date,
                "code": code,
                "name": name,
                "market": market,
                "currency": "USD",
                "close": close,
                "trade_price": close,
                "volume": volume,
                "sma20": sma20,
                "sma60": sma60,
                "volume_ratio": volume_ratio,
                "rsi14": rsi14,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_hist": macd_hist,
            }
        )
    return rows


def _should_enter(row: dict[str, Any], cfg: BacktestConfig) -> bool:
    market = normalize_strategy_market(str(row.get("market") or ""))
    profile = _resolve_backtest_profiles(cfg).get(market)
    return should_enter_from_snapshot(row, profile) if profile else False


def _should_exit(
    row: dict[str, Any],
    holding: dict[str, Any],
    holding_days: int,
    cfg: BacktestConfig,
) -> str | None:
    market = normalize_strategy_market(
        str(holding.get("market") or row.get("market") or ""))
    profile = _resolve_backtest_profiles(cfg).get(market)
    if profile is None:
        return None
    return should_exit_from_snapshot(
        row,
        entry_price=holding.get("entry_price"),
        holding_days=holding_days,
        profile=profile,
    )


def _entry_score(row: dict[str, Any]) -> float:
    return entry_score_from_snapshot(row)


def _compute_metrics(
    initial_cash: float,
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    equities = [float(item["equity"]) for item in equity_curve]
    if not equities:
        return {
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "avg_trade_return_pct": 0.0,
            "sharpe": 0.0,
        }

    peak = equities[0]
    max_drawdown = 0.0
    for equity in equities:
        peak = max(peak, equity)
        drawdown = ((equity / peak) - 1) * 100 if peak else 0.0
        max_drawdown = min(max_drawdown, drawdown)

    total_return_pct = (
        (equities[-1] / initial_cash) - 1) * 100 if initial_cash else 0.0
    years = max(len(equity_curve) / 252, 1 / 252)
    cagr_pct = (((equities[-1] / initial_cash) **
                (1 / years)) - 1) * 100 if initial_cash else 0.0

    trade_returns = [float(item["pnl_pct"]) for item in trades]
    wins = [value for value in trade_returns if value > 0]
    win_rate_pct = (len(wins) / len(trade_returns)
                    * 100) if trade_returns else 0.0
    avg_trade_return_pct = sum(trade_returns) / \
        len(trade_returns) if trade_returns else 0.0

    daily_returns = []
    for prev, curr in zip(equities, equities[1:]):
        if prev:
            daily_returns.append((curr / prev) - 1)
    sharpe = 0.0
    if daily_returns:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((value - mean_return) **
                       2 for value in daily_returns) / len(daily_returns)
        stdev = sqrt(variance)
        if stdev > 0:
            sharpe = (mean_return / stdev) * sqrt(252)

    return {
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "trade_count": len(trades),
        "win_rate_pct": round(win_rate_pct, 2),
        "avg_trade_return_pct": round(avg_trade_return_pct, 2),
        "sharpe": round(sharpe, 2),
    }


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [sum(values[:period]) / period]
    for value in values[period:]:
        ema_values.append(
            (value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for prev, curr in zip(values[-(period + 1):-1], values[-period:]):
        diff = curr - prev
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


_kis_client: KISClient | None = None
_kis_unavailable = False
