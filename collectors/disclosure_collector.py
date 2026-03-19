"""DART 공시 수집기."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree

import requests
from loguru import logger

from collectors.models import DisclosureItem
from config.company_catalog import get_company_catalog
from config.settings import DART_API_KEY

_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
_DISCLOSURE_LIST_URL = "https://opendart.fss.or.kr/api/list.json"

_POSITIVE_KEYWORDS = (
    "공급계약",
    "수주",
    "계약체결",
    "실적",
    "매출액",
    "영업이익",
    "자기주식",
    "배당",
    "시설투자",
)
_CAUTION_KEYWORDS = (
    "유상증자",
    "전환사채",
    "신주인수권부사채",
    "감자",
    "소송",
    "횡령",
    "배임",
    "영업정지",
    "불성실",
)


def _parse_filed_at(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y%m%d")
    except ValueError:
        return None


def _categorize_title(title: str) -> tuple[str, str]:
    lowered = title.lower()
    if any(keyword in title for keyword in ("실적", "매출액", "영업이익", "잠정")):
        return "earnings", "높음"
    if any(keyword in title for keyword in ("공급계약", "수주", "계약체결")):
        return "contract", "높음"
    if any(keyword in title for keyword in ("자기주식", "배당")):
        return "shareholder_return", "중간"
    if any(keyword in title for keyword in ("시설투자", "신규시설")):
        return "investment", "중간"
    if any(keyword in title for keyword in ("유상증자", "감자", "전환사채", "신주인수권부사채")):
        return "capital", "높음"
    if any(keyword in title for keyword in ("소송", "횡령", "배임", "영업정지", "불성실")):
        return "governance", "높음"
    if "합병" in title or "분할" in title:
        return "restructuring", "높음"
    if any(keyword in lowered for keyword in ("change", "revision")):
        return "update", "중간"
    return "general", "중간"


def _fetch_corp_code_map() -> dict[str, str]:
    response = requests.get(_CORP_CODE_URL, params={"crtfc_key": DART_API_KEY}, timeout=20)
    response.raise_for_status()

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    xml_name = archive.namelist()[0]
    root = ElementTree.fromstring(archive.read(xml_name))

    corp_code_map: dict[str, str] = {}
    for node in root.findall("list"):
        stock_code = (node.findtext("stock_code") or "").strip()
        corp_code = (node.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            corp_code_map[stock_code] = corp_code
    return corp_code_map


def collect_disclosures(lookback_days: int = 3, per_company_limit: int = 6, total_limit: int = 24) -> list[DisclosureItem]:
    """DART에서 현재 추적 종목 관련 최근 공시를 수집한다."""
    if not DART_API_KEY:
        logger.warning("DART_API_KEY가 없어 공시 수집을 건너뜁니다.")
        return []

    try:
        corp_code_map = _fetch_corp_code_map()
    except Exception as exc:
        logger.warning(f"공시 corpCode 수집 실패: {exc}")
        return []

    catalog = [entry for entry in get_company_catalog() if entry.code.isdigit()]
    targets = []
    for entry in catalog:
        corp_code = corp_code_map.get(entry.code)
        if corp_code:
            targets.append((entry, corp_code))

    if not targets:
        return []

    end_date = datetime.now().strftime("%Y%m%d")
    begin_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")

    disclosures: list[DisclosureItem] = []
    seen_receipts: set[str] = set()

    for entry, corp_code in targets:
        try:
            response = requests.get(
                _DISCLOSURE_LIST_URL,
                params={
                    "crtfc_key": DART_API_KEY,
                    "corp_code": corp_code,
                    "bgn_de": begin_date,
                    "end_de": end_date,
                    "last_reprt_at": "Y",
                    "page_count": per_company_limit,
                },
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning(f"공시 수집 실패 [{entry.name}]: {exc}")
            continue

        status = str(payload.get("status", ""))
        if status in {"013", "020"}:
            continue
        if status not in {"000", ""}:
            logger.warning(f"공시 응답 오류 [{entry.name}]: {payload.get('message', status)}")
            continue

        for item in payload.get("list", []):
            receipt_no = str(item.get("rcept_no", "")).strip()
            if not receipt_no or receipt_no in seen_receipts:
                continue
            filed_at = _parse_filed_at(str(item.get("rcept_dt", "")))
            if filed_at is None:
                continue
            title = str(item.get("report_nm", "")).strip()
            category, importance = _categorize_title(title)
            disclosures.append(
                DisclosureItem(
                    company_name=entry.name,
                    stock_code=entry.code,
                    corp_code=corp_code,
                    market=entry.market,
                    title=title,
                    filed_at=filed_at,
                    source="DART",
                    url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}",
                    category=category,
                    importance=importance,
                    receipt_no=receipt_no,
                )
            )
            seen_receipts.add(receipt_no)

    disclosures.sort(key=lambda item: item.filed_at, reverse=True)
    return disclosures[:total_limit]
