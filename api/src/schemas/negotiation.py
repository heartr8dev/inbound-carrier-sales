"""Pydantic schemas for the stateless negotiation endpoint."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.src.schemas.enums import CarrierSentiment


class NegotiationState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    load_id: str
    loadboard_rate: Decimal
    round: int = Field(default=0, ge=0, le=3)
    agent_last_offer: Decimal | None = None
    carrier_last_offer: Decimal | None = None
    final_rate: Decimal | None = None
    status: Literal["pending", "agreed", "walked_away"] = "pending"


class NegotiateRequest(BaseModel):
    state: NegotiationState
    carrier_offer: Decimal = Field(..., gt=0)
    carrier_sentiment: CarrierSentiment | None = None
    origin: str | None = None
    destination: str | None = None


class NegotiateResponse(BaseModel):
    state: NegotiationState
    suggested_response: str
    counter_offer: Decimal | None = None
