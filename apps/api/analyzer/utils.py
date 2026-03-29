"""Shared utilities for analyzer modules.

Contains constants and helpers that are used across multiple analyzer files
to avoid code duplication.
"""
from __future__ import annotations

import json
import re

from collectors.models import NewsArticle

# ---------------------------------------------------------------------------
# US ticker extraction constants
# ---------------------------------------------------------------------------

US_TICKER_PATTERN = re.compile(r"(?<![A-Z0-9])(\$?[A-Z]{2,5}(?:\.[A-Z])?)(?![A-Z0-9])")

DYNAMIC_TICKER_BLOCKLIST: frozenset[str] = frozenset({
    "USD", "KRW", "EUR", "JPY", "GBP", "CNY", "CNH", "DXY", "USDT", "USDC",
    "AI", "EV", "ETF", "SEC", "FED", "FOMC", "CPI", "PPI", "GDP", "PMI", "PCE",
    "WTI", "OPEC", "API", "RBI", "ECB", "BOJ", "NFP", "YOY", "QOQ", "EPS",
    "ADR", "IPO", "MNA", "M&A", "CEO", "CFO", "CTO", "GPU", "CPU", "HBM", "LLM",
    "KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "AMEX", "USA", "US", "EU", "UK", "UAE",
})

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


def normalize_lower(value: str) -> str:
    """소문자 정규화 (공백 트림)."""
    return value.lower().strip()


def article_text(article: NewsArticle) -> str:
    """뉴스 기사 제목·요약·본문을 합쳐 소문자 단일 문자열로 반환."""
    return " ".join([
        article.title or "",
        article.summary or "",
        article.body or "",
    ]).lower()


def safe_json_loads(text: str) -> dict | None:
    """JSON 파싱. 실패 시 중괄호 범위를 추출해 재시도한다. 불가능하면 None 반환."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


# ---------------------------------------------------------------------------
# Investor flow helpers
# ---------------------------------------------------------------------------


def has_notable_flow(flow: dict | None) -> bool:
    """외국인·기관이 같은 방향으로 순매수/순매도 중인지 확인한다."""
    if not flow:
        return False
    foreign_1d = flow.get("foreign_net_1d", 0)
    foreign_5d = flow.get("foreign_net_5d", 0)
    institution_1d = flow.get("institution_net_1d", 0)
    institution_5d = flow.get("institution_net_5d", 0)
    same_direction_1d = (
        (foreign_1d > 0 and institution_1d > 0)
        or (foreign_1d < 0 and institution_1d < 0)
    )
    same_direction_5d = (
        (foreign_5d > 0 and institution_5d > 0)
        or (foreign_5d < 0 and institution_5d < 0)
    )
    return same_direction_1d or same_direction_5d
