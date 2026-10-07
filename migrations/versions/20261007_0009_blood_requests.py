"""Add blood_requests table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261007_0009"
down_revision: str | None = "20261005_0008"   # ← replace with your head
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blood_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference_code", sa.String(20), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("community_id", sa.Uuid(), nullable=False),
        sa.Column("hospital_id", sa.Uuid(), nullable=False),
        sa.Column("blood_type_needed", sa.String(3), nullable=False),
        sa.Column("donors_needed", sa.Integer(), nullable=False),
        sa.Column("urgency", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requester_cooldown_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_code"),
        sa.CheckConstraint("donors_needed >= 1 AND donors_needed <= 10",
                           name="ck_requests_donors_needed_range"),
    )
    op.create_index("ix_blood_requests_requester_id", "blood_requests", ["requester_id"])
    op.create_index("ix_blood_requests_community_id", "blood_requests", ["community_id"])
    op.create_index("ix_blood_requests_hospital_id", "blood_requests", ["hospital_id"])
    op.create_index("ix_blood_requests_status", "blood_requests", ["status"])
    op.create_index("ix_blood_requests_blood_type", "blood_requests", ["blood_type_needed"])
    op.create_index("ix_blood_requests_created_at", "blood_requests", ["created_at"])


def downgrade() -> None:
    op.drop_table("blood_requests")