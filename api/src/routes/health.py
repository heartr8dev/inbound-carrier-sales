"""Health probe — DB roundtrip + uptime + version. No auth."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.config import settings
from api.src.db import get_session

router = APIRouter(tags=["health"])

_PROCESS_START = time.monotonic()


@router.get("/health")
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    db_status = "ok"
    try:
        result = await session.execute(text("SELECT 1"))
        if result.scalar_one() != 1:
            db_status = "down"
    except Exception:
        db_status = "down"

    return {
        "status": "ok",
        "db": db_status,
        "uptime_seconds": int(time.monotonic() - _PROCESS_START),
        "version": settings.APP_VERSION,
    }
