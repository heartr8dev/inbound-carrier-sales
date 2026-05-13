"""SQLAlchemy model for cached FMCSA carrier verification responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from api.src.db import Base


class CarrierVerification(Base):
    __tablename__ = "carrier_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mc_number: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dba_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operating_status: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_type: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_to_operate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    safety_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    insurance_bipd_on_file: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    insurance_cargo_on_file: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    is_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
