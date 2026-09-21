"""Add invites table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260919_0004"
down_revision: str | None = "20260918_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("community_name", sa.String(200), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False, server_default="community_admin"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_token_hash", "invites", ["token_hash"], unique=True)
    op.create_index("ix_invites_status", "invites", ["status"])


def downgrade() -> None:
    op.drop_table("invites")