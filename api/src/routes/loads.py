"""Load search routes (Phase 2 — Workstream B)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.db import get_session
from api.src.middleware.auth import require_api_key
from api.src.schemas.load import LoadSearchRequest, LoadSearchResponse
from api.src.services.load_matcher import match_loads

router = APIRouter(
    prefix="/loads",
    tags=["loads"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/search", response_model=LoadSearchResponse, status_code=status.HTTP_200_OK)
async def search_loads(
    payload: LoadSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> LoadSearchResponse:
    """Return the top-N matching loads for a carrier's pitch.

    Always returns 200 — an empty ``matches`` list signals "nothing in your
    lane" so the voice agent can respond gracefully instead of treating a 404
    as an error.
    """
    return await match_loads(session, payload)
