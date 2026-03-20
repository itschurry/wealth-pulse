"""일일 경제 리포트 생성 파이프라인"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from loguru import logger

from config.settings import LOGS_DIR, DELIVERY_METHOD
from analyzer.market_context_builder import build_market_context
from analyzer.openai_signal_engine import generate_stock_aux_signals
from analyzer.today_picks_engine import generate_today_picks
from collectors.calendar_collector import collect_calendar_events
from collectors.disclosure_collector import collect_disclosures
from collectors.flow_collector import collect_investor_flows
from collectors.market_collector import collect_market
from collectors.macro_collector import collect_macro
from collectors.news_collector import collect_news
from collectors.models import DailyData
from analyzer.openai_analyzer import analyze_with_playbook
from analyzer.recommendation_engine import generate_recommendations
from reporter.report_generator import (
    save_analysis_cache,
    save_analysis_playbook_cache,
    save_ai_signals_cache,
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

    logger.info("[1-6/10] 수집 병렬 시작...")
    loop = asyncio.get_event_loop()
    _FALLBACKS = [None, [], [], [], [], []]
    _NAMES = ["market", "news", "macro", "calendar_events", "disclosures", "investor_flows"]
    _COLLECTORS = [collect_market, collect_news, collect_macro,
                   collect_calendar_events, collect_disclosures, collect_investor_flows]
    with ThreadPoolExecutor(max_workers=6) as executor:
        raw_results = await asyncio.gather(
            *[loop.run_in_executor(executor, fn) for fn in _COLLECTORS],
            return_exceptions=True,
        )
    resolved = []
    for name, result, fallback in zip(_NAMES, raw_results, _FALLBACKS):
        if isinstance(result, Exception):
            logger.warning(f"수집 실패 [{name}]: {result!r} — 폴백값 사용")
            resolved.append(fallback)
        else:
            resolved.append(result)
    market, news, macro, calendar_events, disclosures, investor_flows = resolved
    logger.info("수집 완료")

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

    logger.info("[8/10] OpenAI API 분석 중...")
    analysis, analysis_playbook = await analyze_with_playbook(daily_data)

    logger.info("[9/10] OpenAI 보조신호 생성 중...")
    ai_signals = await generate_stock_aux_signals(daily_data)

    logger.info("[10/10] 투자 추천 계산 및 저장...")
    recommendations = generate_recommendations(daily_data, playbook=analysis_playbook)
    today_picks = generate_today_picks(daily_data, ai_signals=ai_signals, playbook=analysis_playbook)

    date_str = datetime.now().strftime("%Y-%m-%d")
    save_analysis_cache(analysis, date_str, playbook=analysis_playbook)
    save_analysis_playbook_cache(analysis_playbook, date_str)
    save_news_cache(daily_data.news, date_str)
    save_macro_cache(daily_data.macro, date_str)
    save_ai_signals_cache(ai_signals, date_str)
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
