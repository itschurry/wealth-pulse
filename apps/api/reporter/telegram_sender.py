"""텔레그램 봇으로 메시지 발송"""
from loguru import logger
from telegram import Bot

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REPORT_WEB_URL
from llm.service import complete_text

_QUOTE_PROMPT = (
    "투자와 관련된 짧은 명언 한 줄을 한국어로 알려주세요. "
    "출처(인물명)도 함께 적어주세요. 다른 설명은 하지 마세요."
)
_FALLBACK_INTRO = "오늘의 리포트가 도착했어요.\n편하실 때 아래 링크에서 확인해 주세요."


async def _generate_investment_quote() -> str | None:
    """LLM을 이용해 투자 관련 짧은 명언을 생성한다. 실패 시 None 반환."""
    try:
        response = await complete_text(
            system_prompt="투자 관련 짧은 인용구만 반환한다.",
            user_prompt=_QUOTE_PROMPT,
            task="quote",
            temperature=1.0,
            max_tokens=128,
        )
        quote = (response.content or "").strip()
        return quote if quote else None
    except Exception as exc:
        logger.warning("LLM 명언 생성 실패: {}", exc)
        return None


async def send_text_message(message: str) -> bool:
    """텔레그램으로 일반 텍스트 메시지를 발송한다."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정이 없습니다. 발송을 건너뜁니다.")
        return False

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logger.info("텔레그램 메시지 발송 성공")
        return True
    except Exception as e:
        logger.error(f"텔레그램 발송 실패: {e}")
        return False


async def send_report(_: str) -> bool:
    """LLM으로 생성한 투자 명언과 함께 리포트 링크를 발송한다."""
    quote = await _generate_investment_quote()
    if quote:
        message = f"{quote}\n\n오늘의 리포트 → {REPORT_WEB_URL}"
    else:
        message = f"{_FALLBACK_INTRO}\n{REPORT_WEB_URL}"
    return await send_text_message(message)
