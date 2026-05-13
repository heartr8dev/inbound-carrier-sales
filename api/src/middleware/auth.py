"""X-API-Key dependency with constant-time compare."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from api.src.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
