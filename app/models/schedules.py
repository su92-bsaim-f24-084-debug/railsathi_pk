from datetime import time, date
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    SmallInteger,
    Time,
    Date,
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
    from app.models.stations import Station
    from app.models.trains import Train
    from app.models.routes import Route
    from app.models.bookings import JourneyCoach, SeatReservationLock, Booking, TicketSeatAllocation
    from app.models.operations import TrainDelayLog, JourneyStationActual


class Schedule(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #23: Timetable blueprint linking a Train and Route with standard departure/arrival timings.
    """
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(
        ForeignKey("trains.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    schedule_code: Mapped[str] = mapped_column(String(30), nullable=False)
    departure_time: Mapped[time] = mapped_column(Time, nullable=False)
    arrival_time: Mapped[time] = mapped_column(Time, nullable=False)
    journey_days_span: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    train: Mapped["Train"] = relationship("Train", back_populates="schedules")
    route: Mapped["Route"] = relationship("Route", back_populates="schedules")
    stops: Mapped[list["ScheduleStop"]] = relationship(
        "ScheduleStop", back_populates="schedule", cascade="all, delete-orphan", order_by="ScheduleStop.stop_sequence"
    )
    journeys: Mapped[list["JourneyInstance"]] = relationship(
        "JourneyInstance", back_populates="schedule", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("journey_days_span >= 1", name="ck_schedules_days_span_positive"),
        Index(
            "uq_schedules_code_active",
            "schedule_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Schedule id={self.id} code='{self.schedule_code}' train_id={self.train_id}>"


class ScheduleStop(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #24: Precise timetable arrival, departure, and day offset for each stop in a Schedule.
    Used for segment overlap and intermediate station validation in the booking workflow.
    """
    __tablename__ = "schedule_stops"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_arrival: Mapped[time | None] = mapped_column(Time, nullable=True)
    scheduled_departure: Mapped[time | None] = mapped_column(Time, nullable=True)
    day_offset: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    # Relationships
    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="stops")
    station: Mapped["Station"] = relationship("Station", back_populates="schedule_stops")

    __table_args__ = (
        CheckConstraint("stop_sequence >= 1", name="ck_schedule_stops_sequence_positive"),
        CheckConstraint("day_offset >= 0", name="ck_schedule_stops_day_offset_non_negative"),
        Index(
            "uq_schedule_stops_schedule_sequence_active",
            "schedule_id",
            "stop_sequence",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ScheduleStop id={self.id} schedule_id={self.schedule_id} seq={self.stop_sequence}>"


class JourneyInstance(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #25: Concrete calendar run of a train schedule on a specific date (e.g., Train 1UP on 2026-11-20).
    """
    __tablename__ = "journey_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    journey_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="Scheduled", nullable=False)
    current_delay_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_booking_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="journeys")
    coaches: Mapped[list["JourneyCoach"]] = relationship(
        "JourneyCoach", back_populates="journey_instance", cascade="all, delete-orphan"
    )
    locks: Mapped[list["SeatReservationLock"]] = relationship(
        "SeatReservationLock", back_populates="journey_instance", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="journey_instance")
    allocations: Mapped[list["TicketSeatAllocation"]] = relationship(
        "TicketSeatAllocation", back_populates="journey_instance"
    )
    delay_logs: Mapped[list["TrainDelayLog"]] = relationship(
        "TrainDelayLog", back_populates="journey_instance", cascade="all, delete-orphan"
    )
    station_actuals: Mapped[list["JourneyStationActual"]] = relationship(
        "JourneyStationActual", back_populates="journey_instance", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('Scheduled', 'Running', 'Delayed', 'Completed', 'Cancelled')",
            name="ck_journey_instances_status_valid",
        ),
        Index(
            "uq_journey_instances_schedule_date_active",
            "schedule_id",
            "journey_date",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<JourneyInstance id={self.id} schedule_id={self.schedule_id} date='{self.journey_date}' status='{self.status}'>"
