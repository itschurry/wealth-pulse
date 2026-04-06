"""Runtime settings for the simplified apps/api layout."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except Exception:  # pragma: no cover - lightweight test environments may omit pydantic-settings
    SettingsConfigDict = dict  # type: ignore[misc,assignment]

    class BaseSettings:  # type: ignore[no-redef]
        def __init__(self, **_: object) -> None:
            for name, annotation in getattr(self.__class__, "__annotations__", {}).items():
                default = getattr(self.__class__, name, None)
                alias = None
                if hasattr(default, "alias"):
                    alias = getattr(default, "alias", None)
                    default = getattr(default, "default", default)
                env_name = alias or name.upper()
                value = os.getenv(env_name, default)
                if annotation is bool and isinstance(value, str):
                    value = value.strip().lower() in {"1", "true", "yes", "on"}
                elif annotation is int and isinstance(value, str):
                    try:
                        value = int(value)
                    except ValueError:
                        value = default
                elif annotation is Path and isinstance(value, str):
                    value = Path(value)
                setattr(self, name, value)


_CURRENT_FILE = Path(__file__).resolve()
_API_DIR_CANDIDATE = _CURRENT_FILE.parents[1]

if _API_DIR_CANDIDATE.name == "api" and _API_DIR_CANDIDATE.parent.name == "apps":
    API_DIR = _API_DIR_CANDIDATE
    REPO_ROOT = API_DIR.parent.parent
else:
    API_DIR = _API_DIR_CANDIDATE
    REPO_ROOT = API_DIR

APPS_DIR = REPO_ROOT / "apps"
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

    report_output_dir: Path = Field(default=REPORTS_DIR, alias="REPORT_OUTPUT_DIR")
    logs_dir: Path = Field(default=LOGS_DIR, alias="LOGS_DIR")

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


def _ensure_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


_ensure_directory(settings.report_output_dir)
_ensure_directory(settings.logs_dir)

BASE_DIR = REPO_ROOT

FRED_API_KEY = settings.effective_fred_api_key
ECOS_API_KEY = settings.effective_ecos_api_key
DART_API_KEY = settings.effective_dart_api_key

KIS_APP_KEY = settings.kis_app_key
KIS_APP_SECRET = settings.kis_app_secret
KIS_ACCOUNT_CANO = settings.kis_account_cano
KIS_ACCOUNT_ACNT_PRDT_CD = settings.kis_account_acnt_prdt_cd
KIS_BASE_URL = settings.kis_base_url

REPORT_OUTPUT_DIR = settings.report_output_dir
LOGS_DIR = settings.logs_dir
