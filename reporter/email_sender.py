"""SMTP 이메일 발송"""
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from loguru import logger

from config.settings import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, REPORT_RECIPIENT


async def send_report(html_content: str, subject: str) -> bool:
    """HTML 이메일 발송. 성공 시 True 반환."""
    if not all([SMTP_USER, SMTP_PASSWORD, REPORT_RECIPIENT]):
        logger.warning("이메일 설정이 불완전합니다. 발송을 건너뜁니다.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = REPORT_RECIPIENT
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info(f"이메일 발송 성공 → {REPORT_RECIPIENT}")
        return True
    except Exception as e:
        logger.error(f"이메일 발송 실패: {e}")
        return False
