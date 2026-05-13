"""Pydantic schemas for the call log endpoints (post-call extraction + listing)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from api.src.schemas.enums import CallOutcome, CarrierSentiment, EquipmentType


class CallLogRequest(BaseModel):
    call_id: str
    carrier_mc: str | None = None
    carrier_name: str | None = None
    carrier_company: str | None = None
    load_id_discussed: str | None = None
    loadboard_rate: Decimal | None = None
    initial_carrier_ask: Decimal | None = None
    final_agreed_rate: Decimal | None = None
    negotiation_rounds: int = 0
    transferred: bool = False
    vetting_passed: bool | None = None
    loads_searched: bool = False
    matches_returned: int = 0
    equipment_type_requested: EquipmentType | None = None
    origin_requested: str | None = None
    destination_requested: str | None = None
    call_duration_seconds: int | None = None
    transcript_summary: str | None = None
    sentiment: CarrierSentiment | None = None


class CallLogResponse(BaseModel):
    call_id: str
    outcome: CallOutcome
    sentiment: CarrierSentiment


class CallListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    call_id: str
    carrier_mc: str | None = None
    carrier_name: str | None = None
    carrier_company: str | None = None
    load_id_discussed: str | None = None
    loadboard_rate: Decimal | None = None
    initial_carrier_ask: Decimal | None = None
    final_agreed_rate: Decimal | None = None
    negotiation_rounds: int
    outcome: CallOutcome
    sentiment: CarrierSentiment
    equipment_type_requested: EquipmentType | None = None
    origin_requested: str | None = None
    destination_requested: str | None = None
    call_duration_seconds: int | None = None
    transcript_summary: str | None = None
    created_at: datetime


class CallListResponse(BaseModel):
    items: list[CallListItem]
    total: int
    page: int
    page_size: int


class CallListQuery(BaseModel):
    date_from: datetime | None = Field(default=None, alias="from")
    date_to: datetime | None = Field(default=None, alias="to")
    outcome: CallOutcome | None = None
    sentiment: CarrierSentiment | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
