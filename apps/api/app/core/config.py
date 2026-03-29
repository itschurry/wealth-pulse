from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[4]
APPS_DIR = REPO_ROOT / "apps"
API_DIR = APPS_DIR / "api"
WEB_DIR = APPS_DIR / "web"
STORAGE_DIR = REPO_ROOT / "storage"
REPORTS_DIR = STORAGE_DIR / "reports"
LOGS_DIR = STORAGE_DIR / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(API_DIR / ".env"), str(REPO_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_signal_model: str | None = Field(default=None, alias="OPENAI_SIGNAL_MODEL")
    openai_playbook_model: str | None = Field(default=None, alias="OPENAI_PLAYBOOK_MODEL")
    nemotron_model: str = Field(default="nemotron-3-super", alias="NEMOTRON_MODEL")
    ollama_host: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_HOST")

    fred_api_key: str = Field(default="", alias="FRED_API_KEY")
    fred_key: str = Field(default="", alias="FRED_KEY")
    fred_api: str = Field(default="", alias="FRED_API")

    ecos_api_key: str = Field(default="", alias="ECOS_API_KEY")
    bok_ecos_api_key: str = Field(default="", alias="BOK_ECOS_API_KEY")
    ecos_key: str = Field(default="", alias="ECOS_KEY")

    dart_api_key: str = Field(default="", alias="DART_API_KEY")
    opendart_api_key: str = Field(default="", alias="OPENDART_API_KEY")

    kis_app_key: str = Field(default="", alias="KIS_APP_KEY")
    kis_app_secret: str = Field(default="", alias="KIS_APP_SECRET")
    kis_account_cano: str = Field(default="", alias="KIS_ACCOUNT_CANO")
    kis_account_acnt_prdt_cd: str = Field(default="", alias="KIS_ACCOUNT_ACNT_PRDT_CD")
    kis_base_url: str = Field(
        default="https://openapi.koreainvestment.com:9443",
        alias="KIS_BASE_URL",
    )

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    report_web_url: str = Field(default="http://localhost:8080", alias="REPORT_WEB_URL")

    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    report_recipient: str = Field(default="", alias="REPORT_RECIPIENT")

    delivery_method: str = Field(default="none", alias="DELIVERY_METHOD")
    report_output_dir: Path = Field(default=REPORTS_DIR, alias="REPORT_OUTPUT_DIR")
    logs_dir: Path = Field(default=LOGS_DIR, alias="LOGS_DIR")

    @property
    def effective_openai_signal_model(self) -> str:
        return self.openai_signal_model or self.openai_model

    @property
    def effective_openai_playbook_model(self) -> str:
        return self.openai_playbook_model or self.openai_model

    @property
    def effective_fred_api_key(self) -> str:
        return self.fred_api_key or self.fred_key or self.fred_api

    @property
    def effective_ecos_api_key(self) -> str:
        return self.ecos_api_key or self.bok_ecos_api_key or self.ecos_key

    @property
    def effective_dart_api_key(self) -> str:
        return self.dart_api_key or self.opendart_api_key


settings = Settings()
settings.report_output_dir.mkdir(parents=True, exist_ok=True)
settings.logs_dir.mkdir(parents=True, exist_ok=True)
