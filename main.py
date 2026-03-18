"""일일 경제 리포트 생성 파이프라인"""
import asyncio
import os
from datetime import datetime

from loguru import logger

from config.settings import LOGS_DIR, DELIVERY_METHOD
from analyzer.market_context_builder import build_market_context
from collectors.market_collector import collect_market
from collectors.macro_collector import collect_macro
from collectors.news_collector import collect_news
from collectors.models import DailyData
from analyzer.openai_analyzer import analyze
from analyzer.recommendation_engine import generate_recommendations
from reporter.report_generator import save_analysis_cache, save_recommendations_cache, save_macro_cache, save_market_context_cache
from reporter.telegram_sender import send_report as send_telegram
from reporter.email_sender import send_report as send_email


def _setup_logging():
    """loguru 로그 설정"""
    log_file = LOGS_DIR / f"daily_report_{datetime.now():%Y-%m-%d}.log"
    logger.add(str(log_file), rotation="1 day",
               retention="30 days", level="INFO", encoding="utf-8")


async def run_daily_report():
    """일일 리포트 생성 메인 파이프라인"""
    _setup_logging()
    logger.info("=== 일일 리포트 생성 시작 ===")

    logger.info("[1/6] 시장 데이터 수집...")
    market = collect_market()

    logger.info("[2/6] 뉴스 수집...")
    news = collect_news()

    logger.info("[3/6] 거시 지표 수집...")
    macro = collect_macro()

    logger.info("[4/6] 시장 컨텍스트 생성...")
    market_context = build_market_context(market, macro)

    daily_data = DailyData(
        collected_at=datetime.now(),
        market=market,
        holdings=[],
        news=news,
        macro=macro,
        market_context=market_context,
    )

    logger.info("[5/6] OpenAI API 분석 중...")
    analysis = await analyze(daily_data)

    logger.info("[6/6] 투자 추천 계산 및 저장...")
    recommendations = generate_recommendations(daily_data)

    date_str = datetime.now().strftime("%Y-%m-%d")
    save_analysis_cache(analysis, date_str)
    save_macro_cache(daily_data.macro, date_str)
    save_market_context_cache(daily_data.market_context, date_str)
    save_recommendations_cache(recommendations, date_str)

    delivery = DELIVERY_METHOD
    if delivery in ("telegram", "both"):
        await send_telegram(analysis)
    if delivery in ("email", "both"):
        simple_html = "<html><body><pre style='font-family:sans-serif;white-space:pre-wrap;'>" + \
            analysis + "</pre></body></html>"
        await send_email(simple_html, f"📊 일일 경제 리포트 {date_str}")

    logger.info("=== 리포트 생성 완료 ===")
