from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """
    Mixin providing timezone-aware created_at and updated_at audit timestamps.
    Uses datetime.now(timezone.utc) for robust cross-database UTC handling.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Reusable soft-delete mixin.
    
    Fields:
      - is_deleted: Boolean flag (indexed, default False).
      - deleted_at: Timestamp when soft deletion occurred.
      - deleted_by_id: Foreign key to the User who executed the soft deletion.
      
    Querying & Constraints:
      - is_active_record(): Classmethod returning the SQL filter expression `is_deleted == False`.
      - Unique constraints on soft-deletable models are defined via partial unique indexes:
        `Index(..., unique=True, postgresql_where=(is_deleted == False), sqlite_where=(is_deleted == False))`
        This guarantees that soft-deleted rows do not block re-creation of the same code, username,
        or sequence.
    """
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    @classmethod
    def is_active_record(cls):
        """Returns the filter expression for active (non-soft-deleted) records."""
        return cls.is_deleted.is_(False)

    def soft_delete(self, user_id: int | None = None) -> None:
        """Mark record as soft-deleted and record timestamp and user."""
        self.is_deleted = True
        self.deleted_at = utc_now()
        self.deleted_by_id = user_id

    def restore(self) -> None:
        """Restore soft-deleted record back to active state."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by_id = None

