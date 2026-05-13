"""Pydantic schema for the dashboard metrics endpoint."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from api.src.schemas.enums import CallOutcome, CarrierSentiment, EquipmentType


MetricsPeriod = Literal["today", "7d", "30d", "all"]


class KPIBar(BaseModel):
    calls_today: int
    booked_rate_pct: float
    avg_margin_saved_usd: Decimal
    avg_negotiation_rounds: float


class FunnelStage(BaseModel):
    name: str
    count: int
    drop_off_pct: float


class FunnelSection(BaseModel):
    stages: list[FunnelStage]


class RevenueSection(BaseModel):
    avg_loadboard_rate: Decimal
    avg_booked_rate: Decimal
    avg_margin_preserved_pct: float


class NegotiationRoundBucket(BaseModel):
    round: int
    agreed: int
    walked: int
    avg_discount_pct: float


class NegotiationSection(BaseModel):
    buckets: list[NegotiationRoundBucket]


class VettingSection(BaseModel):
    pass_count: int
    fail_count: int
    top_failure_reasons: list[dict[str, int | str]]


class SentimentDistribution(BaseModel):
    sentiment: CarrierSentiment
    count: int


class SentimentOutcomeCell(BaseModel):
    sentiment: CarrierSentiment
    outcome: CallOutcome
    count: int


class SentimentSection(BaseModel):
    distribution: list[SentimentDistribution]
    heatmap: list[SentimentOutcomeCell]


class LaneVolume(BaseModel):
    origin: str
    destination: str
    count: int


class EquipmentDemand(BaseModel):
    equipment_type: EquipmentType
    count: int


class LoadMatchingSection(BaseModel):
    top_lanes: list[LaneVolume]
    equipment_demand: list[EquipmentDemand]


class TimeseriesPoint(BaseModel):
    bucket_start: datetime
    calls: int
    booked: int


class TimeseriesSection(BaseModel):
    points: list[TimeseriesPoint]


class RecentCallItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: str
    carrier_mc: str | None
    carrier_name: str | None
    carrier_company: str | None
    load_id_discussed: str | None
    loadboard_rate: Decimal | None
    final_agreed_rate: Decimal | None
    negotiation_rounds: int
    outcome: CallOutcome
    sentiment: CarrierSentiment
    origin_requested: str | None
    destination_requested: str | None
    equipment_type_requested: EquipmentType | None
    transcript_summary: str | None
    created_at: datetime


class MetricsResponse(BaseModel):
    period: MetricsPeriod
    generated_at: datetime
    kpi: KPIBar
    funnel: FunnelSection
    revenue: RevenueSection
    negotiation: NegotiationSection
    vetting: VettingSection
    sentiment: SentimentSection
    load_matching: LoadMatchingSection
    timeseries: TimeseriesSection
    recent_calls: list[RecentCallItem]
