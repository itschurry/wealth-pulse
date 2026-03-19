"""전체 설정 관리"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# FRED
FRED_API_KEY = (
    os.getenv("FRED_API_KEY")
    or os.getenv("FRED_KEY")
    or os.getenv("FRED_API")
    or ""
)

# ECOS (한국은행 경제통계시스템)
ECOS_API_KEY = (
    os.getenv("ECOS_API_KEY")
    or os.getenv("BOK_ECOS_API_KEY")
    or os.getenv("ECOS_KEY")
    or ""
)

# DART (전자공시 Open API)
DART_API_KEY = (
    os.getenv("DART_API_KEY")
    or os.getenv("OPENDART_API_KEY")
    or ""
)

# 한국투자증권 Open API
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ACCOUNT_CANO = os.getenv("KIS_ACCOUNT_CANO", "")
KIS_ACCOUNT_ACNT_PRDT_CD = os.getenv("KIS_ACCOUNT_ACNT_PRDT_CD", "")
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

# 텔레그램
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 이메일
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
REPORT_RECIPIENT = os.getenv("REPORT_RECIPIENT", "")

# 발송
DELIVERY_METHOD = os.getenv("DELIVERY_METHOD", "none")

# 저장 경로
REPORT_OUTPUT_DIR = Path(
    os.getenv("REPORT_OUTPUT_DIR", str(BASE_DIR / "report")))
LOGS_DIR = BASE_DIR / "logs"

# 디렉토리 생성
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
