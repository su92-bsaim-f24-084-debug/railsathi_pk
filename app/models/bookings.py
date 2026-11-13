from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    Numeric,
    DateTime,
    Text,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin, SoftDeleteMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.stations import Station
    from app.models.trains import Seat, TrainCoach
    from app.models.schedules import JourneyInstance
    from app.models.payments import PaymentTransaction, RefundRequest
    from app.models.services import SpecialAssistanceRequest


class JourneyCoach(TimestampMixin, db.Model):
    """
    Model #26: Operational carriage attached to a specific journey instance.
    (SoftDelete: No).
    """
    __tablename__ = "journey_coaches"

    id: Mapped[int] = mapped_column(primary_key=True)
    journey_instance_id: Mapped[int] = mapped_column(
        ForeignKey("journey_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    train_coach_id: Mapped[int] = mapped_column(
        ForeignKey("train_coaches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence_in_train: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    available_seats_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    journey_instance: Mapped["JourneyInstance"] = relationship("JourneyInstance", back_populates="coaches")
    train_coach: Mapped["TrainCoach"] = relationship("TrainCoach")

    __table_args__ = (
        CheckConstraint("available_seats_count >= 0", name="ck_journey_coaches_seats_non_negative"),
        UniqueConstraint("journey_instance_id", "train_coach_id", name="uq_journey_coaches_journey_coach"),
    )

    def __repr__(self) -> str:
        return f"<JourneyCoach id={self.id} journey={self.journey_instance_id} coach={self.train_coach_id}>"


class SeatReservationLock(db.Model):
    """
    Model #27: Temporary operational hold placed on a seat during passenger checkout (10-minute expiry).
    (SoftDelete: No).
    """
    __tablename__ = "seat_reservation_locks"

    id: Mapped[int] = mapped_column(primary_key=True)
    journey_instance_id: Mapped[int] = mapped_column(
        ForeignKey("journey_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    to_stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    lock_token: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    is_released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    journey_instance: Mapped["JourneyInstance"] = relationship("JourneyInstance", back_populates="locks")
    seat: Mapped["Seat"] = relationship("Seat")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        CheckConstraint("from_stop_sequence >= 1", name="ck_seat_reservation_locks_from_seq_positive"),
        CheckConstraint("to_stop_sequence >= 1", name="ck_seat_reservation_locks_to_seq_positive"),
        CheckConstraint("from_stop_sequence < to_stop_sequence", name="ck_seat_reservation_locks_sequence_order"),
        Index("ix_seat_reservation_locks_journey_seat", "journey_instance_id", "seat_id"),
    )

    def __repr__(self) -> str:
        return f"<SeatReservationLock id={self.id} seat={self.seat_id} journey={self.journey_instance_id} released={self.is_released}>"


class Booking(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #28: Master reservation transaction with unique PNR and multi-ticket items.
    """
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    pnr_number: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    journey_instance_id: Mapped[int] = mapped_column(
        ForeignKey("journey_instances.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    origin_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    booking_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    total_passengers: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    booking_status: Mapped[str] = mapped_column(String(20), default="Pending", nullable=False)
    booking_channel: Mapped[str] = mapped_column(String(20), default="Web", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="bookings")
    journey_instance: Mapped["JourneyInstance"] = relationship("JourneyInstance", back_populates="bookings")
    origin_station: Mapped["Station"] = relationship("Station", foreign_keys=[origin_station_id])
    destination_station: Mapped["Station"] = relationship("Station", foreign_keys=[destination_station_id])
    passenger_tickets: Mapped[list["PassengerTicket"]] = relationship(
        "PassengerTicket", back_populates="booking", cascade="all, delete-orphan"
    )
    payment_transactions: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction", back_populates="booking"
    )
    status_history: Mapped[list["BookingStatusHistory"]] = relationship(
        "BookingStatusHistory", back_populates="booking", cascade="all, delete-orphan", order_by="BookingStatusHistory.created_at"
    )
    refund_request: Mapped["RefundRequest | None"] = relationship(
        "RefundRequest", back_populates="booking", uselist=False
    )
    assistance_requests: Mapped[list["SpecialAssistanceRequest"]] = relationship(
        "SpecialAssistanceRequest", back_populates="booking"
    )

    __table_args__ = (
        CheckConstraint("total_passengers >= 1", name="ck_bookings_passengers_positive"),
        CheckConstraint("total_fare >= 0", name="ck_bookings_total_fare_non_negative"),
        CheckConstraint("origin_station_id != destination_station_id", name="ck_bookings_origin_dest_different"),
        CheckConstraint("booking_status IN ('Pending', 'Confirmed', 'Cancelled', 'Refunded')", name="ck_bookings_status_valid"),
        Index(
            "uq_bookings_pnr_active",
            "pnr_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Booking id={self.id} pnr='{self.pnr_number}' status='{self.booking_status}'>"


class PassengerTicket(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #29: Individual traveler boarding pass containing passenger demographics and verification token.
    """
    __tablename__ = "passenger_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    cnic: Mapped[str] = mapped_column(String(15), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    ticket_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fare_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    ticket_status: Mapped[str] = mapped_column(String(20), default="Valid", nullable=False)

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="passenger_tickets")
    seat_allocation: Mapped["TicketSeatAllocation | None"] = relationship(
        "TicketSeatAllocation", back_populates="ticket", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("age >= 1 AND age <= 120", name="ck_passenger_tickets_age_valid"),
        CheckConstraint("fare_amount >= 0", name="ck_passenger_tickets_fare_non_negative"),
        CheckConstraint("ticket_status IN ('Valid', 'Cancelled', 'CheckedIn')", name="ck_passenger_tickets_status_valid"),
        Index(
            "uq_passenger_tickets_token_active",
            "ticket_token",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PassengerTicket id={self.id} booking_id={self.booking_id} name='{self.full_name}'>"


class TicketSeatAllocation(db.Model):
    """
    Model #30: Exact seat/berth allocation bound to an individual passenger ticket with segment sequences.
    (SoftDelete: No).
    """
    __tablename__ = "ticket_seat_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("passenger_tickets.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    journey_instance_id: Mapped[int] = mapped_column(
        ForeignKey("journey_instances.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    from_stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    to_stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    ticket: Mapped["PassengerTicket"] = relationship("PassengerTicket", back_populates="seat_allocation")
    journey_instance: Mapped["JourneyInstance"] = relationship("JourneyInstance", back_populates="allocations")
    seat: Mapped["Seat"] = relationship("Seat")

    __table_args__ = (
        CheckConstraint("from_stop_sequence >= 1", name="ck_ticket_seat_allocations_from_seq_positive"),
        CheckConstraint("to_stop_sequence >= 1", name="ck_ticket_seat_allocations_to_seq_positive"),
        CheckConstraint("from_stop_sequence < to_stop_sequence", name="ck_ticket_seat_allocations_sequence_order"),
        Index("ix_ticket_seat_allocations_journey_seat", "journey_instance_id", "seat_id"),
    )

    def __repr__(self) -> str:
        return f"<TicketSeatAllocation id={self.id} ticket={self.ticket_id} seat={self.seat_id} active={self.is_active}>"


class BookingStatusHistory(db.Model):
    """
    Model #31: Protected historical audit ledger of every status change undergone by a booking.
    (SoftDelete: No).
    """
    __tablename__ = "booking_status_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    change_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="status_history")
    changed_by: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<BookingStatusHistory id={self.id} booking={self.booking_id} {self.old_status}->{self.new_status}>"

