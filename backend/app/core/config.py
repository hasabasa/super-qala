"""Конфигурация приложения. Единственное место, где читается окружение."""

from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Общее ---
    ENV: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = True
    PROJECT_NAME: str = "SmartQala"
    API_PREFIX: str = "/api/v1"

    # --- Инфраструктура ---
    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn

    # --- Безопасность ---
    SECRET_KEY: str
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 90
    CORS_ORIGINS: list[str] = []

    # --- SMS-верификация ---
    SMS_PROVIDER: Literal["console", "smsc", "mobizon"] = "console"
    SMS_API_KEY: str = ""
    SMS_SENDER: str = "SmartQala"
    SMS_CODE_TTL_SECONDS: int = 300
    SMS_CODE_LENGTH: int = 4
    SMS_RATE_LIMIT_PER_PHONE_HOUR: int = 3
    SMS_RATE_LIMIT_PER_IP_HOUR: int = 10

    # --- Файловое хранилище (S3-совместимое) ---
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET: str = "smartqala"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_PUBLIC_URL: str = ""

    # --- Push ---
    FCM_CREDENTIALS_PATH: str = ""

    # --- Наблюдаемость ---
    SENTRY_DSN: str = ""

    @property
    def is_local(self) -> bool:
        return self.ENV == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
