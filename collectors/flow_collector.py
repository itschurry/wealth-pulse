"""종목별 외국인/기관 수급 수집기."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from loguru import logger

from collectors.models import InvestorFlowSnapshot
from config.company_catalog import get_company_catalog

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").strip()


def _parse_signed_number(text: str) -> int | None:
    cleaned = text.replace(",", "").replace(" ", "")
    match = re.search(r"([+-]?\d+)", cleaned)
    if not match:
        return None
    return int(match.group(1))


def _fetch_flow(entry) -> InvestorFlowSnapshot | None:
    if entry.market not in {"KOSPI", "KOSDAQ"} or not entry.code.isdigit():
        return None

    try:
        response = requests.get(
            f"https://finance.naver.com/item/frgn.naver?code={entry.code}",
            headers=_HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        html = response.content.decode("euc-kr", "replace")
    except Exception as exc:
        logger.warning(f"수급 수집 실패 [{entry.name}]: {exc}")
        return None

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
        rows.append(
            {
                "date": date,
                "institution_net": institution_net or 0,
                "foreign_net": foreign_net or 0,
            }
        )
        if len(rows) >= 5:
            break

    if not rows:
        return None

    return InvestorFlowSnapshot(
        code=entry.code,
        name=entry.name,
        market=entry.market,
        as_of=rows[0]["date"],
        source="Naver Finance",
        foreign_net_1d=rows[0]["foreign_net"],
        foreign_net_5d=sum(row["foreign_net"] for row in rows[:5]),
        institution_net_1d=rows[0]["institution_net"],
        institution_net_5d=sum(row["institution_net"] for row in rows[:5]),
    )


def collect_investor_flows(limit: int = 16) -> list[InvestorFlowSnapshot]:
    """추적 종목 중 국내 종목의 최근 수급 스냅샷을 수집한다."""
    targets = []
    for entry in get_company_catalog(scope="core"):
        if entry.market in {"KOSPI", "KOSDAQ"} and entry.code.isdigit():
            targets.append(entry)
        if len(targets) >= limit:
            break

    if not targets:
        return []

    snapshots: list[InvestorFlowSnapshot] = []
    with ThreadPoolExecutor(max_workers=min(6, len(targets))) as executor:
        futures = {executor.submit(_fetch_flow, entry): entry for entry in targets}
        for future in as_completed(futures):
            snapshot = future.result()
            if snapshot is not None:
                snapshots.append(snapshot)

    snapshots.sort(
        key=lambda item: (
            abs(item.foreign_net_5d) + abs(item.institution_net_5d),
            item.name,
        ),
        reverse=True,
    )
    return snapshots
