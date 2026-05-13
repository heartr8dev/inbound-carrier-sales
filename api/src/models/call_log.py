"""SQLAlchemy model for a single inbound call's outcome and extracted metadata."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from api.src.db import Base
from api.src.schemas.enums import CallOutcome, CarrierSentiment, EquipmentType

call_outcome_enum = PgEnum(
    CallOutcome,
    name="call_outcome",
    values_callable=lambda enum: [m.value for m in enum],
    create_type=False,
)
carrier_sentiment_enum = PgEnum(
    CarrierSentiment,
    name="carrier_sentiment",
    values_callable=lambda enum: [m.value for m in enum],
    create_type=False,
)
equipment_type_enum = PgEnum(
    EquipmentType,
    name="equipment_type",
    values_callable=lambda enum: [m.value for m in enum],
    create_type=False,
)


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    carrier_mc: Mapped[str | None] = mapped_column(
        String(16), index=True, nullable=True
    )
    carrier_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    carrier_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    load_id_discussed: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("loads.load_id", ondelete="SET NULL"),
        nullable=True,
    )
    loadboard_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    initial_carrier_ask: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    final_agreed_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    negotiation_rounds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[CallOutcome] = mapped_column(call_outcome_enum, nullable=False)
    sentiment: Mapped[CarrierSentiment] = mapped_column(
        carrier_sentiment_enum, nullable=False
    )
    equipment_type_requested: Mapped[EquipmentType | None] = mapped_column(
        equipment_type_enum, nullable=True
    )
    origin_requested: Mapped[str | None] = mapped_column(String(128), nullable=True)
    destination_requested: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    call_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_call_logs_created_at", "created_at"),)
