from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    Numeric,
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
    from app.models.bookings import Booking


class PaymentMethod(TimestampMixin, SoftDeleteMixin, db.Model):
    """
    Model #32: Master catalog of simulated payment options (JazzCash Demo, EasyPaisa Demo, Card Demo, Wallet).
    """
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    transactions: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction", back_populates="payment_method"
    )

    __table_args__ = (
        Index(
            "uq_payment_methods_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PaymentMethod id={self.id} code='{self.code}'>"


class PaymentTransaction(db.Model):
    """
    Model #33: Protected financial ledger of simulated payment authorizations and reference tokens.
    (SoftDelete: No).
    """
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="PKR", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Success", nullable=False)
    simulated_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="payment_transactions")
    payment_method: Mapped["PaymentMethod"] = relationship("PaymentMethod", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payment_transactions_amount_non_negative"),
        CheckConstraint("status IN ('Initiated', 'Success', 'Failed', 'Reversed')", name="ck_payment_transactions_status_valid"),
    )

    def __repr__(self) -> str:
        return f"<PaymentTransaction id={self.id} ref='{self.transaction_reference}' status='{self.status}'>"


class RefundRequest(db.Model):
    """
    Model #34: Passenger cancellation refund requests requiring deduction calculation and approval.
    (SoftDelete: No).
    """
    __tablename__ = "refund_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    deduction_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    refundable_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Pending", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="refund_request")
    requested_by: Mapped["User"] = relationship("User", foreign_keys=[requested_by_user_id])
    decision_by: Mapped["User | None"] = relationship("User", foreign_keys=[decision_by_user_id])
    audit_trails: Mapped[list["RefundAuditTrail"]] = relationship(
        "RefundAuditTrail", back_populates="refund_request", cascade="all, delete-orphan", order_by="RefundAuditTrail.created_at"
    )

    __table_args__ = (
        CheckConstraint("original_amount >= 0", name="ck_refund_requests_original_amount_non_negative"),
        CheckConstraint("deduction_amount >= 0", name="ck_refund_requests_deduction_non_negative"),
        CheckConstraint("refundable_amount >= 0", name="ck_refund_requests_refundable_non_negative"),
        CheckConstraint("status IN ('Pending', 'Approved', 'Rejected', 'Processed')", name="ck_refund_requests_status_valid"),
    )

    def __repr__(self) -> str:
        return f"<RefundRequest id={self.id} booking_id={self.booking_id} status='{self.status}'>"


class RefundAuditTrail(db.Model):
    """
    Model #35: Step-by-step audit history of refund verification, deduction changes, and payout records.
    (SoftDelete: No).
    """
    __tablename__ = "refund_audit_trails"

    id: Mapped[int] = mapped_column(primary_key=True)
    refund_request_id: Mapped[int] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_taken: Mapped[str] = mapped_column(String(50), nullable=False)
    performed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    refund_request: Mapped["RefundRequest"] = relationship("RefundRequest", back_populates="audit_trails")
    performed_by: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<RefundAuditTrail id={self.id} refund_id={self.refund_request_id} action='{self.action_taken}'>"

