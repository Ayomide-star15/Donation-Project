"""Replace TOTP and JWT refresh sessions with email OTP and opaque sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0002"
down_revision: str | None = "20260916_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Authentication challenges are intentionally short-lived, so legacy TOTP
    # challenges are discarded instead of translated into email OTP challenges.
    op.execute("DELETE FROM auth_challenges")
    op.drop_index("ix_auth_challenges_expires_at", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_user_id", table_name="auth_challenges")
    op.rename_table("auth_challenges", "otp_challenges")
    op.alter_column(
        "otp_challenges",
        "purpose",
        existing_type=sa.String(32),
        type_=sa.String(50),
    )
    op.add_column("otp_challenges", sa.Column("code_hash", sa.String(64), nullable=False))
    op.add_column(
        "otp_challenges",
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
    )
    op.add_column(
        "otp_challenges",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "otp_challenges",
        sa.Column("resend_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "otp_challenges",
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "otp_challenges",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("otp_challenges", sa.Column("requested_ip", sa.String(64), nullable=True))
    op.create_index("ix_otp_challenges_user_id", "otp_challenges", ["user_id"])
    op.create_index("ix_otp_challenges_purpose", "otp_challenges", ["purpose"])
    op.create_index("ix_otp_challenges_expires_at", "otp_challenges", ["expires_at"])

    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_methods")

    op.drop_index("ix_sessions_token_family_id", table_name="sessions")
    op.drop_constraint("sessions_refresh_token_hash_key", "sessions", type_="unique")
    op.alter_column(
        "sessions",
        "refresh_token_hash",
        existing_type=sa.String(64),
        new_column_name="token_hash",
    )
    op.drop_column("sessions", "token_family_id")
    op.alter_column(
        "sessions",
        "last_used_at",
        existing_type=sa.DateTime(timezone=True),
        new_column_name="last_seen_at",
    )
    op.add_column(
        "sessions",
        sa.Column("auth_level", sa.String(30), nullable=False, server_default="password_otp"),
    )
    op.add_column("sessions", sa.Column("device_name", sa.String(255), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_idle_expires_at", "sessions", ["idle_expires_at"])
    op.execute(
        "UPDATE sessions SET revoked_at = NOW(), "
        "revocation_reason = 'authentication_architecture_changed' "
        "WHERE revoked_at IS NULL"
    )

    op.add_column("users", sa.Column("user_code", sa.String(20), nullable=True))
    op.execute(
        "UPDATE users SET user_code = 'USR-' || UPPER(SUBSTRING(MD5(id::text), 1, 10)) "
        "WHERE user_code IS NULL"
    )
    op.alter_column("users", "user_code", nullable=False)
    op.create_index("ix_users_user_code", "users", ["user_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_user_code", table_name="users")
    op.drop_column("users", "user_code")

    op.drop_index("ix_sessions_idle_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_column("sessions", "idle_expires_at")
    op.drop_column("sessions", "device_name")
    op.drop_column("sessions", "auth_level")
    op.alter_column(
        "sessions",
        "last_seen_at",
        existing_type=sa.DateTime(timezone=True),
        new_column_name="last_used_at",
    )
    op.add_column("sessions", sa.Column("token_family_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE sessions SET token_family_id = id WHERE token_family_id IS NULL")
    op.alter_column("sessions", "token_family_id", nullable=False)
    op.alter_column(
        "sessions",
        "token_hash",
        existing_type=sa.String(64),
        new_column_name="refresh_token_hash",
    )
    op.create_unique_constraint(
        "sessions_refresh_token_hash_key", "sessions", ["refresh_token_hash"]
    )
    op.create_index("ix_sessions_token_family_id", "sessions", ["token_family_id"])

    op.create_table(
        "mfa_methods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("encrypted_secret", sa.String(512), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "method"),
    )
    op.create_index("ix_mfa_methods_user_id", "mfa_methods", ["user_id"])
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"])

    op.drop_index("ix_otp_challenges_expires_at", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_purpose", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_user_id", table_name="otp_challenges")
    op.drop_column("otp_challenges", "requested_ip")
    op.drop_column("otp_challenges", "superseded_at")
    op.drop_column("otp_challenges", "last_sent_at")
    op.drop_column("otp_challenges", "resend_count")
    op.drop_column("otp_challenges", "max_attempts")
    op.drop_column("otp_challenges", "channel")
    op.drop_column("otp_challenges", "code_hash")
    op.alter_column(
        "otp_challenges",
        "purpose",
        existing_type=sa.String(50),
        type_=sa.String(32),
    )
    op.rename_table("otp_challenges", "auth_challenges")
    op.create_index("ix_auth_challenges_user_id", "auth_challenges", ["user_id"])
    op.create_index("ix_auth_challenges_expires_at", "auth_challenges", ["expires_at"])
