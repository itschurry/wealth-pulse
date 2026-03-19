"""매 3시간마다 자동 실행 스케줄러 (06:00, 09:00, 12:00, 15:00, 18:00, 21:00 KST)

주의: schedule 라이브러리는 시스템 로츅 시간을 기준으로 동작합니다.
KST(UTC+9) 맞욤 실행을 보장하려면 TZ=Asia/Seoul 환경 변수를 설정하세요.
"""
import asyncio
import os
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
    tz = os.getenv("TZ", "")
    if tz not in ("Asia/Seoul", "KST-9", "KST"):
        logger.warning(
            f"⚠️ TZ 환경변수가 Asia/Seoul이 아닙니다 (현재: {tz or '미설정'}). "
            "스케줄러는 시스템 로츅 시간으로 동작해 KST 기준 실행 시각과 차이가 날 수 있습니다. "
            "'export TZ=Asia/Seoul' 또는 systemd/docker에 TZ=Asia/Seoul을 설정하세요."
        )

    # 3시간 간격: 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 KST
    for hour in (6, 9, 12, 15, 18, 21):
        schedule.every().day.at(f"{hour:02d}:00").do(_run)

    logger.info(
        "스케줄러 시작 (06:00 / 09:00 / 12:00 / 15:00 / 18:00 / 21:00 KST, 3시간 간격)")
    while True:
        schedule.run_pending()
        time.sleep(30)
