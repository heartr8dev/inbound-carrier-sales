"""Shared enums used by both SQLAlchemy models and Pydantic schemas."""

from __future__ import annotations

from enum import Enum


class CallOutcome(str, Enum):
    BOOKED = "booked"
    NO_MATCHING_LOADS = "no_matching_loads"
    CARRIER_DECLINED_RATE = "carrier_declined_rate"
    CARRIER_FAILED_VETTING = "carrier_failed_vetting"
    NEGOTIATION_STALLED = "negotiation_stalled"
    CARRIER_HUNG_UP = "carrier_hung_up"
    TRANSFERRED_TO_REP = "transferred_to_rep"


class CarrierSentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    SKEPTICAL = "skeptical"
    FRUSTRATED = "frustrated"
    HOSTILE = "hostile"


class EquipmentType(str, Enum):
    DRY_VAN = "dry_van"
    REEFER = "reefer"
    FLATBED = "flatbed"
    STEP_DECK = "step_deck"
    POWER_ONLY = "power_only"
