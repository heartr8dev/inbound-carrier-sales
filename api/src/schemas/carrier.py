"""Pydantic schemas for the FMCSA carrier verify endpoint."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CarrierVerifyRequest(BaseModel):
    mc: str = Field(..., min_length=1, max_length=8, description="MC docket number digits only.")


class CarrierVerifyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mc_number: str
    legal_name: str | None = None
    dba_name: str | None = None
    operating_status: str | None = None
    authority_type: str | None = None
    allowed_to_operate: bool | None = None
    safety_rating: str | None = None
    insurance_bipd_on_file: Decimal | None = None
    insurance_cargo_on_file: Decimal | None = None
    is_eligible: bool | None = None
    rejection_reason: str | None = None
    verified_at: datetime | None = None
    cached: bool = False
