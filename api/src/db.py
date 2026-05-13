"""Async SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.src.config import settings


class Base(DeclarativeBase):
    pass


def _connect_args() -> dict[str, object]:
    # Fly's internal Postgres on .flycast / .internal is plaintext — disable
    # asyncpg's default SSL handshake (which prefers TLS) or it ConnectionReset's.
    url = settings.DATABASE_URL
    if ".flycast" in url or ".internal" in url:
        return {"ssl": False}
    return {}


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
    connect_args=_connect_args(),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
