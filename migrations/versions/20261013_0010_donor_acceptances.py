"""Add donor_acceptances table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261013_0010"
down_revision: str | None = "20261007_0009"   # ← replace with your actual head
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "donor_acceptances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("donor_id", sa.Uuid(), nullable=False),
        sa.Column("verification_code_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["blood_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["donor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "donor_id", name="uq_acceptance_request_donor"),
    )
    op.create_index("ix_donor_acceptances_request_id", "donor_acceptances", ["request_id"])
    op.create_index("ix_donor_acceptances_donor_id", "donor_acceptances", ["donor_id"])
    op.create_index("ix_donor_acceptances_status", "donor_acceptances", ["status"])

    # Enforce: one active acceptance per donor (at a time)
    op.execute("""
        CREATE UNIQUE INDEX one_active_acceptance_per_donor
        ON donor_acceptances (donor_id)
        WHERE status = 'accepted';
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS one_active_acceptance_per_donor")
    op.drop_table("donor_acceptances")