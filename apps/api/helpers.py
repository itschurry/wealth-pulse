import datetime
import re

import cache as _cache
from broker.kis_client import KISAPIError, KISClient, KISConfigError

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
    return None


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
