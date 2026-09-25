"""Add community_members, community_join_links, and invites.community_id."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260925_0006"
down_revision: str | None = "20260924_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add community_id to invites (for member invites)
    op.add_column(
        "invites",
        sa.Column("community_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_invites_community_id",
        "invites",
        "communities",
        ["community_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_invites_community_id", "invites", ["community_id"])

    # community_members — the queue
    op.create_table(
        "community_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("community_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("community_id", "email", name="uq_community_members_email"),
    )
    op.create_index("ix_community_members_community_id", "community_members", ["community_id"])
    op.create_index("ix_community_members_user_id", "community_members", ["user_id"])
    op.create_index("ix_community_members_status", "community_members", ["status"])

    # community_join_links — shareable public link
    op.create_table(
        "community_join_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("community_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_community_join_links_code", "community_join_links", ["code"], unique=True)
    op.create_index("ix_community_join_links_community_id", "community_join_links", ["community_id"])


def downgrade() -> None:
    op.drop_table("community_join_links")
    op.drop_table("community_members")
    op.drop_index("ix_invites_community_id", table_name="invites")
    op.drop_constraint("fk_invites_community_id", "invites", type_="foreignkey")
    op.drop_column("invites", "community_id")