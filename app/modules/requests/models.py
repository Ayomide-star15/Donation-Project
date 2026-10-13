import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.hospitals.models import Hospital


class BloodRequest(Base):
    __tablename__ = "blood_requests"
    __table_args__ = (
        CheckConstraint(
            "donors_needed >= 1 AND donors_needed <= 10",
            name="ck_requests_donors_needed_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reference_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    requester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    community_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="RESTRICT"), index=True
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitals.id", ondelete="RESTRICT"), index=True
    )

    blood_type_needed: Mapped[str] = mapped_column(String(3), index=True)
    donors_needed: Mapped[int] = mapped_column(Integer)
    urgency: Mapped[str] = mapped_column(String(20), default="medium")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open", index=True
    )
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    requester_cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    hospital: Mapped[Hospital] = relationship(lazy="joined")

class DonorAcceptance(Base):
    __tablename__ = "donor_acceptances"
    __table_args__ = (
        UniqueConstraint("request_id", "donor_id", name="uq_acceptance_request_donor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blood_requests.id", ondelete="CASCADE"), index=True
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    verification_code_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), default="accepted", server_default="accepted", index=True
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )