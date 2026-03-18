"""텔레그램 봇으로 메시지 발송"""
from loguru import logger
from telegram import Bot
from telegram.constants import ParseMode

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

_MAX_MSG_LEN = 4096


async def send_report(markdown_text: str) -> bool:
    """Markdown 리포트를 텔레그램으로 발송. 4096자 초과 시 분할 전송."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정이 없습니다. 발송을 건너뜁니다.")
        return False

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    chunks = [markdown_text[i:i + _MAX_MSG_LEN] for i in range(0, len(markdown_text), _MAX_MSG_LEN)]

    try:
        for chunk in chunks:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN,
            )
        logger.info(f"텔레그램 발송 성공 ({len(chunks)}개 메시지)")
        return True
    except Exception as e:
        logger.error(f"텔레그램 발송 실패: {e}")
        return False
