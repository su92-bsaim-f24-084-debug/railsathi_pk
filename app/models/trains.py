from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    SmallInteger,
    Numeric,
    Text,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.stations import Station
    from app.models.routes import FareRule
    from app.models.schedules import Schedule


class TrainType(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #12: Rolling stock operational categories (Express, Intercity, Mail, Super Fast).
    """
    __tablename__ = "train_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_speed_kmh: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    trains: Mapped[list["Train"]] = relationship("Train", back_populates="train_type")

    __table_args__ = (
        Index(
            "uq_train_types_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_train_types_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<TrainType id={self.id} code='{self.code}'>"


class Train(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #13: Master rolling stock definitions representing trains (e.g., '1UP', '5DN').
    """
    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_type_id: Mapped[int] = mapped_column(
        ForeignKey("train_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    train_number: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    origin_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    train_type: Mapped["TrainType"] = relationship("TrainType", back_populates="trains")
    origin_station: Mapped["Station"] = relationship("Station", foreign_keys=[origin_station_id])
    destination_station: Mapped["Station"] = relationship("Station", foreign_keys=[destination_station_id])
    operational_days: Mapped[list["TrainOperationalDay"]] = relationship(
        "TrainOperationalDay", back_populates="train", cascade="all, delete-orphan"
    )
    coaches: Mapped[list["TrainCoach"]] = relationship(
        "TrainCoach", back_populates="train", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship("Schedule", back_populates="train")

    __table_args__ = (
        Index(
            "uq_trains_number_active",
            "train_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Train id={self.id} number='{self.train_number}' name='{self.name}'>"


class TrainOperationalDay(db.Model):
    """
    Model #14: Days of the week a recurring train operates (0=Mon, 6=Sun).
    (SoftDelete: No).
    """
    __tablename__ = "train_operational_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(
        ForeignKey("trains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    train: Mapped["Train"] = relationship("Train", back_populates="operational_days")

    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_train_operational_days_range"),
        UniqueConstraint("train_id", "day_of_week", name="uq_train_operational_days_train_day"),
    )

    def __repr__(self) -> str:
        return f"<TrainOperationalDay train_id={self.train_id} day={self.day_of_week}>"


class CoachClass(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #15: Accommodation classes (AC Sleeper, AC Business, AC Standard, Economy).
    """
    __tablename__ = "coach_classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    base_fare_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.00"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    coaches: Mapped[list["TrainCoach"]] = relationship("TrainCoach", back_populates="coach_class")
    fare_rules: Mapped[list["FareRule"]] = relationship("FareRule", back_populates="coach_class")

    __table_args__ = (
        CheckConstraint("base_fare_multiplier > 0", name="ck_coach_classes_multiplier_positive"),
        Index(
            "uq_coach_classes_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<CoachClass id={self.id} code='{self.code}'>"


class SeatLayoutType(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #16: Structural coach layout schema (2x2 Chair Car, 3x2 Economy, 6-Berth Coupe).
    """
    __tablename__ = "seat_layout_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_per_row: Mapped[int] = mapped_column(Integer, nullable=False)
    aisle_position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    coaches: Mapped[list["TrainCoach"]] = relationship("TrainCoach", back_populates="layout_type")

    __table_args__ = (
        CheckConstraint("total_rows > 0 AND seats_per_row > 0", name="ck_seat_layout_types_dimensions_positive"),
        Index(
            "uq_seat_layout_types_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<SeatLayoutType id={self.id} name='{self.name}'>"


class BerthType(TimestampMixin, db.Model):
    """
    Model #17: Comfort & positioning characteristics (Lower, Middle, Upper, Window, Aisle).
    Static reference authority (SoftDelete: No).
    """
    __tablename__ = "berth_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    seats: Mapped[list["Seat"]] = relationship("Seat", back_populates="berth_type")

    def __repr__(self) -> str:
        return f"<BerthType id={self.id} code='{self.code}'>"


class TrainCoach(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #18: Physical carriage attached to a specific train rake.
    """
    __tablename__ = "train_coaches"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(
        ForeignKey("trains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coach_class_id: Mapped[int] = mapped_column(
        ForeignKey("coach_classes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    layout_type_id: Mapped[int] = mapped_column(
        ForeignKey("seat_layout_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    coach_code: Mapped[str] = mapped_column(String(10), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    train: Mapped["Train"] = relationship("Train", back_populates="coaches")
    coach_class: Mapped["CoachClass"] = relationship("CoachClass", back_populates="coaches")
    layout_type: Mapped["SeatLayoutType"] = relationship("SeatLayoutType", back_populates="coaches")
    seats: Mapped[list["Seat"]] = relationship("Seat", back_populates="coach", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("sequence_number >= 1", name="ck_train_coaches_sequence_positive"),
        CheckConstraint("total_capacity > 0", name="ck_train_coaches_capacity_positive"),
        Index(
            "uq_train_coaches_train_code_active",
            "train_id",
            "coach_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_train_coaches_train_seq_active",
            "train_id",
            "sequence_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<TrainCoach id={self.id} train_id={self.train_id} code='{self.coach_code}'>"


class Seat(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #19: Master individual seat/berth slot in a train coach.
    """
    __tablename__ = "seats"

    id: Mapped[int] = mapped_column(primary_key=True)
    coach_id: Mapped[int] = mapped_column(
        ForeignKey("train_coaches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    berth_type_id: Mapped[int] = mapped_column(
        ForeignKey("berth_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seat_number: Mapped[str] = mapped_column(String(10), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_window: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_ladies_quota: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    coach: Mapped["TrainCoach"] = relationship("TrainCoach", back_populates="seats")
    berth_type: Mapped["BerthType"] = relationship("BerthType", back_populates="seats")

    __table_args__ = (
        CheckConstraint("row_number >= 1 AND column_number >= 1", name="ck_seats_grid_positive"),
        Index(
            "uq_seats_coach_number_active",
            "coach_id",
            "seat_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Seat id={self.id} coach_id={self.coach_id} number='{self.seat_number}'>"
