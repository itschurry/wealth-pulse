"""장중 30분 + 장외 3시간 자동 실행 스케줄러.

- 한국장: KST 09:00-15:30, 30분 단위
- 미국장: ET 09:30-16:00, 30분 단위
- 장외: KST 06/09/12/15/18/21시
"""
import asyncio
import os
import time

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from loguru import logger

from config.market_calendar import is_market_half_hour_slot
from main import run_daily_report

KST_TZ = "Asia/Seoul"
KST_ZONE = ZoneInfo(KST_TZ)
OUT_OF_SESSION_RUN_HOURS = (6, 9, 12, 15, 18, 21)
POLL_INTERVAL_SECONDS = 30
_last_run_slot_id = ""


def _run():
    """동기 래퍼 - schedule 라이브러리 호환."""
    logger.info(f"스케줄 실행 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        asyncio.run(run_daily_report())
        logger.info("스케줄 실행 완료")
    except Exception:
        # 예외로 프로세스가 종료되면 다음 슬롯(예: 21:00)을 통째로 놓칠 수 있으므로
        # 로그를 남기고 루프는 계속 유지한다.
        logger.exception("스케줄 실행 실패")


def _matches_off_session_slot(now_kst: datetime) -> bool:
    return now_kst.minute == 0 and now_kst.hour in OUT_OF_SESSION_RUN_HOURS


def _current_slot(now_utc: datetime | None = None) -> tuple[str, list[str]]:
    source = now_utc or datetime.now(timezone.utc)
    kst_now = source.astimezone(KST_ZONE)
    reasons: list[str] = []

    if _matches_off_session_slot(kst_now):
        reasons.append(f"off-session:{kst_now:%H:%M} KST")
    if is_market_half_hour_slot("KR", source):
        reasons.append(f"kr-market:{kst_now:%H:%M} KST")
    if is_market_half_hour_slot("US", source):
        reasons.append("us-market:ET half-hour slot")

    slot_id = source.replace(second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    return slot_id, reasons


def _run_if_slot() -> None:
    global _last_run_slot_id

    slot_id, reasons = _current_slot()
    if not reasons:
        return
    if slot_id == _last_run_slot_id:
        return

    logger.info(f"실행 슬롯 감지: {slot_id} reasons={', '.join(reasons)}")
    _last_run_slot_id = slot_id
    _run()


def _log_schedule_policy() -> None:
    logger.info("장외 스케줄: 06:00 / 09:00 / 12:00 / 15:00 / 18:00 / 21:00 KST")
    logger.info("한국장 스케줄: 09:00-15:30 KST, 30분 단위 (주말/한국 공휴일 제외)")
    logger.info("미국장 스케줄: 09:30-16:00 ET, 30분 단위 (주말/미국 거래소 휴장일 제외)")


if __name__ == "__main__":
    tz = os.getenv("TZ", "")
    if tz not in (KST_TZ, "KST-9", "KST"):
        logger.warning(
            f"⚠️ TZ 환경변수가 {KST_TZ}이 아닙니다 (현재: {tz or '미설정'}). "
            f"코드상 로그 기준은 {KST_TZ}를 기대하므로, 로그/운영 혼선을 막으려면 "
            f"'export TZ={KST_TZ}' 또는 systemd/docker에 TZ={KST_TZ}을 설정하세요."
        )

    logger.info(
        "스케줄러 시작 (장중 30분 단위 + 장외 3시간 단위)"
    )
    _log_schedule_policy()
    while True:
        _run_if_slot()
        time.sleep(POLL_INTERVAL_SECONDS)
