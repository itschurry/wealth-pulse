import datetime
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache as _cache
from helpers import _HEADERS, _KST, _get_kis_client, _normalize_text
from broker.kis_client import KISConfigError
from config.company_catalog import get_company_catalog
from market_utils import lookup_company_listing, normalize_market, resolve_quote_market

_ALLOWED_SEARCH_MARKETS = {"KOSPI", "KOSDAQ", "NASDAQ"}
_SEARCH_CATALOG = [
    entry for entry in get_company_catalog(scope="core")
    if entry.market in _ALLOWED_SEARCH_MARKETS
]


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
    rows = [line for line in text.strip().splitlines()
            if line and not line.startswith("Date")]
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
    rows = [line for line in text.strip().splitlines()
            if line and not line.startswith("Symbol")]
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


def _normalize_quote_market(code: str, market: str) -> str:
    return resolve_quote_market(code=code, market=market, scope="core")


def _overseas_exchange_candidates(market: str) -> list[str]:
    normalized = (market or "").strip().upper()
    if normalized in {"NYSE", "AMEX", "NASDAQ"}:
        ordered = [normalized, "NASDAQ", "NYSE", "AMEX"]
    elif normalized in {"NAS", "US", "USA", ""}:
        ordered = ["NASDAQ", "NYSE", "AMEX"]
    else:
        ordered = ["NASDAQ", "NYSE", "AMEX"]
    deduped: list[str] = []
    for item in ordered:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _search_catalog(query: str, limit: int = 10) -> list[dict]:
    query_raw = query.strip()
    if not query_raw:
        return []

    query_upper = query_raw.upper()
    query_normalized = _normalize_text(query_raw)
    scored: dict[tuple[str, str], tuple[int, dict]] = {}

    for entry in _SEARCH_CATALOG:
        code = entry.code.strip().upper()
        market = entry.market.strip().upper()
        name = entry.name.strip()
        if not code or market not in _ALLOWED_SEARCH_MARKETS:
            continue

        terms = [name, code, *entry.aliases]
        score = 0
        if query_upper == code:
            score = 400
        elif query_upper and code.startswith(query_upper):
            score = 350

        for term in terms:
            normalized_term = _normalize_text(str(term))
            if not normalized_term:
                continue
            if normalized_term == query_normalized:
                score = max(score, 320)
            elif normalized_term.startswith(query_normalized):
                score = max(score, 260)
            elif query_normalized in normalized_term:
                score = max(score, 220)

        if score <= 0:
            continue

        key = (market, code)
        candidate = {"name": name, "code": code, "market": market}
        existing = scored.get(key)
        if not existing or score > existing[0]:
            scored[key] = (score, candidate)

    if re.fullmatch(r"\d{4,6}", query_upper):
        code = query_upper.zfill(6)
        key = ("KOSPI", code)
        scored.setdefault(key, (280, {"name": code, "code": code, "market": "KOSPI"}))

    ordered = sorted(
        scored.values(),
        key=lambda item: (-item[0], item[1]["market"], item[1]["code"]),
    )
    return [item[1] for item in ordered[:max(1, limit)]]


def _paper_fx_rate() -> float | None:
    try:
        if _cache._market_cache["data"] is not None:
            usd_krw = _cache._market_cache["data"].get("usd_krw")
            if isinstance(usd_krw, (int, float)) and usd_krw > 0:
                return float(usd_krw)
        value = _usd_krw()
        return float(value) if value and value > 0 else None
    except Exception:
        return None


def _resolve_stock_quote(code: str, market: str = "") -> dict:
    normalized_input = code.split(".")[0].strip().upper()
    if not normalized_input:
        raise ValueError("code required")

    listing = lookup_company_listing(code=normalized_input, name=normalized_input, scope="core")
    if not listing:
        listing = lookup_company_listing(code=normalized_input, name=normalized_input, scope="live")
    resolved_code = str((listing or {}).get("code") or normalized_input).strip().upper()
    resolved_name = str((listing or {}).get("name") or normalized_input).strip()
    resolved_market = str((listing or {}).get("market") or market or "").strip()
    normalized_market = _normalize_quote_market(resolved_code, resolved_market)
    if normalized_market not in {"KOSPI", "NASDAQ"}:
        raise ValueError("market could not be resolved; provide a valid market or use a known stock code")

    client = _get_kis_client()
    if client is None:
        raise KISConfigError("KIS가 설정되지 않았거나 비활성 상태입니다.")

    if normalized_market == "KOSPI":
        kis_price = client.get_domestic_price(resolved_code)
        return {
            "code": resolved_code,
            "name": kis_price.get("name") or resolved_name,
            "price": kis_price.get("price"),
            "change_pct": kis_price.get("change_pct"),
            "market": normalize_market(resolved_market) or "KOSPI",
            "source": "KIS",
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds"),
            "is_stale": False,
        }

    last_exc: Exception | None = None
    kis_price = None
    resolved_exchange = normalize_market(resolved_market) or "NASDAQ"
    for exchange in _overseas_exchange_candidates(resolved_exchange):
        try:
            kis_price = client.get_overseas_price(resolved_code, exchange=exchange)
            resolved_exchange = exchange
            break
        except Exception as exc:
            last_exc = exc
            continue
    if kis_price is None:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("해외 현재가 조회에 실패했습니다.")

    return {
        "code": resolved_code,
        "name": kis_price.get("name") or resolved_name,
        "price": kis_price.get("price"),
        "change_pct": kis_price.get("change_pct"),
        "market": resolved_exchange,
        "source": "KIS",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "is_stale": False,
    }


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


def handle_live_market() -> tuple[int, dict]:
    now = time.time()
    if _cache._market_cache["data"] is None or now - _cache._market_cache["ts"] > _cache.CACHE_TTL:
        try:
            _cache._market_cache["data"] = _build_market()
            _cache._market_cache["ts"] = now
        except Exception as e:
            return 500, {"error": str(e)}
    return 200, _cache._market_cache["data"]


def handle_stock_search(query: str) -> tuple[int, dict]:
    if not query:
        return 200, {"results": []}
    try:
        return 200, {"results": _search_catalog(query, limit=10)}
    except Exception as e:
        return 500, {"error": str(e)}


def handle_stock_price(code: str, market: str) -> tuple[int, dict]:
    try:
        return 200, _resolve_stock_quote(code, market)
    except ValueError as e:
        return 400, {"error": str(e), "source": "resolver"}
    except Exception as e:
        return 500, {"error": str(e), "source": "KIS"}
