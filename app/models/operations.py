from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin, SoftDeleteMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.stations import Station, StationPlatform
    from app.models.trains import Train
    from app.models.schedules import JourneyInstance


class TrainDelayLog(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #36: Station Master operational entries documenting train schedule deviations and causes.
    """
    __tablename__ = "train_delay_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    journey_instance_id: Mapped[int] = mapped_column(
        ForeignKey("journey_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(150), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    journey_instance: Mapped["JourneyInstance"] = relationship("JourneyInstance", back_populates="delay_logs")
    station: Mapped["Station"] = relationship("Station")
    recorded_by: Mapped["User | None"] = relationship("User", foreign_keys=[recorded_by_id])

    __table_args__ = (
        CheckConstraint("delay_minutes >= 0", name="ck_train_delay_logs_minutes_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<TrainDelayLog id={self.id} journey={self.journey_instance_id} delay={self.delay_minutes}m>"


class JourneyStationActual(db.Model):
    """
    Model #37: Realized operational timetable logs (actual arrival, departure, and platform berth) at every station.
    (SoftDelete: No).
    """
    __tablename__ = "journey_station_actuals"

    id: Mapped[int] = mapped_column(primary_key=True)
    journey_instance_id: Mapped[int] = mapped_column(
        ForeignKey("journey_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actual_platform_id: Mapped[int | None] = mapped_column(
        ForeignKey("station_platforms.id", ondelete="SET NULL"), nullable=True
    )
    actual_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Arrived", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    journey_instance: Mapped["JourneyInstance"] = relationship("JourneyInstance", back_populates="station_actuals")
    station: Mapped["Station"] = relationship("Station")
    actual_platform: Mapped["StationPlatform | None"] = relationship("StationPlatform")

    __table_args__ = (
        CheckConstraint("status IN ('Arrived', 'Departed', 'Skipped')", name="ck_journey_station_actuals_status_valid"),
    )

    def __repr__(self) -> str:
        return f"<JourneyStationActual id={self.id} journey={self.journey_instance_id} station={self.station_id} status='{self.status}'>"


class ServiceAlert(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #38: Emergency announcements and public service disruption notices across stations and trains.
    """
    __tablename__ = "service_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="Info", nullable=False)
    station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    train_id: Mapped[int | None] = mapped_column(
        ForeignKey("trains.id", ondelete="SET NULL"), nullable=True, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    station: Mapped["Station | None"] = relationship("Station")
    train: Mapped["Train | None"] = relationship("Train")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        CheckConstraint("severity IN ('Info', 'Warning', 'Critical')", name="ck_service_alerts_severity_valid"),
    )

    def __repr__(self) -> str:
        return f"<ServiceAlert id={self.id} title='{self.title}' severity='{self.severity}'>"
