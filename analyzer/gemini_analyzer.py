"""Google Gemini API를 이용한 경제 리포트 분석"""
import asyncio
import time
from loguru import logger
from google import genai
from google.genai import types
from analyzer.market_context_builder import summarize_macro_for_prompt, summarize_market_context_for_prompt
from config.settings import GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL
from config.prompts import SYSTEM_PROMPT, DAILY_REPORT_PROMPT
from collectors.models import DailyData


def _format_daily_data(data: DailyData) -> dict:
    """DailyData를 프롬프트용 텍스트로 변환"""
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
    if m.brent_oil:
        lines.append(f"Brent유가: ${m.brent_oil:.2f}")
    if m.wti_oil:
        lines.append(f"WTI유가: ${m.wti_oil:.2f}")
    if m.gold:
        lines.append(f"금: ${m.gold:,.2f}")
    if m.vix:
        lines.append(f"VIX(공포지수): {m.vix:.2f}")
    market_data = "\n".join(lines) if lines else "시장 데이터 수집 실패"

    h_lines = []
    for h in data.holdings:
        h_lines.append(
            f"- {h.name} ({h.ticker}): 현재가 {h.current_price:,.0f}원, 수익률 {h.unrealized_return_pct:+.2f}%")
    holdings_summary = "\n".join(h_lines) if h_lines else "보유종목 데이터 없음"

    n_lines = []
    for i, article in enumerate(data.news[:15]):
        n_lines.append(
            f"{i+1}. [{article.source}] {article.title}\n   URL: {article.url}\n   요약: {article.summary[:200] if article.summary else article.body[:200]}")
    news_summary = "\n\n".join(n_lines) if n_lines else "뉴스 수집 실패"

    return {
        "market_data": market_data,
        "holdings_summary": holdings_summary,
        "news_summary": news_summary,
        "macro_summary": summarize_macro_for_prompt(data.macro),
        "market_context_summary": summarize_market_context_for_prompt(data.market_context),
    }


async def analyze(data: DailyData) -> str:
    """Gemini API로 일일 리포트 분석 생성"""
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY가 설정되지 않았습니다. 분석을 건너뜁니다.")
        return _fallback_report(data)

    client = genai.Client(api_key=GOOGLE_API_KEY)

    formatted = _format_daily_data(data)
    from config.portfolio import INVESTMENT_PROFILE
    investment_profile = f"투자 성향: {INVESTMENT_PROFILE['style']}, 선호 리스크: {INVESTMENT_PROFILE['risk_preference']}"
    prompt = DAILY_REPORT_PROMPT.format(
        investment_profile=investment_profile,
        holdings_summary=formatted["holdings_summary"],
        market_data=formatted["market_data"],
        news_summary=formatted["news_summary"],
        macro_summary=formatted["macro_summary"],
        market_context_summary=formatted["market_context_summary"],
    )

    for attempt in range(3):
        try:
            logger.info(f"Gemini API 호출 시도 {attempt+1}/3 (모델: {GEMINI_MODEL})")
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            # API가 응답한 retryDelay 파싱 (예: 'retryDelay': '12s')
            retry_sec = 15  # 기본 대기시간
            import re as _re
            m = _re.search(r"retryDelay.*?'(\d+)s'", err_str)
            if m:
                retry_sec = int(m.group(1)) + 2
            logger.warning(
                f"Gemini API 실패 (시도 {attempt+1}): 429 rate limit, {retry_sec}초 대기")
            if attempt < 2:
                time.sleep(retry_sec)

    # gemini-2.0-flash 실패 시 gemini-2.0-flash-lite 로 재시도
    logger.warning(f"{GEMINI_MODEL} 3회 실패, {GEMINI_FALLBACK_MODEL}로 재시도...")
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_FALLBACK_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
        return response.text
    except Exception as e:
        logger.error(f"{GEMINI_FALLBACK_MODEL} 도 실패: {e}")

    logger.error("Gemini API 모두 실패. 폴백 리포트 생성.")
    return _fallback_report(data)


def _fallback_report(data: DailyData) -> str:
    """API 실패 시 원본 데이터 기반 간단 리포트"""
    lines = ["# 일일 경제 리포트 (분석 API 실패 - 원본 데이터)\n"]
    m = data.market
    lines.append("## 시장 현황")
    if m.kospi:
        lines.append(f"- KOSPI: {m.kospi:,.2f} ({m.kospi_change_pct:+.2f}%)")
    if m.kosdaq:
        lines.append(
            f"- KOSDAQ: {m.kosdaq:,.2f} ({m.kosdaq_change_pct:+.2f}%)")
    if m.sp100:
        lines.append(f"- S&P100: {m.sp100:,.2f} ({m.sp100_change_pct:+.2f}%)")
    if m.usd_krw:
        lines.append(f"- USD/KRW: {m.usd_krw:,.2f}")
    if data.market_context:
        lines.append("\n## 거시 환경")
        lines.append(f"- 시장 국면: {data.market_context.regime}")
        lines.append(f"- 요약: {data.market_context.summary}")
    lines.append("\n## 주요 뉴스 (원본)")
    for a in data.news[:10]:
        lines.append(f"- [{a.source}] {a.title} - {a.url}")
    return "\n".join(lines)
