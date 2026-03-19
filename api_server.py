#!/usr/bin/env python3
"""
실시간 시장 데이터 + AI 분석/추천 캐시 API 서버 (Python 표준 라이브러리만 사용)
GET /api/live-market     → JSON (5분 캐시)
GET /api/analysis        → JSON (파일 mtime 기반 캐시)
GET /api/recommendations → JSON (파일 mtime 기반 캐시)
"""
import datetime
import glob
import json
import os
import re
import asyncio
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest
from analyzer.today_picks_engine import build_watchlist_actions
from broker.execution_engine import EngineConfig, PaperExecutionEngine
from broker.kis_client import KISAPIError, KISClient, KISConfigError
from config.settings import LOGS_DIR
from reporter.telegram_sender import send_text_message

PORT = 8001
CACHE_TTL = 300   # 5분

_market_cache: dict = {"data": None, "ts": 0.0}
_analysis_cache: dict = {"data": None, "mtime": 0.0}
_recommendation_cache: dict = {"data": None, "mtime": 0.0}
_macro_cache: dict = {"data": None, "mtime": 0.0}
_market_context_cache: dict = {"data": None, "mtime": 0.0}
_today_picks_cache: dict = {"data": None, "mtime": 0.0}
_ai_signals_cache: dict = {"data": None, "mtime": 0.0}
_backtest_cache: dict = {"data": None, "mtime": 0.0}
_backtest_run_cache: dict = {}
_technical_cache: dict = {}
_investor_flow_cache: dict = {}
_kis_client: KISClient | None = None
_kis_client_disabled = False
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

_KST = datetime.timezone(datetime.timedelta(hours=9))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Referer": "https://finance.naver.com/",
}

_ALLOWED_SEARCH_MARKETS = {"KOSPI", "NASDAQ", "코스피", "나스닥 증권거래소"}
TECHNICAL_CACHE_TTL = 900
INVESTOR_FLOW_CACHE_TTL = 900


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _format_krw(value: float | int | None) -> str:
    amount = float(value or 0.0)
    return f"{amount:,.0f}원"


def _format_usd(value: float | int | None) -> str:
    amount = float(value or 0.0)
    return f"${amount:,.2f}"


def _send_paper_trade_notification(event: dict, account: dict) -> None:
    side = str(event.get("side") or "").lower()
    market = str(event.get("market") or "").upper()
    code = str(event.get("code") or "")
    name = str(event.get("name") or code)
    quantity = int(event.get("quantity") or 0)
    price_local = float(event.get("filled_price_local") or 0.0)
    notional_krw = float(event.get("notional_krw") or 0.0)
    realized_pnl_krw = float(event.get("realized_pnl_krw") or 0.0)
    side_label = "매수" if side == "buy" else "매도"
    price_label = _format_usd(price_local) if market == "NASDAQ" else _format_krw(price_local)
    cash_label = f"KRW {_format_krw(account.get('cash_krw'))} / USD {_format_usd(account.get('cash_usd'))}"
    pnl_line = ""
    if side == "sell":
        pnl_line = f"\n실현손익: {_format_krw(realized_pnl_krw)}"

    message = (
        "[모의투자 체결]\n"
        f"{market} {side_label}\n"
        f"{name} ({code})\n"
        f"수량: {quantity}주\n"
        f"체결가: {price_label}\n"
        f"체결금액(KRW 환산): {_format_krw(notional_krw)}"
        f"{pnl_line}\n"
        f"총자산: {_format_krw(account.get('equity_krw'))}\n"
        f"현금: {cash_label}"
    )
    asyncio.run(send_text_message(message))


def _resolve_reports_dir() -> str:
    candidates = [
        os.getenv("REPORT_OUTPUT_DIR"),
        "/reports",
        os.path.join(os.getcwd(), "report"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return candidates[-1]


REPORTS_DIR = _resolve_reports_dir()


# ──────────────────────────────────────────
#  Fetch helpers
# ──────────────────────────────────────────
def _get(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _naver_index(symbol: str):
    url = f"https://m.stock.naver.com/api/index/{symbol}/basic"
    d = json.loads(_get(url, timeout=4))
    price = float(d["closePrice"].replace(",", ""))
    pct = float(d["fluctuationsRatio"])
    code = d.get("compareToPreviousPrice", {}).get("code", "3")
    if code == "5":
        pct = -abs(pct)
    elif code == "2":
        pct = abs(pct)
    return price, pct


def _stooq_daily(symbol: str):
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    text = _get(url, timeout=4)
    rows = [l for l in text.strip().splitlines()
            if l and not l.startswith("Date")]
    if len(rows) < 2:
        return None, None
    last = rows[-1].split(",")
    prev = rows[-2].split(",")
    close = float(last[4])
    prev_close = float(prev[4])
    pct = (close - prev_close) / prev_close * 100
    return close, pct


def _yahoo_chart(symbol: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    payload = json.loads(_get(url, timeout=4))
    result = payload["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    valid = [float(value) for value in closes if value is not None]
    if not valid:
        return None, None
    close = valid[-1]
    prev_close = valid[-2] if len(valid) >= 2 else close
    pct = (close - prev_close) / prev_close * 100 if prev_close else None
    return close, pct


def _stooq_spot(symbol: str):
    url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcvp&h&e=csv"
    text = _get(url, timeout=4)
    rows = [l for l in text.strip().splitlines()
            if l and not l.startswith("Symbol")]
    if not rows:
        return None, None
    parts = rows[-1].split(",")
    if len(parts) < 9:
        return None, None
    try:
        close = float(parts[6])
        prev = float(parts[8])
        pct = (close - prev) / prev * 100 if prev else None
        return close, pct
    except (ValueError, IndexError):
        return None, None


def _usd_krw():
    text = _get("https://finance.naver.com/marketindex/", timeout=4)
    m = re.search(r'class="value"[^>]*>(1[,\d]+\.\d{2})', text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _is_allowed_market_label(*labels: str) -> bool:
    normalized_labels = {label.strip().upper() for label in labels if label and label.strip()}
    return any(label in _ALLOWED_SEARCH_MARKETS for label in normalized_labels)


def _resolve_chart_symbol(code: str, market: str) -> str | None:
    normalized_code = code.strip().upper()
    normalized_market = market.strip().upper()
    if not normalized_code:
        return None
    if normalized_market == "KOSPI" and normalized_code.isdigit():
        return f"{normalized_code}.KS"
    if normalized_market == "NASDAQ":
        return normalized_code
    return None


def _get_kis_client() -> KISClient | None:
    global _kis_client, _kis_client_disabled

    if _kis_client_disabled:
        return None
    if _kis_client is not None:
        return _kis_client
    if not KISClient.is_configured():
        _kis_client_disabled = True
        return None
    try:
        _kis_client = KISClient.from_env(timeout=8.0)
        return _kis_client
    except (KISConfigError, KISAPIError):
        _kis_client_disabled = True
        return None


def _paper_fx_rate() -> float | None:
    try:
        if _market_cache["data"] is not None:
            usd_krw = _market_cache["data"].get("usd_krw")
            if isinstance(usd_krw, (int, float)) and usd_krw > 0:
                return float(usd_krw)
        value = _usd_krw()
        return float(value) if value and value > 0 else None
    except Exception:
        return None


def _resolve_stock_quote(code: str, market: str = "") -> dict:
    normalized_code = code.split(".")[0].strip().upper()
    normalized_market = market.strip().upper()
    if not normalized_code:
        raise ValueError("code required")

    if normalized_market == "NASDAQ":
        technicals = _compute_technical_snapshot(normalized_code, normalized_market)
        if technicals:
            return {
                "code": normalized_code,
                "name": normalized_code,
                "price": technicals.get("current_price"),
                "change_pct": technicals.get("change_pct"),
                "market": normalized_market,
            }

    if normalized_market == "KOSPI":
        client = _get_kis_client()
        if client is not None:
            kis_price = client.get_domestic_price(normalized_code)
            return {
                "code": normalized_code,
                "name": kis_price.get("name") or normalized_code,
                "price": kis_price.get("price"),
                "change_pct": kis_price.get("change_pct"),
                "market": "KOSPI",
            }

    url = f"https://m.stock.naver.com/api/stock/{normalized_code}/basic"
    d = json.loads(_get(url))
    price = float(d["closePrice"].replace(",", ""))
    pct = float(d["fluctuationsRatio"])
    direction = d.get("compareToPreviousPrice", {}).get("code", "3")
    if direction == "5":
        pct = -abs(pct)
    elif direction == "2":
        pct = abs(pct)
    return {
        "code": normalized_code,
        "name": d.get("stockName", normalized_code),
        "price": price,
        "change_pct": round(pct, 2),
        "market": d.get("stockExchangeType", {}).get("name", normalized_market),
    }


def _get_paper_engine() -> PaperExecutionEngine:
    global _paper_engine
    if _paper_engine is None:
        state_path = Path(os.getenv("PAPER_TRADING_STATE_PATH", str(LOGS_DIR / "paper_account_state.json")))
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
    normalized = (market or "").strip().upper()
    if normalized in {"NASDAQ", "NAS", "US", "USA"}:
        return "NASDAQ"
    if normalized in {"KOSPI", "KRX", "KR", "KOREA"}:
        return "KOSPI"
    return normalized


def _infer_pick_market(code: str, market: str) -> str:
    normalized_market = _normalize_pick_market(market)
    if normalized_market in {"KOSPI", "NASDAQ"}:
        return normalized_market
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        return normalized_market
    if normalized_code.isdigit():
        return "KOSPI"
    if normalized_code.isalpha():
        return "NASDAQ"
    return normalized_market


def _auto_invest_picks(
    *,
    market: str = "NASDAQ",
    max_positions: int = 5,
    min_score: float = 60.0,
    include_neutral: bool = False,
) -> dict:
    target_market = _normalize_pick_market(market)
    if target_market not in {"NASDAQ", "KOSPI"}:
        return {"ok": False, "error": "market은 NASDAQ/KOSPI만 허용합니다."}

    picks_payload = _get_today_picks()
    picks = picks_payload.get("picks", [])
    if not isinstance(picks, list):
        picks = []

    allowed_signals = {"추천", "buy", "BUY"}
    if include_neutral:
        allowed_signals.update({"중립", "hold", "HOLD"})

    candidates: list[dict] = []
    for item in picks:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        signal = str(item.get("signal") or "")
        score = float(item.get("score") or 0.0)
        item_market = _infer_pick_market(code, str(item.get("market") or ""))
        if not code:
            continue
        if item_market != target_market:
            continue
        if signal not in allowed_signals:
            continue
        if score < min_score:
            continue
        candidates.append(item)

    # today-picks에 후보가 없으면 recommendations에서 동일 조건으로 보강한다.
    if not candidates:
        recommendations = _get_recommendations().get("recommendations", [])
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            code = ticker.split(".")[0]
            if not code:
                continue
            inferred_market = "KOSPI" if ticker.endswith(".KS") else "NASDAQ"
            if inferred_market != target_market:
                continue
            signal = str(item.get("signal") or "")
            score = float(item.get("score") or 0.0)
            if signal not in allowed_signals:
                continue
            if score < min_score:
                continue
            candidates.append({
                "name": item.get("name") or code,
                "code": code,
                "market": inferred_market,
                "signal": signal,
                "score": score,
            })

    candidates.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
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

    available_cash = float(account.get("cash_usd") or 0.0) if target_market == "NASDAQ" else float(account.get("cash_krw") or 0.0)
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
        message = "조건에 맞는 자동매수 후보가 없습니다. market/signal/min_score 조건을 낮춰 보세요."
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
        "message": message,
        "account": final_account,
    }


def _default_auto_trader_config() -> dict:
    return {
        "interval_seconds": 300,
        "markets": ["KOSPI", "NASDAQ"],
        "max_positions_per_market": 5,
        "min_score": 60.0,
        "include_neutral": False,
        "daily_buy_limit": 20,
        "daily_sell_limit": 20,
        "max_orders_per_symbol_per_day": 1,
        "rsi_min": 45.0,
        "rsi_max": 68.0,
        "volume_ratio_min": 1.2,
        "signal_interval": "5m",
        "signal_range": "5d",
        "stop_loss_pct": 7.0,
        "take_profit_pct": 18.0,
        "max_holding_days": 30,
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


def _should_enter_by_indicators(technicals: dict, cfg: dict) -> bool:
    close = technicals.get("current_price")
    sma20 = technicals.get("sma20")
    sma60 = technicals.get("sma60")
    volume_ratio = technicals.get("volume_ratio")
    rsi14 = technicals.get("rsi14")
    macd = technicals.get("macd")
    macd_signal = technicals.get("macd_signal")
    macd_hist = technicals.get("macd_hist")
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
        and volume_ratio >= float(cfg.get("volume_ratio_min", 1.2))
        and float(cfg.get("rsi_min", 45.0)) <= rsi14 <= float(cfg.get("rsi_max", 68.0))
        and macd_hist > 0
        and macd > macd_signal
    )


def _should_exit_by_indicators(position: dict, technicals: dict, cfg: dict) -> str | None:
    price = technicals.get("current_price")
    if price is None:
        return None
    avg = float(position.get("avg_price_local") or 0.0)
    if avg > 0:
        pnl_pct = ((float(price) / avg) - 1) * 100
        stop_loss = float(cfg.get("stop_loss_pct", 7.0))
        take_profit = float(cfg.get("take_profit_pct", 18.0))
        if pnl_pct <= -abs(stop_loss):
            return "손절"
        if pnl_pct >= abs(take_profit):
            return "익절"
    if _position_holding_days(position) >= int(cfg.get("max_holding_days", 30)):
        return "보유기간 만료"
    sma20 = technicals.get("sma20")
    rsi14 = technicals.get("rsi14")
    macd = technicals.get("macd")
    macd_signal = technicals.get("macd_signal")
    macd_hist = technicals.get("macd_hist")
    if sma20 is not None and price < sma20:
        return "20일선 이탈"
    if macd is not None and macd_signal is not None and macd_hist is not None and macd < macd_signal and macd_hist < 0:
        return "MACD 약세 전환"
    if rsi14 is not None and rsi14 >= 75:
        return "RSI 과열"
    return None


def _collect_pick_candidates(market: str, min_score: float, include_neutral: bool) -> list[dict]:
    allowed_signals = {"추천", "buy", "BUY"}
    if include_neutral:
        allowed_signals.update({"중립", "hold", "HOLD"})

    picks_payload = _get_today_picks()
    picks = picks_payload.get("picks", [])
    if not isinstance(picks, list):
        picks = []

    candidates: list[dict] = []
    for item in picks:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        if not code:
            continue
        item_market = _infer_pick_market(code, str(item.get("market") or ""))
        signal = str(item.get("signal") or "")
        score = float(item.get("score") or 0.0)
        if item_market != market or signal not in allowed_signals or score < min_score:
            continue
        candidates.append({
            "code": code,
            "name": item.get("name") or code,
            "score": score,
            "signal": signal,
        })
    if candidates:
        return sorted(candidates, key=lambda item: item["score"], reverse=True)

    recommendations = _get_recommendations().get("recommendations", [])
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        code = ticker.split(".")[0]
        if not code:
            continue
        inferred_market = "KOSPI" if ticker.endswith(".KS") else "NASDAQ"
        signal = str(item.get("signal") or "")
        score = float(item.get("score") or 0.0)
        if inferred_market != market or signal not in allowed_signals or score < min_score:
            continue
        candidates.append({
            "code": code,
            "name": item.get("name") or code,
            "score": score,
            "signal": signal,
        })
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


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

    executed_buys: list[dict] = []
    executed_sells: list[dict] = []
    skipped: list[dict] = []
    markets = [m for m in cfg.get("markets", ["KOSPI", "NASDAQ"]) if m in {"KOSPI", "NASDAQ"}]

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
            technicals = _compute_technical_snapshot(
                code,
                market,
                range_=str(cfg.get("signal_range") or "5d"),
                interval=str(cfg.get("signal_interval") or "5m"),
            )
            if not technicals:
                continue
            reason = _should_exit_by_indicators(position, technicals, cfg)
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
        max_positions = int(cfg.get("max_positions_per_market", 5))
        slots = max(0, max_positions - market_position_count)
        if slots <= 0:
            continue
        buy_count = _count_orders(market, "buy")
        candidates = _collect_pick_candidates(
            market=market,
            min_score=float(cfg.get("min_score", 60.0)),
            include_neutral=bool(cfg.get("include_neutral", False)),
        )
        for candidate in candidates:
            if slots <= 0 or buy_count >= daily_buy_limit:
                break
            code = str(candidate.get("code") or "").upper()
            if not code or code in held_codes:
                continue
            if _symbol_order_count(market, "buy", code) >= max_orders_per_symbol:
                continue
            technicals = _compute_technical_snapshot(
                code,
                market,
                range_=str(cfg.get("signal_range") or "5d"),
                interval=str(cfg.get("signal_interval") or "5m"),
            )
            if not technicals:
                skipped.append({"code": code, "market": market, "reason": "technicals_unavailable"})
                continue
            if not _should_enter_by_indicators(technicals, cfg):
                skipped.append({"code": code, "market": market, "reason": "entry_signal_not_matched"})
                continue
            quote = _resolve_stock_quote(code, market)
            price_local = float(quote.get("price") or 0.0)
            if price_local <= 0:
                skipped.append({"code": code, "market": market, "reason": "invalid_quote"})
                continue
            account = engine.get_account(refresh_quotes=False)
            available_cash = float(account.get("cash_usd") or 0.0) if market == "NASDAQ" else float(account.get("cash_krw") or 0.0)
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

    final_account = engine.get_account(refresh_quotes=True)
    return {
        "ok": True,
        "ran_at": _now_iso(),
        "executed_buy_count": len(executed_buys),
        "executed_sell_count": len(executed_sells),
        "executed_buys": executed_buys,
        "executed_sells": executed_sells,
        "skipped": skipped[:50],
        "account": final_account,
    }


def _auto_trader_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        with _auto_trader_lock:
            cfg = dict(_auto_trader_state.get("config") or _default_auto_trader_config())
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
    global _auto_trader_thread, _auto_trader_stop_event
    with _auto_trader_lock:
        if _auto_trader_state.get("running") and _auto_trader_thread and _auto_trader_thread.is_alive():
            return {"ok": True, "running": True, "message": "이미 실행 중입니다.", "state": dict(_auto_trader_state)}
        merged = _default_auto_trader_config()
        merged.update(config or {})
        merged["interval_seconds"] = max(30, min(3600, int(merged.get("interval_seconds") or 300)))
        merged["max_positions_per_market"] = max(1, min(20, int(merged.get("max_positions_per_market") or 5)))
        merged["daily_buy_limit"] = max(1, min(200, int(merged.get("daily_buy_limit") or 20)))
        merged["daily_sell_limit"] = max(1, min(200, int(merged.get("daily_sell_limit") or 20)))
        merged["max_orders_per_symbol_per_day"] = max(1, min(10, int(merged.get("max_orders_per_symbol_per_day") or 1)))
        merged["min_score"] = max(0.0, min(100.0, float(merged.get("min_score") or 60.0)))
        merged["rsi_min"] = max(10.0, min(90.0, float(merged.get("rsi_min") or 45.0)))
        merged["rsi_max"] = max(10.0, min(90.0, float(merged.get("rsi_max") or 68.0)))
        if merged["rsi_min"] > merged["rsi_max"]:
            merged["rsi_min"], merged["rsi_max"] = merged["rsi_max"], merged["rsi_min"]
        merged["volume_ratio_min"] = max(0.5, min(5.0, float(merged.get("volume_ratio_min") or 1.2)))
        merged["stop_loss_pct"] = max(1.0, min(50.0, float(merged.get("stop_loss_pct") or 7.0)))
        merged["take_profit_pct"] = max(1.0, min(100.0, float(merged.get("take_profit_pct") or 18.0)))
        merged["max_holding_days"] = max(1, min(180, int(merged.get("max_holding_days") or 30)))
        signal_interval = str(merged.get("signal_interval") or "5m").strip().lower()
        if signal_interval not in {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1d"}:
            signal_interval = "5m"
        merged["signal_interval"] = signal_interval
        signal_range = str(merged.get("signal_range") or "5d").strip().lower()
        if signal_range not in {"1d", "5d", "1mo", "3mo", "6mo", "1y"}:
            signal_range = "5d"
        if signal_interval == "1d" and signal_range in {"1d", "5d"}:
            signal_range = "6mo"
        merged["signal_range"] = signal_range
        markets = merged.get("markets") or ["KOSPI", "NASDAQ"]
        if not isinstance(markets, list):
            markets = ["KOSPI", "NASDAQ"]
        merged["markets"] = [m for m in markets if m in {"KOSPI", "NASDAQ"}] or ["KOSPI", "NASDAQ"]

        _auto_trader_stop_event = threading.Event()
        _auto_trader_thread = threading.Thread(target=_auto_trader_loop, args=(_auto_trader_stop_event,), daemon=True)
        _auto_trader_state["running"] = True
        _auto_trader_state["started_at"] = _now_iso()
        _auto_trader_state["config"] = merged
        _auto_trader_state["last_error"] = ""
        _auto_trader_thread.start()
        return {"ok": True, "running": True, "state": dict(_auto_trader_state)}


def _stop_auto_trader() -> dict:
    global _auto_trader_thread, _auto_trader_stop_event
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
    if state.get("running") and not (_auto_trader_thread and _auto_trader_thread.is_alive()):
        state["running"] = False
        with _auto_trader_lock:
            _auto_trader_state["running"] = False
    engine = _get_paper_engine()
    account = engine.get_account(refresh_quotes=False)
    return {"ok": True, "state": state, "account": account}


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(values[:-1], values[1:]):
        delta = current - prev
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for idx in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _fetch_chart_history(symbol: str, range_: str = "6mo", interval: str = "1d") -> dict | None:
    payload = json.loads(_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval={interval}",
        timeout=5,
    ))
    result = payload.get("chart", {}).get("result", [])
    if not result:
        return None
    chart = result[0]
    quote = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    volumes = quote.get("volume", [])

    history = []
    for close, volume in zip(closes, volumes):
        if close is None:
            continue
        history.append({
            "close": float(close),
            "volume": float(volume) if volume is not None else None,
        })
    return {"history": history}


def _fetch_kis_domestic_history(code: str, lookback_days: int = 180) -> dict | None:
    client = _get_kis_client()
    if client is None:
        return None

    end_date = datetime.datetime.now(_KST).strftime("%Y%m%d")
    start_date = (datetime.datetime.now(_KST) - datetime.timedelta(days=lookback_days)).strftime("%Y%m%d")
    try:
        rows = client.get_domestic_daily_history(
            code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        return None

    history = []
    for item in rows:
        close = item.get("close")
        volume = item.get("volume")
        if close is None:
            continue
        history.append({
            "close": float(close),
            "volume": float(volume) if volume is not None else None,
        })
    return {"history": history} if history else None


def _compute_technical_snapshot(
    code: str,
    market: str,
    *,
    range_: str = "6mo",
    interval: str = "1d",
) -> dict | None:
    symbol = _resolve_chart_symbol(code, market)
    if not symbol:
        return None

    cache_key = f"{market}:{code}:{range_}:{interval}"
    cached = _technical_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] < TECHNICAL_CACHE_TTL:
        return cached["data"]

    normalized_market = market.strip().upper()
    chart = _fetch_kis_domestic_history(code) if normalized_market == "KOSPI" and interval == "1d" else None
    if not chart:
        chart = _fetch_chart_history(symbol, range_=range_, interval=interval)
    if not chart:
        return None

    history = chart["history"]
    closes = [item["close"] for item in history if item.get("close") is not None]
    volumes = [item["volume"] for item in history if item.get("volume") is not None]
    if len(closes) < 35:
        return None

    current_price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    sma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    volume = volumes[-1] if volumes else None
    volume_avg20 = (sum(volumes[-20:]) / 20) if len(volumes) >= 20 else None
    volume_ratio = (volume / volume_avg20) if volume and volume_avg20 else None

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_series = [fast - slow for fast, slow in zip(ema12[-len(ema26):], ema26)]
    signal_series = _ema(macd_series, 9)
    macd = macd_series[-1] if macd_series else None
    macd_signal = signal_series[-1] if signal_series else None
    macd_hist = (macd - macd_signal) if macd is not None and macd_signal is not None else None
    rsi14 = _rsi(closes, 14)

    trend = "neutral"
    if sma20 is not None and sma60 is not None:
        if current_price > sma20 and sma20 > sma60:
            trend = "bullish"
        elif current_price < sma20 and sma20 < sma60:
            trend = "bearish"

    snapshot = {
        "current_price": round(current_price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "sma20": round(sma20, 2) if sma20 is not None else None,
        "sma60": round(sma60, 2) if sma60 is not None else None,
        "volume": int(volume) if volume is not None else None,
        "volume_avg20": int(volume_avg20) if volume_avg20 is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "rsi14": round(rsi14, 1) if rsi14 is not None else None,
        "macd": round(macd, 3) if macd is not None else None,
        "macd_signal": round(macd_signal, 3) if macd_signal is not None else None,
        "macd_hist": round(macd_hist, 3) if macd_hist is not None else None,
        "trend": trend,
    }
    _technical_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").strip()


def _parse_signed_number(text: str) -> int | None:
    cleaned = text.replace(",", "").replace(" ", "")
    match = re.search(r"([+-]?\d+)", cleaned)
    if not match:
        return None
    return int(match.group(1))


def _fetch_investor_flow_snapshot(code: str, market: str) -> dict | None:
    if market.strip().upper() not in {"KOSPI", "KOSDAQ"} or not code.strip().isdigit():
        return None

    cache_key = f"{market}:{code}"
    cached = _investor_flow_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] < INVESTOR_FLOW_CACHE_TTL:
        return cached["data"]

    req = urllib.request.Request(
        f"https://finance.naver.com/item/frgn.naver?code={code}",
        headers=_HEADERS,
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        html = response.read().decode("euc-kr", "replace")

    table_match = re.search(
        r"외국인ㆍ기관.*?순매매 거래량.*?<table[^>]*class=\"type2\"[^>]*>(.*?)</table>",
        html,
        re.S,
    )
    if not table_match:
        return None

    rows = []
    for row_html in re.findall(r"<tr[^>]*onMouseOver=.*?>(.*?)</tr>", table_match.group(1), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
        if len(cells) < 7:
            continue
        date = _strip_html(cells[0])
        institution_net = _parse_signed_number(_strip_html(cells[5]))
        foreign_net = _parse_signed_number(_strip_html(cells[6]))
        if not date:
            continue
        rows.append({
            "date": date,
            "institution_net": institution_net or 0,
            "foreign_net": foreign_net or 0,
        })
        if len(rows) >= 5:
            break

    if not rows:
        return None

    snapshot = {
        "date": rows[0]["date"],
        "foreign_net_1d": rows[0]["foreign_net"],
        "foreign_net_5d": sum(row["foreign_net"] for row in rows[:5]),
        "institution_net_1d": rows[0]["institution_net"],
        "institution_net_5d": sum(row["institution_net"] for row in rows[:5]),
    }
    _investor_flow_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot


# ──────────────────────────────────────────
#  Market snapshot
# ──────────────────────────────────────────
def _build_market() -> dict:
    result: dict = {}

    tasks = {
        "kospi": lambda: _naver_index("KOSPI"),
        "kosdaq": lambda: _naver_index("KOSDAQ"),
        "usd_krw": _usd_krw,
        "sp100": lambda: _yahoo_chart("^OEX"),
        "nasdaq": lambda: _stooq_daily("%5Endx"),
        "wti": lambda: _stooq_spot("cl.f"),
    }

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(task): key for key, task in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                value = future.result()
                if key == "usd_krw":
                    if value:
                        result["usd_krw"] = round(value, 2)
                    continue

                price, change_pct = value
                if price:
                    result[key] = round(price, 2)
                    if change_pct is not None:
                        result[f"{key}_pct"] = round(change_pct, 2)
            except Exception as e:
                result[f"{key}_err"] = str(e)

    result["updated_at"] = datetime.datetime.now(_KST).strftime("%H:%M:%S KST")
    return result


def _list_report_dates() -> list[str]:
    pattern = os.path.join(REPORTS_DIR, "*_analysis.json")
    dates = []
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)
        if base.endswith("_analysis.json"):
            dates.append(base.replace("_analysis.json", ""))
    return sorted(set(dates))


def _pick_date(requested: str | None = None) -> str | None:
    dates = _list_report_dates()
    if not dates:
        return None
    if requested and requested in dates:
        return requested
    return dates[-1]


def _previous_date(current: str | None = None) -> str | None:
    dates = _list_report_dates()
    if len(dates) < 2:
        return None
    if current and current in dates:
        index = dates.index(current)
        if index > 0:
            return dates[index - 1]
    return dates[-2]


def _report_file(date: str, suffix: str) -> str:
    return os.path.join(REPORTS_DIR, f"{date}_{suffix}.json")


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_report_json(suffix: str, date: str | None = None, latest: bool = True) -> dict:
    target_date = _pick_date(date) if latest else date
    if not target_date:
        return {}

    path = _report_file(target_date, suffix)
    if not os.path.exists(path):
        return {}
    return _read_json(path)


def _build_compare_payload(base_date: str | None = None, prev_date: str | None = None) -> dict:
    base_date = _pick_date(base_date)
    if not base_date:
        return {"error": "비교할 리포트가 없습니다."}

    prev_date = _previous_date(base_date) if prev_date is None else prev_date
    if not prev_date:
        return {"error": "전일 비교 데이터가 없습니다.", "base_date": base_date}

    base_analysis = _load_report_json("analysis", base_date, latest=False)
    prev_analysis = _load_report_json("analysis", prev_date, latest=False)
    base_recommendations = _load_report_json("recommendations", base_date, latest=False)
    prev_recommendations = _load_report_json("recommendations", prev_date, latest=False)
    base_context = _load_report_json("market_context", base_date, latest=False)
    prev_context = _load_report_json("market_context", prev_date, latest=False)
    base_today_picks = _load_report_json("today_picks", base_date, latest=False) or _fallback_today_picks(base_date)
    prev_today_picks = _load_report_json("today_picks", prev_date, latest=False) or _fallback_today_picks(prev_date)

    base_rec_map = {}
    prev_rec_map = {}
    for item in base_recommendations.get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        base_rec_map[key] = item
        base_rec_map[item.get("name")] = item
    for item in prev_recommendations.get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        prev_rec_map[key] = item
        prev_rec_map[item.get("name")] = item

    recommendation_changes = []
    for current in base_recommendations.get("recommendations", []):
        key = (current.get("ticker") or "").split(".")[0] or current.get("name")
        previous = prev_rec_map.get(key) or prev_rec_map.get(current.get("name"))
        if not previous:
            continue
        if current.get("signal") != previous.get("signal") or current.get("score") != previous.get("score"):
            recommendation_changes.append({
                "name": current.get("name"),
                "ticker": current.get("ticker", ""),
                "current_signal": current.get("signal"),
                "previous_signal": previous.get("signal"),
                "score_diff": round(float(current.get("score", 0)) - float(previous.get("score", 0)), 1),
            })

    base_pick_map = {item.get("code") or item.get("name"): item for item in base_today_picks.get("picks", [])}
    prev_pick_map = {item.get("code") or item.get("name"): item for item in prev_today_picks.get("picks", [])}
    today_pick_changes = []
    for key, current in base_pick_map.items():
        previous = prev_pick_map.get(key)
        if not previous:
            today_pick_changes.append({
                "name": current.get("name"),
                "status": "new",
                "current_signal": current.get("signal"),
                "score_diff": current.get("score"),
            })
            continue
        if current.get("signal") != previous.get("signal") or current.get("score") != previous.get("score"):
            today_pick_changes.append({
                "name": current.get("name"),
                "status": "changed",
                "current_signal": current.get("signal"),
                "previous_signal": previous.get("signal"),
                "score_diff": round(float(current.get("score", 0)) - float(previous.get("score", 0)), 1),
            })

    base_ctx = base_context.get("context", {})
    prev_ctx = prev_context.get("context", {})
    context_changes = []
    for field in ("regime", "risk_level", "inflation_signal", "labor_signal", "policy_signal", "yield_curve_signal", "dollar_signal"):
        if base_ctx.get(field) != prev_ctx.get(field):
            context_changes.append({
                "field": field,
                "previous": prev_ctx.get(field),
                "current": base_ctx.get(field),
            })

    base_risks = set(base_ctx.get("risks", []))
    prev_risks = set(prev_ctx.get("risks", []))

    return {
        "base_date": base_date,
        "prev_date": prev_date,
        "summary_lines": {
            "base": base_analysis.get("summary_lines", []),
            "prev": prev_analysis.get("summary_lines", []),
        },
        "signal_counts": {
            "base": base_recommendations.get("signal_counts", {}),
            "prev": prev_recommendations.get("signal_counts", {}),
        },
        "recommendation_changes": sorted(recommendation_changes, key=lambda item: abs(item["score_diff"]), reverse=True)[:10],
        "today_pick_changes": sorted(today_pick_changes, key=lambda item: abs(item["score_diff"]), reverse=True)[:10],
        "context_changes": context_changes,
        "new_risks": sorted(base_risks - prev_risks),
        "resolved_risks": sorted(prev_risks - base_risks),
    }


# ──────────────────────────────────────────
#  Analysis cache (reads *_analysis.json)
# ──────────────────────────────────────────
def _get_analysis() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_analysis.json")), reverse=True)
    if not files:
        return {"error": "분석 결과가 없습니다. run_once.py를 먼저 실행하세요."}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    # 파일이 변경된 경우에만 다시 읽기
    if _analysis_cache["data"] is not None and mtime == _analysis_cache["mtime"]:
        return _analysis_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _analysis_cache["data"] = data
    _analysis_cache["mtime"] = mtime
    return data


def _get_recommendations() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_recommendations.json")), reverse=True)
    if not files:
        return {"error": "추천 결과가 없습니다. run_once.py를 먼저 실행하세요.", "recommendations": []}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    if _recommendation_cache["data"] is not None and mtime == _recommendation_cache["mtime"]:
        return _recommendation_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _recommendation_cache["data"] = data
    _recommendation_cache["mtime"] = mtime
    return data


def _get_today_picks() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_today_picks.json")), reverse=True)
    if not files:
        fallback = _fallback_today_picks()
        if fallback.get("picks"):
            return fallback
        return {"error": "오늘의 추천 결과가 없습니다.", "picks": []}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    if _today_picks_cache["data"] is not None and mtime == _today_picks_cache["mtime"]:
        return _today_picks_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _today_picks_cache["data"] = data
    _today_picks_cache["mtime"] = mtime
    return data


def _get_ai_signals() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_ai_signals.json")), reverse=True)
    if not files:
        return {"signals": []}

    latest = files[0]
    mtime = os.path.getmtime(latest)

    if _ai_signals_cache["data"] is not None and mtime == _ai_signals_cache["mtime"]:
        return _ai_signals_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _ai_signals_cache["data"] = data
    _ai_signals_cache["mtime"] = mtime
    return data


def _fallback_today_picks(date: str | None = None) -> dict:
    recommendations = _get_recommendations() if not date else _load_report_json("recommendations", date, latest=False)
    if not recommendations.get("recommendations"):
        return {"picks": []}

    picks = []
    for item in recommendations.get("recommendations", [])[:8]:
        ticker = (item.get("ticker") or "").split(".")[0]
        picks.append({
            "name": item.get("name"),
            "code": ticker,
            "market": "KOSPI" if item.get("ticker", "").endswith(".KS") else "KOSDAQ" if item.get("ticker", "").endswith(".KQ") else "",
            "sector": item.get("sector"),
            "signal": item.get("signal"),
            "score": item.get("score"),
            "confidence": item.get("confidence", 55),
            "reasons": item.get("reasons", []),
            "risks": item.get("risks", []),
            "catalysts": item.get("reasons", [])[:2],
            "related_news": [],
        })

    return {
        "generated_at": recommendations.get("generated_at"),
        "date": recommendations.get("date"),
        "market_tone": "fallback",
        "strategy": "recommendation-fallback",
        "picks": picks,
    }


def _get_macro() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_macro.json")), reverse=True)
    if not files:
        return {"error": "거시 지표 결과가 없습니다."}

    latest = files[0]
    mtime = os.path.getmtime(latest)
    if _macro_cache["data"] is not None and mtime == _macro_cache["mtime"]:
        return _macro_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _macro_cache["data"] = data
    _macro_cache["mtime"] = mtime
    return data


def _get_market_context() -> dict:
    files = sorted(glob.glob(os.path.join(
        REPORTS_DIR, "*_market_context.json")), reverse=True)
    if not files:
        return {"error": "시장 컨텍스트 결과가 없습니다."}

    latest = files[0]
    mtime = os.path.getmtime(latest)
    if _market_context_cache["data"] is not None and mtime == _market_context_cache["mtime"]:
        return _market_context_cache["data"]

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    _market_context_cache["data"] = data
    _market_context_cache["mtime"] = mtime
    return data


def _get_market_dashboard() -> dict:
    market = _market_cache["data"]
    now = time.time()
    if market is None or now - _market_cache["ts"] > CACHE_TTL:
        market = _build_market()
        _market_cache["data"] = market
        _market_cache["ts"] = now

    return {
        "market": market,
        "macro": _get_macro(),
        "context": _get_market_context(),
    }


def _get_kospi_backtest() -> dict:
    path = os.path.join(REPORTS_DIR, "kospi_backtest_latest.json")
    if not os.path.exists(path):
        return {"error": "백테스트 결과가 없습니다. scripts/run_kospi_backtest.py를 먼저 실행하세요."}

    mtime = os.path.getmtime(path)
    if _backtest_cache["data"] is not None and mtime == _backtest_cache["mtime"]:
        return _backtest_cache["data"]

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    _backtest_cache["data"] = data
    _backtest_cache["mtime"] = mtime
    return data


def _parse_backtest_config(query: dict[str, list[str]]) -> BacktestConfig:
    market_scope = (query.get("market_scope", ["kospi"])[0] or "kospi").strip().lower()
    if market_scope == "nasdaq":
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

    rsi_min = _parse_float("rsi_min", 45.0, 10.0, 90.0)
    rsi_max = _parse_float("rsi_max", 68.0, 10.0, 90.0)
    if rsi_min > rsi_max:
        rsi_min, rsi_max = rsi_max, rsi_min

    return BacktestConfig(
        initial_cash=_parse_float("initial_cash", initial_default, initial_minimum, initial_maximum),
        base_currency=base_currency,
        max_positions=_parse_int("max_positions", 5, 1, 20),
        max_holding_days=_parse_int("max_holding_days", 30, 5, 180),
        lookback_days=_parse_int("lookback_days", 1095, 180, 1825),
        markets=markets,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        volume_ratio_min=_parse_float("volume_ratio_min", 1.2, 0.5, 5.0),
        stop_loss_pct=_parse_optional_float("stop_loss_pct", 1.0, 50.0),
        take_profit_pct=_parse_optional_float("take_profit_pct", 1.0, 100.0),
    )


def _config_cache_key(config: BacktestConfig) -> str:
    return json.dumps(
        {
            "initial_cash": config.initial_cash,
            "base_currency": config.base_currency,
            "max_positions": config.max_positions,
            "max_holding_days": config.max_holding_days,
            "lookback_days": config.lookback_days,
            "markets": list(config.markets),
            "rsi_min": config.rsi_min,
            "rsi_max": config.rsi_max,
            "volume_ratio_min": config.volume_ratio_min,
            "stop_loss_pct": config.stop_loss_pct,
            "take_profit_pct": config.take_profit_pct,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _run_backtest(config: BacktestConfig) -> dict:
    cache_key = _config_cache_key(config)
    cached = _backtest_run_cache.get(cache_key)
    if cached:
        return cached

    result = run_kospi_backtest(config)
    _backtest_run_cache[cache_key] = result
    if len(_backtest_run_cache) > 12:
        oldest_key = next(iter(_backtest_run_cache))
        if oldest_key != cache_key:
            _backtest_run_cache.pop(oldest_key, None)
    return result


# ──────────────────────────────────────────
#  HTTP Handler
# ──────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/live-market":
            self._serve_market()
        elif parsed.path == "/api/reports":
            self._serve_reports()
        elif parsed.path == "/api/analysis":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_analysis(date or None)
        elif parsed.path == "/api/recommendations":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_recommendations(date or None)
        elif parsed.path == "/api/today-picks":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_today_picks(date or None)
        elif parsed.path == "/api/compare":
            query = parse_qs(parsed.query)
            self._serve_compare(query.get("base", [""])[0] or None, query.get("prev", [""])[0] or None)
        elif parsed.path == "/api/macro/latest":
            self._serve_macro()
        elif parsed.path == "/api/market-context/latest":
            date = parse_qs(parsed.query).get("date", [""])[0]
            self._serve_market_context(date or None)
        elif parsed.path == "/api/market-dashboard":
            self._serve_market_dashboard()
        elif parsed.path == "/api/backtest/run":
            self._serve_backtest_run(parse_qs(parsed.query))
        elif parsed.path == "/api/backtest/kospi":
            self._serve_kospi_backtest()
        elif parsed.path.startswith("/api/stock-search"):
            q = parse_qs(parsed.query).get("q", [""])[0]
            self._serve_stock_search(q)
        elif parsed.path.startswith("/api/stock/"):
            code = parsed.path[len("/api/stock/"):]
            market = parse_qs(parsed.query).get("market", [""])[0]
            self._serve_stock_price(code, market)
        elif parsed.path == "/api/paper/account":
            query = parse_qs(parsed.query)
            refresh_quotes = (query.get("refresh", ["1"])[0] or "1").strip() != "0"
            self._serve_paper_account(refresh_quotes=refresh_quotes)
        elif parsed.path == "/api/paper/engine/status":
            self._serve_paper_engine_status()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/watchlist-actions":
            self._serve_watchlist_actions()
            return
        if self.path == "/api/paper/order":
            self._serve_paper_order()
            return
        if self.path == "/api/paper/reset":
            self._serve_paper_reset()
            return
        if self.path == "/api/paper/auto-invest":
            self._serve_paper_auto_invest()
            return
        if self.path == "/api/paper/engine/start":
            self._serve_paper_engine_start()
            return
        if self.path == "/api/paper/engine/stop":
            self._serve_paper_engine_stop()
            return
        self.send_response(404)
        self.end_headers()

    def _serve_market(self):
        now = time.time()
        if _market_cache["data"] is None or now - _market_cache["ts"] > CACHE_TTL:
            try:
                _market_cache["data"] = _build_market()
                _market_cache["ts"] = now
            except Exception as e:
                self._json_resp(500, {"error": str(e)})
                return
        self._json_resp(200, _market_cache["data"])

    def _serve_reports(self):
        self._json_resp(200, {"dates": _list_report_dates()})

    def _serve_analysis(self, date: str | None = None):
        try:
            data = _get_analysis() if not date else _load_report_json("analysis", date, latest=False) or {"error": "해당 날짜 분석이 없습니다."}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_recommendations(self, date: str | None = None):
        try:
            data = _get_recommendations() if not date else _load_report_json("recommendations", date, latest=False) or {"error": "해당 날짜 추천이 없습니다.", "recommendations": []}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "recommendations": []})

    def _serve_today_picks(self, date: str | None = None):
        try:
            if not date:
                data = _get_today_picks()
            else:
                data = _load_report_json("today_picks", date, latest=False) or _fallback_today_picks(date) or {"error": "해당 날짜 오늘의 추천이 없습니다.", "picks": []}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "picks": []})

    def _serve_compare(self, base_date: str | None, prev_date: str | None):
        try:
            self._json_resp(200, _build_compare_payload(base_date, prev_date))
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_macro(self):
        try:
            data = _get_macro()
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_market_context(self, date: str | None = None):
        try:
            data = _get_market_context() if not date else _load_report_json("market_context", date, latest=False) or {"error": "해당 날짜 시장 컨텍스트가 없습니다."}
            self._json_resp(200, data)
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_market_dashboard(self):
        try:
            self._json_resp(200, _get_market_dashboard())
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_kospi_backtest(self):
        try:
            self._json_resp(200, _get_kospi_backtest())
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_backtest_run(self, query: dict[str, list[str]]):
        try:
            config = _parse_backtest_config(query)
            self._json_resp(200, _run_backtest(config))
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_stock_search(self, query: str):
        if not query:
            self._json_resp(200, {"results": []})
            return
        try:
            url = f"https://ac.stock.naver.com/ac?q={quote(query)}&target=stock,index"
            raw = json.loads(_get(url))
            items = raw.get("items", [])
            results = [
                {
                    "name":   r["name"],
                    "code":   r["code"],
                    "market": r.get("typeCode", r.get("typeName", "")),
                }
                for r in items[:10]
                if _is_allowed_market_label(r.get("typeCode", ""), r.get("typeName", ""))
            ]
            self._json_resp(200, {"results": results})
        except Exception as e:
            self._json_resp(500, {"error": str(e)})

    def _serve_watchlist_actions(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw or "{}")
            items = payload.get("items", [])
            base_date = payload.get("date") or _pick_date()
            prev_date = _previous_date(base_date)
            today_picks = _get_today_picks() if not payload.get("date") else (_load_report_json("today_picks", base_date, latest=False) or _fallback_today_picks(base_date))
            ai_signals = _get_ai_signals() if not payload.get("date") else (_load_report_json("ai_signals", base_date, latest=False) or {"signals": []})
            recommendations = _get_recommendations() if not payload.get("date") else _load_report_json("recommendations", base_date, latest=False)
            previous_recommendations = _load_report_json("recommendations", prev_date, latest=False) if prev_date else {}
            previous_today_picks = (_load_report_json("today_picks", prev_date, latest=False) or _fallback_today_picks(prev_date)) if prev_date else {}
            previous_ai_signals = (_load_report_json("ai_signals", prev_date, latest=False) or {"signals": []}) if prev_date else {"signals": []}
            enriched_items = [dict(item) for item in items]
            with ThreadPoolExecutor(max_workers=max(1, min(len(enriched_items), 6))) as executor:
                futures = {
                    executor.submit(_compute_technical_snapshot, item.get("code", ""), item.get("market", "")): idx
                    for idx, item in enumerate(enriched_items)
                    if item.get("code")
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    technicals = future.result()
                    enriched = enriched_items[idx]
                    if technicals:
                        if enriched.get("price") is None and technicals.get("current_price") is not None:
                            enriched["price"] = technicals["current_price"]
                        if enriched.get("change_pct") is None and technicals.get("change_pct") is not None:
                            enriched["change_pct"] = technicals["change_pct"]
                        enriched["technicals"] = technicals
                    flow = _fetch_investor_flow_snapshot(enriched.get("code", ""), enriched.get("market", ""))
                    if flow:
                        enriched["investor_flow"] = flow
            result = build_watchlist_actions(
                enriched_items,
                today_picks,
                recommendations,
                previous_recommendations,
                previous_today_picks,
                ai_signals,
                previous_ai_signals,
            )
            self._json_resp(200, result)
        except Exception as e:
            self._json_resp(500, {"error": str(e), "actions": []})

    def _serve_stock_price(self, code: str, market: str = ""):
        try:
            self._json_resp(200, _resolve_stock_quote(code, market))
        except Exception as e:
            technicals = _compute_technical_snapshot(code, market) if market else None
            if technicals:
                self._json_resp(200, {
                    "code": code,
                    "name": code,
                    "price": technicals.get("current_price"),
                    "change_pct": technicals.get("change_pct"),
                    "market": market,
                })
                return
            self._json_resp(500, {"error": str(e)})

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}

    def _serve_paper_account(self, *, refresh_quotes: bool = True):
        try:
            engine = _get_paper_engine()
            self._json_resp(200, engine.get_account(refresh_quotes=refresh_quotes))
        except Exception as exc:
            self._json_resp(500, {"error": str(exc)})

    def _serve_paper_order(self):
        try:
            payload = self._read_json_body()
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
            self._json_resp(status, result)
        except Exception as exc:
            self._json_resp(500, {"ok": False, "error": str(exc)})

    def _serve_paper_reset(self):
        try:
            payload = self._read_json_body()
            initial_cash_krw_raw = payload.get("initial_cash_krw")
            initial_cash_usd_raw = payload.get("initial_cash_usd")
            paper_days_raw = payload.get("paper_days")
            initial_cash_krw = float(initial_cash_krw_raw) if initial_cash_krw_raw not in (None, "") else None
            initial_cash_usd = float(initial_cash_usd_raw) if initial_cash_usd_raw not in (None, "") else None
            paper_days = int(paper_days_raw) if paper_days_raw not in (None, "") else None
            engine = _get_paper_engine()
            self._json_resp(200, {
                "ok": True,
                "account": engine.reset(
                    initial_cash_krw=initial_cash_krw,
                    initial_cash_usd=initial_cash_usd,
                    paper_days=paper_days,
                ),
            })
        except Exception as exc:
            self._json_resp(500, {"ok": False, "error": str(exc)})

    def _serve_paper_auto_invest(self):
        try:
            payload = self._read_json_body()
            market = str(payload.get("market") or "NASDAQ").strip().upper()
            try:
                max_positions_raw = payload.get("max_positions")
                max_positions = int(5 if max_positions_raw in (None, "") else max_positions_raw)
            except (TypeError, ValueError):
                max_positions = 5
            try:
                min_score_raw = payload.get("min_score")
                min_score = float(60.0 if min_score_raw in (None, "") else min_score_raw)
            except (TypeError, ValueError):
                min_score = 60.0
            include_neutral = bool(payload.get("include_neutral") is True)
            max_positions = max(1, min(20, max_positions))
            min_score = max(0.0, min(100.0, min_score))
            result = _auto_invest_picks(
                market=market,
                max_positions=max_positions,
                min_score=min_score,
                include_neutral=include_neutral,
            )
            status = 200 if result.get("ok") else 400
            self._json_resp(status, result)
        except Exception as exc:
            self._json_resp(500, {"ok": False, "error": str(exc)})

    def _serve_paper_engine_start(self):
        try:
            payload = self._read_json_body()
            self._json_resp(200, _start_auto_trader(payload))
        except Exception as exc:
            self._json_resp(500, {"ok": False, "error": str(exc)})

    def _serve_paper_engine_stop(self):
        try:
            self._json_resp(200, _stop_auto_trader())
        except Exception as exc:
            self._json_resp(500, {"ok": False, "error": str(exc)})

    def _serve_paper_engine_status(self):
        try:
            self._json_resp(200, _auto_trader_status())
        except Exception as exc:
            self._json_resp(500, {"ok": False, "error": str(exc)})

    def _json_resp(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 관심 있는 API 호출만 로그
        msg = format % args if args else format
        if '/api/' in msg or 'GET' in msg:
            print(f"[{self.client_address[0]}] {msg}", flush=True)


def run(host: str = "127.0.0.1", port: int = PORT):
    server = HTTPServer((host, port), Handler)
    print(f"✅ API server running on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
