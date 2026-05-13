"""FMCSA carrier verification routes (Phase 2 — Workstream A)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.db import get_session
from api.src.middleware.auth import require_api_key
from api.src.schemas.carrier import CarrierVerifyRequest, CarrierVerifyResponse
from api.src.services.fmcsa import (
    FMCSAClient,
    FMCSANotFound,
    FMCSAUnavailable,
)

router = APIRouter(
    prefix="/carrier",
    tags=["carrier"],
    dependencies=[Depends(require_api_key)],
)

_MC_PATTERN = re.compile(r"^\d{1,8}$")


def _bad_format_response() -> CarrierVerifyResponse:
    return CarrierVerifyResponse(
        mc_number="",
        is_eligible=False,
        rejection_reason="invalid_mc_format",
    )


@router.post(
    "/verify",
    response_model=CarrierVerifyResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_carrier(
    payload: CarrierVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> CarrierVerifyResponse:
    mc = payload.mc.strip()
    log = logger.bind(component="route.carrier", mc=mc)

    if not _MC_PATTERN.match(mc):
        log.info("rejecting invalid mc format")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "invalid_mc_format", "mc": mc},
        )

    client = FMCSAClient()
    try:
        result = await client.lookup_by_mc(mc, db)
    except FMCSANotFound:
        log.info("mc not found in FMCSA")
        await client.aclose()
        return CarrierVerifyResponse(
            mc_number=mc,
            is_eligible=False,
            rejection_reason="mc_not_found",
            verified_at=datetime.now(timezone.utc),
            cached=False,
        )
    except FMCSAUnavailable as exc:
        log.warning("FMCSA unavailable: {!r}", exc)
        await client.aclose()
        # 503 with Retry-After tells the agent (and any retry middleware) to back off.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"reason": "fmcsa_unavailable", "error": str(exc)},
            headers={"Retry-After": "60"},
        ) from exc
    finally:
        # If client.aclose was already called in an except branch the second
        # call is a no-op on httpx.AsyncClient.aclose().
        await client.aclose()

    if result.circuit_open:
        log.warning("circuit open — returning fmcsa_unavailable as 200")
        return CarrierVerifyResponse(
            mc_number=mc,
            is_eligible=None,
            rejection_reason="fmcsa_unavailable",
            verified_at=datetime.now(timezone.utc),
            cached=False,
        )

    row = result.row
    assert row is not None  # circuit_open=False => row populated

    return CarrierVerifyResponse(
        mc_number=row.mc_number,
        legal_name=row.legal_name,
        dba_name=row.dba_name,
        operating_status=row.operating_status,
        authority_type=row.authority_type,
        allowed_to_operate=row.allowed_to_operate,
        safety_rating=row.safety_rating,
        insurance_bipd_on_file=row.insurance_bipd_on_file,
        insurance_cargo_on_file=row.insurance_cargo_on_file,
        is_eligible=row.is_eligible,
        rejection_reason=row.rejection_reason,
        verified_at=row.verified_at,
        cached=result.cached,
    )
