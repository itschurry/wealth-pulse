"""KOSPI + NASDAQ 가상 매매 백테스트 엔진."""

from __future__ import annotations

from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from typing import Any

import requests

from broker.kis_client import KISClient
from config.backtest_universe import get_kospi_universe, get_sp100_nasdaq_universe


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 10_000_000.0
    max_positions: int = 5
    buy_fee_rate: float = 0.00015
    sell_fee_rate: float = 0.00015
    max_holding_days: int = 30
    lookback_days: int = 1095
    markets: tuple[str, ...] = ("KOSPI", "NASDAQ")
    rsi_min: float = 45.0
    rsi_max: float = 68.0
    volume_ratio_min: float = 1.2
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None


def run_kospi_backtest(config: BacktestConfig | None = None) -> dict[str, Any]:
    cfg = config or BacktestConfig()
    universe = _get_backtest_universe(cfg.markets)
    histories = _load_histories(universe, cfg.lookback_days)

    available_histories = {
        code: rows for code, rows in histories.items() if len(rows) >= 80
    }
    if not available_histories:
        raise RuntimeError("백테스트에 사용할 KOSPI/NASDAQ 히스토리를 불러오지 못했습니다.")

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
            exit_reason = _should_exit(row, holding, holding_days, cfg)
            if not exit_reason:
                continue

            exit_price = float(row["trade_price"])
            gross_value = exit_price * holding["shares"]
            fee = gross_value * cfg.sell_fee_rate
            cash += gross_value - fee
            pnl = (exit_price - holding["entry_price"]) * holding["shares"] - holding["buy_fee"] - fee
            pnl_pct = ((exit_price / holding["entry_price"]) - 1) * 100 if holding["entry_price"] else 0.0
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
        slots = cfg.max_positions - len(positions)
        if slots > 0 and cash > 0:
            candidates = []
            for code, rows in row_maps.items():
                if code in positions:
                    continue
                row = rows.get(current_date)
                if not row or not _should_enter(row, cfg):
                    continue
                candidates.append((code, _entry_score(row), row))

            candidates.sort(key=lambda item: item[1], reverse=True)
            for code, _, row in candidates[:slots]:
                budget = cash / max(1, (cfg.max_positions - len(positions)))
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
                    "shares": shares,
                    "entry_price": float(row["trade_price"]),
                    "last_trade_price": float(row["trade_price"]),
                    "entry_date": current_date,
                    "buy_fee": fee,
                }

        market_value = 0.0
        open_positions = []
        for code, holding in positions.items():
            row = row_maps[code].get(current_date)
            price = float(row["trade_price"]) if row and row.get("trade_price") is not None else float(holding["last_trade_price"])
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
        "strategy": "trend-momentum-volume-fx-v2",
        "config": {
            "initial_cash": cfg.initial_cash,
            "max_positions": cfg.max_positions,
            "buy_fee_rate": cfg.buy_fee_rate,
            "sell_fee_rate": cfg.sell_fee_rate,
            "max_holding_days": cfg.max_holding_days,
            "lookback_days": cfg.lookback_days,
            "markets": list(cfg.markets),
            "rsi_min": cfg.rsi_min,
            "rsi_max": cfg.rsi_max,
            "volume_ratio_min": cfg.volume_ratio_min,
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
        },
        "symbols": [
            {"code": code, "name": rows[-1]["name"], "market": rows[-1]["market"]}
            for code, rows in available_histories.items()
        ],
        "metrics": {
            **metrics,
            "final_equity": round(final_equity, 2),
        },
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _universe_label(markets: tuple[str, ...]) -> str:
    labels = []
    for market in markets:
        if market == "KOSPI":
            labels.append("KOSPI 확장")
        elif market == "NASDAQ":
            labels.append("S&P100 NASDAQ")
        else:
            labels.append(market)
    return " + ".join(labels)


def _get_backtest_universe(markets: tuple[str, ...]) -> list[tuple[str, str, str, str]]:
    universe = []
    allowed_markets = set(markets)
    if "KOSPI" in allowed_markets:
        for entry in get_kospi_universe():
            universe.append((entry["code"], entry["name"], entry["market"], _ticker_for_entry(entry["code"], entry["market"])))
    if "NASDAQ" in allowed_markets:
        for entry in get_sp100_nasdaq_universe():
            universe.append((entry["code"], entry["name"], entry["market"], _ticker_for_entry(entry["code"], entry["market"])))
    return universe


def _load_histories(
    universe: list[tuple[str, str, str, str]],
    lookback_days: int,
) -> dict[str, list[dict[str, Any]]]:
    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).date()
    histories: dict[str, list[dict[str, Any]]] = {}
    fx_lookup = _load_usdkrw_lookup(cutoff_date)
    domestic_count = sum(1 for _, _, market, _ in universe if market == "KOSPI")
    use_kis_for_domestic = domestic_count <= 80 and _get_kis_client() is not None

    def _load_one(entry: tuple[str, str, str, str]) -> tuple[str, list[dict[str, Any]]]:
        code, name, market, ticker = entry
        if market == "KOSPI":
            rows = _fetch_kis_daily_history(code, name, market, cutoff_date) if use_kis_for_domestic else []
            if len(rows) < 80:
                rows = _fetch_naver_daily_history(code, name, market, cutoff_date)
        else:
            rows = _fetch_yahoo_daily_history(code, name, ticker, market, cutoff_date, fx_lookup)
        return f"{market}:{code}", rows

    max_workers = 18 if len(universe) > 100 else 8
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_load_one, entry) for entry in universe]
        for future in as_completed(futures):
            code, rows = future.result()
            if len(rows) < 80:
                continue
            histories[code] = rows
    return histories


def _fetch_naver_daily_history(
    code: str,
    name: str,
    market: str,
    cutoff_date,
) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            "https://fchart.stock.naver.com/sise.nhn",
            params={
                "symbol": code,
                "timeframe": "day",
                "count": "800",
                "requestType": "0",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        text = response.content.decode("euc-kr", "replace")
    except Exception:
        return []

    raw_rows = []
    for line in text.splitlines():
        if 'item data="' not in line:
            continue
        item = line.split('item data="', 1)[1].split('"', 1)[0]
        parts = item.split("|")
        if len(parts) != 6:
            continue
        try:
            date = datetime.strptime(parts[0], "%Y%m%d").date()
            close = float(parts[4])
            volume = float(parts[5])
        except ValueError:
            continue
        if date < cutoff_date:
            continue
        raw_rows.append((date, close, volume))

    if len(raw_rows) < 80:
        return []

    rows = []
    valid_closes: list[float] = []
    valid_volumes: list[float] = []
    for date, close, volume in raw_rows:
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


def _fetch_yahoo_daily_history(
    code: str,
    name: str,
    ticker: str,
    market: str,
    cutoff_date,
    fx_lookup,
) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={
                "range": "5y",
                "interval": "1d",
                "includePrePost": "false",
                "events": "div,splits",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
    except Exception:
        return []

    raw_rows = []
    for ts, close, volume in zip(timestamps, closes, volumes):
        if close is None or volume is None:
            continue
        date = datetime.utcfromtimestamp(ts).date()
        if date < cutoff_date:
            continue
        fx_rate = fx_lookup(date)
        if fx_rate is None:
            continue
        raw_rows.append((date, float(close), float(volume), float(close) * fx_rate))

    if len(raw_rows) < 80:
        return []

    rows = []
    valid_closes: list[float] = []
    valid_volumes: list[float] = []
    for date, close, volume, trade_price in raw_rows:
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
                "trade_price": trade_price,
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


def _load_usdkrw_lookup(cutoff_date):
    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X",
            params={
                "range": "5y",
                "interval": "1d",
                "includePrePost": "false",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result:
            raise ValueError("FX history missing")
        timestamps = result.get("timestamp") or []
        closes = ((result.get("indicators", {}).get("quote") or [{}])[0]).get("close") or []
    except Exception:
        return lambda _date: None

    dates: list[Any] = []
    values: list[float] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = datetime.utcfromtimestamp(ts).date()
        if date < cutoff_date - timedelta(days=10):
            continue
        dates.append(date)
        values.append(float(close))

    def lookup(target_date):
        if not dates:
            return None
        idx = bisect_right(dates, target_date) - 1
        if idx < 0:
            return None
        return values[idx]

    return lookup


def _ticker_for_entry(code: str, market: str) -> str:
    if market == "KOSPI":
        return f"{code}.KS"
    return code


def _should_enter(row: dict[str, Any], cfg: BacktestConfig) -> bool:
    close = row.get("close")
    sma20 = row.get("sma20")
    sma60 = row.get("sma60")
    volume_ratio = row.get("volume_ratio")
    rsi14 = row.get("rsi14")
    macd = row.get("macd")
    macd_signal = row.get("macd_signal")
    macd_hist = row.get("macd_hist")

    return bool(
        close is not None
        and sma20 is not None
        and sma60 is not None
        and volume_ratio is not None
        and rsi14 is not None
        and macd is not None
        and macd_signal is not None
        and macd_hist is not None
        and close > sma20 > sma60
        and volume_ratio >= cfg.volume_ratio_min
        and cfg.rsi_min <= rsi14 <= cfg.rsi_max
        and macd_hist > 0
        and macd > macd_signal
    )


def _should_exit(
    row: dict[str, Any],
    holding: dict[str, Any],
    holding_days: int,
    cfg: BacktestConfig,
) -> str | None:
    close = row.get("close")
    sma20 = row.get("sma20")
    rsi14 = row.get("rsi14")
    macd = row.get("macd")
    macd_signal = row.get("macd_signal")
    macd_hist = row.get("macd_hist")
    trade_price = row.get("trade_price")
    entry_price = holding.get("entry_price")

    if holding_days >= cfg.max_holding_days:
        return "보유기간 만료"
    if (
        cfg.stop_loss_pct is not None
        and trade_price is not None
        and entry_price
        and ((float(trade_price) / float(entry_price)) - 1) * 100 <= -cfg.stop_loss_pct
    ):
        return "손절"
    if (
        cfg.take_profit_pct is not None
        and trade_price is not None
        and entry_price
        and ((float(trade_price) / float(entry_price)) - 1) * 100 >= cfg.take_profit_pct
    ):
        return "익절"
    if close is not None and sma20 is not None and close < sma20:
        return "20일선 이탈"
    if macd is not None and macd_signal is not None and macd_hist is not None:
        if macd < macd_signal and macd_hist < 0:
            return "MACD 약세 전환"
    if rsi14 is not None and rsi14 >= 75:
        return "RSI 과열"
    return None


def _entry_score(row: dict[str, Any]) -> float:
    close = float(row["close"])
    sma20 = float(row["sma20"])
    sma60 = float(row["sma60"])
    volume_ratio = float(row["volume_ratio"])
    rsi14 = float(row["rsi14"])
    macd_hist = float(row["macd_hist"])
    trend_score = ((close / sma20) - 1) * 100 + ((sma20 / sma60) - 1) * 100
    rsi_score = max(0.0, 70 - abs(57 - rsi14))
    return round(trend_score + volume_ratio * 2.5 + macd_hist * 12 + rsi_score * 0.1, 4)


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

    total_return_pct = ((equities[-1] / initial_cash) - 1) * 100 if initial_cash else 0.0
    years = max(len(equity_curve) / 252, 1 / 252)
    cagr_pct = (((equities[-1] / initial_cash) ** (1 / years)) - 1) * 100 if initial_cash else 0.0

    trade_returns = [float(item["pnl_pct"]) for item in trades]
    wins = [value for value in trade_returns if value > 0]
    win_rate_pct = (len(wins) / len(trade_returns) * 100) if trade_returns else 0.0
    avg_trade_return_pct = sum(trade_returns) / len(trade_returns) if trade_returns else 0.0

    daily_returns = []
    for prev, curr in zip(equities, equities[1:]):
        if prev:
            daily_returns.append((curr / prev) - 1)
    sharpe = 0.0
    if daily_returns:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((value - mean_return) ** 2 for value in daily_returns) / len(daily_returns)
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
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
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
