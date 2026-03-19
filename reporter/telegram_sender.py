"""텔레그램 봇으로 메시지 발송"""
from loguru import logger
from telegram import Bot

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REPORT_WEB_URL


async def send_report(_: str) -> bool:
    """텔레그램으로 리포트 안내 링크만 발송한다."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정이 없습니다. 발송을 건너뜁니다.")
        return False

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    message = (
        "오늘의 리포트가 도착했어요.\n"
        "편하실 때 아래 링크에서 확인해 주세요.\n"
        f"{REPORT_WEB_URL}"
    )

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logger.info("텔레그램 링크 알림 발송 성공")
        return True
    except Exception as e:
        logger.error(f"텔레그램 발송 실패: {e}")
        return False
