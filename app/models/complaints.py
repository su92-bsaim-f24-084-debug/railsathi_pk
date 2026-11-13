from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    SmallInteger,
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
from app.models.base import TimestampMixin, SoftDeleteMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.stations import Station
    from app.models.trains import Train


class ComplaintCategory(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #39: Structured grievance classification (Cleanliness, AC, Conduct, Catering, Punctuality).
    """
    __tablename__ = "complaint_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    complaints: Mapped[list["Complaint"]] = relationship("Complaint", back_populates="category")

    __table_args__ = (
        CheckConstraint("sla_hours > 0", name="ck_complaint_categories_sla_positive"),
        Index(
            "uq_complaint_categories_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ComplaintCategory id={self.id} name='{self.name}'>"


class Complaint(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #40: Passenger grievance ticket with tracking code, priority, and resolution lifecycle.
    """
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("complaint_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    train_id: Mapped[int | None] = mapped_column(
        ForeignKey("trains.id", ondelete="SET NULL"), nullable=True, index=True
    )
    station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Submitted", nullable=False)
    priority: Mapped[str] = mapped_column(String(15), default="Medium", nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="complaints")
    category: Mapped["ComplaintCategory"] = relationship("ComplaintCategory", back_populates="complaints")
    train: Mapped["Train | None"] = relationship("Train")
    station: Mapped["Station | None"] = relationship("Station")
    timelines: Mapped[list["ComplaintTimeline"]] = relationship(
        "ComplaintTimeline", back_populates="complaint", cascade="all, delete-orphan", order_by="ComplaintTimeline.created_at"
    )
    feedback_rating: Mapped["FeedbackRating | None"] = relationship(
        "FeedbackRating", back_populates="complaint", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('Submitted', 'InReview', 'Resolved', 'Rejected')", name="ck_complaints_status_valid"),
        CheckConstraint("priority IN ('Low', 'Medium', 'High', 'Urgent')", name="ck_complaints_priority_valid"),
        Index(
            "uq_complaints_tracking_active",
            "tracking_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Complaint id={self.id} tracking='{self.tracking_number}' status='{self.status}'>"


class ComplaintTimeline(db.Model):
    """
    Model #41: Chronological investigation notes, commentary, and status transitions for a complaint.
    (SoftDelete: No).
    """
    __tablename__ = "complaint_timelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="timelines")
    author: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ComplaintTimeline id={self.id} complaint={self.complaint_id} status='{self.new_status}'>"


class FeedbackRating(db.Model):
    """
    Model #42: Passenger post-resolution service quality review (1 to 5 stars).
    (SoftDelete: No).
    """
    __tablename__ = "feedback_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="feedback_rating")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_ratings_range"),
    )

    def __repr__(self) -> str:
        return f"<FeedbackRating id={self.id} complaint={self.complaint_id} rating={self.rating}>"
