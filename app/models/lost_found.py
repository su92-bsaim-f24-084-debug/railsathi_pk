from datetime import date, datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Date,
    DateTime,
    Text,
    ForeignKey,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin, SoftDeleteMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.stations import Station
    from app.models.trains import Train


class LostFoundCategory(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #43: Classification for lost and found property (Luggage, Electronics, Documents, Valuables).
    """
    __tablename__ = "lost_found_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    reports: Mapped[list["LostFoundReport"]] = relationship("LostFoundReport", back_populates="category")

    __table_args__ = (
        Index(
            "uq_lost_found_categories_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<LostFoundCategory id={self.id} name='{self.name}'>"


class LostFoundReport(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #44: Registry report for misplaced or recovered property at stations or on trains.
    """
    __tablename__ = "lost_found_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'Lost' or 'Found'
    category_id: Mapped[int] = mapped_column(
        ForeignKey("lost_found_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reported_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    train_id: Mapped[int | None] = mapped_column(
        ForeignKey("trains.id", ondelete="SET NULL"), nullable=True, index=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    item_color: Mapped[str | None] = mapped_column(String(30), nullable=True)
    lost_found_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Reported", nullable=False)
    storage_location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    category: Mapped["LostFoundCategory"] = relationship("LostFoundCategory", back_populates="reports")
    reported_by: Mapped["User"] = relationship("User", foreign_keys=[reported_by_id])
    train: Mapped["Train | None"] = relationship("Train")
    station: Mapped["Station"] = relationship("Station")
    claims: Mapped[list["LostFoundClaim"]] = relationship(
        "LostFoundClaim", back_populates="report", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("report_type IN ('Lost', 'Found')", name="ck_lost_found_reports_type_valid"),
        CheckConstraint("status IN ('Reported', 'StoredAtStation', 'ClaimPending', 'Returned', 'Unclaimed')", name="ck_lost_found_reports_status_valid"),
    )

    def __repr__(self) -> str:
        return f"<LostFoundReport id={self.id} type='{self.report_type}' item='{self.item_name}'>"


class LostFoundClaim(db.Model):
    """
    Model #45: Formal claim over a registered found article requiring proof of ownership verification.
    (SoftDelete: No).
    """
    __tablename__ = "lost_found_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("lost_found_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claimant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proof_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="UnderReview", nullable=False)
    verified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    report: Mapped["LostFoundReport"] = relationship("LostFoundReport", back_populates="claims")
    claimant: Mapped["User"] = relationship("User", foreign_keys=[claimant_id])
    verified_by: Mapped["User | None"] = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        CheckConstraint("status IN ('UnderReview', 'Approved', 'Rejected')", name="ck_lost_found_claims_status_valid"),
    )

    def __repr__(self) -> str:
        return f"<LostFoundClaim id={self.id} report={self.report_id} status='{self.status}'>"

