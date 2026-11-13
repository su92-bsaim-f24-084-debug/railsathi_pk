from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Numeric,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.stations import Station
    from app.models.bookings import Booking


class AssistanceType(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #46: Catalog of station passenger aid facilities (Wheelchair Service, Elderly Escort, Licensed Station Porter).
    """
    __tablename__ = "assistance_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    standard_fee: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"), nullable=False)
    requires_advance_booking_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    requests: Mapped[list["SpecialAssistanceRequest"]] = relationship(
        "SpecialAssistanceRequest", back_populates="assistance_type"
    )

    __table_args__ = (
        CheckConstraint("standard_fee >= 0", name="ck_assistance_types_fee_non_negative"),
        CheckConstraint("requires_advance_booking_hours >= 0", name="ck_assistance_types_advance_hours_non_negative"),
        Index(
            "uq_assistance_types_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<AssistanceType id={self.id} name='{self.name}'>"


class SpecialAssistanceRequest(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #47: Station assistance fulfillment booking for wheelchair, elderly support, or licensed coolie.
    """
    __tablename__ = "special_assistance_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assistance_type_id: Mapped[int] = mapped_column(
        ForeignKey("assistance_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    special_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Requested", nullable=False)
    assigned_staff_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    booking: Mapped["Booking | None"] = relationship("Booking", back_populates="assistance_requests")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    station: Mapped["Station"] = relationship("Station")
    assistance_type: Mapped["AssistanceType"] = relationship("AssistanceType", back_populates="requests")

    __table_args__ = (
        CheckConstraint("status IN ('Requested', 'Assigned', 'Completed', 'Cancelled')", name="ck_special_assistance_status_valid"),
    )

    def __repr__(self) -> str:
        return f"<SpecialAssistanceRequest id={self.id} station={self.station_id} status='{self.status}'>"
