"""Add donor_profiles table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_0008"
down_revision: str | None = "20261005_0007"   # ← replace with your actual head
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "donor_profiles",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("blood_type", sa.String(3), nullable=False),
        sa.Column(
            "is_genotype_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("lga_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "availability",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("last_donation_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lga_id"], ["lgas.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_index("ix_donor_profiles_blood_type", "donor_profiles", ["blood_type"])
    op.create_index("ix_donor_profiles_state_id", "donor_profiles", ["state_id"])
    op.create_index("ix_donor_profiles_lga_id", "donor_profiles", ["lga_id"])
    op.create_index("ix_donor_profiles_availability", "donor_profiles", ["availability"])


def downgrade() -> None:
    op.drop_table("donor_profiles")