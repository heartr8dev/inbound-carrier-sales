"""Negotiation engine routes (Phase 2 — Workstream C).

Single stateless endpoint.  The HappyRobot agent (or any caller) sends the
current ``NegotiationState`` along with the carrier's latest offer; we run
the pricing logic in :mod:`api.src.services.negotiation_engine` and hand
back the updated state plus a tactical natural-language reply.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from api.src.middleware.auth import require_api_key
from api.src.schemas.negotiation import NegotiateRequest, NegotiateResponse
from api.src.services.negotiation_engine import negotiate as run_negotiation

router = APIRouter(
    prefix="/negotiate",
    tags=["negotiate"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=NegotiateResponse, status_code=status.HTTP_200_OK)
async def negotiate(payload: NegotiateRequest) -> NegotiateResponse:
    return run_negotiation(payload)
