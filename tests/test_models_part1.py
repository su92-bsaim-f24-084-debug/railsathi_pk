import pytest
from datetime import datetime, date, time, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers
from app.extensions import db
from app.models.identity import (
    User,
    Role,
    UserRole,
    UserProfile,
    StaffProfile,
    UserSessionLog,
)
from app.models.stations import (
    StationDivision,
    Station,
    StationPlatform,
    FacilityCategory,
    StationFacility,
)
from app.models.trains import (
    TrainType,
    Train,
    TrainOperationalDay,
    CoachClass,
    SeatLayoutType,
    BerthType,
    TrainCoach,
    Seat,
)
from app.models.routes import (
    Route,
    RouteStop,
    FareRule,
)
from app.models.schedules import (
    Schedule,
    ScheduleStop,
    JourneyInstance,
)

EXPECTED_PART1_TABLES = {
    "users",
    "roles",
    "user_roles",
    "user_profiles",
    "staff_profiles",
    "user_session_logs",
    "station_divisions",
    "stations",
    "station_platforms",
    "facility_categories",
    "station_facilities",
    "train_types",
    "trains",
    "train_operational_days",
    "coach_classes",
    "seat_layout_types",
    "berth_types",
    "train_coaches",
    "seats",
    "routes",
    "route_stops",
    "fare_rules",
    "schedules",
    "schedule_stops",
    "journey_instances",
}


def test_25_tables_registered_in_metadata(app):
    """Verify exactly the first 25 approved domain tables are registered in MetaData."""
    registered_tables = set(db.metadata.tables.keys())
    assert EXPECTED_PART1_TABLES.issubset(registered_tables), (
        f"Missing tables! Diff: {EXPECTED_PART1_TABLES - registered_tables}"
    )
    assert len(EXPECTED_PART1_TABLES) == 25


def test_mappers_configure_cleanly():
    """Verify that all relationships, foreign keys, and mapper configurations resolve without error."""
    try:
        configure_mappers()
    except Exception as exc:
        pytest.fail(f"configure_mappers() raised an exception: {exc}")


def test_user_password_hashing_and_verification():
    """Verify secure password hashing and verification on User model."""
    user = User(
        email="passenger@railsathi.pk",
        first_name="Ahmed",
        last_name="Khan",
        phone_number="03001234567",
        cnic="35201-1234567-1",
    )
    user.password = "PakRail@2026#Secure"

    assert user.password_hash != "PakRail@2026#Secure"
    assert user.check_password("PakRail@2026#Secure") is True
    assert user.check_password("WrongPassword") is False

    with pytest.raises(AttributeError, match="Password hash is write-only"):
        _ = user.password


def test_user_soft_delete_and_is_active(app):
    """Verify soft_delete, restore, and Flask-Login is_active behavior on User."""
    user = User(
        email="test_active@railsathi.pk",
        first_name="Tariq",
        last_name="Aziz",
        phone_number="03019876543",
        cnic="35201-9876543-1",
        password="ValidPassword123",
    )
    db.session.add(user)
    db.session.commit()

    assert user.is_deleted is False
    assert user.is_active is True

    # Perform soft deletion
    user.soft_delete(user_id=1)
    db.session.commit()

    assert user.is_deleted is True
    assert user.deleted_at is not None
    assert user.deleted_by_id == 1
    assert user.is_active is False  # Flask-Login respects soft delete

    # Restore record
    user.restore()
    db.session.commit()

    assert user.is_deleted is False
    assert user.deleted_at is None
    assert user.deleted_by_id is None
    assert user.is_active is True


def test_soft_delete_query_filtering(app):
    """Verify is_active_record filter isolates active from soft-deleted rows."""
    div = StationDivision(code="LHR", name="Lahore Division", headquarters_city="Lahore")
    db.session.add(div)
    db.session.commit()

    s1 = Station(
        division_id=div.id,
        code="LHE",
        name="Lahore Junction",
        city="Lahore",
        province="Punjab",
    )
    s2 = Station(
        division_id=div.id,
        code="KCH",
        name="Karachi Cantt",
        city="Karachi",
        province="Sindh",
    )
    db.session.add_all([s1, s2])
    db.session.commit()

    s2.soft_delete()
    db.session.commit()

    active_stations = db.session.scalars(select(Station).where(Station.is_active_record())).all()
    assert len(active_stations) == 1
    assert active_stations[0].code == "LHE"

    deleted_stations = db.session.scalars(select(Station).where(Station.is_deleted.is_(True))).all()
    assert len(deleted_stations) == 1
    assert deleted_stations[0].code == "KCH"


def test_partial_unique_index_allows_recreating_code(app):
    """
    Verify that partial unique index allows re-inserting the same station code
    once the previous record has been soft-deleted.
    """
    div = StationDivision(code="RWP", name="Rawalpindi Division", headquarters_city="Rawalpindi")
    db.session.add(div)
    db.session.commit()

    st1 = Station(
        division_id=div.id,
        code="ISB",
        name="Islamabad Station",
        city="Islamabad",
        province="Federal",
    )
    db.session.add(st1)
    db.session.commit()

    # Soft delete the initial station
    st1.soft_delete()
    db.session.commit()

    # Create new station with same code 'ISB'
    st2 = Station(
        division_id=div.id,
        code="ISB",
        name="Islamabad Modern Terminal",
        city="Islamabad",
        province="Federal",
    )
    db.session.add(st2)
    # Should commit successfully without unique constraint violation
    db.session.commit()

    assert st2.id is not None
    assert st2.code == "ISB"


def test_unique_constraint_user_roles_duplicate(app):
    """Verify unique constraint on (user_id, role_id) prevents duplicate role assignments."""
    user = User(
        email="operator@railsathi.pk",
        first_name="Zahid",
        last_name="Hussain",
        phone_number="03001112233",
        cnic="35201-1112233-1",
        password="Password123!",
    )
    role = Role(name="Station Master", code="STATION_MASTER", description="Platform controller")
    db.session.add_all([user, role])
    db.session.commit()

    ur1 = UserRole(user_id=user.id, role_id=role.id)
    db.session.add(ur1)
    db.session.commit()

    ur2 = UserRole(user_id=user.id, role_id=role.id)
    db.session.add(ur2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_unique_constraint_route_stop_sequence(app):
    """Verify unique constraint on (route_id, stop_sequence)."""
    div = StationDivision(code="MUL", name="Multan Division", headquarters_city="Multan")
    db.session.add(div)
    db.session.commit()

    s1 = Station(division_id=div.id, code="MUL1", name="Multan Cantt", city="Multan", province="Punjab")
    s2 = Station(division_id=div.id, code="MUL2", name="Khanewal", city="Khanewal", province="Punjab")
    s3 = Station(division_id=div.id, code="MUL3", name="Shorkot", city="Shorkot", province="Punjab")
    db.session.add_all([s1, s2, s3])
    db.session.commit()

    route = Route(code="R-MUL-01", name="Multan-Shorkot Route", source_station_id=s1.id, destination_station_id=s3.id)
    db.session.add(route)
    db.session.commit()

    rs1 = RouteStop(route_id=route.id, station_id=s1.id, stop_sequence=1, distance_from_origin_km=Decimal("0.0"))
    rs2 = RouteStop(route_id=route.id, station_id=s2.id, stop_sequence=1, distance_from_origin_km=Decimal("45.0"))
    db.session.add_all([rs1, rs2])

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_check_constraint_negative_fare(app):
    """Verify check constraint rejects negative base fares on FareRule."""
    cc = CoachClass(code="EC", name="Economy Class", base_fare_multiplier=Decimal("1.00"))
    db.session.add(cc)
    db.session.commit()

    bad_rule = FareRule(
        coach_class_id=cc.id,
        min_distance_km=Decimal("1.00"),
        max_distance_km=Decimal("50.00"),
        base_fare=Decimal("-150.00"),  # Negative fare violates check constraint
        rate_per_km=Decimal("1.50"),
    )
    db.session.add(bad_rule)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_check_constraint_station_facility_fee_negative(app):
    """Verify check constraint rejects negative fee on StationFacility."""
    div = StationDivision(code="PEW", name="Peshawar Division", headquarters_city="Peshawar")
    db.session.add(div)
    db.session.commit()

    st = Station(division_id=div.id, code="PEW1", name="Peshawar Cantt", city="Peshawar", province="KPK")
    cat = FacilityCategory(name="Executive Lounge")
    db.session.add_all([st, cat])
    db.session.commit()

    bad_fac = StationFacility(
        station_id=st.id,
        category_id=cat.id,
        name="VIP Lounge",
        is_free=False,
        fee_amount=Decimal("-50.00"),  # Negative fee violates check constraint
    )
    db.session.add(bad_fac)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_journey_instance_status_check_constraint(app):
    """Verify check constraint validates allowed status values on JourneyInstance."""
    div = StationDivision(code="SKZ", name="Sukkur Division", headquarters_city="Sukkur")
    db.session.add(div)
    db.session.commit()

    s1 = Station(division_id=div.id, code="ROH", name="Rohri Junction", city="Rohri", province="Sindh")
    s2 = Station(division_id=div.id, code="SKR", name="Sukkur Station", city="Sukkur", province="Sindh")
    tt = TrainType(name="Express Shuttle", code="SHUTTLE")
    db.session.add_all([s1, s2, tt])
    db.session.commit()

    train = Train(
        train_type_id=tt.id,
        train_number="101UP",
        name="Rohri Shuttle",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
    )
    route = Route(code="R-ROH-SKR", name="Rohri-Sukkur Branch", source_station_id=s1.id, destination_station_id=s2.id)
    db.session.add_all([train, route])
    db.session.commit()

    sched = Schedule(
        train_id=train.id,
        route_id=route.id,
        schedule_code="SCH-101UP-DAILY",
        departure_time=time(8, 0),
        arrival_time=time(9, 30),
    )
    db.session.add(sched)
    db.session.commit()

    # Valid status 'Scheduled' succeeds
    valid_journey = JourneyInstance(
        schedule_id=sched.id,
        journey_date=date(2026, 11, 25),
        status="Scheduled",
    )
    db.session.add(valid_journey)
    db.session.commit()
    assert valid_journey.id is not None

    # Invalid status violates check constraint
    invalid_journey = JourneyInstance(
        schedule_id=sched.id,
        journey_date=date(2026, 11, 26),
        status="FlyingPlane",  # Invalid status
    )
    db.session.add(invalid_journey)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

