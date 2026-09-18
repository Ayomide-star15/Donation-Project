import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.locations.models import Lga, State


class Hospital(Base):
    __tablename__ = "hospitals"
    __table_args__ = (
        UniqueConstraint("name", "state_id", "lga_id", name="uq_hospitals_name_state_lga"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str] = mapped_column(String(500))
    state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("states.id", ondelete="RESTRICT"), index=True
    )
    lga_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lgas.id", ondelete="RESTRICT"), index=True
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
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