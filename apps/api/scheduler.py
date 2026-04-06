"""APScheduler 기반 스케줄러.

- 한국장 정규장: KST 09:00-15:30, 30분 단위 cron
- 미국장 정규장: ET 09:30-16:00, 30분 단위 cron
- 장외: KST 06:00-21:00, 1시간 단위 기준, 한국장 정규장은 제외
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.market_calendar import is_market_half_hour_slot
from jobs.runtime_jobs import run_optimization_job, run_report_job

KST_TZ = "Asia/Seoul"
KST_ZONE = ZoneInfo(KST_TZ)


def _run():
    """동기 래퍼 - APScheduler job 함수."""
    logger.info(f"스케줄 실행 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        run_report_job()
        logger.info("스케줄 실행 완료")
    except Exception:
        # 예외로 프로세스가 종료되면 다음 슬롯을 통째로 놓칠 수 있으므로
        # 로그를 남기고 스케줄러는 계속 유지한다.
        logger.exception("스케줄 실행 실패")


def _kr_market_job():
    """한국장 슬롯 핸들러 — is_market_half_hour_slot으로 공휴일 필터."""
    now_utc = datetime.now(timezone.utc)
    if not is_market_half_hour_slot("KR", now_utc):
        return
    now_kst = now_utc.astimezone(KST_ZONE)
    # 15:30 초과 슬롯은 스킵
    if now_kst.hour == 15 and now_kst.minute > 30:
        return
    logger.info(f"한국장 슬롯 실행: {now_kst:%H:%M} KST")
    _run()


def _us_market_job():
    """미국장 슬롯 핸들러 — is_market_half_hour_slot으로 공휴일 필터."""
    now_utc = datetime.now(timezone.utc)
    if not is_market_half_hour_slot("US", now_utc):
        return
    et_zone = ZoneInfo("America/New_York")
    now_et = now_utc.astimezone(et_zone)
    # 16:00 초과 슬롯은 스킵
    if now_et.hour >= 16:
        return
    logger.info(f"미국장 슬롯 실행: {now_et:%H:%M} ET")
    _run()


def _off_session_job():
    """장외 슬롯 핸들러.

    한국장 거래일의 정규장 슬롯과 겹치면 스킵한다.
    """
    now_utc = datetime.now(timezone.utc)
    if is_market_half_hour_slot("KR", now_utc):
        now_kst = now_utc.astimezone(KST_ZONE)
        logger.info(f"장외 슬롯 스킵(한국장 정규장과 중복): {now_kst:%H:%M} KST")
        return
    now_kst = now_utc.astimezone(KST_ZONE)
    logger.info(f"장외 슬롯 실행: {now_kst:%H:%M} KST")
    _run()


def _run_optimization():
    """몬테카를로 파라미터 최적화 — 일요일 새벽 2시에 실행."""
    try:
        run_optimization_job()
    except Exception:
        logger.exception("몬테카를로 최적화 실행 중 예외 발생")


def _log_schedule_policy() -> None:
    logger.info("장외 스케줄: 06:00-21:00 KST 매 정시, 한국장 정규장과 중복 시 스킵")
    logger.info("한국장 스케줄: 09:00-15:30 KST, 30분 단위 (주말/한국 공휴일 제외)")
    logger.info("미국장 스케줄: 09:30-16:00 ET, 30분 단위 (주말/미국 거래소 휴장일 제외)")


def main() -> None:
    tz = os.getenv("TZ", "")
    if tz not in (KST_TZ, "KST-9", "KST"):
        logger.warning(
            f"⚠️ TZ 환경변수가 {KST_TZ}이 아닙니다 (현재: {tz or '미설정'}). "
            f"코드상 로그 기준은 {KST_TZ}를 기대하므로, 로그/운영 혼선을 막으려면 "
            f"'export TZ={KST_TZ}' 또는 systemd/셸 실행 환경에 TZ={KST_TZ}을 설정하세요."
        )

    scheduler = BlockingScheduler()

    # 한국장: KST 09:00-15:30, 30분 단위
    scheduler.add_job(
        _kr_market_job,
        CronTrigger(hour="9-15", minute="0,30", timezone=KST_TZ),
        max_instances=1,
        id="kr_market",
    )

    # 미국장: ET 09:30-15:30, 30분 단위 (16:00 초과는 핸들러에서 스킵)
    scheduler.add_job(
        _us_market_job,
        CronTrigger(hour="9-15", minute="0,30", timezone="America/New_York"),
        max_instances=1,
        id="us_market",
    )

    # 장외: KST 06:00-21:00 매 정시, 한국장 정규장과 중복 시 핸들러에서 스킵
    scheduler.add_job(
        _off_session_job,
        CronTrigger(hour="6-21", minute=0, timezone=KST_TZ),
        max_instances=1,
        id="off_session",
    )

    # 몬테카를로 최적화: 매주 일요일 KST 02:00
    scheduler.add_job(
        _run_optimization,
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=KST_TZ),
        max_instances=1,
        misfire_grace_time=3600,
        id="weekly_optimization",
    )

    logger.info("APScheduler 시작")
    _log_schedule_policy()
    scheduler.start()


if __name__ == "__main__":
    main()
