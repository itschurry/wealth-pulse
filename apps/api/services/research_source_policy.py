from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


BUY_RATINGS = {"strong_buy", "overweight"}
BUY_ACTIONS = {"buy", "buy_watch"}
NEWS_MAX_AGE_HOURS = 72

ALLOWED_SOURCE_LABELS = {
    "naver-openapi",
    "google-news-rss",
    "dart",
    "opendart",
    "krx",
    "kind",
    "company_ir",
    "company_newsroom",
    "sec",
    "nasdaq",
    "nyse",
}

OFFICIAL_SOURCE_LABELS = {
    "dart",
    "opendart",
    "krx",
    "kind",
    "company_ir",
    "company_newsroom",
    "sec",
    "nasdaq",
    "nyse",
}

ALLOWED_NEWS_DOMAINS = {
    "ajunews.com",
    "asiae.co.kr",
    "biz.chosun.com",
    "businesspost.co.kr",
    "chosun.com",
    "daum.net",
    "digitaltoday.co.kr",
    "donga.com",
    "edaily.co.kr",
    "etnews.com",
    "fnnews.com",
    "hankyung.com",
    "hankookilbo.com",
    "joins.com",
    "joongang.co.kr",
    "kdpress.co.kr",
    "mk.co.kr",
    "moneytoday.co.kr",
    "mt.co.kr",
    "naver.com",
    "news1.kr",
    "newsis.com",
    "sedaily.com",
    "thebell.co.kr",
    "viva100.com",
    "wowtv.co.kr",
    "yna.co.kr",
    "yonhapnewstv.co.kr",
    "zdnet.co.kr",
}

ALLOWED_OFFICIAL_DOMAINS = {
    "dart.fss.or.kr",
    "opendart.fss.or.kr",
    "kind.krx.co.kr",
    "krx.co.kr",
    "sec.gov",
    "nasdaq.com",
    "nyse.com",
}

BLOCKED_DOMAINS = {
    "blog.naver.com",
    "m.blog.naver.com",
    "cafe.naver.com",
    "tistory.com",
    "dcinside.com",
    "fmkorea.com",
    "clien.net",
    "ppomppu.co.kr",
    "reddit.com",
    "youtube.com",
}


@dataclass(frozen=True)
class ResearchQualityError(ValueError):
    code: str
    reason: str

    def __str__(self) -> str:
        return self.code


def is_buy_intent(rating: Any, action: Any) -> bool:
    return str(rating or "").strip().lower() in BUY_RATINGS and str(action or "").strip().lower() in BUY_ACTIONS


def _parse_dt(value: Any) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _hostname(url: Any) -> str:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _domain_matches(host: str, allowed: set[str]) -> bool:
    if not host:
        return False
    for domain in allowed:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def _source_label(value: Any) -> str:
    return str(value or "").strip().lower()


def _source_label_matches(source: str, labels: set[str]) -> bool:
    if source in labels:
        return True
    compact = source.replace("_", "-").replace(" ", "-")
    if "opendart" in compact or "open-dart" in compact:
        return "opendart" in labels
    for label in labels:
        if label in compact:
            return True
    return False


def _is_allowed_news_source(item: dict[str, Any]) -> tuple[bool, bool, str]:
    source = _source_label(item.get("source") or item.get("publisher"))
    url = str(item.get("url") or "").strip()
    host = _hostname(url)
    if not url:
        return False, False, "news_url_required"
    if _domain_matches(host, BLOCKED_DOMAINS):
        return False, False, "source_not_allowed"
    source_allowed = _source_label_matches(source, ALLOWED_SOURCE_LABELS)
    official = _source_label_matches(source, OFFICIAL_SOURCE_LABELS) or _domain_matches(host, ALLOWED_OFFICIAL_DOMAINS)
    domain_allowed = official or _domain_matches(host, ALLOWED_NEWS_DOMAINS)
    if source_allowed or domain_allowed:
        return True, official, ""
    return False, False, "source_not_allowed"


def _evidence_is_trusted(item: dict[str, Any]) -> tuple[bool, bool]:
    source = _source_label(item.get("source") or item.get("type"))
    url = str(item.get("url") or "").strip()
    host = _hostname(url)
    if url:
        if _domain_matches(host, BLOCKED_DOMAINS):
            return False, False
        if _domain_matches(host, ALLOWED_OFFICIAL_DOMAINS) or _domain_matches(host, ALLOWED_NEWS_DOMAINS):
            return True, _domain_matches(host, ALLOWED_OFFICIAL_DOMAINS)
    if _source_label_matches(source, OFFICIAL_SOURCE_LABELS):
        return True, True
    return False, False


def evaluate_research_quality(
    item: dict[str, Any],
    *,
    reference_time: Any | None = None,
) -> dict[str, Any]:
    news_inputs = item.get("news_inputs") if isinstance(item.get("news_inputs"), list) else []
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    reference_dt = _parse_dt(reference_time or item.get("generated_at")) or datetime.datetime.now(datetime.timezone.utc)

    trusted_news_count = 0
    fresh_news_count = 0
    official_source_count = 0
    untrusted_source_count = 0
    stale_news_count = 0
    missing_news_url_count = 0
    missing_published_at_count = 0

    for news in news_inputs:
        if not isinstance(news, dict):
            untrusted_source_count += 1
            continue
        allowed, official, reason = _is_allowed_news_source(news)
        if reason == "news_url_required":
            missing_news_url_count += 1
        if not allowed:
            untrusted_source_count += 1
        else:
            trusted_news_count += 1
        if official:
            official_source_count += 1
        published_at = _parse_dt(news.get("published_at"))
        if published_at is None:
            missing_published_at_count += 1
            continue
        age_hours = (reference_dt - published_at).total_seconds() / 3600.0
        if age_hours < 0:
            age_hours = 0
        if age_hours <= NEWS_MAX_AGE_HOURS:
            fresh_news_count += 1
        else:
            stale_news_count += 1

    evidence_url_count = 0
    trusted_evidence_count = 0
    for row in evidence:
        if not isinstance(row, dict):
            continue
        if str(row.get("url") or "").strip():
            evidence_url_count += 1
        trusted, official = _evidence_is_trusted(row)
        if trusted:
            trusted_evidence_count += 1
        if official:
            official_source_count += 1

    source_quality_score = 0.0
    if news_inputs:
        source_quality_score += min(0.55, trusted_news_count * 0.25)
        source_quality_score += min(0.25, fresh_news_count * 0.15)
    if evidence:
        source_quality_score += min(0.15, trusted_evidence_count * 0.1)
    source_quality_score += min(0.05, official_source_count * 0.025)
    source_quality_score = round(max(0.0, min(1.0, source_quality_score)), 4)

    blocked_reason = ""
    if is_buy_intent(item.get("rating"), item.get("action")):
        if not news_inputs:
            blocked_reason = "news_inputs_required_for_buy"
        elif missing_news_url_count > 0:
            blocked_reason = "news_url_required"
        elif missing_published_at_count > 0:
            blocked_reason = "news_published_at_required"
        elif untrusted_source_count > 0 or trusted_news_count <= 0:
            blocked_reason = "source_not_allowed"
        elif stale_news_count > 0 or fresh_news_count <= 0:
            blocked_reason = "news_stale"
        elif not evidence:
            blocked_reason = "evidence_url_required"
        elif trusted_evidence_count <= 0:
            blocked_reason = "evidence_url_required"
        else:
            data_quality = item.get("data_quality") if isinstance(item.get("data_quality"), dict) else {}
            if data_quality.get("has_news") is not True:
                blocked_reason = "research_quality_gate_failed"
            elif data_quality.get("has_recent_price") is not True:
                blocked_reason = "research_quality_gate_failed"
            elif data_quality.get("has_technical_features") is not True:
                blocked_reason = "research_quality_gate_failed"

    return {
        "trusted_news_count": trusted_news_count,
        "fresh_news_count": fresh_news_count,
        "official_source_count": official_source_count,
        "evidence_url_count": evidence_url_count,
        "trusted_evidence_count": trusted_evidence_count,
        "untrusted_source_count": untrusted_source_count,
        "stale_news_count": stale_news_count,
        "missing_news_url_count": missing_news_url_count,
        "missing_published_at_count": missing_published_at_count,
        "source_quality_score": source_quality_score,
        "blocked_reason": blocked_reason,
    }


def warning_codes_for_quality(quality: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if int(quality.get("trusted_news_count") or 0) <= 0 and int(quality.get("trusted_evidence_count") or 0) <= 0:
        warnings.append("low_evidence_density")
    if int(quality.get("untrusted_source_count") or 0) > 0:
        warnings.append("untrusted_source")
    if int(quality.get("stale_news_count") or 0) > 0:
        warnings.append("stale_news")
    if int(quality.get("missing_news_url_count") or 0) > 0 or int(quality.get("missing_published_at_count") or 0) > 0:
        warnings.append("missing_news_url")
    return warnings


def assert_quality_allows_ingest(item: dict[str, Any], *, reference_time: Any | None = None) -> dict[str, Any]:
    quality = evaluate_research_quality(item, reference_time=reference_time)
    blocked_reason = str(quality.get("blocked_reason") or "")
    if blocked_reason:
        raise ResearchQualityError(blocked_reason, blocked_reason)
    return quality
