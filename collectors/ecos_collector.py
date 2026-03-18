"""한국은행 ECOS 핵심통계 기반 거시 지표 수집기."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import requests
from loguru import logger

from collectors.models import MacroIndicator
from config.settings import ECOS_API_KEY

_ECOS_KEY_STATS_URL = "https://ecos.bok.or.kr/api/KeyStatisticList/{api_key}/json/kr/1/200"

# ECOS 핵심통계 명칭과 내부 키 매핑(부분 일치)
_KR_KEYWORDS = {
    "kr_cpi": ["소비자물가지수"],
    "kr_ppi": ["생산자물가지수"],
    "kr_base_rate": ["한국은행 기준금리", "기준금리"],
    "kr_unemployment": ["실업률"],
    "kr_usdkrw": ["원/달러", "환율"],
}

_KR_LABELS = {
    "kr_cpi": "한국 소비자물가지수",
    "kr_ppi": "한국 생산자물가지수",
    "kr_base_rate": "한국은행 기준금리",
    "kr_unemployment": "한국 실업률",
    "kr_usdkrw": "원/달러 환율",
}


def _to_float(raw: str) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _format_kr_value(key: str, value: Optional[float]) -> str:
    if value is None:
        return "데이터 없음"
    if key in ("kr_base_rate", "kr_unemployment"):
        return f"{value:.2f}%"
    if key == "kr_usdkrw":
        return f"{value:,.2f}원"
    return f"{value:,.2f}"


def _pick_key(name: str) -> Optional[str]:
    for key, patterns in _KR_KEYWORDS.items():
        if any(pattern in name for pattern in patterns):
            return key
    return None


def collect_ecos_macro() -> list[MacroIndicator]:
    """ECOS 핵심통계에서 한국 거시 지표를 수집한다."""
    if not ECOS_API_KEY:
        logger.warning("ECOS_API_KEY가 없어 한국 거시 지표 수집을 건너뜁니다.")
        return []

    url = _ECOS_KEY_STATS_URL.format(api_key=ECOS_API_KEY)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning(f"ECOS 호출 실패: {exc}")
        return []

    rows = payload.get("KeyStatisticList", {}).get("row", [])
    if not rows:
        logger.warning("ECOS 핵심통계 응답이 비어 있습니다.")
        return []

    picked: dict[str, MacroIndicator] = {}
    for row in rows:
        name = str(row.get("KEYSTAT_NAME", "")).strip()
        if not name:
            continue

        key = _pick_key(name)
        if key is None or key in picked:
            continue

        value = _to_float(row.get("DATA_VALUE", ""))
        unit = str(row.get("UNIT_NAME", "")).strip()
        cycle = str(row.get("CYCLE", "")).strip()

        summary_parts = ["한국은행 ECOS 핵심통계"]
        if cycle:
            summary_parts.append(f"주기: {cycle}")
        if unit:
            summary_parts.append(f"단위: {unit}")

        picked[key] = MacroIndicator(
            key=key,
            label=_KR_LABELS.get(key, name),
            value=value,
            previous=None,
            unit=unit,
            as_of=datetime.now().strftime("%Y-%m-%d"),
            source="ECOS",
            series_id="KeyStatisticList",
            display_value=_format_kr_value(key, value),
            summary=" / ".join(summary_parts),
        )

        if len(picked) == len(_KR_KEYWORDS):
            break

    return list(picked.values())
