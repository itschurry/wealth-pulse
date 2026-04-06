import datetime
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache as _cache
from helpers import _HEADERS, _KST, _get_kis_client, _parse_signed_number, _strip_html
from routes.market import _overseas_exchange_candidates
from routes.reports import (
    _fallback_today_picks,
    _get_recommendations,
    _get_today_picks,
    _load_report_json,
    _pick_date,
    _previous_date,
)
from analyzer.technical_snapshot import fetch_technical_snapshot
from analyzer.today_picks_engine import build_watchlist_actions
from config.settings import LOGS_DIR

WATCHLIST_PATH = LOGS_DIR / "watchlist.json"


def _sanitize_watchlist_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    code = str(item.get("code") or "").strip().upper()
    name = str(item.get("name") or "").strip()
    market = str(item.get("market") or "").strip().upper()
    if not code or not name or not market:
        return None
    sanitized = {
        "code": code,
        "name": name,
        "market": market,
    }
    price = item.get("price")
    change_pct = item.get("change_pct")
    try:
        if price not in (None, ""):
            sanitized["price"] = float(price)
    except (TypeError, ValueError):
        pass
    try:
        if change_pct not in (None, ""):
            sanitized["change_pct"] = float(change_pct)
    except (TypeError, ValueError):
        pass
    return sanitized


def _load_watchlist() -> list[dict]:
    try:
        if not WATCHLIST_PATH.exists():
            return []
        raw = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw:
        sanitized = _sanitize_watchlist_item(entry)
        if not sanitized:
            continue
        key = (sanitized["market"], sanitized["code"])
        if key in seen:
            continue
        seen.add(key)
        items.append(sanitized)
    return items


def _save_watchlist(items: list[dict]) -> list[dict]:
    sanitized_items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in items:
        sanitized = _sanitize_watchlist_item(entry)
        if not sanitized:
            continue
        key = (sanitized["market"], sanitized["code"])
        if key in seen:
            continue
        seen.add(key)
        sanitized_items.append(sanitized)
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(
        json.dumps(sanitized_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return sanitized_items


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


def _fetch_kis_history(code: str, market: str, lookback_days: int = 180) -> dict | None:
    client = _get_kis_client()
    if client is None:
        return None

    normalized_market = market.strip().upper()
    end_date = datetime.datetime.now(_KST).strftime("%Y%m%d")
    start_date = (datetime.datetime.now(_KST) - datetime.timedelta(days=lookback_days)).strftime("%Y%m%d")
    try:
        if normalized_market == "KOSPI":
            rows = client.get_domestic_daily_history(
                code,
                start_date=start_date,
                end_date=end_date,
            )
        elif normalized_market in {"NASDAQ", "NYSE", "AMEX"}:
            rows = []
            for exchange in _overseas_exchange_candidates(normalized_market):
                try:
                    rows = client.get_overseas_daily_history(
                        code,
                        exchange=exchange,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception:
                    rows = []
                    continue
                if rows:
                    break
        else:
            return None
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
            "high": float(item.get("high")) if item.get("high") is not None else float(close),
            "low": float(item.get("low")) if item.get("low") is not None else float(close),
            "volume": float(volume) if volume is not None else None,
        })
    return {"history": history} if history else None


def _lookback_days(range_: str) -> int:
    normalized = (range_ or "").strip().lower()
    if normalized == "1d":
        return 5
    if normalized == "5d":
        return 10
    if normalized == "1mo":
        return 45
    if normalized == "3mo":
        return 120
    if normalized == "1y":
        return 420
    return 180


def _compute_technical_snapshot(
    code: str,
    market: str,
    *,
    range_: str = "6mo",
    interval: str = "1d",
) -> dict | None:
    return fetch_technical_snapshot(code, market, range_=range_, interval=interval)


def _fetch_investor_flow_snapshot(code: str, market: str) -> dict | None:
    if market.strip().upper() not in {"KOSPI", "KOSDAQ"} or not code.strip().isdigit():
        return None

    cache_key = f"{market}:{code}"
    cached = _cache._investor_flow_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] < _cache.INVESTOR_FLOW_CACHE_TTL:
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
    _cache._investor_flow_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot


def handle_watchlist_get() -> tuple[int, dict]:
    try:
        return 200, {"items": _load_watchlist()}
    except Exception as exc:
        return 500, {"error": str(exc), "items": []}


def handle_watchlist_save(payload: dict) -> tuple[int, dict]:
    try:
        items = payload.get("items", [])
        if not isinstance(items, list):
            return 400, {"ok": False, "error": "items 형식이 올바르지 않습니다.", "items": _load_watchlist()}
        saved = _save_watchlist(items)
        return 200, {"ok": True, "items": saved}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc), "items": _load_watchlist()}


def handle_watchlist_actions(payload: dict) -> tuple[int, dict]:
    try:
        items = payload.get("items", [])
        base_date = payload.get("date") or _pick_date()
        prev_date = _previous_date(base_date)
        today_picks = (
            _get_today_picks() if not payload.get("date")
            else (_load_report_json("today_picks", base_date, latest=False) or _fallback_today_picks(base_date))
        )
        recommendations = (
            _get_recommendations() if not payload.get("date")
            else _load_report_json("recommendations", base_date, latest=False)
        )
        previous_recommendations = _load_report_json("recommendations", prev_date, latest=False) if prev_date else {}
        previous_today_picks = (
            (_load_report_json("today_picks", prev_date, latest=False) or _fallback_today_picks(prev_date))
            if prev_date else {}
        )
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
        )
        return 200, result
    except Exception as e:
        return 500, {"error": str(e), "actions": []}
