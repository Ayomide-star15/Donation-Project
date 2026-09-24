import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.locations.models import Lga, State


class Community(Base):
    __tablename__ = "communities"
    __table_args__ = (
        UniqueConstraint("name", "state_id", "lga_id", name="uq_communities_name_state_lga"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50))
    state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("states.id", ondelete="RESTRICT"), index=True
    )
    lga_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lgas.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    state: Mapped[State] = relationship(lazy="joined")
    lga: Mapped[Lga] = relationship(lazy="joined")


class CommunityAdmin(Base):
    __tablename__ = "community_admins"
    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_community_admins_comm_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    community_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )