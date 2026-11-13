"""PostgreSQL-specific concurrency and constraint tests for RailSathi PK.

Verifies:
1. SELECT FOR UPDATE row locking across two concurrent database sessions.
2. PostgreSQL partial unique index enforcement allowing re-creation after soft deletion.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, IntegrityError

from app.extensions import db
from app.models.identity import User
from app.models.stations import StationDivision, Station
from app.models.trains import TrainType, Train, CoachClass, SeatLayoutType, BerthType, TrainCoach, Seat
from app.models.routes import Route
from app.models.schedules import Schedule, JourneyInstance
from app.models.bookings import SeatReservationLock


def test_select_for_update_row_locking_two_sessions(app):
    """Verify SELECT FOR UPDATE row locking on seats blocks a second session in PostgreSQL."""
    # Setup test data: create coach hierarchy and a target seat
    div = StationDivision(code="LHR-LK", name="Lahore Division", headquarters_city="Lahore")
    db.session.add(div)
    db.session.flush()

    st1 = Station(division_id=div.id, code="LK1", name="Lock Station 1", city="Lahore", province="Punjab")
    st2 = Station(division_id=div.id, code="LK2", name="Lock Station 2", city="Rawalpindi", province="Punjab")
    ttype = TrainType(code="LK-EXP", name="Lock Express")
    cclass = CoachClass(code="LK-CC", name="Lock Class")
    layout = SeatLayoutType(name="Lock Layout", total_rows=10, seats_per_row=4, aisle_position=2)
    berth = BerthType(code="LK-B", name="Lock Berth")
    db.session.add_all([st1, st2, ttype, cclass, layout, berth])
    db.session.flush()

    train = Train(train_type_id=ttype.id, train_number="LK-99", name="Lock Express", origin_station_id=st1.id, destination_station_id=st2.id)
    db.session.add(train)
    db.session.flush()

    coach = TrainCoach(train_id=train.id, coach_class_id=cclass.id, layout_type_id=layout.id, coach_code="LK-1", sequence_number=1, total_capacity=30)
    db.session.add(coach)
    db.session.flush()

    seat = Seat(coach_id=coach.id, berth_type_id=berth.id, seat_number="1A", row_number=1, column_number=1)
    db.session.add(seat)
    db.session.commit()

    target_seat_id = seat.id
    engine = db.engine

    # Open Session 1 and Session 2 directly against the database engine
    session1 = Session(bind=engine)
    session2 = Session(bind=engine)

    try:
        # Session 1 acquires exclusive row lock on seats using SELECT FOR UPDATE
        locked_seat = session1.execute(
            select(Seat).filter_by(id=target_seat_id).with_for_update()
        ).scalar_one()
        assert locked_seat.id == target_seat_id

        # Session 2 attempts to acquire lock on the SAME seat row with NOWAIT
        # In PostgreSQL, this must raise OperationalError ("could not obtain lock on row")
        with pytest.raises(OperationalError) as exc_info:
            session2.execute(
                select(Seat).filter_by(id=target_seat_id).with_for_update(nowait=True)
            ).scalar_one()

        assert "could not obtain lock" in str(exc_info.value).lower() or "lock" in str(exc_info.value).lower()

    finally:
        session1.rollback()
        session1.close()
        session2.rollback()
        session2.close()


def test_postgresql_partial_unique_index_recreate_after_soft_delete(app):
    """Verify that PostgreSQL partial unique index allows reusing unique code after soft-delete."""
    div = StationDivision(code="PUI-DIV", name="Lahore Div PUI", headquarters_city="Lahore")
    db.session.add(div)
    db.session.flush()

    # Step 1: Create first active station with code 'PUI-STN'
    st1 = Station(
        division_id=div.id,
        code="PUI-STN",
        name="PUI Station First",
        city="Lahore",
        province="Punjab",
    )
    db.session.add(st1)
    db.session.commit()
    assert st1.id is not None
    assert st1.is_deleted is False

    # Step 2: Attempting to create duplicate active station with same code must fail
    st_dup = Station(
        division_id=div.id,
        code="PUI-STN",
        name="PUI Station Duplicate",
        city="Lahore",
        province="Punjab",
    )
    db.session.add(st_dup)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    # Step 3: Soft-delete the first station
    st1_refreshed = db.session.scalar(select(Station).filter_by(code="PUI-STN"))
    st1_refreshed.soft_delete(user_id=None)
    db.session.commit()
    assert st1_refreshed.is_deleted is True

    # Step 4: Create a new active station with the EXACT same code 'PUI-STN'
    # PostgreSQL partial index (WHERE is_deleted = false) must allow this
    st2 = Station(
        division_id=div.id,
        code="PUI-STN",
        name="PUI Station Recreated",
        city="Lahore",
        province="Punjab",
    )
    db.session.add(st2)
    db.session.commit()
    assert st2.id is not None
    assert st2.is_deleted is False
    assert st2.id != st1_refreshed.id

    # Step 5: Trying to add another active one fails again
    st3 = Station(
        division_id=div.id,
        code="PUI-STN",
        name="PUI Station Third",
        city="Lahore",
        province="Punjab",
    )
    db.session.add(st3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

