"""Add communities and community_admins tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260924_0005"
down_revision: str | None = "20260919_0004"   # ← matches your current head
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "communities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("lga_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lga_id"], ["lgas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "state_id", "lga_id", name="uq_communities_name_state_lga"),
    )
    op.create_index("ix_communities_state_id", "communities", ["state_id"])
    op.create_index("ix_communities_status", "communities", ["status"])

    op.create_table(
        "community_admins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("community_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("community_id", "user_id", name="uq_community_admins_comm_user"),
    )
    op.create_index("ix_community_admins_user_id", "community_admins", ["user_id"])
    op.create_index("ix_community_admins_community_id", "community_admins", ["community_id"])


def downgrade() -> None:
    op.drop_table("community_admins")
    op.drop_table("communities")