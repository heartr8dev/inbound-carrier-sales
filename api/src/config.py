"""Process-wide settings loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    HAPPYROBOT_API_KEY: str = ""
    FMCSA_WEBKEY: str = ""
    FMCSA_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0.0, le=120.0)
    FMCSA_CACHE_TTL_HOURS: int = Field(default=24, ge=1, le=24 * 30)
    FMCSA_CIRCUIT_FAIL_THRESHOLD: int = Field(default=5, ge=1, le=100)
    FMCSA_CIRCUIT_WINDOW_SECONDS: float = Field(default=60.0, gt=0.0, le=3600.0)
    FMCSA_CIRCUIT_OPEN_SECONDS: float = Field(default=60.0, gt=0.0, le=3600.0)
    API_KEY: str = "devkey-please-change"
    DATABASE_URL: str = "postgresql+asyncpg://app:app@db:5432/inbound"
    DASHBOARD_ORIGIN: str = "http://localhost:5173"
    MAX_DISCOUNT_PCT: float = Field(default=0.10, ge=0.0, le=0.5)

    OPENAI_API_KEY: str = ""
    WAVESPEED_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    APP_VERSION: str = "0.1.0"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.DASHBOARD_ORIGIN.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
