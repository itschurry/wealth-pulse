"""OpenAI API를 이용한 경제 리포트 및 플레이북 생성."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from loguru import logger
from openai import APIError, OpenAI, RateLimitError

from analyzer.market_context_builder import summarize_macro_for_prompt, summarize_market_context_for_prompt
from analyzer.technical_snapshot import evaluate_technical_snapshot, fetch_technical_snapshot
from analyzer.utils import (
    DYNAMIC_TICKER_BLOCKLIST as _DYNAMIC_TICKER_BLOCKLIST,
    US_TICKER_PATTERN as _US_TICKER_PATTERN,
    article_text as _article_text,
    has_notable_flow as _has_notable_flow,
    normalize_lower as _normalize,
    safe_json_loads as _safe_json_loads,
)
from collectors.models import DailyData, NewsArticle
from config.company_catalog import CompanyCatalogEntry, get_company_catalog
from config.prompts import DAILY_REPORT_PROMPT, PLAYBOOK_PROMPT, PLAYBOOK_SYSTEM_PROMPT, SYSTEM_PROMPT
from config.settings import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_PLAYBOOK_MODEL

_DISCLOSURE_POSITIVE = {"earnings", "contract", "shareholder_return", "investment"}
_ALLOWED_BIAS = {"bullish", "neutral", "defensive"}
_ALLOWED_ACTION = {"buy", "watch", "avoid"}
_ALLOWED_MARKETS = {"KOSPI", "KOSDAQ", "NASDAQ", "NYSE"}


def _extract_dynamic_us_ticker_entries(news: list[NewsArticle], existing_codes: set[str]) -> list[CompanyCatalogEntry]:
    mention_counts: dict[str, int] = {}
    dollar_mentioned: set[str] = set()

    for article in news:
        raw_text = " ".join([article.title or "", article.summary or "", article.body or ""])
        if not raw_text:
            continue
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


def _collect_candidate_pool(data: DailyData, limit: int = 24) -> list[dict]:
    disclosure_map: dict[str, list] = {}
    flow_map: dict[str, dict] = {}
    candidates: list[dict] = []

    for item in data.disclosures:
        disclosure_map.setdefault(item.stock_code, []).append(item)
        disclosure_map.setdefault(item.company_name, []).append(item)

    for flow in data.investor_flows:
        flow_payload = {
            "as_of": flow.as_of,
            "source": flow.source,
            "foreign_net_1d": flow.foreign_net_1d,
            "foreign_net_5d": flow.foreign_net_5d,
            "institution_net_1d": flow.institution_net_1d,
            "institution_net_5d": flow.institution_net_5d,
        }
        flow_map[flow.code] = flow_payload
        flow_map[flow.name] = flow_payload

    catalog_entries = get_company_catalog(scope="live")
    existing_codes = {entry.code.upper() for entry in catalog_entries if entry.code}
    all_entries = catalog_entries + _extract_dynamic_us_ticker_entries(data.news, existing_codes)

    for entry in all_entries:
        aliases = tuple(_normalize(alias) for alias in entry.aliases)
        related_articles = []
        for article in data.news:
            text = _article_text(article)
            if any(alias in text for alias in aliases):
                related_articles.append(article)

        disclosures = disclosure_map.get(entry.code, []) or disclosure_map.get(entry.name, [])
        flow = flow_map.get(entry.code) or flow_map.get(entry.name)
        if not related_articles and not disclosures and not _has_notable_flow(flow):
            continue

        candidates.append(
            {
                "entry": entry,
                "articles": related_articles[:3],
                "disclosures": disclosures[:2],
                "flow": flow,
                "priority": len(related_articles) * 4 + len(disclosures) * 5 + (3 if _has_notable_flow(flow) else 0),
            }
        )

    candidates.sort(key=lambda item: (item["priority"], item["entry"].name), reverse=True)
    return candidates[:limit]


def _format_candidate_pool(candidates: list[dict]) -> str:
    if not candidates:
        return "후보 종목 없음"

    blocks: list[str] = []
    for item in candidates:
        entry: CompanyCatalogEntry = item["entry"]
        lines = [f"- 종목: {entry.name} ({entry.code}, {entry.market}, {entry.sector})"]
        if item["articles"]:
            lines.append("  뉴스:")
            for article in item["articles"]:
                lines.append(f"  - [{article.source}] {article.title}")
        if item["disclosures"]:
            lines.append("  공시:")
            for disclosure in item["disclosures"]:
                lines.append(f"  - [{disclosure.importance}/{disclosure.category}] {disclosure.title}")
        if item["flow"]:
            flow = item["flow"]
            lines.append(
                "  수급: "
                f"외국인 1일 {flow['foreign_net_1d']:+,}, 5일 {flow['foreign_net_5d']:+,}; "
                f"기관 1일 {flow['institution_net_1d']:+,}, 5일 {flow['institution_net_5d']:+,}"
            )
        technical_snapshot = item.get("technical_snapshot")
        if technical_snapshot:
            lines.append("  기술:")
            lines.append(
                "  - "
                f"현재가 {technical_snapshot.get('current_price')}, "
                f"등락률 {technical_snapshot.get('change_pct')}%, "
                f"SMA20 {technical_snapshot.get('sma20')}, SMA60 {technical_snapshot.get('sma60')}"
            )
            lines.append(
                "  - "
                f"RSI14 {technical_snapshot.get('rsi14')}, "
                f"MACD {technical_snapshot.get('macd')}, Signal {technical_snapshot.get('macd_signal')}, Hist {technical_snapshot.get('macd_hist')}"
            )
            lines.append(
                "  - "
                f"거래량배수 {technical_snapshot.get('volume_ratio')}, "
                f"ATR14 {technical_snapshot.get('atr14')} ({technical_snapshot.get('atr14_pct')}%), "
                f"20일 돌파 {technical_snapshot.get('breakout_20d')}, "
                f"추세 {technical_snapshot.get('trend')}"
            )
        if item.get("technical_view"):
            lines.append(f"  기술해석: {item['technical_view']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _candidate_to_playbook_item(item: dict, action: str, thesis: str) -> dict:
    entry: CompanyCatalogEntry = item["entry"]
    articles = item["articles"]
    disclosures = item["disclosures"]
    flow = item["flow"]
    reasons = [f"관련 뉴스 {len(articles)}건" if articles else "", f"관련 공시 {len(disclosures)}건" if disclosures else ""]
    if flow and _has_notable_flow(flow):
        reasons.append("외국인·기관 동행 수급 확인")
    risks = []
    if flow and flow.get("foreign_net_5d", 0) < 0 and flow.get("institution_net_5d", 0) < 0:
        risks.append("최근 5일 외국인·기관 동반 순매도")
    if not articles and not disclosures:
        risks.append("직접 뉴스/공시 근거가 제한적")
    technical_view = str(item.get("technical_view", "")).strip()
    setup_quality = str(item.get("setup_quality", "")).strip() or "mixed"
    if technical_view:
        reasons.append(f"기술해석: {technical_view}")
    return {
        "name": entry.name,
        "code": entry.code,
        "market": entry.market if entry.market in _ALLOWED_MARKETS else "NASDAQ",
        "sector": entry.sector,
        "thesis": thesis,
        "action": action,
        "confidence": 62 + min(item["priority"], 18),
        "reasons": [reason for reason in reasons if reason][:3],
        "risks": risks[:3],
        "technical_snapshot": item.get("technical_snapshot"),
        "technical_view": technical_view,
        "setup_quality": setup_quality,
    }


def _normalize_technical_snapshot(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    breakout_20d = item.get("breakout_20d")
    if breakout_20d is not None:
        breakout_20d = bool(breakout_20d)
    trend = str(item.get("trend", "neutral")).strip().lower()
    if trend not in {"bullish", "bearish", "neutral"}:
        trend = "neutral"
    snapshot = {
        "current_price": item.get("current_price"),
        "change_pct": item.get("change_pct"),
        "sma20": item.get("sma20"),
        "sma60": item.get("sma60"),
        "volume": item.get("volume"),
        "volume_avg20": item.get("volume_avg20"),
        "volume_ratio": item.get("volume_ratio"),
        "rsi14": item.get("rsi14"),
        "macd": item.get("macd"),
        "macd_signal": item.get("macd_signal"),
        "macd_hist": item.get("macd_hist"),
        "atr14": item.get("atr14"),
        "atr14_pct": item.get("atr14_pct"),
        "breakout_20d": breakout_20d,
        "breakout_20d_high": item.get("breakout_20d_high"),
        "trend": trend,
    }
    if not any(value is not None for key, value in snapshot.items() if key != "trend"):
        return None
    return snapshot


def _enrich_candidate_pool_with_technicals(candidates: list[dict], limit: int = 12) -> list[dict]:
    if not candidates:
        return []

    enriched = [dict(item) for item in candidates]
    indices = [idx for idx, item in enumerate(enriched[:limit]) if getattr(item.get("entry"), "code", "")]
    if not indices:
        return enriched

    with ThreadPoolExecutor(max_workers=max(1, min(len(indices), 6))) as executor:
        futures = {
            executor.submit(
                fetch_technical_snapshot,
                enriched[idx]["entry"].code,
                enriched[idx]["entry"].market,
            ): idx
            for idx in indices
        }
        for future in as_completed(futures):
            idx = futures[future]
            snapshot = future.result()
            enriched[idx]["technical_snapshot"] = snapshot
            assessment = evaluate_technical_snapshot(snapshot, horizon="short_term")
            enriched[idx]["technical_view"] = assessment.get("technical_view")
            enriched[idx]["setup_quality"] = assessment.get("setup_quality")
    return enriched


def _fallback_playbook(data: DailyData, candidates: list[dict] | None = None) -> dict:
    context = data.market_context
    market = data.market
    regime = (context.regime if context else "") or "neutral"
    short_term_bias = "neutral"
    mid_term_bias = "neutral"
    if context and context.risk_level == "높음":
        short_term_bias = "defensive"
    elif market.kospi_change_pct is not None and market.kospi_change_pct >= 0.8:
        short_term_bias = "bullish"
    elif market.kospi_change_pct is not None and market.kospi_change_pct <= -0.8:
        short_term_bias = "defensive"

    if context and context.regime == "risk_on":
        mid_term_bias = "bullish"
    elif context and context.regime == "risk_off":
        mid_term_bias = "defensive"

    candidate_pool = candidates or _collect_candidate_pool(data, limit=8)
    short_term_items = [
        _candidate_to_playbook_item(item, "buy", "뉴스/공시/수급이 단기적으로 겹친 후보") for item in candidate_pool[:4]
    ]
    mid_term_items = [
        _candidate_to_playbook_item(item, "watch", "단기 촉매는 있으나 중기 검증이 더 필요한 후보") for item in candidate_pool[4:8]
    ]
    favored = []
    avoided = []
    for item in candidate_pool:
        sector = item["entry"].sector
        if sector not in favored:
            favored.append(sector)
    if context and context.risk_level == "높음":
        avoided.extend(["고밸류 성장", "이벤트 민감 섹터"])
    if context and context.dollar_signal == "강세":
        avoided.extend(["환율 민감 수입주"])

    event_watchlist = [
        {
            "name": event.name,
            "timing": event.scheduled_at.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
            "importance": event.importance,
            "note": event.summary or f"{event.country} 이벤트",
        }
        for event in data.calendar_events[:4]
    ]

    return {
        "market_regime": regime,
        "short_term_bias": short_term_bias,
        "mid_term_bias": mid_term_bias,
        "favored_sectors": favored[:6],
        "avoided_sectors": avoided[:6],
        "tactical_setups": [
            "뉴스·공시·수급이 동시에 맞는 종목 우선",
            "장대 양봉 추격보다 눌림 확인 후 대응",
        ],
        "invalid_setups": [
            "고점 추격 매수",
            "이벤트 직전 무리한 비중 확대",
        ],
        "key_risks": (list(context.risks)[:4] if context else []) or ["거시 이벤트 전후 변동성 확대 가능성"],
        "event_watchlist": event_watchlist,
        "stock_candidates_short_term": short_term_items,
        "stock_candidates_mid_term": mid_term_items,
        "gating_rules": [
            "근거 부족 후보는 watch 이하",
            "시장 국면과 역행하면 비중 축소 또는 보류",
            "이벤트 리스크가 큰 날은 추격 매수 지양",
        ],
    }


def _normalize_playbook_candidate(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name", "")).strip()
    code = str(item.get("code", "")).strip().upper()
    if not name:
        return None
    market = str(item.get("market", "NASDAQ")).strip().upper()
    if market not in _ALLOWED_MARKETS:
        market = "NASDAQ" if code.isalpha() else "KOSPI"
    action = str(item.get("action", "watch")).strip().lower()
    if action not in _ALLOWED_ACTION:
        action = "watch"
    try:
        confidence = int(round(float(item.get("confidence", 60))))
    except (TypeError, ValueError):
        confidence = 60
    confidence = max(25, min(95, confidence))
    setup_quality = str(item.get("setup_quality", "mixed")).strip().lower() or "mixed"
    if setup_quality not in {"high", "mixed", "low", "unknown"}:
        setup_quality = "mixed"
    return {
        "name": name,
        "code": code,
        "market": market,
        "sector": str(item.get("sector", "")).strip() or "미분류",
        "thesis": str(item.get("thesis", "")).strip()[:160],
        "action": action,
        "confidence": confidence,
        "reasons": [str(value).strip() for value in item.get("reasons", []) if str(value).strip()][:3],
        "risks": [str(value).strip() for value in item.get("risks", []) if str(value).strip()][:3],
        "technical_snapshot": _normalize_technical_snapshot(item.get("technical_snapshot")),
        "technical_view": str(item.get("technical_view", "")).strip()[:180],
        "setup_quality": setup_quality,
    }


def _normalize_playbook(payload: dict | None, fallback: dict) -> dict:
    source = payload or {}
    playbook = {
        "market_regime": str(source.get("market_regime", fallback["market_regime"])).strip() or fallback["market_regime"],
        "short_term_bias": str(source.get("short_term_bias", fallback["short_term_bias"])).strip().lower(),
        "mid_term_bias": str(source.get("mid_term_bias", fallback["mid_term_bias"])).strip().lower(),
        "favored_sectors": [str(value).strip() for value in source.get("favored_sectors", fallback["favored_sectors"]) if str(value).strip()][:6],
        "avoided_sectors": [str(value).strip() for value in source.get("avoided_sectors", fallback["avoided_sectors"]) if str(value).strip()][:6],
        "tactical_setups": [str(value).strip() for value in source.get("tactical_setups", fallback["tactical_setups"]) if str(value).strip()][:6],
        "invalid_setups": [str(value).strip() for value in source.get("invalid_setups", fallback["invalid_setups"]) if str(value).strip()][:6],
        "key_risks": [str(value).strip() for value in source.get("key_risks", fallback["key_risks"]) if str(value).strip()][:6],
        "gating_rules": [str(value).strip() for value in source.get("gating_rules", fallback["gating_rules"]) if str(value).strip()][:6],
    }
    if playbook["short_term_bias"] not in _ALLOWED_BIAS:
        playbook["short_term_bias"] = fallback["short_term_bias"]
    if playbook["mid_term_bias"] not in _ALLOWED_BIAS:
        playbook["mid_term_bias"] = fallback["mid_term_bias"]

    event_watchlist = []
    for item in source.get("event_watchlist", fallback["event_watchlist"]):
        if not isinstance(item, dict):
            continue
        event_watchlist.append(
            {
                "name": str(item.get("name", "")).strip(),
                "timing": str(item.get("timing", "")).strip(),
                "importance": str(item.get("importance", "중간")).strip() or "중간",
                "note": str(item.get("note", "")).strip(),
            }
        )
    playbook["event_watchlist"] = event_watchlist[:6]

    fallback_short_lookup = {
        f"{str(item.get('code', '')).strip().upper()}::{str(item.get('name', '')).strip()}": item
        for item in fallback.get("stock_candidates_short_term", [])
        if isinstance(item, dict)
    }
    fallback_mid_lookup = {
        f"{str(item.get('code', '')).strip().upper()}::{str(item.get('name', '')).strip()}": item
        for item in fallback.get("stock_candidates_mid_term", [])
        if isinstance(item, dict)
    }

    short_term = []
    for item in source.get("stock_candidates_short_term", fallback["stock_candidates_short_term"]):
        normalized = _normalize_playbook_candidate(item)
        if normalized:
            ref = fallback_short_lookup.get(f"{normalized['code']}::{normalized['name']}")
            if ref:
                if not normalized.get("technical_snapshot"):
                    normalized["technical_snapshot"] = ref.get("technical_snapshot")
                if not normalized.get("technical_view"):
                    normalized["technical_view"] = ref.get("technical_view")
                if normalized.get("setup_quality") in {"", "mixed"} and ref.get("setup_quality"):
                    normalized["setup_quality"] = ref.get("setup_quality")
            short_term.append(normalized)
    mid_term = []
    for item in source.get("stock_candidates_mid_term", fallback["stock_candidates_mid_term"]):
        normalized = _normalize_playbook_candidate(item)
        if normalized:
            ref = fallback_mid_lookup.get(f"{normalized['code']}::{normalized['name']}")
            if ref:
                if not normalized.get("technical_snapshot"):
                    normalized["technical_snapshot"] = ref.get("technical_snapshot")
                if not normalized.get("technical_view"):
                    normalized["technical_view"] = ref.get("technical_view")
                if normalized.get("setup_quality") in {"", "mixed"} and ref.get("setup_quality"):
                    normalized["setup_quality"] = ref.get("setup_quality")
            mid_term.append(normalized)
    playbook["stock_candidates_short_term"] = short_term[:8]
    playbook["stock_candidates_mid_term"] = mid_term[:8]
    return playbook


def _format_daily_data(data: DailyData) -> dict:
    """DailyData를 프롬프트용 텍스트로 변환."""
    m = data.market
    lines = []
    if m.kospi:
        lines.append(f"KOSPI: {m.kospi:,.2f} ({m.kospi_change_pct:+.2f}%)")
    if m.kosdaq:
        lines.append(f"KOSDAQ: {m.kosdaq:,.2f} ({m.kosdaq_change_pct:+.2f}%)")
    if m.sp100:
        lines.append(f"S&P100: {m.sp100:,.2f} ({m.sp100_change_pct:+.2f}%)")
    if m.nasdaq:
        lines.append(f"NASDAQ: {m.nasdaq:,.2f} ({m.nasdaq_change_pct:+.2f}%)")
    if m.usd_krw:
        lines.append(f"USD/KRW: {m.usd_krw:,.2f}")
    if m.wti_oil:
        lines.append(f"WTI유가: ${m.wti_oil:.2f}")
    if m.gold:
        lines.append(f"금: ${m.gold:,.2f}")
    if m.btc_usd:
        lines.append(f"BTC: ${m.btc_usd:,.0f}")
    if m.vix:
        lines.append(f"VIX(공포지수): {m.vix:.2f}")
    market_data = "\n".join(lines) if lines else "시장 데이터 수집 실패"

    n_lines = []
    for i, article in enumerate(data.news[:18]):
        snippet = (article.summary or article.body or "")[:220]
        n_lines.append(
            f"{i+1}. [{article.source}] {article.title}\n"
            f"   URL: {article.url}\n"
            f"   요약: {snippet}"
        )
    news_summary = "\n\n".join(n_lines) if n_lines else "뉴스 수집 실패"

    disclosure_lines = []
    for item in data.disclosures[:10]:
        filed_at = item.filed_at.strftime("%Y-%m-%d")
        disclosure_lines.append(
            f"- [{item.company_name}] {item.title} ({filed_at}, {item.source}, 중요도 {item.importance})\n"
            f"  URL: {item.url}"
        )
    disclosure_summary = "\n".join(disclosure_lines) if disclosure_lines else "주요 공시 없음"

    calendar_lines = []
    for event in data.calendar_events[:10]:
        scheduled = event.scheduled_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
        calendar_lines.append(
            f"- [{event.country}] {event.name} ({scheduled}, 중요도 {event.importance})\n"
            f"  URL: {event.url or event.source}"
        )
    calendar_summary = "\n".join(calendar_lines) if calendar_lines else "향후 7일 내 핵심 일정 없음"

    flow_lines = []
    for flow in sorted(
        data.investor_flows,
        key=lambda item: abs(item.foreign_net_5d) + abs(item.institution_net_5d),
        reverse=True,
    )[:10]:
        flow_lines.append(
            f"- [{flow.name}] 외국인 5일 {flow.foreign_net_5d:+,} / 기관 5일 {flow.institution_net_5d:+,}"
            f" (1일 외국인 {flow.foreign_net_1d:+,}, 기관 {flow.institution_net_1d:+,})"
        )
    flow_summary = "\n".join(flow_lines) if flow_lines else "수급 데이터 없음"

    candidate_pool = _enrich_candidate_pool_with_technicals(_collect_candidate_pool(data))
    return {
        "market_data": market_data,
        "news_summary": news_summary,
        "macro_summary": summarize_macro_for_prompt(data.macro),
        "market_context_summary": summarize_market_context_for_prompt(data.market_context),
        "disclosure_summary": disclosure_summary,
        "calendar_summary": calendar_summary,
        "flow_summary": flow_summary,
        "candidate_universe": _format_candidate_pool(candidate_pool),
        "candidate_pool": candidate_pool,
    }


async def _create_report(client: OpenAI, prompt: str) -> str:
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
        max_completion_tokens=8192,
    )
    return response.choices[0].message.content or ""


async def _create_playbook(client: OpenAI, prompt: str) -> dict | None:
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=OPENAI_PLAYBOOK_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PLAYBOOK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.15,
        max_completion_tokens=3200,
    )
    content = response.choices[0].message.content or "{}"
    return _safe_json_loads(content)


async def analyze_with_playbook(data: DailyData) -> tuple[str, dict]:
    """OpenAI API로 일일 리포트와 구조화 플레이북을 생성한다."""
    formatted = _format_daily_data(data)
    from config.portfolio import INVESTMENT_PROFILE

    investment_profile = (
        f"투자 성향: {INVESTMENT_PROFILE['style']}, "
        f"선호 리스크: {INVESTMENT_PROFILE['risk_preference']}"
    )
    report_prompt = DAILY_REPORT_PROMPT.format(
        investment_profile=investment_profile,
        market_data=formatted["market_data"],
        news_summary=formatted["news_summary"],
        macro_summary=formatted["macro_summary"],
        market_context_summary=formatted["market_context_summary"],
        disclosure_summary=formatted["disclosure_summary"],
        calendar_summary=formatted["calendar_summary"],
        flow_summary=formatted["flow_summary"],
        candidate_universe=formatted["candidate_universe"],
    )
    playbook_prompt = PLAYBOOK_PROMPT.format(
        investment_profile=investment_profile,
        market_data=formatted["market_data"],
        news_summary=formatted["news_summary"],
        macro_summary=formatted["macro_summary"],
        market_context_summary=formatted["market_context_summary"],
        disclosure_summary=formatted["disclosure_summary"],
        calendar_summary=formatted["calendar_summary"],
        flow_summary=formatted["flow_summary"],
        candidate_universe=formatted["candidate_universe"],
    )

    fallback_playbook = _fallback_playbook(data, formatted["candidate_pool"])
    now = datetime.now()
    playbook_date = now.strftime("%Y-%m-%d")
    playbook_generated_at = now.strftime("%Y-%m-%d %H:%M KST")

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY가 설정되지 않았습니다. 분석/플레이북을 폴백으로 생성합니다.")
        fallback_playbook["date"] = playbook_date
        fallback_playbook["generated_at"] = playbook_generated_at
        return _fallback_report(data), fallback_playbook

    client = OpenAI(api_key=OPENAI_API_KEY)
    report = ""
    playbook_payload: dict | None = None

    for attempt in range(3):
        try:
            logger.info(f"OpenAI 리포트/플레이북 호출 시도 {attempt+1}/3 (리포트 모델: {OPENAI_MODEL}, 플레이북 모델: {OPENAI_PLAYBOOK_MODEL})")
            report, playbook_payload = await asyncio.gather(
                _create_report(client, report_prompt),
                _create_playbook(client, playbook_prompt),
            )
            normalized_playbook = _normalize_playbook(playbook_payload, fallback_playbook)
            normalized_playbook["date"] = playbook_date
            normalized_playbook["generated_at"] = playbook_generated_at
            return report or _fallback_report(data), normalized_playbook
        except RateLimitError as exc:
            wait = 20 + attempt * 10
            logger.warning(f"OpenAI RateLimit (시도 {attempt+1}): {exc} — {wait}초 대기")
            if attempt < 2:
                await asyncio.sleep(wait)
        except APIError as exc:
            logger.error(f"OpenAI APIError (시도 {attempt+1}): {exc}")
            if attempt < 2:
                await asyncio.sleep(5)
        except Exception as exc:
            logger.error(f"OpenAI 예상 외 오류 (시도 {attempt+1}): {exc}")
            if attempt < 2:
                await asyncio.sleep(5)

    logger.error("OpenAI API 3회 모두 실패. 폴백 리포트와 플레이북을 생성합니다.")
    fallback_playbook["date"] = playbook_date
    fallback_playbook["generated_at"] = playbook_generated_at
    return _fallback_report(data), fallback_playbook


async def analyze(data: DailyData) -> str:
    """기존 호환용: 서술형 리포트만 반환한다."""
    report, _ = await analyze_with_playbook(data)
    return report


def _fallback_report(data: DailyData) -> str:
    """API 실패 시 원본 데이터 기반 간단 플레이북 리포트."""
    lines = ["## 3줄 요약"]
    context_summary = data.market_context.summary if data.market_context else "거시 컨텍스트 데이터 없음"
    lines.append("1. AI 분석 API 호출 실패로 원본 데이터 기반 플레이북을 제공합니다.")
    lines.append(f"2. 오늘 시장 해석의 핵심은 {context_summary}")
    lines.append("3. 근거가 약한 추격 매수보다 뉴스·공시·수급이 겹치는 후보만 선별 점검하세요.")
    lines.append("")
    lines.append("## 1. 시장 국면")
    m = data.market
    if m.kospi:
        lines.append(f"- KOSPI {m.kospi:,.2f} ({m.kospi_change_pct:+.2f}%)")
    if m.kosdaq:
        lines.append(f"- KOSDAQ {m.kosdaq:,.2f} ({m.kosdaq_change_pct:+.2f}%)")
    if m.sp100:
        lines.append(f"- S&P100 {m.sp100:,.2f} ({m.sp100_change_pct:+.2f}%)")
    if m.nasdaq:
        lines.append(f"- NASDAQ {m.nasdaq:,.2f} ({m.nasdaq_change_pct:+.2f}%)")
    if m.usd_krw:
        lines.append(f"- USD/KRW {m.usd_krw:,.2f}")
    lines.append("")
    lines.append("## 2. 오늘의 수급/테이프 해석")
    if data.investor_flows:
        for flow in sorted(
            data.investor_flows,
            key=lambda item: abs(item.foreign_net_5d) + abs(item.institution_net_5d),
            reverse=True,
        )[:3]:
            lines.append(
                f"- {flow.name}: 외국인 5일 {flow.foreign_net_5d:+,}, 기관 5일 {flow.institution_net_5d:+,}"
            )
    else:
        lines.append("- 수급 데이터가 제한적입니다.")
    lines.append("")
    lines.append("## 3. 단타 대응")
    lines.append("**1. 바로 볼 것**")
    lines.append("- 뉴스·공시·수급이 동시에 확인되는 후보만 우선 점검")
    lines.append("**2. 눌림목/추세추종 중 유리한 쪽**")
    lines.append("- 변동성 높은 장은 추격보다 눌림 확인 후 대응")
    lines.append("**3. 피해야 할 대응**")
    lines.append("- 이벤트 직전 무리한 비중 확대")
    lines.append("")
    lines.append("## 4. 중기 관찰")
    lines.append("**1. 2주~2개월 관점에서 유지되는 논리**")
    lines.append(f"- {context_summary}")
    lines.append("**2. 아직 확인이 더 필요한 논리**")
    lines.append("- 단기 뉴스가 실적/수급으로 이어지는지 추가 확인 필요")
    lines.append("")
    lines.append("## 5. 유리한 섹터 / 불리한 섹터")
    lines.append("**유리한 섹터**")
    lines.append("- 뉴스/공시/수급이 겹치는 섹터 우선")
    lines.append("**불리한 섹터**")
    lines.append("- 이벤트 민감도가 높은 과열 구간 종목")
    lines.append("")
    lines.append("## 6. 리스크 이벤트")
    if data.calendar_events:
        for event in data.calendar_events[:4]:
            scheduled = event.scheduled_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
            lines.append(f"- [{event.country}] {event.name} ({scheduled})")
    else:
        lines.append("- 향후 7일 내 핵심 이벤트 데이터 없음")
    lines.append("")
    lines.append("## 7. 후보 종목")
    candidate_pool = _collect_candidate_pool(data, limit=6)
    lines.append("**단타 후보**")
    for item in candidate_pool[:3]:
        enriched_item = _enrich_candidate_pool_with_technicals([item], limit=1)[0]
        technical_view = str(enriched_item.get("technical_view", "")).strip()
        suffix = f" ({technical_view})" if technical_view else ""
        lines.append(f"- {item['entry'].name}: 뉴스/공시/수급이 동시에 관측된 후보{suffix}")
    lines.append("**중기 후보**")
    for item in candidate_pool[3:5]:
        enriched_item = _enrich_candidate_pool_with_technicals([item], limit=1)[0]
        technical_view = str(enriched_item.get("technical_view", "")).strip()
        suffix = f" ({technical_view})" if technical_view else ""
        lines.append(f"- {item['entry'].name}: 중기 관점에서 후속 확인이 필요한 후보{suffix}")
    lines.append("**보류/제외 후보**")
    lines.append("- 근거가 약하거나 이벤트 리스크가 큰 종목은 보류")
    lines.append("")
    lines.append("## 8. 하면 안 되는 대응")
    lines.append("- 헤드라인만 보고 추격 매수")
    lines.append("- 리스크 이벤트 직전 과도한 레버리지")
    lines.append("- 근거가 빈약한 종목에 단기 과몰입")
    lines.append("")
    lines.append("⚠️ 본 자료는 투자 판단을 돕기 위한 참고 정보이며 투자 자문이나 매수·매도 추천이 아닙니다.")
    return "\n".join(lines)
