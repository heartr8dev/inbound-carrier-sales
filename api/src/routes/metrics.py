"""Dashboard metrics aggregation routes (Phase 2 — Workstream E).

Thin handler that delegates to :func:`metrics_aggregator.aggregate_metrics`.
The handler exists only to bind query params + the DB session; all aggregation
is SQL-side.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.db import get_session
from api.src.middleware.auth import require_api_key
from api.src.schemas.metrics import MetricsPeriod, MetricsResponse
from api.src.services.metrics_aggregator import aggregate_metrics

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=MetricsResponse, status_code=status.HTTP_200_OK)
async def get_metrics(
    period: MetricsPeriod = Query(default="7d"),
    session: AsyncSession = Depends(get_session),
) -> MetricsResponse:
    """Return the full dashboard payload for the selected ``period``."""
    return await aggregate_metrics(session, period)
