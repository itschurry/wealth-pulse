"""Report orchestration as a service layer.

The report output remains available, but this service is now an explainability
layer around the trading core architecture.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from loguru import logger

from analyzer.market_context_builder import build_market_context
from analyzer.recommendation_engine import generate_recommendations
from analyzer.today_picks_engine import generate_today_picks
from services.hanna_brief_service import build_hanna_daily_report_text
from collectors.calendar_collector import collect_calendar_events
from collectors.disclosure_collector import collect_disclosures
from collectors.flow_collector import collect_investor_flows
from collectors.macro_collector import collect_macro
from collectors.market_collector import collect_market
from collectors.models import DailyData
from collectors.news_collector import collect_news
from config.settings import LOGS_DIR
from reporter.report_generator import (
    save_analysis_cache,
    save_calendar_cache,
    save_disclosures_cache,
    save_investor_flows_cache,
    save_macro_cache,
    save_market_context_cache,
    save_news_cache,
    save_recommendations_cache,
    save_today_picks_cache,
)

_log_handler_id: int | None = None


def _setup_logging() -> None:
    global _log_handler_id
    if _log_handler_id is not None:
        try:
            logger.remove(_log_handler_id)
        except Exception:
            pass
    log_file = LOGS_DIR / f"daily_report_{datetime.now():%Y-%m-%d}.log"
    _log_handler_id = logger.add(
        str(log_file),
        rotation="1 day",
        retention="30 days",
        level="INFO",
        encoding="utf-8",
    )


async def run_report_pipeline() -> None:
    _setup_logging()
    logger.info("=== 일일 리포트 생성 시작 ===")

    logger.info("[1-6/10] 수집 병렬 시작...")
    loop = asyncio.get_event_loop()
    fallbacks = [None, [], [], [], [], []]
    names = ["market", "news", "macro", "calendar_events", "disclosures", "investor_flows"]
    collectors = [
        collect_market,
        collect_news,
        collect_macro,
        collect_calendar_events,
        collect_disclosures,
        collect_investor_flows,
    ]

    with ThreadPoolExecutor(max_workers=6) as executor:
        raw_results = await asyncio.gather(
            *[loop.run_in_executor(executor, fn) for fn in collectors],
            return_exceptions=True,
        )

    resolved: list = []
    for name, result, fallback in zip(names, raw_results, fallbacks):
        if isinstance(result, Exception):
            logger.warning(f"수집 실패 [{name}]: {result!r} — 폴백값 사용")
            resolved.append(fallback)
        else:
            resolved.append(result)
    market, news, macro, calendar_events, disclosures, investor_flows = resolved

    logger.info("[7/10] 시장 컨텍스트 생성...")
    market_context = build_market_context(market, macro)

    daily_data = DailyData(
        collected_at=datetime.now(),
        market=market,
        holdings=[],
        news=news,
        macro=macro,
        market_context=market_context,
        calendar_events=calendar_events,
        disclosures=disclosures,
        investor_flows=investor_flows,
    )

    logger.info("[8/10] 한나 투자 브리프 생성 중...")
    analysis = build_hanna_daily_report_text(daily_data=daily_data)
    hanna_context = {
        "owner": "hanna",
        "market_regime": str(getattr(market_context, "market_regime", "neutral") or "neutral"),
        "short_term_bias": str(getattr(market_context, "short_term_bias", "neutral") or "neutral"),
        "mid_term_bias": str(getattr(market_context, "mid_term_bias", "neutral") or "neutral"),
        "key_risks": list(getattr(market_context, "risks", []) or [])[:3],
        "favored_sectors": list(getattr(market_context, "supports", []) or [])[:3],
    }

    logger.info("[9/10] 내부 보조신호 없이 추천 계산을 진행합니다...")

    logger.info("[10/10] 투자 추천 계산 및 저장...")
    recommendations = generate_recommendations(daily_data, playbook=None)
    today_picks = generate_today_picks(daily_data, playbook=None)

    date_str = datetime.now().strftime("%Y-%m-%d")
    save_analysis_cache(analysis, date_str, playbook=hanna_context)
    save_news_cache(daily_data.news, date_str)
    save_macro_cache(daily_data.macro, date_str)
    save_calendar_cache(daily_data.calendar_events, date_str)
    save_disclosures_cache(daily_data.disclosures, date_str)
    save_investor_flows_cache(daily_data.investor_flows, date_str)
    save_market_context_cache(daily_data.market_context, date_str)
    save_recommendations_cache(recommendations, date_str)
    save_today_picks_cache(today_picks, date_str)

    logger.info("=== 리포트 생성 완료 ===")
