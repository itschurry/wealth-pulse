"""텔레그램 봇으로 메시지 발송"""
from loguru import logger
from telegram import Bot

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REPORT_WEB_URL

_FALLBACK_INTRO = "오늘의 리포트가 도착했어요.\n편하실 때 아래 링크에서 확인해 주세요."


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
    """고정 문구와 함께 리포트 링크를 발송한다."""
    message = f"{_FALLBACK_INTRO}\n{REPORT_WEB_URL}"
    return await send_text_message(message)
