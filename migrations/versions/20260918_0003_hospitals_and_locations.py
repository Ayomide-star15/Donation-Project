"""Add states, LGAs, and hospitals tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260918_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- states ----
    op.create_table(
        "states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_states_code", "states", ["code"], unique=True)
    op.create_index("ix_states_name", "states", ["name"], unique=True)

    # ---- lgas ----
    op.create_table(
        "lgas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_id", "name", name="uq_lgas_state_name"),
    )
    op.create_index("ix_lgas_state_id", "lgas", ["state_id"])
    op.create_index("ix_lgas_name", "lgas", ["name"])

    # ---- hospitals ----
    op.create_table(
        "hospitals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("lga_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lga_id"], ["lgas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "state_id", "lga_id", name="uq_hospitals_name_state_lga"),
    )
    op.create_index("ix_hospitals_state_id", "hospitals", ["state_id"])
    op.create_index("ix_hospitals_lga_id", "hospitals", ["lga_id"])
    op.create_index("ix_hospitals_is_active", "hospitals", ["is_active"])


def downgrade() -> None:
    op.drop_table("hospitals")
    op.drop_table("lgas")
    op.drop_table("states")