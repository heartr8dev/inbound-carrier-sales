"""Call log routes (Phase 2 — Workstream D).

``POST /api/v1/calls/log`` receives the rich post-call payload that the
HappyRobot workflow's AI Extract node forwards via webhook. We classify the
outcome and sentiment from that payload, persist a ``CallLog`` row, and echo
the three derived fields back. ``GET /api/v1/calls`` lists rows with the
filter / pagination knobs the dashboard needs.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.db import get_session
from api.src.middleware.auth import require_api_key
from api.src.models.call_log import CallLog
from api.src.schemas.call import (
    CallListItem,
    CallListResponse,
    CallLogRequest,
    CallLogResponse,
)
from api.src.schemas.enums import CallOutcome, CarrierSentiment
from api.src.services.call_classifier import classify_outcome, classify_sentiment
from api.src.services.events import event_bus
from loguru import logger

router = APIRouter(
    prefix="/calls",
    tags=["calls"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/log", response_model=CallLogResponse, status_code=status.HTTP_200_OK)
async def log_call(
    payload: CallLogRequest,
    session: AsyncSession = Depends(get_session),
) -> CallLogResponse:
    """Persist a single call log row derived from the post-call extraction.

    Returns 409 on duplicate ``call_id`` so the agent's webhook retry logic
    won't silently insert duplicates if it fires twice for the same call.
    """

    outcome = classify_outcome(payload)
    sentiment = classify_sentiment(payload)

    row = CallLog(
        call_id=payload.call_id,
        carrier_mc=payload.carrier_mc,
        carrier_name=payload.carrier_name,
        carrier_company=payload.carrier_company,
        load_id_discussed=payload.load_id_discussed,
        loadboard_rate=payload.loadboard_rate,
        initial_carrier_ask=payload.initial_carrier_ask,
        final_agreed_rate=payload.final_agreed_rate,
        negotiation_rounds=payload.negotiation_rounds,
        outcome=outcome,
        sentiment=sentiment,
        equipment_type_requested=payload.equipment_type_requested,
        origin_requested=payload.origin_requested,
        destination_requested=payload.destination_requested,
        call_duration_seconds=payload.call_duration_seconds,
        transcript_summary=payload.transcript_summary,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"call_id {payload.call_id!r} already exists",
        ) from exc

    # Fire-and-forget: push the new row out to any SSE subscribers so the
    # dashboard updates in near-real-time instead of waiting for the next
    # 30s TanStack poll. We swallow + log failures so a pub/sub hiccup never
    # rolls back a successful insert.
    try:
        await event_bus.publish(
            "call.created",
            {
                "call_id": row.call_id,
                "outcome": str(row.outcome.value),
                "sentiment": str(row.sentiment.value),
                "carrier_mc": row.carrier_mc,
                "carrier_company": row.carrier_company,
                "load_id_discussed": row.load_id_discussed,
                "final_agreed_rate": (
                    str(row.final_agreed_rate) if row.final_agreed_rate is not None else None
                ),
                "created_at": row.created_at.isoformat(),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("event_publish_failed", error=str(exc), call_id=row.call_id)

    return CallLogResponse(call_id=payload.call_id, outcome=outcome, sentiment=sentiment)


@router.get("", response_model=CallListResponse, status_code=status.HTTP_200_OK)
async def list_calls(
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    outcome: CallOutcome | None = None,
    sentiment: CarrierSentiment | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> CallListResponse:
    """List call logs newest-first with optional filters and pagination."""

    filters = []
    if date_from is not None:
        filters.append(CallLog.created_at >= date_from)
    if date_to is not None:
        filters.append(CallLog.created_at <= date_to)
    if outcome is not None:
        filters.append(CallLog.outcome == outcome)
    if sentiment is not None:
        filters.append(CallLog.sentiment == sentiment)

    count_stmt = select(func.count()).select_from(CallLog)
    items_stmt = select(CallLog).order_by(CallLog.created_at.desc())
    for f in filters:
        count_stmt = count_stmt.where(f)
        items_stmt = items_stmt.where(f)

    total = (await session.execute(count_stmt)).scalar_one()
    offset = (page - 1) * page_size
    items_stmt = items_stmt.offset(offset).limit(page_size)
    rows = (await session.execute(items_stmt)).scalars().all()

    items = [
        CallListItem(
            id=str(row.id),
            call_id=row.call_id,
            carrier_mc=row.carrier_mc,
            carrier_name=row.carrier_name,
            carrier_company=row.carrier_company,
            load_id_discussed=row.load_id_discussed,
            loadboard_rate=row.loadboard_rate,
            initial_carrier_ask=row.initial_carrier_ask,
            final_agreed_rate=row.final_agreed_rate,
            negotiation_rounds=row.negotiation_rounds,
            outcome=row.outcome,
            sentiment=row.sentiment,
            equipment_type_requested=row.equipment_type_requested,
            origin_requested=row.origin_requested,
            destination_requested=row.destination_requested,
            call_duration_seconds=row.call_duration_seconds,
            transcript_summary=row.transcript_summary,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return CallListResponse(items=items, total=total, page=page, page_size=page_size)
