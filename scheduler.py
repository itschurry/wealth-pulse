"""매 3시간마다 자동 실행 스케줄러 (06:00, 09:00, 12:00, 15:00, 18:00, 21:00 KST)"""
import asyncio
import schedule
import time

from datetime import datetime
from loguru import logger

from main import run_daily_report


def _run():
    """동기 래퍼 - schedule 라이브러리 호환"""
    logger.info(f"스케줄 실행: {datetime.now():%Y-%m-%d %H:%M}")
    asyncio.run(run_daily_report())


if __name__ == "__main__":
    # 3시간 간격: 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 KST
    for hour in (6, 9, 12, 15, 18, 21):
        schedule.every().day.at(f"{hour:02d}:00").do(_run)

    logger.info("스케줄러 시작 (06:00 / 09:00 / 12:00 / 15:00 / 18:00 / 21:00 KST, 3시간 간격)")
    while True:
        schedule.run_pending()
        time.sleep(30)
