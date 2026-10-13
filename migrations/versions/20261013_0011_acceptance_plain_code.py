"""Add plaintext verification_code for donor display."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261013_0011"
down_revision: str | None = "20261013_0010"   # ← replace with your actual head
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clear existing acceptances since we can't backfill the plaintext codes
    op.execute("DELETE FROM donor_acceptances")

    op.add_column(
        "donor_acceptances",
        sa.Column("verification_code", sa.String(6), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("donor_acceptances", "verification_code")