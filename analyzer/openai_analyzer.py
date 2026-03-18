"""OpenAI API를 이용한 경제 리포트 분석"""
import asyncio
import time
from loguru import logger
from openai import OpenAI, RateLimitError, APIError
from analyzer.market_context_builder import summarize_macro_for_prompt, summarize_market_context_for_prompt
from config.settings import OPENAI_API_KEY, OPENAI_MODEL
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
    for i, article in enumerate(data.news[:15]):
        snippet = (article.summary or article.body or "")[:200]
        n_lines.append(
            f"{i+1}. [{article.source}] {article.title}\n"
            f"   URL: {article.url}\n"
            f"   요약: {snippet}"
        )
    news_summary = "\n\n".join(n_lines) if n_lines else "뉴스 수집 실패"

    return {
        "market_data":    market_data,
        "news_summary":   news_summary,
        "macro_summary": summarize_macro_for_prompt(data.macro),
        "market_context_summary": summarize_market_context_for_prompt(data.market_context),
    }


async def analyze(data: DailyData) -> str:
    """OpenAI API로 일일 리포트 분석 생성"""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY가 설정되지 않았습니다. 분석을 건너뜁니다.")
        return _fallback_report(data)

    client = OpenAI(api_key=OPENAI_API_KEY)

    formatted = _format_daily_data(data)
    from config.portfolio import INVESTMENT_PROFILE
    investment_profile = (
        f"투자 성향: {INVESTMENT_PROFILE['style']}, "
        f"선호 리스크: {INVESTMENT_PROFILE['risk_preference']}"
    )
    prompt = DAILY_REPORT_PROMPT.format(
        investment_profile=investment_profile,
        market_data=formatted["market_data"],
        news_summary=formatted["news_summary"],
        macro_summary=formatted["macro_summary"],
        market_context_summary=formatted["market_context_summary"],
    )

    for attempt in range(3):
        try:
            logger.info(f"OpenAI API 호출 시도 {attempt+1}/3 (모델: {OPENAI_MODEL})")
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.3,
                max_completion_tokens=8192,
            )
            return response.choices[0].message.content

        except RateLimitError as e:
            wait = 20 + attempt * 10
            logger.warning(
                f"OpenAI RateLimit (시도 {attempt+1}): {e} — {wait}초 대기")
            if attempt < 2:
                time.sleep(wait)
        except APIError as e:
            logger.error(f"OpenAI APIError (시도 {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(5)
        except Exception as e:
            logger.error(f"OpenAI 예상 외 오류 (시도 {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(5)

    logger.error("OpenAI API 3회 모두 실패. 폴백 리포트 생성.")
    return _fallback_report(data)


def _fallback_report(data: DailyData) -> str:
    """API 실패 시 원본 데이터 기반 간단 리포트"""
    lines = ["# 일일 경제 리포트 (AI 분석 실패 - 원본 데이터)\n"]
    m = data.market
    lines.append(
        "## 3줄 요약\n1. AI 분석 API 호출 실패\n2. 아래 시장 데이터 및 뉴스 원본을 확인하세요\n3. OPENAI_API_KEY 설정을 확인하세요\n")
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
        lines.append(f"- [{a.source}] {a.title} — {a.url}")
    return "\n".join(lines)
