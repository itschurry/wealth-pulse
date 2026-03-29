"""미국 거시 지표 수집 모듈 (Phase 1)."""
from __future__ import annotations

from typing import Optional

import requests
from loguru import logger

from collectors.models import MacroIndicator
from collectors.ecos_collector import collect_ecos_macro
from config.settings import FRED_API_KEY

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

_SERIES = {
    "cpi_yoy": {"series_id": "CPIAUCSL", "label": "미국 CPI YoY", "unit": "%", "mode": "yoy", "window": 13},
    "ppi_yoy": {"series_id": "PPIACO", "label": "미국 PPI YoY", "unit": "%", "mode": "yoy", "window": 13},
    "nfp_change": {"series_id": "PAYEMS", "label": "비농업고용 증감", "unit": "천명", "mode": "diff", "window": 3},
    "unemployment": {"series_id": "UNRATE", "label": "실업률", "unit": "%", "mode": "latest", "window": 3},
    "fed_funds": {"series_id": "FEDFUNDS", "label": "연준 기준금리", "unit": "%", "mode": "latest", "window": 3},
    "us2y": {"series_id": "DGS2", "label": "미국 2년물", "unit": "%", "mode": "latest", "window": 5},
    "us10y": {"series_id": "DGS10", "label": "미국 10년물", "unit": "%", "mode": "latest", "window": 5},
    "dxy": {"series_id": "DTWEXBGS", "label": "달러 인덱스(무역가중)", "unit": "", "mode": "latest", "window": 5},
}


def _fred_observations(series_id: str, limit: int) -> list[tuple[str, float]]:
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    response = requests.get(_FRED_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    observations = []
    for item in payload.get("observations", []):
        value = item.get("value")
        if value in (None, "."):
            continue
        try:
            observations.append((item.get("date", ""), float(value)))
        except ValueError:
            continue
    return observations


def _format_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return "데이터 없음"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "천명":
        return f"{value:,.0f}천명"
    return f"{value:,.2f}{unit}"


def _build_indicator(key: str, label: str, series_id: str, unit: str, as_of: str, value: Optional[float], previous: Optional[float], summary: str, source: str = "FRED") -> MacroIndicator:
    return MacroIndicator(
        key=key,
        label=label,
        value=value,
        previous=previous,
        unit=unit,
        as_of=as_of,
        source=source,
        series_id=series_id,
        display_value=_format_value(value, unit),
        summary=summary,
    )


def collect_macro() -> list[MacroIndicator]:
    """FRED/ECOS 기반 거시 지표를 수집한다."""
    indicators: list[MacroIndicator] = []

    if FRED_API_KEY:
        for key, meta in _SERIES.items():
            try:
                observations = _fred_observations(
                    meta["series_id"], meta["window"])
                if not observations:
                    continue
                as_of, latest = observations[0]
                previous = observations[1][1] if len(
                    observations) >= 2 else None

                if meta["mode"] == "yoy":
                    base = observations[12][1] if len(
                        observations) >= 13 else None
                    value = ((latest - base) / base * 100) if base else None
                    summary = "전년 동월 대비 상승률"
                elif meta["mode"] == "diff":
                    value = latest - previous if previous is not None else None
                    summary = "전월 대비 고용 증가분"
                else:
                    value = latest
                    if key == "dxy" and previous is not None:
                        delta = latest - previous
                        summary = f"직전 발표 대비 {delta:+.2f} (FRED DTWEXBGS)"
                    elif previous is not None:
                        delta = latest - previous
                        summary = f"직전 발표 대비 {delta:+.2f}{meta['unit']}"
                    else:
                        summary = "최신 발표치"

                indicators.append(
                    _build_indicator(
                        key=key,
                        label=meta["label"],
                        series_id=meta["series_id"],
                        unit=meta["unit"],
                        as_of=as_of,
                        value=value,
                        previous=previous,
                        summary=summary,
                    )
                )
            except Exception as exc:
                logger.warning(f"거시 지표 수집 실패 [{key}]: {exc}")
    else:
        logger.warning("FRED_API_KEY가 없어 미국 거시 지표 수집을 건너뜁니다.")

    indicators.extend(collect_ecos_macro())

    return indicators
