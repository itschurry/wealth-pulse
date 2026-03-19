"""일일 경제 리포트 생성 파이프라인"""
import asyncio
import os
from datetime import datetime

from loguru import logger

from config.settings import LOGS_DIR, DELIVERY_METHOD
from analyzer.market_context_builder import build_market_context
from analyzer.today_picks_engine import generate_today_picks
from collectors.calendar_collector import collect_calendar_events
from collectors.disclosure_collector import collect_disclosures
from collectors.flow_collector import collect_investor_flows
from collectors.market_collector import collect_market
from collectors.macro_collector import collect_macro
from collectors.news_collector import collect_news
from collectors.models import DailyData
from analyzer.openai_analyzer import analyze
from analyzer.recommendation_engine import generate_recommendations
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
from reporter.telegram_sender import send_report as send_telegram
from reporter.email_sender import send_report as send_email

_log_handler_id: int | None = None


def _setup_logging():
    """loguru 로그 설정 (중복 핸들러 방지)"""
    global _log_handler_id
    if _log_handler_id is not None:
        try:
            logger.remove(_log_handler_id)
        except Exception:
            pass
    log_file = LOGS_DIR / f"daily_report_{datetime.now():%Y-%m-%d}.log"
    _log_handler_id = logger.add(str(log_file), rotation="1 day",
                                 retention="30 days", level="INFO", encoding="utf-8")


async def run_daily_report():
    """일일 리포트 생성 메인 파이프라인"""
    _setup_logging()
    logger.info("=== 일일 리포트 생성 시작 ===")

    logger.info("[1/9] 시장 데이터 수집...")
    market = collect_market()

    logger.info("[2/9] 뉴스 수집...")
    news = collect_news()

    logger.info("[3/9] 거시 지표 수집...")
    macro = collect_macro()

    logger.info("[4/9] 경제 일정 수집...")
    calendar_events = collect_calendar_events()

    logger.info("[5/9] 공시 수집...")
    disclosures = collect_disclosures()

    logger.info("[6/9] 수급 데이터 수집...")
    investor_flows = collect_investor_flows()

    logger.info("[7/9] 시장 컨텍스트 생성...")
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

    logger.info("[8/9] OpenAI API 분석 중...")
    analysis = await analyze(daily_data)

    logger.info("[9/9] 투자 추천 계산 및 저장...")
    recommendations = generate_recommendations(daily_data)
    today_picks = generate_today_picks(daily_data)

    date_str = datetime.now().strftime("%Y-%m-%d")
    save_analysis_cache(analysis, date_str)
    save_news_cache(daily_data.news, date_str)
    save_macro_cache(daily_data.macro, date_str)
    save_calendar_cache(daily_data.calendar_events, date_str)
    save_disclosures_cache(daily_data.disclosures, date_str)
    save_investor_flows_cache(daily_data.investor_flows, date_str)
    save_market_context_cache(daily_data.market_context, date_str)
    save_recommendations_cache(recommendations, date_str)
    save_today_picks_cache(today_picks, date_str)

    delivery = DELIVERY_METHOD
    if delivery in ("telegram", "both"):
        await send_telegram(analysis)
    if delivery in ("email", "both"):
        simple_html = "<html><body><pre style='font-family:sans-serif;white-space:pre-wrap;'>" + \
            analysis + "</pre></body></html>"
        await send_email(simple_html, f"📊 일일 경제 리포트 {date_str}")

    logger.info("=== 리포트 생성 완료 ===")
