"""initial schema — loads, call_logs, carrier_verifications + enum types.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EQUIPMENT_TYPES = ("dry_van", "reefer", "flatbed", "step_deck", "power_only")
CALL_OUTCOMES = (
    "booked",
    "no_matching_loads",
    "carrier_declined_rate",
    "carrier_failed_vetting",
    "negotiation_stalled",
    "carrier_hung_up",
    "transferred_to_rep",
)
CARRIER_SENTIMENTS = ("positive", "neutral", "skeptical", "frustrated", "hostile")


def upgrade() -> None:
    equipment_type = postgresql.ENUM(
        *EQUIPMENT_TYPES, name="equipment_type", create_type=True
    )
    call_outcome = postgresql.ENUM(
        *CALL_OUTCOMES, name="call_outcome", create_type=True
    )
    carrier_sentiment = postgresql.ENUM(
        *CARRIER_SENTIMENTS, name="carrier_sentiment", create_type=True
    )
    bind = op.get_bind()
    equipment_type.create(bind, checkfirst=True)
    call_outcome.create(bind, checkfirst=True)
    carrier_sentiment.create(bind, checkfirst=True)

    op.create_table(
        "loads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("load_id", sa.String(32), nullable=False),
        sa.Column("origin", sa.String(128), nullable=False),
        sa.Column("destination", sa.String(128), nullable=False),
        sa.Column("pickup_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "equipment_type",
            postgresql.ENUM(*EQUIPMENT_TYPES, name="equipment_type", create_type=False),
            nullable=False,
        ),
        sa.Column("loadboard_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("commodity_type", sa.String(128), nullable=False),
        sa.Column("num_of_pieces", sa.Integer(), nullable=False),
        sa.Column("miles", sa.Integer(), nullable=False),
        sa.Column("dimensions", sa.String(64), nullable=False),
        sa.Column(
            "is_available", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("load_id", name="uq_loads_load_id"),
    )
    op.create_index("ix_loads_load_id", "loads", ["load_id"], unique=True)
    op.create_index("ix_loads_equipment_type", "loads", ["equipment_type"])
    op.create_index("ix_loads_pickup_datetime", "loads", ["pickup_datetime"])

    op.create_table(
        "call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", sa.String(64), nullable=False),
        sa.Column("carrier_mc", sa.String(16), nullable=True),
        sa.Column("carrier_name", sa.String(128), nullable=True),
        sa.Column("carrier_company", sa.String(255), nullable=True),
        sa.Column(
            "load_id_discussed",
            sa.String(32),
            sa.ForeignKey("loads.load_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("loadboard_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("initial_carrier_ask", sa.Numeric(10, 2), nullable=True),
        sa.Column("final_agreed_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "negotiation_rounds", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "outcome",
            postgresql.ENUM(*CALL_OUTCOMES, name="call_outcome", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "sentiment",
            postgresql.ENUM(
                *CARRIER_SENTIMENTS, name="carrier_sentiment", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "equipment_type_requested",
            postgresql.ENUM(*EQUIPMENT_TYPES, name="equipment_type", create_type=False),
            nullable=True,
        ),
        sa.Column("origin_requested", sa.String(128), nullable=True),
        sa.Column("destination_requested", sa.String(128), nullable=True),
        sa.Column("call_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("transcript_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("call_id", name="uq_call_logs_call_id"),
    )
    op.create_index("ix_call_logs_call_id", "call_logs", ["call_id"], unique=True)
    op.create_index("ix_call_logs_carrier_mc", "call_logs", ["carrier_mc"])
    op.create_index("ix_call_logs_created_at", "call_logs", ["created_at"])

    op.create_table(
        "carrier_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mc_number", sa.String(16), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("dba_name", sa.String(255), nullable=True),
        sa.Column("operating_status", sa.String(64), nullable=False),
        sa.Column("authority_type", sa.String(32), nullable=False),
        sa.Column("allowed_to_operate", sa.Boolean(), nullable=False),
        sa.Column("safety_rating", sa.String(32), nullable=True),
        sa.Column("insurance_bipd_on_file", sa.Numeric(12, 2), nullable=True),
        sa.Column("insurance_cargo_on_file", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_eligible", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.String(255), nullable=True),
        sa.Column(
            "raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("mc_number", name="uq_carrier_verifications_mc_number"),
    )
    op.create_index(
        "ix_carrier_verifications_mc_number",
        "carrier_verifications",
        ["mc_number"],
        unique=True,
    )
    op.create_index(
        "ix_carrier_verifications_verified_at", "carrier_verifications", ["verified_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_carrier_verifications_verified_at", table_name="carrier_verifications"
    )
    op.drop_index(
        "ix_carrier_verifications_mc_number", table_name="carrier_verifications"
    )
    op.drop_table("carrier_verifications")

    op.drop_index("ix_call_logs_created_at", table_name="call_logs")
    op.drop_index("ix_call_logs_carrier_mc", table_name="call_logs")
    op.drop_index("ix_call_logs_call_id", table_name="call_logs")
    op.drop_table("call_logs")

    op.drop_index("ix_loads_pickup_datetime", table_name="loads")
    op.drop_index("ix_loads_equipment_type", table_name="loads")
    op.drop_index("ix_loads_load_id", table_name="loads")
    op.drop_table("loads")

    bind = op.get_bind()
    postgresql.ENUM(name="carrier_sentiment").drop(bind, checkfirst=True)
    postgresql.ENUM(name="call_outcome").drop(bind, checkfirst=True)
    postgresql.ENUM(name="equipment_type").drop(bind, checkfirst=True)
