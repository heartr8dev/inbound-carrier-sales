"""SQLAlchemy model for freight loads available to inbound carriers."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
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
from api.src.schemas.enums import EquipmentType

equipment_type_enum = PgEnum(
    EquipmentType,
    name="equipment_type",
    values_callable=lambda enum: [m.value for m in enum],
    create_type=False,
)


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    load_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    origin: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(128), nullable=False)
    pickup_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivery_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    equipment_type: Mapped[EquipmentType] = mapped_column(
        equipment_type_enum, nullable=False
    )
    loadboard_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    commodity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    num_of_pieces: Mapped[int] = mapped_column(Integer, nullable=False)
    miles: Mapped[int] = mapped_column(Integer, nullable=False)
    dimensions: Mapped[str] = mapped_column(String(64), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_loads_equipment_type", "equipment_type"),
        Index("ix_loads_pickup_datetime", "pickup_datetime"),
    )
