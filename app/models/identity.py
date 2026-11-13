from datetime import datetime, date, timezone
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    Date,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.base import TimestampMixin, SoftDeleteMixin, utc_now

if TYPE_CHECKING:
    from app.models.stations import Station
    from app.models.trains import CoachClass
    from app.models.bookings import Booking
    from app.models.complaints import Complaint


class User(TimestampMixin, SoftDeleteMixin, UserMixin, db.Model):
    """
    Model #1: Core identity representing all system actors (passengers, staff, administrators).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    cnic: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    is_active_user: Mapped[bool] = mapped_column("is_active", Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships within Phase 3A models - specify foreign_keys explicitly to distinguish from deleted_by_id
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        foreign_keys="UserProfile.user_id",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    staff_profile: Mapped["StaffProfile"] = relationship(
        "StaffProfile",
        foreign_keys="StaffProfile.user_id",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        foreign_keys="UserRole.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    session_logs: Mapped[list["UserSessionLog"]] = relationship(
        "UserSessionLog",
        foreign_keys="UserSessionLog.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        foreign_keys="Booking.user_id",
        back_populates="user",
    )
    complaints: Mapped[list["Complaint"]] = relationship(
        "Complaint",
        foreign_keys="Complaint.user_id",
        back_populates="user",
    )

    __table_args__ = (
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_users_cnic_active",
            "cnic",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    @property
    def password(self):
        raise AttributeError("Password hash is write-only and cannot be read.")

    @password.setter
    def password(self, plain_password: str) -> None:
        self.password_hash = generate_password_hash(plain_password)

    def check_password(self, candidate_password: str) -> bool:
        return check_password_hash(self.password_hash, candidate_password)

    @property
    def is_active(self) -> bool:
        """Flask-Login is_active property respecting account state and soft deletion."""
        return self.is_active_user and not self.is_deleted

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.is_active_user = bool(value)

    def get_id(self) -> str:
        return str(self.id)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def roles(self) -> list[str]:
        """Return list of role names assigned to the user."""
        return [ur.role.name for ur in self.user_roles if ur.role]

    def has_role(self, *role_names: str) -> bool:
        """Check if user has any of the specified roles."""
        user_roles = set(self.roles)
        return any(r in user_roles for r in role_names)

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' active={self.is_active}>"


class Role(TimestampMixin, db.Model):
    """
    Model #2: Standardized permission roles (Passenger, Reservation Officer, Station Master, etc.).
    Static reference authority (SoftDelete: No).
    """
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", foreign_keys="UserRole.role_id", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} code='{self.code}'>"


class UserRole(db.Model):
    """
    Model #3: Explicit junction associating users with roles and tracking assignment provenance.
    (SoftDelete: No).
    """
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="user_roles")
    role: Mapped["Role"] = relationship("Role", foreign_keys=[role_id], back_populates="user_roles")
    assigned_by: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_by_id])

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),
    )

    def __repr__(self) -> str:
        return f"<UserRole user_id={self.user_id} role_id={self.role_id}>"


class UserProfile(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #4: Extended passenger demographics, emergency contacts, and accessibility preferences.
    """
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    province: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_class_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_classes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="profile")
    preferred_class: Mapped["CoachClass | None"] = relationship("CoachClass")

    def __repr__(self) -> str:
        return f"<UserProfile id={self.id} user_id={self.user_id}>"


class StaffProfile(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #5: Railway staff operational metadata, employee credentials, and assigned station.
    """
    __tablename__ = "staff_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    employee_code: Mapped[str] = mapped_column(String(30), nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False)
    designation: Mapped[str] = mapped_column(String(50), nullable=False)
    station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    shift_timing: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="staff_profile")
    station: Mapped["Station | None"] = relationship("Station", back_populates="staff_profiles")

    __table_args__ = (
        Index(
            "uq_staff_profiles_employee_code_active",
            "employee_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<StaffProfile id={self.id} code='{self.employee_code}'>"


class UserSessionLog(db.Model):
    """
    Model #6: Protected security log of user sign-in sessions and client agents.
    (SoftDelete: No).
    """
    __tablename__ = "user_session_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False)
    login_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    logout_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="session_logs")

    def __repr__(self) -> str:
        return f"<UserSessionLog id={self.id} user_id={self.user_id} ip='{self.ip_address}'>"
