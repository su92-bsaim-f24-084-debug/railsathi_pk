"""Schema verification tests for RailSathi PK.

Verifies:
1. Exact 50 tables in SQLAlchemy metadata.
2. Exact 33/17 SoftDeleteMixin split across all 50 models.
3. Every single table has at least one meaningful incoming or outgoing foreign key.
4. Partial unique indexes defined on soft-deletable models.
"""
import pytest
from app.extensions import db
from app.models.base import SoftDeleteMixin
import app.models as m

EXPECTED_50_TABLES = {
    # Identity & Access (#1-#6)
    "users",
    "roles",
    "user_roles",
    "user_profiles",
    "staff_profiles",
    "user_session_logs",
    # Stations & Infrastructure (#7-#11)
    "station_divisions",
    "stations",
    "station_platforms",
    "facility_categories",
    "station_facilities",
    # Trains & Rolling Stock (#12-#19)
    "train_types",
    "trains",
    "train_operational_days",
    "coach_classes",
    "seat_layout_types",
    "berth_types",
    "train_coaches",
    "seats",
    # Routes & Network (#20-#22)
    "routes",
    "route_stops",
    "fare_rules",
    # Schedules & Journeys (#23-#25)
    "schedules",
    "schedule_stops",
    "journey_instances",
    # Bookings & Ticketing (#26-#31)
    "journey_coaches",
    "seat_reservation_locks",
    "bookings",
    "passenger_tickets",
    "ticket_seat_allocations",
    "booking_status_histories",
    # Payments & Refunds (#32-#35)
    "payment_methods",
    "payment_transactions",
    "refund_requests",
    "refund_audit_trails",
    # Operations & Tracking (#36-#38)
    "train_delay_logs",
    "journey_station_actuals",
    "service_alerts",
    # Customer Service & Feedback (#39-#42)
    "complaint_categories",
    "complaints",
    "complaint_timelines",
    "feedback_ratings",
    # Lost & Found (#43-#45)
    "lost_found_categories",
    "lost_found_reports",
    "lost_found_claims",
    # Special Services (#46-#47)
    "assistance_types",
    "special_assistance_requests",
    # Governance & Audit (#48-#50)
    "notification_templates",
    "notifications",
    "audit_logs",
}

MODELS_WITH_SOFT_DELETE = {
    m.User,
    m.UserProfile,
    m.StaffProfile,
    m.StationDivision,
    m.Station,
    m.StationPlatform,
    m.FacilityCategory,
    m.StationFacility,
    m.TrainType,
    m.Train,
    m.CoachClass,
    m.SeatLayoutType,
    m.TrainCoach,
    m.Seat,
    m.Route,
    m.RouteStop,
    m.FareRule,
    m.Schedule,
    m.ScheduleStop,
    m.JourneyInstance,
    m.Booking,
    m.PassengerTicket,
    m.PaymentMethod,
    m.TrainDelayLog,
    m.ServiceAlert,
    m.ComplaintCategory,
    m.Complaint,
    m.LostFoundCategory,
    m.LostFoundReport,
    m.AssistanceType,
    m.SpecialAssistanceRequest,
    m.NotificationTemplate,
    m.Notification,
}

MODELS_WITHOUT_SOFT_DELETE = {
    m.Role,
    m.UserRole,
    m.UserSessionLog,
    m.TrainOperationalDay,
    m.BerthType,
    m.JourneyCoach,
    m.SeatReservationLock,
    m.TicketSeatAllocation,
    m.BookingStatusHistory,
    m.PaymentTransaction,
    m.RefundRequest,
    m.RefundAuditTrail,
    m.JourneyStationActual,
    m.ComplaintTimeline,
    m.FeedbackRating,
    m.LostFoundClaim,
    m.AuditLog,
}


def test_exact_50_tables_registered(app):
    """Verify that exactly 50 domain tables are registered in SQLAlchemy metadata."""
    registered_tables = set(db.metadata.tables.keys())
    assert len(registered_tables) == 50, f"Expected 50 tables, found {len(registered_tables)}: {registered_tables}"
    assert registered_tables == EXPECTED_50_TABLES, f"Difference: {registered_tables ^ EXPECTED_50_TABLES}"


def test_soft_delete_model_split():
    """Verify the approved 33/17 soft-delete split across all 50 models."""
    assert len(MODELS_WITH_SOFT_DELETE) == 33, f"Expected 33 soft-deletable models, got {len(MODELS_WITH_SOFT_DELETE)}"
    assert len(MODELS_WITHOUT_SOFT_DELETE) == 17, f"Expected 17 non-soft-deletable models, got {len(MODELS_WITHOUT_SOFT_DELETE)}"
    assert len(MODELS_WITH_SOFT_DELETE & MODELS_WITHOUT_SOFT_DELETE) == 0, "Overlap found between lists!"

    for model in MODELS_WITH_SOFT_DELETE:
        assert issubclass(model, SoftDeleteMixin), f"{model.__name__} should inherit SoftDeleteMixin"
        assert hasattr(model, "is_deleted"), f"{model.__name__} missing is_deleted column"
        assert hasattr(model, "deleted_at"), f"{model.__name__} missing deleted_at column"
        assert hasattr(model, "deleted_by_id"), f"{model.__name__} missing deleted_by_id column"
        assert hasattr(model, "soft_delete"), f"{model.__name__} missing soft_delete method"
        assert hasattr(model, "restore"), f"{model.__name__} missing restore method"

    for model in MODELS_WITHOUT_SOFT_DELETE:
        assert not issubclass(model, SoftDeleteMixin), f"{model.__name__} should NOT inherit SoftDeleteMixin"
        assert not hasattr(model, "is_deleted"), f"{model.__name__} must not have is_deleted"


def test_all_50_tables_have_foreign_key_connectivity(app):
    """Verify that every single table has at least one incoming or outgoing foreign key."""
    all_tables = db.metadata.tables
    outgoing_fks = {name: set(tbl.foreign_keys) for name, tbl in all_tables.items()}

    incoming_fks = {name: set() for name in all_tables}
    for source_name, tbl in all_tables.items():
        for fk in tbl.foreign_keys:
            target_table_name = fk.column.table.name
            incoming_fks[target_table_name].add((source_name, fk))

    isolated_tables = []
    for name in all_tables:
        has_outgoing = len(outgoing_fks[name]) > 0
        has_incoming = len(incoming_fks[name]) > 0
        if not (has_outgoing or has_incoming):
            isolated_tables.append(name)

    assert len(isolated_tables) == 0, f"Found isolated tables with no relationships: {isolated_tables}"


def test_partial_unique_indexes_exist(app):
    """Verify that partial unique indexes exist on core soft-deletable tables."""
    users_table = db.metadata.tables["users"]
    index_names = {idx.name for idx in users_table.indexes}
    assert "uq_users_email_active" in index_names
    assert "uq_users_cnic_active" in index_names

    email_idx = next(idx for idx in users_table.indexes if idx.name == "uq_users_email_active")
    assert email_idx.unique is True
    assert email_idx.dialect_options["postgresql"]["where"] is not None
