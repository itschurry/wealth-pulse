import asyncio
import datetime
import re

import api.cache as _cache
from broker.kis_client import KISAPIError, KISClient, KISConfigError
from reporter.telegram_sender import send_text_message

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

_SUPPORTED_AUTO_TRADE_MARKETS = {"KOSPI", "NASDAQ"}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _format_krw(value: float | int | None) -> str:
    amount = float(value or 0.0)
    return f"{amount:,.0f}원"


def _format_usd(value: float | int | None) -> str:
    amount = float(value or 0.0)
    return f"${amount:,.2f}"


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").strip()


def _parse_signed_number(text: str) -> int | None:
    cleaned = text.replace(",", "").replace(" ", "")
    match = re.search(r"([+-]?\d+)", cleaned)
    if not match:
        return None
    return int(match.group(1))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().lower()


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


def _get_kis_client() -> KISClient | None:
    if _cache._kis_client_disabled:
        return None
    if _cache._kis_client is not None:
        return _cache._kis_client
    if not KISClient.is_configured():
        _cache._kis_client_disabled = True
        return None
    try:
        _cache._kis_client = KISClient.from_env(timeout=8.0)
        return _cache._kis_client
    except (KISConfigError, KISAPIError):
        _cache._kis_client_disabled = True
        return None
