from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Integer,
    Numeric,
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
    from app.models.trains import CoachClass
    from app.models.schedules import Schedule


class Route(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #20: Defined railway corridor linking origin and destination terminal stations.
    """
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    total_distance_km: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )

    # Relationships
    source_station: Mapped["Station"] = relationship("Station", foreign_keys=[source_station_id])
    destination_station: Mapped["Station"] = relationship("Station", foreign_keys=[destination_station_id])
    stops: Mapped[list["RouteStop"]] = relationship(
        "RouteStop", back_populates="route", cascade="all, delete-orphan", order_by="RouteStop.stop_sequence"
    )
    schedules: Mapped[list["Schedule"]] = relationship("Schedule", back_populates="route")

    __table_args__ = (
        CheckConstraint("total_distance_km >= 0", name="ck_routes_distance_non_negative"),
        Index(
            "uq_routes_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Route id={self.id} code='{self.code}' name='{self.name}'>"


class RouteStop(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #21: Sequential station stop along a route with cumulative distance from origin.
    """
    __tablename__ = "route_stops"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_from_origin_km: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )
    standard_halt_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Relationships
    route: Mapped["Route"] = relationship("Route", back_populates="stops")
    station: Mapped["Station"] = relationship("Station", back_populates="route_stops")

    __table_args__ = (
        CheckConstraint("stop_sequence >= 1", name="ck_route_stops_sequence_positive"),
        CheckConstraint("distance_from_origin_km >= 0", name="ck_route_stops_distance_non_negative"),
        CheckConstraint("standard_halt_minutes >= 0", name="ck_route_stops_halt_non_negative"),
        Index(
            "uq_route_stops_route_sequence_active",
            "route_id",
            "stop_sequence",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<RouteStop id={self.id} route_id={self.route_id} seq={self.stop_sequence}>"


class FareRule(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #22: Distance-bracketed pricing rules per coach class (base rate, rate per km, reservation fee).
    """
    __tablename__ = "fare_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    coach_class_id: Mapped[int] = mapped_column(
        ForeignKey("coach_classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    min_distance_km: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    max_distance_km: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("9999.00"), nullable=False)
    base_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    rate_per_km: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    reservation_charge: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"), nullable=False)

    # Relationships
    coach_class: Mapped["CoachClass"] = relationship("CoachClass", back_populates="fare_rules")

    __table_args__ = (
        CheckConstraint("base_fare >= 0", name="ck_fare_rules_base_fare_non_negative"),
        CheckConstraint("rate_per_km >= 0", name="ck_fare_rules_rate_per_km_non_negative"),
        CheckConstraint("reservation_charge >= 0", name="ck_fare_rules_reservation_charge_non_negative"),
        CheckConstraint("max_distance_km >= min_distance_km", name="ck_fare_rules_distance_range"),
    )

    def __repr__(self) -> str:
        return f"<FareRule id={self.id} coach_class_id={self.coach_class_id} base={self.base_fare}>"
