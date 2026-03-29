"""Backward-compatible settings exports backed by pydantic-settings."""

from app.core.config import API_DIR, APPS_DIR, LOGS_DIR, REPO_ROOT, REPORTS_DIR, STORAGE_DIR, WEB_DIR, settings

BASE_DIR = REPO_ROOT

LLM_PROVIDER = settings.llm_provider
OPENAI_API_KEY = settings.openai_api_key
OPENAI_MODEL = settings.openai_model
OPENAI_SIGNAL_MODEL = settings.effective_openai_signal_model
OPENAI_PLAYBOOK_MODEL = settings.effective_openai_playbook_model
NEMOTRON_MODEL = settings.nemotron_model
OLLAMA_HOST = settings.ollama_host

FRED_API_KEY = settings.effective_fred_api_key
ECOS_API_KEY = settings.effective_ecos_api_key
DART_API_KEY = settings.effective_dart_api_key

KIS_APP_KEY = settings.kis_app_key
KIS_APP_SECRET = settings.kis_app_secret
KIS_ACCOUNT_CANO = settings.kis_account_cano
KIS_ACCOUNT_ACNT_PRDT_CD = settings.kis_account_acnt_prdt_cd
KIS_BASE_URL = settings.kis_base_url

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
TELEGRAM_CHAT_ID = settings.telegram_chat_id
REPORT_WEB_URL = settings.report_web_url

SMTP_HOST = settings.smtp_host
SMTP_PORT = settings.smtp_port
SMTP_USER = settings.smtp_user
SMTP_PASSWORD = settings.smtp_password
REPORT_RECIPIENT = settings.report_recipient

DELIVERY_METHOD = settings.delivery_method
REPORT_OUTPUT_DIR = settings.report_output_dir
LOGS_DIR = settings.logs_dir
