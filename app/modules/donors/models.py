import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.locations.models import Lga, State


class DonorProfile(Base):
    __tablename__ = "donor_profiles"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blood_type: Mapped[str] = mapped_column(String(3), index=True)

    # Raw genotype is NEVER stored — only this boolean.
    # SS and SC → false. Everyone else → true.
    is_genotype_eligible: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("states.id", ondelete="RESTRICT"), index=True
    )
    lga_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lgas.id", ondelete="RESTRICT"), index=True
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    last_donation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    state: Mapped[State] = relationship(lazy="joined")
    lga: Mapped[Lga] = relationship(lazy="joined")