"""뉴스 기반 오늘의 추천 및 관심종목 액션 계산."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from analyzer.utils import (
    DYNAMIC_TICKER_BLOCKLIST as _DYNAMIC_TICKER_BLOCKLIST,
    US_TICKER_PATTERN as _US_TICKER_PATTERN,
    article_text as _article_text,
    normalize_lower as _normalize,
)
from collectors.models import DailyData, NewsArticle
from config.company_catalog import CompanyCatalogEntry, get_company_catalog
from market_utils import resolve_market

_KST = ZoneInfo("Asia/Seoul")

_POSITIVE_KEYWORDS = (
    "상승", "강세", "확대", "수혜", "개선", "성장", "급등", "돌파", "신제품",
    "실적 개선", "상향", "기대", "주목", "계약", "수주", "출시", "진출",
)
_NEGATIVE_KEYWORDS = (
    "하락", "약세", "불확실", "우려", "악화", "급락", "리스크", "경고", "압박",
    "둔화", "매파", "전쟁", "충돌", "지연", "축소", "실적 부진",
)
_THEME_BOOSTS = {
    "방산": ("전쟁", "국방", "무기", "방산"),
    "에너지": ("유가", "원유", "에너지"),
    "항공": ("여행", "노선", "관광"),
    "반도체": ("반도체", "hbm", "ai", "칩", "엔비디아"),
    "자동차": ("자동차", "전기차", "자율주행", "sdv", "robotaxi"),
    "로봇": ("로봇", "협동로봇", "휴머노이드", "humanoid", "physical ai"),
    "플랫폼": ("ai 에이전트", "멀티모달", "physical ai"),
    "가전": ("가전", "냉장고", "가정용 ai", "비스포크"),
}
_DISCLOSURE_POSITIVE = {"earnings", "contract",
                        "shareholder_return", "investment"}
_DISCLOSURE_NEGATIVE = {"capital", "governance", "restructuring"}
_EVENT_RISK_CATEGORIES = {"inflation", "policy", "labor"}
_THEME_GATE_MIN_SCORE = 2.5
_THEME_GATE_MIN_NEWS = 1
_AUTO_TRADE_MARKETS = {"KOSPI", "NASDAQ", "NYSE", "AMEX"}
_SECTOR_THEME_HINTS = {
    "자동차": {"automotive", "physical_ai"},
    "자동차부품": {"automotive", "robotics", "physical_ai"},
    "로봇": {"robotics", "physical_ai"},
    "반도체": {"physical_ai", "robotics"},
    "플랫폼": {"physical_ai"},
    "가전": {"robotics", "physical_ai"},
}
_US_CONTEXT_KEYWORDS = (
    "nasdaq", "nyse", "amex", "미국증시", "뉴욕증시", "월가", "us stock", "u.s. stock",
    "adr", "premarket", "after-hours", "after hours", "pre-market",
)
_ASCII_ALIAS_PATTERN = re.compile(r"[a-z0-9][a-z0-9 .&\\-]*")


def _alias_in_text(alias: str, text: str) -> bool:
    normalized_alias = _normalize(alias)
    if not normalized_alias:
        return False
    if _ASCII_ALIAS_PATTERN.fullmatch(normalized_alias):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return normalized_alias in text


def _has_us_market_context(raw_text: str) -> bool:
    lowered = str(raw_text or "").lower()
    return any(keyword in lowered for keyword in _US_CONTEXT_KEYWORDS)


def _score_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _market_adjustment(data: DailyData, sector: str) -> float:
    adjustment = 0.0
    context = data.market_context
    market = data.market

    if context and context.dollar_signal == "강세" and sector in {"반도체", "자동차", "자동차부품"}:
        adjustment -= 2.0
    if context and context.risk_level == "높음":
        adjustment -= 3.0
    elif context and context.risk_level == "중간":
        adjustment -= 1.0

    if market.kospi_change_pct is not None:
        adjustment += max(min(market.kospi_change_pct, 2.0), -2.0)
    if market.nasdaq_change_pct is not None and sector in {"반도체", "플랫폼", "가전"}:
        adjustment += max(min(market.nasdaq_change_pct, 2.0), -2.0)

    return adjustment


def _signal_from_score(score: float) -> str:
    if score >= 68:
        return "추천"
    if score >= 52:
        return "중립"
    return "회피"


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _external_watchlist_score(current_pick: dict | None, current_rec: dict | None) -> tuple[float, list[str]]:
    score = 50.0
    notes: list[str] = []

    pick_score = _safe_float((current_pick or {}).get("score"))
    if pick_score is not None:
        score += (pick_score - 50.0) * 0.55
        notes.append(f"오늘의 추천 점수 {pick_score:.1f}점 반영")

    recommendation_score = _safe_float((current_rec or {}).get("score"))
    if recommendation_score is not None:
        score += (recommendation_score - 50.0) * 0.35
        notes.append(f"보유 추천 점수 {recommendation_score:.1f}점 반영")

    return score, notes


def _serialize_article(article: NewsArticle) -> dict:
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "published": article.published.astimezone(_KST).strftime("%Y-%m-%d %H:%M KST"),
        "summary": article.summary[:240],
        "theme_score": round(float(getattr(article, "theme_score", 0.0) or 0.0), 2),
        "matched_themes": list(getattr(article, "matched_themes", []) or []),
    }


def _serialize_disclosure(item) -> dict:
    return {
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "filed_at": item.filed_at.strftime("%Y-%m-%d"),
        "category": item.category,
        "importance": item.importance,
    }


def _serialize_calendar_event(event) -> dict:
    return {
        "name": event.name,
        "country": event.country,
        "scheduled_at": event.scheduled_at.astimezone(_KST).strftime("%Y-%m-%d %H:%M KST"),
        "source": event.source,
        "category": event.category,
        "importance": event.importance,
        "url": event.url,
    }


def _serialize_flow(flow) -> dict:
    return {
        "as_of": flow.as_of,
        "source": flow.source,
        "foreign_net_1d": flow.foreign_net_1d,
        "foreign_net_5d": flow.foreign_net_5d,
        "institution_net_1d": flow.institution_net_1d,
        "institution_net_5d": flow.institution_net_5d,
    }


def _ai_signal_adjustment(ai_signal: dict | None) -> tuple[float, list[str], list[str], dict | None]:
    if not ai_signal:
        return 0.0, [], [], None

    score = max(-4.0, min(4.0, _safe_float(ai_signal.get("score_adjustment")) or 0.0))
    reasons = [str(item).strip() for item in ai_signal.get(
        "reasons", []) if str(item).strip()][:2]
    risks = [str(item).strip()
             for item in ai_signal.get("risks", []) if str(item).strip()][:2]
    summary = str(ai_signal.get("summary", "")).strip()
    if summary and not reasons:
        reasons.append(f"AI 해석: {summary}")
    serialized = {
        "score_adjustment": round(score, 1),
        "action_bias": ai_signal.get("action_bias", "중립"),
        "risk_level": ai_signal.get("risk_level", "중간"),
        "confidence": ai_signal.get("confidence"),
        "summary": summary,
        "reasons": reasons,
        "risks": risks,
        "source": ai_signal.get("source", "openai-aux-signal-v1"),
    }
    return round(score, 1), reasons, risks, serialized


def _playbook_candidate_map(playbook: dict | None) -> dict[str, dict]:
    candidate_map: dict[str, dict] = {}
    if not playbook:
        return candidate_map
    for horizon in ("short_term", "mid_term"):
        for item in playbook.get(f"stock_candidates_{horizon}", []):
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            candidate["horizon"] = horizon
            for key in {
                str(item.get("code") or "").strip().upper(),
                str(item.get("name") or "").strip(),
            }:
                if key:
                    candidate_map[key] = candidate
    return candidate_map


def _event_watchlist_risk(playbook: dict | None, sector: str) -> str | None:
    if not playbook or not playbook.get("event_watchlist"):
        return None
    joined = " ".join(
        f"{item.get('name', '')} {item.get('note', '')}"
        for item in playbook.get("event_watchlist", [])
        if isinstance(item, dict)
    ).lower()
    sector_lower = sector.lower()
    if any(keyword in joined for keyword in ("cpi", "fomc", "금리", "고용", "인플레이션")) and sector_lower in {"반도체", "플랫폼", "자동차", "가전", "로봇"}:
        return "이벤트 리스크가 커 단기 추격은 보수적으로 접근"
    return None


def _apply_playbook_overlay(
    entry: CompanyCatalogEntry,
    score: float,
    reasons: list[str],
    risks: list[str],
    playbook: dict | None,
    playbook_candidate: dict | None,
) -> tuple[float, list[str], list[str], dict]:
    favored = {str(item).strip().lower() for item in (
        playbook or {}).get("favored_sectors", []) if str(item).strip()}
    avoided = {str(item).strip().lower() for item in (
        playbook or {}).get("avoided_sectors", []) if str(item).strip()}
    invalid_setups = [str(item).strip().lower() for item in (
        playbook or {}).get("invalid_setups", []) if str(item).strip()]
    short_term_bias = str((playbook or {}).get(
        "short_term_bias", "neutral")).strip().lower()

    next_score = score
    gate_status = "passed"
    gate_reasons: list[str] = []
    horizon = "short_term"
    ai_thesis = ""
    alignment = 50.0
    technical_view = ""
    setup_quality = "mixed"
    technical_snapshot = None

    if entry.sector.lower() in favored:
        next_score += 3.0
        alignment += 10.0
        reasons.append("플레이북 유리 섹터에 포함")
    if entry.sector.lower() in avoided:
        next_score -= 4.0
        alignment -= 12.0
        gate_reasons.append("플레이북에서 불리한 섹터로 분류")

    event_risk = _event_watchlist_risk(playbook, entry.sector)
    if event_risk:
        gate_reasons.append(event_risk)
        alignment -= 5.0

    if playbook_candidate:
        horizon = str(playbook_candidate.get("horizon", "short_term"))
        ai_thesis = str(playbook_candidate.get("thesis", "")).strip()
        technical_view = str(playbook_candidate.get(
            "technical_view", "")).strip()
        setup_quality = str(playbook_candidate.get(
            "setup_quality", "mixed")).strip().lower() or "mixed"
        technical_snapshot = playbook_candidate.get("technical_snapshot")
        action = str(playbook_candidate.get("action", "watch")).strip().lower()
        confidence = _safe_float(playbook_candidate.get("confidence")) or 60.0
        next_score += max(-6.0, min(8.0, (confidence - 55.0) * 0.12))
        alignment += max(-15.0, min(18.0, (confidence - 50.0) * 0.4))
        if ai_thesis:
            reasons.append(f"플레이북 논리: {ai_thesis}")
        if technical_view:
            reasons.append(f"기술해석: {technical_view}")
        reasons.extend(str(item).strip() for item in playbook_candidate.get(
            "reasons", []) if str(item).strip())
        risks.extend(str(item).strip() for item in playbook_candidate.get(
            "risks", []) if str(item).strip())

        if action == "buy":
            next_score += 4.0
            alignment += 8.0
        elif action == "watch":
            next_score += 1.0
        elif action == "avoid":
            next_score -= 12.0
            alignment -= 18.0
            gate_reasons.append("플레이북에서 보류/제외 후보로 분류")

        thesis_blob = " ".join([ai_thesis] + [str(item)
                               for item in playbook_candidate.get("reasons", [])]).lower()
        if any(rule in thesis_blob for rule in invalid_setups):
            gate_reasons.append("플레이북 금지 셋업과 충돌")
            alignment -= 18.0

        if short_term_bias == "defensive" and action == "buy":
            gate_reasons.append("단기 시장 바이어스와 역행")
            alignment -= 10.0

        if setup_quality == "high":
            next_score += 2.0
            alignment += 5.0
        elif setup_quality == "low":
            gate_reasons.append("기술 셋업 기대값 낮음")
            next_score -= 5.0
            alignment -= 10.0
        elif setup_quality == "unknown":
            gate_reasons.append("기술지표 확인 전")
            next_score -= 2.0
            alignment -= 6.0

    deduped_gate_reasons = list(dict.fromkeys(gate_reasons))[:4]
    if any(reason in {"플레이북 금지 셋업과 충돌", "플레이북에서 보류/제외 후보로 분류"} for reason in deduped_gate_reasons):
        gate_status = "blocked"
        next_score -= 10.0
    elif deduped_gate_reasons:
        gate_status = "caution"
        next_score -= 3.0

    return next_score, reasons, risks, {
        "horizon": horizon if horizon in {"short_term", "mid_term"} else "short_term",
        "gate_status": gate_status,
        "gate_reasons": deduped_gate_reasons,
        "playbook_alignment": round(max(5.0, min(95.0, alignment)), 1),
        "ai_thesis": ai_thesis,
        "technical_snapshot": technical_snapshot,
        "technical_view": technical_view,
        "setup_quality": setup_quality,
    }


def _calendar_adjustment(data: DailyData, entry: CompanyCatalogEntry) -> tuple[float, list[str], list[str], list]:
    upcoming_events = []
    risks: list[str] = []
    score = 0.0
    now = datetime.now(_KST)

    for event in data.calendar_events:
        scheduled = event.scheduled_at.astimezone(_KST)
        delta_hours = (scheduled - now).total_seconds() / 3600
        if delta_hours < -12 or delta_hours > 36:
            continue
        if event.category not in _EVENT_RISK_CATEGORIES:
            continue
        upcoming_events.append(event)

    if upcoming_events and entry.sector in {"반도체", "플랫폼", "2차전지", "자동차", "가전"}:
        high_impact = any(event.importance ==
                          "높음" for event in upcoming_events)
        score -= 1.5 if high_impact else 0.5
        event_names = ", ".join(event.name for event in upcoming_events[:2])
        risks.append(f"주요 일정({event_names}) 전후로 단기 변동성 확대 가능성")

    return score, [], risks[:1], upcoming_events[:2]


def _disclosure_adjustment(disclosures: list) -> tuple[float, list[str], list[str], list]:
    if not disclosures:
        return 0.0, [], [], []

    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []

    for item in disclosures[:2]:
        if item.category in _DISCLOSURE_POSITIVE:
            score += 4.0 if item.importance == "높음" else 2.0
            reasons.append(f"최근 공시 반영: {item.title}")
        elif item.category in _DISCLOSURE_NEGATIVE:
            score -= 3.0 if item.importance == "높음" else 1.5
            risks.append(f"공시 점검 필요: {item.title}")
        else:
            reasons.append(f"최근 공시 확인: {item.title}")

    return score, reasons[:2], risks[:2], disclosures[:2]


def _flow_adjustment(flow) -> tuple[float, list[str], list[str], dict | None]:
    if flow is None:
        return 0.0, [], [], None

    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    if flow.foreign_net_1d > 0 and flow.institution_net_1d > 0:
        score += 1.5
        reasons.append("외국인·기관이 최근 1일 동반 순매수")
    elif flow.foreign_net_1d < 0 and flow.institution_net_1d < 0:
        score -= 1.5
        risks.append("외국인·기관이 최근 1일 동반 순매도")

    if flow.foreign_net_5d > 0 and flow.institution_net_5d > 0:
        score += 2.5
        reasons.append("외국인·기관이 최근 5일 누적 순매수")
    elif flow.foreign_net_5d < 0 and flow.institution_net_5d < 0:
        score -= 2.5
        risks.append("외국인·기관이 최근 5일 누적 순매도")
    elif flow.foreign_net_5d * flow.institution_net_5d < 0:
        score -= 0.5
        risks.append("외국인과 기관 수급 방향이 엇갈림")

    return score, reasons[:2], risks[:2], _serialize_flow(flow)


def _has_notable_flow(flow) -> bool:
    if flow is None:
        return False
    same_direction_5d = (
        (flow.foreign_net_5d > 0 and flow.institution_net_5d > 0)
        or (flow.foreign_net_5d < 0 and flow.institution_net_5d < 0)
    )
    same_direction_1d = (
        (flow.foreign_net_1d > 0 and flow.institution_net_1d > 0)
        or (flow.foreign_net_1d < 0 and flow.institution_net_1d < 0)
    )
    return same_direction_5d or same_direction_1d


def _article_theme_metrics(articles: list[NewsArticle]) -> tuple[float, int, list[str], int]:
    total_score = 0.0
    total_hits = 0
    themed_articles = 0
    theme_set: set[str] = set()

    for article in articles:
        score = _safe_float(getattr(article, "theme_score", 0.0)) or 0.0
        raw_hits = getattr(article, "theme_hit_count", 0) or 0
        hit_count = int(raw_hits) if isinstance(raw_hits, (int, float)) else 0
        matched_themes = [
            str(theme).strip().lower()
            for theme in (getattr(article, "matched_themes", []) or [])
            if str(theme).strip()
        ]
        if score > 0 or hit_count > 0 or matched_themes:
            themed_articles += 1
        total_score += score
        total_hits += max(hit_count, len(matched_themes))
        theme_set.update(matched_themes)

    return round(total_score, 2), total_hits, sorted(theme_set), themed_articles


def _theme_alignment_bonus(sector: str, matched_themes: set[str]) -> float:
    hints = _SECTOR_THEME_HINTS.get(sector, set())
    if not hints or not matched_themes:
        return 0.0
    overlap = len(hints & matched_themes)
    if overlap <= 0:
        return 0.0
    return 1.5 + overlap * 1.5


def _keyword_gate_passed(
    sector: str,
    theme_score: float,
    themed_article_count: int,
    matched_themes: list[str],
    *,
    min_score: float = _THEME_GATE_MIN_SCORE,
    min_news: int = _THEME_GATE_MIN_NEWS,
) -> bool:
    if themed_article_count < min_news:
        return False
    if theme_score < min_score:
        return False
    matched = set(matched_themes)
    sector_hints = _SECTOR_THEME_HINTS.get(sector, set())
    if sector_hints and not (sector_hints & matched):
        return False
    return True


def _extract_dynamic_us_ticker_entries(
    news: list[NewsArticle],
    *,
    existing_codes: set[str],
) -> list[CompanyCatalogEntry]:
    mention_counts: dict[str, int] = {}
    dollar_mentioned: set[str] = set()

    for article in news:
        raw_text = " ".join(
            [article.title or "", article.summary or "", article.body or ""])
        if not raw_text:
            continue
        has_us_context = _has_us_market_context(raw_text)
        article_counts: dict[str, int] = {}
        for match in _US_TICKER_PATTERN.finditer(raw_text):
            token = str(match.group(1) or "").strip().upper()
            if not token:
                continue
            if token.startswith("$"):
                token = token[1:]
                if token:
                    dollar_mentioned.add(token)
            if (
                not token
                or len(token) < 2
                or token in _DYNAMIC_TICKER_BLOCKLIST
                or token in existing_codes
            ):
                continue
            resolved_market = resolve_market(
                code=token, name=token, scope="core")
            if resolved_market in {"KOSPI", "KOSDAQ"}:
                continue
            if not resolved_market:
                if len(token) < 3 and token not in dollar_mentioned:
                    continue
                if token not in dollar_mentioned and not has_us_context:
                    continue
            article_counts[token] = article_counts.get(token, 0) + 1
        for code, count in article_counts.items():
            mention_counts[code] = mention_counts.get(code, 0) + count

    entries: list[CompanyCatalogEntry] = []
    for code, mentions in sorted(mention_counts.items(), key=lambda item: (-item[1], item[0])):
        if mentions < 2 and code not in dollar_mentioned:
            continue
        entries.append(
            CompanyCatalogEntry(
                name=code,
                code=code,
                market="NASDAQ",
                sector="미국주식",
                aliases=(code, code.lower()),
            )
        )
    return entries


def _build_pick(
    entry: CompanyCatalogEntry,
    articles: list[NewsArticle],
    data: DailyData,
    disclosures: list,
    investor_flow,
    ai_signal: dict | None,
    playbook: dict | None,
    playbook_candidate: dict | None,
) -> dict:
    texts = [_article_text(article) for article in articles]
    joined = " ".join(texts)
    positive = sum(_score_keywords(text, _POSITIVE_KEYWORDS) for text in texts)
    negative = sum(_score_keywords(text, _NEGATIVE_KEYWORDS) for text in texts)
    theme_boost = sum(1 for keyword in _THEME_BOOSTS.get(
        entry.sector, ()) if keyword.lower() in joined)
    recent_bonus = sum(1 for article in articles if (datetime.now(
        _KST) - article.published.astimezone(_KST)).total_seconds() <= 12 * 3600)
    article_theme_score, article_theme_hits, matched_themes, themed_article_count = _article_theme_metrics(
        articles)
    theme_alignment_bonus = _theme_alignment_bonus(
        entry.sector, set(matched_themes))
    aggressive_theme_boost = min(
        article_theme_score, 16.0) * 1.6 + theme_alignment_bonus

    score = 48 + len(articles) * 8 + positive * 3 - negative * \
        4 + theme_boost * 2 + recent_bonus * 2
    score += aggressive_theme_boost
    score += _market_adjustment(data, entry.sector)
    disclosure_score, disclosure_reasons, disclosure_risks, related_disclosures = _disclosure_adjustment(
        disclosures)
    flow_score, flow_reasons, flow_risks, serialized_flow = _flow_adjustment(
        investor_flow)
    ai_score, ai_reasons, ai_risks, serialized_ai_signal = _ai_signal_adjustment(
        ai_signal)
    calendar_score, calendar_reasons, calendar_risks, upcoming_events = _calendar_adjustment(
        data, entry)
    score += disclosure_score + flow_score + ai_score + calendar_score

    reasons = [
        f"관련 뉴스 {len(articles)}건",
        f"긍정 신호 {positive}건 / 부정 신호 {negative}건",
    ]
    if article_theme_score > 0:
        themes_text = ", ".join(
            matched_themes[:3]) if matched_themes else "theme"
        reasons.append(
            f"테마 점수 {article_theme_score:.1f}점 ({themes_text}, 키워드 {article_theme_hits}건)"
        )
    if theme_boost:
        reasons.append(f"{entry.sector} 테마 키워드 반영")

    risks = []
    if negative > 0:
        risks.append("부정 기사 비중이 높아 변동성 확대 가능성")
    if data.market_context and data.market_context.dollar_signal == "강세":
        risks.append("달러 강세 국면으로 위험자산 변동성 확대 가능성")
    reasons = reasons[:2] + disclosure_reasons + \
        flow_reasons + ai_reasons + reasons[2:]
    reasons.extend(calendar_reasons)
    if data.market_context:
        reasons.append(f"거시 컨텍스트: {data.market_context.summary}")
    risks.extend(disclosure_risks)
    risks.extend(flow_risks)
    risks.extend(ai_risks)
    risks.extend(calendar_risks)
    if not risks:
        risks.append("단기 재료 소멸 여부를 점검할 필요")

    score, reasons, risks, playbook_meta = _apply_playbook_overlay(
        entry,
        score,
        reasons,
        risks,
        playbook,
        playbook_candidate,
    )
    score = max(25, min(95, round(score, 1)))

    catalysts = [article.title for article in articles[:2]]
    catalysts.extend(item.title for item in related_disclosures[:1])
    catalysts.extend(event.name for event in upcoming_events[:1])
    keyword_gate_passed = _keyword_gate_passed(
        entry.sector,
        article_theme_score,
        themed_article_count,
        matched_themes,
    )

    return {
        "name": entry.name,
        "code": entry.code,
        "market": entry.market,
        "sector": entry.sector,
        "signal": "회피" if playbook_meta["gate_status"] == "blocked" else ("중립" if playbook_meta["gate_status"] == "caution" and _signal_from_score(score) == "추천" else _signal_from_score(score)),
        "score": score,
        "confidence": max(
            45,
            min(
                92,
                round(
                    max(45, min(92, 42 + len(articles) * 9 +
                        abs(positive - negative) * 5)) * 0.75
                    + ((_safe_float((serialized_ai_signal or {}).get("confidence")) or 60.0) * 0.25)
                ),
            ),
        ),
        "reasons": reasons[:4],
        "risks": risks[:3],
        "catalysts": catalysts[:3],
        "related_news": [_serialize_article(article) for article in articles[:3]],
        "related_disclosures": [_serialize_disclosure(item) for item in related_disclosures],
        "upcoming_events": [_serialize_calendar_event(event) for event in upcoming_events],
        "investor_flow": serialized_flow,
        "ai_signal": serialized_ai_signal,
        "theme_score": round(article_theme_score, 2),
        "theme_hit_count": article_theme_hits,
        "matched_themes": matched_themes,
        "keyword_gate_passed": keyword_gate_passed,
        "horizon": playbook_meta["horizon"],
        "gate_status": playbook_meta["gate_status"],
        "gate_reasons": playbook_meta["gate_reasons"],
        "playbook_alignment": playbook_meta["playbook_alignment"],
        "ai_thesis": playbook_meta["ai_thesis"] or (serialized_ai_signal or {}).get("summary"),
        "technical_snapshot": playbook_meta["technical_snapshot"],
        "technical_view": playbook_meta["technical_view"],
        "setup_quality": playbook_meta["setup_quality"],
    }


def generate_today_picks(
    data: DailyData,
    limit: int = 8,
    auto_candidate_limit: int = 100,
    ai_signals: dict | None = None,
    playbook: dict | None = None,
) -> dict:
    """뉴스에서 기업을 매칭해 오늘의 추천 종목을 생성한다."""
    now = datetime.now(_KST)
    matched: list[dict] = []
    disclosure_map = {}
    flow_map = {}
    ai_signal_map = {}
    playbook_candidate_map = _playbook_candidate_map(playbook)

    for item in data.disclosures:
        disclosure_map.setdefault(item.stock_code, []).append(item)
        disclosure_map.setdefault(item.company_name, []).append(item)

    for flow in data.investor_flows:
        flow_map[flow.code] = flow
        flow_map[flow.name] = flow

    for item in (ai_signals or {}).get("signals", []):
        ai_signal_map[item.get("code") or item.get("name")] = item
        ai_signal_map[item.get("name")] = item

    catalog_entries = get_company_catalog(scope="live")
    existing_codes = {entry.code.upper()
                      for entry in catalog_entries if entry.code}
    dynamic_entries = _extract_dynamic_us_ticker_entries(
        data.news,
        existing_codes=existing_codes,
    )
    all_entries = catalog_entries + dynamic_entries

    for entry in all_entries:
        aliases = tuple(_normalize(alias) for alias in entry.aliases)
        related = []
        entry_disclosures = disclosure_map.get(
            entry.code, []) or disclosure_map.get(entry.name, [])
        entry_flow = flow_map.get(entry.code) or flow_map.get(entry.name)
        entry_ai_signal = ai_signal_map.get(
            entry.code) or ai_signal_map.get(entry.name)
        entry_playbook_candidate = playbook_candidate_map.get(
            entry.code) or playbook_candidate_map.get(entry.name)
        for article in data.news:
            text = _article_text(article)
            if any(_alias_in_text(alias, text) for alias in aliases):
                related.append(article)

        if not related and not entry_disclosures and not _has_notable_flow(entry_flow) and not entry_ai_signal and not entry_playbook_candidate:
            continue

        matched.append(
            _build_pick(
                entry,
                related,
                data,
                entry_disclosures,
                entry_flow,
                entry_ai_signal,
                playbook,
                entry_playbook_candidate,
            )
        )

    matched.sort(
        key=lambda item: (
            {"passed": 2, "caution": 1, "blocked": 0}.get(
                str(item.get("gate_status", "passed")), 0),
            item["score"],
            item["confidence"],
        ),
        reverse=True,
    )

    auto_limit = max(1, int(auto_candidate_limit))
    auto_candidates = [
        item
        for item in matched
        if str(item.get("market") or "").upper() in _AUTO_TRADE_MARKETS
    ][:auto_limit]
    auto_candidate_market_counts = {
        market: sum(
            1 for item in auto_candidates
            if str(item.get("market") or "").upper() == market
        )
        for market in sorted(_AUTO_TRADE_MARKETS)
    }

    market_tone = "중립"
    if data.market.kospi_change_pct is not None and data.market.kospi_change_pct >= 1:
        market_tone = "국내 위험선호"
    elif data.market.nasdaq_change_pct is not None and data.market.nasdaq_change_pct <= -1:
        market_tone = "글로벌 위험회피"

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "date": now.strftime("%Y-%m-%d"),
        "market_tone": market_tone,
        "strategy": "news-driven-picks-v1+playbook+openai-aux" if playbook else ("news-driven-picks-v1+openai-aux" if (ai_signals or {}).get("signals") else "news-driven-picks-v1"),
        "playbook_ref": (playbook or {}).get("generated_at") or (playbook or {}).get("date"),
        "picks": matched[:limit],
        "auto_candidates": auto_candidates,
        "auto_candidate_limit": auto_limit,
        "auto_candidate_total": len(auto_candidates),
        "auto_candidate_market_counts": auto_candidate_market_counts,
    }


def build_watchlist_actions(
    watchlist_items: list[dict],
    today_picks: dict | None,
    recommendations: dict | None,
    previous_recommendations: dict | None = None,
    previous_today_picks: dict | None = None,
    ai_signals: dict | None = None,
    previous_ai_signals: dict | None = None,
) -> dict:
    """관심종목에 대해 buy/hold/sell/watch 액션을 계산한다."""
    now = datetime.now(_KST)
    pick_map = {}
    previous_pick_map = {}
    recommendation_map = {}
    previous_recommendation_map = {}
    ai_signal_map = {}
    previous_ai_signal_map = {}

    for item in (today_picks or {}).get("picks", []):
        pick_map[item.get("code") or item.get("name")] = item
        pick_map[item.get("name")] = item

    for item in (previous_today_picks or {}).get("picks", []):
        previous_pick_map[item.get("code") or item.get("name")] = item
        previous_pick_map[item.get("name")] = item

    for item in (recommendations or {}).get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        recommendation_map[key] = item
        recommendation_map[item.get("name")] = item

    for item in (previous_recommendations or {}).get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        previous_recommendation_map[key] = item
        previous_recommendation_map[item.get("name")] = item

    for item in (ai_signals or {}).get("signals", []):
        ai_signal_map[item.get("code") or item.get("name")] = item
        ai_signal_map[item.get("name")] = item

    for item in (previous_ai_signals or {}).get("signals", []):
        previous_ai_signal_map[item.get("code") or item.get("name")] = item
        previous_ai_signal_map[item.get("name")] = item

    actions = []
    for watch in watchlist_items:
        key = watch.get("code") or watch.get("name")
        current_pick = pick_map.get(key) or pick_map.get(watch.get("name"))
        current_rec = recommendation_map.get(
            key) or recommendation_map.get(watch.get("name"))
        previous_pick = previous_pick_map.get(
            key) or previous_pick_map.get(watch.get("name"))
        previous_rec = previous_recommendation_map.get(
            key) or previous_recommendation_map.get(watch.get("name"))
        current_ai_signal = ai_signal_map.get(
            key) or ai_signal_map.get(watch.get("name"))
        previous_ai_signal = previous_ai_signal_map.get(
            key) or previous_ai_signal_map.get(watch.get("name"))

        score, score_notes = _external_watchlist_score(
            current_pick, current_rec)
        reasons = []
        risks = []
        technical_reasons = []
        technical_risks = []
        flow_reasons = []
        flow_risks = []
        related_news = []
        signal = "중립"
        technicals = watch.get("technicals") or {}
        investor_flow = watch.get("investor_flow") or {}
        ai_reasons = []
        ai_risks = []
        serialized_ai_signal = None
        gate_status = "passed"
        gate_reasons: list[str] = []
        horizon = "short_term"
        playbook_alignment = None
        ai_thesis = None

        if current_pick:
            signal = current_pick.get("signal", signal)
            reasons.extend(current_pick.get("reasons", []))
            risks.extend(current_pick.get("risks", []))
            related_news = current_pick.get("related_news", [])
            if not investor_flow:
                investor_flow = current_pick.get("investor_flow") or {}
            serialized_ai_signal = current_pick.get("ai_signal")
            gate_status = str(current_pick.get("gate_status", gate_status))
            gate_reasons = list(current_pick.get(
                "gate_reasons", gate_reasons) or [])
            horizon = str(current_pick.get("horizon", horizon))
            playbook_alignment = current_pick.get("playbook_alignment")
            ai_thesis = current_pick.get("ai_thesis")
        if current_rec:
            if not current_pick:
                signal = current_rec.get("signal", signal)
            reasons.extend(current_rec.get("reasons", []))
            risks.extend(current_rec.get("risks", []))
            if not gate_reasons:
                gate_status = str(current_rec.get("gate_status", gate_status))
                gate_reasons = list(current_rec.get(
                    "gate_reasons", gate_reasons) or [])
                horizon = str(current_rec.get("horizon", horizon))
                playbook_alignment = current_rec.get(
                    "playbook_alignment", playbook_alignment)
                ai_thesis = current_rec.get("ai_thesis", ai_thesis)
        if not current_pick and current_ai_signal:
            ai_score, ai_reasons, ai_risks, serialized_ai_signal = _ai_signal_adjustment(
                current_ai_signal)
            score += ai_score
            reasons.extend(ai_reasons)
            risks.extend(ai_risks)
            signal = serialized_ai_signal.get("action_bias", signal) or signal

        if watch.get("change_pct") is not None:
            change_pct = float(watch["change_pct"])
            if change_pct <= -2:
                score -= 2
                risks.append("단기 낙폭이 커 변동성 관리 필요")
            elif change_pct >= 2:
                reasons.append("단기 모멘텀이 확인되는 흐름")

        if technicals:
            current_price = technicals.get("current_price")
            sma20 = technicals.get("sma20")
            sma60 = technicals.get("sma60")
            volume_ratio = technicals.get("volume_ratio")
            rsi14 = technicals.get("rsi14")
            macd_hist = technicals.get("macd_hist")
            macd = technicals.get("macd")
            macd_signal = technicals.get("macd_signal")

            if current_price is not None and sma20 is not None:
                if current_price > sma20:
                    score += 2.0
                    technical_reasons.append("주가가 20일 이동평균선 위에서 유지")
                else:
                    score -= 2.0
                    technical_risks.append("주가가 20일 이동평균선 아래에 위치")

            if sma20 is not None and sma60 is not None:
                if sma20 > sma60:
                    score += 1.5
                    technical_reasons.append("20일선이 60일선 위로 올라선 추세")
                else:
                    score -= 1.5
                    technical_risks.append("20일선이 60일선 아래로 약화된 추세")

            if volume_ratio is not None:
                if volume_ratio >= 1.5:
                    score += 1.5
                    technical_reasons.append(
                        f"거래량이 20일 평균 대비 {volume_ratio:.2f}배")
                elif volume_ratio <= 0.7:
                    score -= 0.5
                    technical_risks.append("거래량이 줄어 추세 신뢰도가 낮음")

            if rsi14 is not None:
                if rsi14 <= 30:
                    score += 1.5
                    technical_reasons.append(f"RSI {rsi14:.1f}로 과매도 구간")
                elif rsi14 >= 70:
                    score -= 2.0
                    technical_risks.append(f"RSI {rsi14:.1f}로 과열 구간")

            if macd_hist is not None and macd is not None and macd_signal is not None:
                if macd_hist > 0 and macd > macd_signal:
                    score += 2.0
                    technical_reasons.append("MACD가 시그널선 위에서 모멘텀 개선")
                elif macd_hist < 0 and macd < macd_signal:
                    score -= 2.0
                    technical_risks.append("MACD가 시그널선 아래로 약세 전환")

        if investor_flow:
            foreign_1d = investor_flow.get("foreign_net_1d")
            foreign_5d = investor_flow.get("foreign_net_5d")
            institution_1d = investor_flow.get("institution_net_1d")
            institution_5d = investor_flow.get("institution_net_5d")

            if foreign_1d is not None and institution_1d is not None:
                if foreign_1d > 0 and institution_1d > 0:
                    score += 1.5
                    flow_reasons.append("외국인·기관이 최근 1일 동반 순매수")
                elif foreign_1d < 0 and institution_1d < 0:
                    score -= 1.5
                    flow_risks.append("외국인·기관이 최근 1일 동반 순매도")

            if foreign_5d is not None and institution_5d is not None:
                if foreign_5d > 0 and institution_5d > 0:
                    score += 2.5
                    flow_reasons.append("외국인·기관이 최근 5일 누적 순매수")
                elif foreign_5d < 0 and institution_5d < 0:
                    score -= 2.5
                    flow_risks.append("외국인·기관이 최근 5일 누적 순매도")
                elif foreign_5d * institution_5d < 0:
                    score -= 0.5
                    flow_risks.append("외국인과 기관 수급 방향이 엇갈림")

        score = round(max(20, min(95, score)), 1)
        if signal == "회피" and score <= 54:
            action = "sell"
        elif signal == "추천" and score >= 68:
            action = "buy"
        elif score >= 58:
            action = "hold"
        elif score >= 48:
            action = "watch"
        else:
            action = "sell"

        previous_signal = None
        if previous_pick:
            previous_signal = previous_pick.get("signal")
        elif previous_rec:
            previous_signal = previous_rec.get("signal")
        elif previous_ai_signal:
            previous_signal = previous_ai_signal.get("action_bias")

        changed_from_yesterday = None
        previous_score = None
        if previous_pick or previous_rec:
            previous_score, _ = _external_watchlist_score(
                previous_pick, previous_rec)
        if previous_score is None and previous_ai_signal:
            previous_score = 50.0
        if previous_score is not None and not previous_pick and previous_ai_signal:
            previous_ai_score, _, _, _ = _ai_signal_adjustment(
                previous_ai_signal)
            previous_score += previous_ai_score
        if previous_signal is not None or previous_score is not None:
            changed_from_yesterday = {
                "previous_signal": previous_signal,
                "score_diff": round(score - (previous_score or 0), 1),
            }

        confidence = 55
        if current_pick:
            confidence = current_pick.get("confidence", confidence)
        elif current_rec:
            confidence = current_rec.get("confidence", confidence)

        actions.append({
            "code": watch.get("code", ""),
            "name": watch.get("name", ""),
            "market": watch.get("market", ""),
            "price": watch.get("price"),
            "change_pct": watch.get("change_pct"),
            "action": action,
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "reasons": (score_notes + technical_reasons + flow_reasons + reasons)[:4] or ["오늘 기준 뚜렷한 추가 재료는 제한적입니다."],
            "risks": (technical_risks + flow_risks + ai_risks + risks)[:3] or ["단기 변동성 관리가 필요합니다."],
            "related_news": related_news[:2],
            "technicals": technicals or None,
            "investor_flow": investor_flow or None,
            "ai_signal": serialized_ai_signal,
            "changed_from_yesterday": changed_from_yesterday,
            "gate_status": gate_status,
            "gate_reasons": gate_reasons[:3],
            "horizon": horizon if horizon in {"short_term", "mid_term"} else "short_term",
            "playbook_alignment": playbook_alignment,
            "ai_thesis": ai_thesis,
        })

    actions.sort(key=lambda item: item["score"], reverse=True)
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "date": now.strftime("%Y-%m-%d"),
        "actions": actions,
    }
