"""Process-wide settings loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_db_url(url: str) -> str:
    """Coerce a Postgres URL into SQLAlchemy + asyncpg form.

    Fly Postgres attach writes DATABASE_URL=postgres://... ?sslmode=disable, but
    SQLAlchemy needs an explicit driver (+asyncpg) and asyncpg ignores libpq's
    sslmode query param. Strip both and let runtime/connect_args control TLS.
    """
    if not url:
        return url
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+asyncpg"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "sslmode"]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


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

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return normalize_db_url(v)
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
