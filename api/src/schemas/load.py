"""Pydantic schemas for load search and load-detail responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from api.src.schemas.enums import EquipmentType


class LoadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    load_id: str
    origin: str
    destination: str
    pickup_datetime: datetime
    delivery_datetime: datetime
    equipment_type: EquipmentType
    loadboard_rate: Decimal
    notes: str | None = None
    weight: int
    commodity_type: str
    num_of_pieces: int
    miles: int
    dimensions: str


class LoadOut(LoadBase):
    is_available: bool
    created_at: datetime


class LoadSearchRequest(BaseModel):
    origin: str | None = Field(
        default=None, description="Free-form origin string from the carrier."
    )
    destination: str | None = Field(
        default=None, description="Free-form destination string."
    )
    equipment_type: EquipmentType | None = None
    pickup_date: datetime | None = Field(
        default=None, description="Target pickup date — matched within +/- 2 days."
    )
    max_results: int = Field(default=3, ge=1, le=10)


class LoadMatch(LoadBase):
    score: int = Field(..., ge=0, le=100)
    rate_per_mile: Decimal
    match_score: int = Field(
        ..., ge=0, le=100, description="Alias of score; preferred name per spec."
    )
    partial_match: bool = Field(
        default=False,
        description="True when this match came from the origin-only fallback rather than the primary filter.",
    )


class LoadSearchResponse(BaseModel):
    matches: list[LoadMatch]
    total_found: int
    partial: bool = False
    message: str | None = None
