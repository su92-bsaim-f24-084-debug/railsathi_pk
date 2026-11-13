from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    Numeric,
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
    from app.models.identity import StaffProfile
    from app.models.routes import RouteStop
    from app.models.schedules import ScheduleStop


class StationDivision(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #7: Regional administrative railway divisions (e.g., Lahore, Karachi, Rawalpindi).
    """
    __tablename__ = "station_divisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    headquarters_city: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    stations: Mapped[list["Station"]] = relationship(
        "Station", back_populates="division", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uq_station_divisions_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<StationDivision id={self.id} code='{self.code}'>"


class Station(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #8: Operational railway stations across Pakistan with codes, coordinates, and contacts.
    """
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    division_id: Mapped[int] = mapped_column(
        ForeignKey("station_divisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str] = mapped_column(String(50), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_junction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    division: Mapped["StationDivision"] = relationship("StationDivision", back_populates="stations")
    platforms: Mapped[list["StationPlatform"]] = relationship(
        "StationPlatform", back_populates="station", cascade="all, delete-orphan"
    )
    facilities: Mapped[list["StationFacility"]] = relationship(
        "StationFacility", back_populates="station", cascade="all, delete-orphan"
    )
    route_stops: Mapped[list["RouteStop"]] = relationship(
        "RouteStop", back_populates="station", cascade="all, delete-orphan"
    )
    schedule_stops: Mapped[list["ScheduleStop"]] = relationship(
        "ScheduleStop", back_populates="station", cascade="all, delete-orphan"
    )
    staff_profiles: Mapped[list["StaffProfile"]] = relationship(
        "StaffProfile", foreign_keys="StaffProfile.station_id", back_populates="station"
    )

    __table_args__ = (
        Index(
            "uq_stations_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Station id={self.id} code='{self.code}' name='{self.name}'>"


class StationPlatform(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #9: Physical platforms within a station for berthing trains and boarding.
    """
    __tablename__ = "station_platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_number: Mapped[str] = mapped_column(String(10), nullable=False)
    length_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_disabled_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_operational: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    station: Mapped["Station"] = relationship("Station", back_populates="platforms")

    __table_args__ = (
        Index(
            "uq_station_platforms_station_platform_active",
            "station_id",
            "platform_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<StationPlatform id={self.id} station_id={self.station_id} platform='{self.platform_number}'>"


class FacilityCategory(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #10: Passenger amenity classification (Waiting Room, Prayer Area, Tuck Shop, Medical).
    """
    __tablename__ = "facility_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    facilities: Mapped[list["StationFacility"]] = relationship(
        "StationFacility", back_populates="category", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uq_facility_categories_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<FacilityCategory id={self.id} name='{self.name}'>"


class StationFacility(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #11: Concrete amenities stationed at specific stations, detailing location and fees.
    """
    __tablename__ = "station_facilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("facility_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_details: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    opening_hours: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    station: Mapped["Station"] = relationship("Station", back_populates="facilities")
    category: Mapped["FacilityCategory"] = relationship("FacilityCategory", back_populates="facilities")

    __table_args__ = (
        CheckConstraint("fee_amount >= 0", name="ck_station_facilities_fee_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<StationFacility id={self.id} name='{self.name}' station_id={self.station_id}>"
