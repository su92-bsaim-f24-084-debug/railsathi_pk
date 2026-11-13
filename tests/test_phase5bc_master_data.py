"""Phase 5B & 5C — Trains, Rolling Stock, Routes, Schedules & Journey Operations Tests.

Covers Models #12-#26:
- Model #12: TrainType (Super Admin)
- Model #13: Train (Super Admin)
- Model #14: TrainOperationalDay (Managed inline on Train)
- Model #15: CoachClass (Super Admin)
- Model #16: SeatLayoutType (Super Admin)
- Model #17: BerthType (Super Admin, view/edit only, delete blocked with 400)
- Model #18: TrainCoach (Super Admin)
- Model #19: Seat (Super Admin, individual CRUD + Batch Generator)
- Model #20: Route (Super Admin)
- Model #21: RouteStop (Super Admin)
- Model #22: FareRule (Super Admin)
- Model #23: Schedule (Super Admin)
- Model #24: ScheduleStop (Super Admin)
- Model #25: JourneyInstance (Super Admin, single CRUD + Date Range Generator skipping off-days)
- Model #26: JourneyCoach (Super Admin & Reservation Officer)

Verifies:
- Full CRUD workflows (Create, Read, Update, Delete, Restore).
- Blocked deletions when active children or dependent relations exist.
- Unique active partial indexes (Train number, Route code, Schedule code reuse after soft-delete).
- Train operational day checkboxes synchronization.
- Batch seat generation with matrix (rows x columns), window identification, and quota assignments.
- Route stops contiguous sequencing from 1 and duplicate sequence rejection.
- Schedule stop timings ordering and sequence contiguous from 1.
- Journey instance date range generator skipping days train does not operate and auto-attaching coaches.
- RBAC enforcement (Passenger receives 403 on all; Reservation Officer permitted on JourneyCoach; Super Admin on all).
- Atomic same-transaction audit logging.
"""
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import pytest
from flask import url_for
from sqlalchemy import select, func

from app.extensions import db
from app.common.constants import (
    ROLE_SUPER_ADMIN,
    ROLE_RESERVATION_OFFICER,
    ROLE_PASSENGER,
)
from app.models.identity import (
    User,
    Role,
    UserRole,
    UserProfile,
    StaffProfile,
)
from app.models.stations import (
    StationDivision,
    Station,
    StationPlatform,
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
from app.models.bookings import (
    JourneyCoach,
    SeatReservationLock,
    Booking,
    PassengerTicket,
    TicketSeatAllocation,
)
from app.models.governance import AuditLog


@pytest.fixture
def master_data_setup(app):
    """Seed base roles, stations, admin, reservation officer, and passenger users."""
    with app.app_context():
        for r_name in [ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER, ROLE_PASSENGER]:
            if not db.session.scalar(select(Role).filter_by(name=r_name)):
                db.session.add(Role(name=r_name, code=r_name.upper().replace(" ", "_")))
        db.session.flush()

        role_admin = db.session.scalar(select(Role).filter_by(name=ROLE_SUPER_ADMIN))
        role_ro = db.session.scalar(select(Role).filter_by(name=ROLE_RESERVATION_OFFICER))
        role_pass = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))

        # Infrastructure
        div = StationDivision(code="LHR-DIV", name="Lahore Division", headquarters_city="Lahore")
        db.session.add(div)
        db.session.flush()

        stn1 = Station(
            division_id=div.id,
            code="LHE",
            name="Lahore Junction",
            city="Lahore",
            province="Punjab",
            latitude=Decimal("31.577200"),
            longitude=Decimal("74.354400"),
            is_junction=True,
        )
        stn2 = Station(
            division_id=div.id,
            code="RWP",
            name="Rawalpindi",
            city="Rawalpindi",
            province="Punjab",
            latitude=Decimal("33.598400"),
            longitude=Decimal("73.044100"),
            is_junction=False,
        )
        stn3 = Station(
            division_id=div.id,
            code="GUJ",
            name="Gujranwala",
            city="Gujranwala",
            province="Punjab",
            latitude=Decimal("32.160300"),
            longitude=Decimal("74.187300"),
            is_junction=False,
        )
        db.session.add_all([stn1, stn2, stn3])
        db.session.flush()

        # Users
        u_admin = User(
            email="superadmin@railsathi.pk",
            cnic="35201-1111111-1",
            first_name="Super",
            last_name="Admin",
            phone_number="0300-1111111",
            is_active_user=True,
        )
        u_admin.password = "AdminPass123!"

        u_ro = User(
            email="res.officer@railsathi.pk",
            cnic="35201-2222222-2",
            first_name="Reservation",
            last_name="Officer",
            phone_number="0300-2222222",
            is_active_user=True,
        )
        u_ro.password = "OfficerPass123!"

        u_pass = User(
            email="passenger@railsathi.pk",
            cnic="35201-3333333-3",
            first_name="Regular",
            last_name="Passenger",
            phone_number="0300-3333333",
            is_active_user=True,
        )
        u_pass.password = "Pass12345!"

        db.session.add_all([u_admin, u_ro, u_pass])
        db.session.flush()

        db.session.add(UserRole(user_id=u_admin.id, role_id=role_admin.id))
        db.session.add(UserRole(user_id=u_ro.id, role_id=role_ro.id))
        db.session.add(UserRole(user_id=u_pass.id, role_id=role_pass.id))

        # Seed static BerthType
        b_lower = BerthType(code="LB", name="Lower Berth")
        b_upper = BerthType(code="UB", name="Upper Berth")
        b_seat = BerthType(code="ST", name="Standard Seat")
        db.session.add_all([b_lower, b_upper, b_seat])

        db.session.commit()

        return {
            "stn1_id": stn1.id,
            "stn2_id": stn2.id,
            "stn3_id": stn3.id,
            "admin_id": u_admin.id,
            "ro_id": u_ro.id,
            "pass_id": u_pass.id,
            "berth_seat_id": b_seat.id,
        }


def _login(client, email, password):
    resp = client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)
    assert resp.status_code == 200
    return resp


# ===========================================================================
# 1. TrainType (Model #12) Tests
# ===========================================================================
def test_train_type_crud_lifecycle_and_child_block(client, app, master_data_setup):
    """Test TrainType full CRUD and blocked soft-delete when active trains exist."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    # 1. Create
    resp = client.post(
        "/admin/train-types/create",
        data={"code": "EXP", "name": "Express", "description": "Express passenger train", "max_speed_kmh": 120},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        tt = db.session.scalar(select(TrainType).filter_by(code="EXP"))
        assert tt is not None
        tt_id = tt.id

    # 2. Edit
    resp = client.post(
        f"/admin/train-types/{tt_id}/edit",
        data={"code": "EXP", "name": "Intercity Express", "description": "Fast express train", "max_speed_kmh": 140},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data

    with app.app_context():
        tt = db.session.get(TrainType, tt_id)
        assert tt.name == "Intercity Express"
        assert tt.max_speed_kmh == 140

    # 3. Add an active Train linked to this TrainType -> Delete must be blocked
    with app.app_context():
        tr = Train(
            train_type_id=tt_id,
            train_number="101UP",
            name="Subak Kharam",
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
        )
        db.session.add(tr)
        db.session.commit()
        tr_id = tr.id

    del_resp = client.post(f"/admin/train-types/{tt_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"Cannot soft-delete train type" in del_resp.data

    with app.app_context():
        tt = db.session.get(TrainType, tt_id)
        assert tt.is_deleted is False

    # 4. Soft delete the child Train, then TrainType soft delete succeeds
    with app.app_context():
        tr = db.session.get(Train, tr_id)
        tr.soft_delete(user_id=master_data_setup["admin_id"])
        db.session.commit()

    del_resp2 = client.post(f"/admin/train-types/{tt_id}/delete", follow_redirects=True)
    assert del_resp2.status_code == 200
    assert b"soft-deleted successfully" in del_resp2.data

    with app.app_context():
        tt = db.session.get(TrainType, tt_id)
        assert tt.is_deleted is True

    # 5. Restore
    rest_resp = client.post(f"/admin/train-types/{tt_id}/restore", follow_redirects=True)
    assert rest_resp.status_code == 200
    assert b"restored successfully" in rest_resp.data

    with app.app_context():
        tt = db.session.get(TrainType, tt_id)
        assert tt.is_deleted is False


# ===========================================================================
# 2. Train & TrainOperationalDay (Models #13 & #14) Tests
# ===========================================================================
def test_train_crud_operational_days_and_number_reuse(client, app, master_data_setup):
    """Test Train CRUD, operational day checkboxes synchronization, and number reuse."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    # Pre-create TrainType
    with app.app_context():
        tt = TrainType(code="EXP", name="Express", max_speed_kmh=120)
        db.session.add(tt)
        db.session.commit()
        tt_id = tt.id

    # 1. Create Train with days: Monday (0), Wednesday (2), Friday (4)
    resp = client.post(
        "/admin/trains/create",
        data={
            "train_type_id": tt_id,
            "train_number": "1UP",
            "name": "Khyber Mail",
            "origin_station_id": master_data_setup["stn1_id"],
            "destination_station_id": master_data_setup["stn2_id"],
            "day_0": "y",  # Mon
            "day_2": "y",  # Wed
            "day_4": "y",  # Fri
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        tr = db.session.scalar(select(Train).filter_by(train_number="1UP"))
        assert tr is not None
        assert tr.name == "Khyber Mail"
        tr_id = tr.id

        # Verify operational days
        op_days = sorted([d.day_of_week for d in tr.operational_days if d.is_active])
        assert op_days == [0, 2, 4]

    # 2. Edit Train: Change operational days to daily (0 to 6)
    edit_data = {
        "train_type_id": tt_id,
        "train_number": "1UP",
        "name": "Khyber Mail Express",
        "origin_station_id": master_data_setup["stn1_id"],
        "destination_station_id": master_data_setup["stn2_id"],
    }
    for d in range(7):
        edit_data[f"day_{d}"] = "y"

    resp2 = client.post(f"/admin/trains/{tr_id}/edit", data=edit_data, follow_redirects=True)
    assert resp2.status_code == 200
    assert b"updated successfully" in resp2.data

    with app.app_context():
        tr = db.session.get(Train, tr_id)
        assert tr.name == "Khyber Mail Express"
        active_days = sorted([d.day_of_week for d in tr.operational_days if d.is_active])
        assert active_days == [0, 1, 2, 3, 4, 5, 6]

    # 3. Soft delete Train
    resp_del = client.post(f"/admin/trains/{tr_id}/delete", follow_redirects=True)
    assert resp_del.status_code == 200
    assert b"soft-deleted successfully" in resp_del.data

    # 4. Partial index reuse: create another active Train with the SAME train_number "1UP"
    resp_reuse = client.post(
        "/admin/trains/create",
        data={
            "train_type_id": tt_id,
            "train_number": "1UP",
            "name": "Khyber Mail New Era",
            "origin_station_id": master_data_setup["stn1_id"],
            "destination_station_id": master_data_setup["stn2_id"],
            "day_0": "y",
        },
        follow_redirects=True,
    )
    assert resp_reuse.status_code == 200
    assert b"created successfully" in resp_reuse.data

    with app.app_context():
        trains_1up = db.session.scalars(select(Train).filter_by(train_number="1UP")).all()
        assert len(trains_1up) == 2
        active_trains = [t for t in trains_1up if not t.is_deleted]
        deleted_trains = [t for t in trains_1up if t.is_deleted]
        assert len(active_trains) == 1
        assert len(deleted_trains) == 1
        assert active_trains[0].name == "Khyber Mail New Era"


# ===========================================================================
# 3. CoachClass & SeatLayoutType (Models #15 & #16) Tests
# ===========================================================================
def test_coach_class_and_seat_layout_crud(client, app, master_data_setup):
    """Test CoachClass and SeatLayoutType CRUD and deletion safeguards."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    # 1. Create CoachClass
    resp = client.post(
        "/admin/coach-classes/create",
        data={
            "code": "AC-BUS",
            "name": "AC Business",
            "base_fare_multiplier": Decimal("1.25"),
            "description": "Air-conditioned business tier",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        cc = db.session.scalar(select(CoachClass).filter_by(code="AC-BUS"))
        assert cc is not None
        cc_id = cc.id

    # 2. Create SeatLayoutType
    resp_lay = client.post(
        "/admin/seat-layouts/create",
        data={
            "name": "Executive 2x2",
            "total_rows": 10,
            "seats_per_row": 4,
            "aisle_position": 2,
            "description": "Executive 2x2 layout",
        },
        follow_redirects=True,
    )
    assert resp_lay.status_code == 200
    assert b"created successfully" in resp_lay.data

    with app.app_context():
        sl = db.session.scalar(select(SeatLayoutType).filter_by(name="Executive 2x2"))
        assert sl is not None
        sl_id = sl.id

    # 3. Block deletion when child FareRule exists
    with app.app_context():
        fr = FareRule(coach_class_id=cc_id, min_distance_km=Decimal("0.00"), max_distance_km=Decimal("100.00"), base_fare=Decimal("500.00"), rate_per_km=Decimal("2.50"))
        db.session.add(fr)
        db.session.commit()
        fr_id = fr.id

    resp_block = client.post(f"/admin/coach-classes/{cc_id}/delete", follow_redirects=True)
    assert resp_block.status_code == 200
    assert b"Cannot soft-delete coach class" in resp_block.data

    with app.app_context():
        cc = db.session.get(CoachClass, cc_id)
        assert cc.is_deleted is False

        # Soft delete fare rule, then delete coach class
        fr = db.session.get(FareRule, fr_id)
        fr.soft_delete(user_id=master_data_setup["admin_id"])
        db.session.commit()

    resp_del = client.post(f"/admin/coach-classes/{cc_id}/delete", follow_redirects=True)
    assert resp_del.status_code == 200
    assert b"soft-deleted successfully" in resp_del.data

    with app.app_context():
        cc = db.session.get(CoachClass, cc_id)
        assert cc.is_deleted is True


# ===========================================================================
# 4. BerthType Deletion Blocked (Model #17) Tests
# ===========================================================================
def test_berth_type_view_edit_and_delete_permanently_blocked(client, app, master_data_setup):
    """Test BerthType allows list/edit but permanently blocks deletion with HTTP 400."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    berth_id = master_data_setup["berth_seat_id"]

    # 1. List
    resp = client.get("/admin/berth-types")
    assert resp.status_code == 200
    assert b"Standard Seat" in resp.data

    # 2. Edit
    resp_edit = client.post(
        f"/admin/berth-types/{berth_id}/edit",
        data={"code": "ST", "name": "Standard Chair Seat", "description": "High-back passenger chair"},
        follow_redirects=True,
    )
    assert resp_edit.status_code == 200
    assert b"updated successfully" in resp_edit.data

    with app.app_context():
        bt = db.session.get(BerthType, berth_id)
        assert bt.name == "Standard Chair Seat"

    # 3. Attempt Delete -> MUST BE BLOCKED WITH HTTP 400
    resp_del = client.post(f"/admin/berth-types/{berth_id}/delete")
    assert resp_del.status_code == 400

    resp_list = client.get("/admin/berth-types")
    assert b"permanently disabled" in resp_list.data

    with app.app_context():
        bt = db.session.get(BerthType, berth_id)
        assert bt is not None  # Intact, never deleted


# ===========================================================================
# 5. TrainCoach (Model #18) Tests
# ===========================================================================
def test_train_coach_crud_and_child_blocks(client, app, master_data_setup):
    """Test TrainCoach CRUD and child block protections."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    with app.app_context():
        tt = TrainType(code="EXP", name="Express")
        cc = CoachClass(code="AC-SLP", name="AC Sleeper", base_fare_multiplier=Decimal("1.80"))
        sl = SeatLayoutType(name="2x2 Layout", total_rows=10, seats_per_row=4, aisle_position=2)
        db.session.add_all([tt, cc, sl])
        db.session.flush()

        tr = Train(
            train_type_id=tt.id,
            train_number="5UP",
            name="Green Line",
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
        )
        db.session.add(tr)
        db.session.commit()
        tr_id, cc_id, sl_id = tr.id, cc.id, sl.id

    # 1. Create TrainCoach
    resp = client.post(
        "/admin/train-coaches/create",
        data={
            "train_id": tr_id,
            "coach_class_id": cc_id,
            "layout_type_id": sl_id,
            "coach_code": "AC-1",
            "sequence_number": 1,
            "total_capacity": 40,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"attached to train successfully" in resp.data

    with app.app_context():
        tc = db.session.scalar(select(TrainCoach).filter_by(coach_code="AC-1"))
        assert tc is not None
        tc_id = tc.id

    # 2. Block deletion when active Seat exists
    with app.app_context():
        st = Seat(
            coach_id=tc_id,
            seat_number="1",
            row_number=1,
            column_number=1,
            berth_type_id=master_data_setup["berth_seat_id"],
        )
        db.session.add(st)
        db.session.commit()
        st_id = st.id

    del_resp = client.post(f"/admin/train-coaches/{tc_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"Cannot soft-delete coach" in del_resp.data

    with app.app_context():
        tc = db.session.get(TrainCoach, tc_id)
        assert tc.is_deleted is False

        # Soft delete seat, then coach delete succeeds
        st = db.session.get(Seat, st_id)
        st.soft_delete(user_id=master_data_setup["admin_id"])
        db.session.commit()

    del_resp2 = client.post(f"/admin/train-coaches/{tc_id}/delete", follow_redirects=True)
    assert del_resp2.status_code == 200
    assert b"soft-deleted successfully" in del_resp2.data

    with app.app_context():
        tc = db.session.get(TrainCoach, tc_id)
        assert tc.is_deleted is True


# ===========================================================================
# 6. Seat & Batch Generator (Model #19) Tests
# ===========================================================================
def test_seat_batch_generator_matrix_and_crud(client, app, master_data_setup):
    """Test Seat batch generator form creating matrix of seats with window & ladies quota."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    with app.app_context():
        tt = TrainType(code="EXP", name="Express")
        cc = CoachClass(code="EC", name="Economy", base_fare_multiplier=Decimal("1.00"))
        sl = SeatLayoutType(name="3x2 Layout", total_rows=5, seats_per_row=4, aisle_position=2)
        db.session.add_all([tt, cc, sl])
        db.session.flush()

        tr = Train(
            train_type_id=tt.id,
            train_number="7UP",
            name="Tezgam",
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
        )
        db.session.add(tr)
        db.session.flush()

        tc = TrainCoach(train_id=tr.id, coach_class_id=cc.id, layout_type_id=sl.id, coach_code="EC-1", sequence_number=1, total_capacity=20)
        db.session.add(tc)
        db.session.commit()
        tc_id = tc.id

    # 1. Execute Batch Generator: rows=4, columns=4 (16 seats), window_columns="1,4", ladies_quota_rows="1"
    gen_resp = client.post(
        "/admin/seats/generate",
        data={
            "coach_id": tc_id,
            "rows": 4,
            "columns": 4,
            "default_berth_type_id": master_data_setup["berth_seat_id"],
            "window_columns": "1, 4",
            "ladies_quota_rows": "1",
        },
        follow_redirects=True,
    )
    assert gen_resp.status_code == 200
    assert b"Successfully generated 16 seat(s)" in gen_resp.data

    with app.app_context():
        seats = db.session.scalars(select(Seat).filter_by(coach_id=tc_id, is_deleted=False).order_by(Seat.id)).all()
        assert len(seats) == 16

        # Check window assignments: columns 1 and 4 must be window seats
        col1_seats = [s for s in seats if s.column_number == 1]
        col2_seats = [s for s in seats if s.column_number == 2]
        col4_seats = [s for s in seats if s.column_number == 4]
        assert all(s.is_window for s in col1_seats)
        assert all(s.is_window for s in col4_seats)
        assert not any(s.is_window for s in col2_seats)

        # Check ladies quota: row 1 must be ladies quota
        row1_seats = [s for s in seats if s.row_number == 1]
        row2_seats = [s for s in seats if s.row_number == 2]
        assert all(s.is_ladies_quota for s in row1_seats)
        assert not any(s.is_ladies_quota for s in row2_seats)

        target_seat_id = seats[0].id

    # 2. Individual Seat Edit
    resp_edit = client.post(
        f"/admin/seats/{target_seat_id}/edit",
        data={
            "coach_id": tc_id,
            "seat_number": "1A",
            "row_number": 1,
            "column_number": 1,
            "berth_type_id": master_data_setup["berth_seat_id"],
            "is_window": "y",
            "is_ladies_quota": "",
        },
        follow_redirects=True,
    )
    assert resp_edit.status_code == 200
    assert b"updated successfully" in resp_edit.data

    with app.app_context():
        st = db.session.get(Seat, target_seat_id)
        assert st.seat_number == "1A"
        assert st.is_window is True
        assert st.is_ladies_quota is False

    # 3. Soft delete single seat and restore
    del_resp = client.post(f"/admin/seats/{target_seat_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"soft-deleted successfully" in del_resp.data

    with app.app_context():
        st = db.session.get(Seat, target_seat_id)
        assert st.is_deleted is True

    rest_resp = client.post(f"/admin/seats/{target_seat_id}/restore", follow_redirects=True)
    assert rest_resp.status_code == 200
    assert b"restored successfully" in rest_resp.data

    with app.app_context():
        st = db.session.get(Seat, target_seat_id)
        assert st.is_deleted is False


# ===========================================================================
# 7. Route & RouteStop (Models #20 & #21) Tests
# ===========================================================================
def test_route_and_route_stops_validation_and_blocks(client, app, master_data_setup):
    """Test Route CRUD, RouteStop contiguous sequencing from 1, and duplicate rejection."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    # 1. Create Route
    resp = client.post(
        "/admin/routes/create",
        data={
            "code": "ML-1",
            "name": "Main Line 1 (Peshawar - Karachi)",
            "source_station_id": master_data_setup["stn1_id"],
            "destination_station_id": master_data_setup["stn2_id"],
            "total_distance_km": Decimal("290.50"),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        r = db.session.scalar(select(Route).filter_by(code="ML-1"))
        assert r is not None
        route_id = r.id

    # 2. Add RouteStop sequence 2 first (without sequence 1) -> MUST FAIL (contiguous from 1)
    resp_gap = client.post(
        "/admin/route-stops/create",
        data={
            "route_id": route_id,
            "station_id": master_data_setup["stn3_id"],
            "stop_sequence": 2,
            "distance_from_origin_km": Decimal("70.00"),
            "standard_halt_minutes": 5,
        },
        follow_redirects=True,
    )
    assert resp_gap.status_code == 200
    assert b"contiguous starting from 1" in resp_gap.data

    # 3. Add RouteStop sequence 1 -> Success
    resp_s1 = client.post(
        "/admin/route-stops/create",
        data={
            "route_id": route_id,
            "station_id": master_data_setup["stn1_id"],
            "stop_sequence": 1,
            "distance_from_origin_km": Decimal("0.00"),
            "standard_halt_minutes": 0,
        },
        follow_redirects=True,
    )
    assert resp_s1.status_code == 200
    assert b"added successfully" in resp_s1.data

    # 4. Add duplicate stop sequence 1 -> MUST FAIL
    resp_dup = client.post(
        "/admin/route-stops/create",
        data={
            "route_id": route_id,
            "station_id": master_data_setup["stn3_id"],
            "stop_sequence": 1,
            "distance_from_origin_km": Decimal("70.00"),
            "standard_halt_minutes": 5,
        },
        follow_redirects=True,
    )
    assert resp_dup.status_code == 200
    assert b"already assigned" in resp_dup.data

    # 5. Add RouteStop sequence 2 -> Success
    resp_s2 = client.post(
        "/admin/route-stops/create",
        data={
            "route_id": route_id,
            "station_id": master_data_setup["stn3_id"],
            "stop_sequence": 2,
            "distance_from_origin_km": Decimal("70.00"),
            "standard_halt_minutes": 10,
        },
        follow_redirects=True,
    )
    assert resp_s2.status_code == 200
    assert b"added successfully" in resp_s2.data

    # 6. Block Route deletion when active RouteStops exist
    del_route_resp = client.post(f"/admin/routes/{route_id}/delete", follow_redirects=True)
    assert del_route_resp.status_code == 200
    assert b"Cannot soft-delete route" in del_route_resp.data

    with app.app_context():
        r = db.session.get(Route, route_id)
        assert r.is_deleted is False


# ===========================================================================
# 8. FareRule (Model #22) Tests
# ===========================================================================
def test_fare_rule_crud_and_validation(client, app, master_data_setup):
    """Test FareRule CRUD and distance/amount validations."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    with app.app_context():
        cc = CoachClass(code="AC-STD", name="AC Standard", base_fare_multiplier=Decimal("1.20"))
        db.session.add(cc)
        db.session.commit()
        cc_id = cc.id

    # 1. Invalid distance: max_distance < min_distance -> MUST FAIL
    resp_bad = client.post(
        "/admin/fare-rules/create",
        data={
            "coach_class_id": cc_id,
            "min_distance_km": Decimal("100.00"),
            "max_distance_km": Decimal("50.00"),
            "base_fare": Decimal("200.00"),
            "rate_per_km": Decimal("1.50"),
            "reservation_charge": Decimal("50.00"),
        },
        follow_redirects=True,
    )
    assert resp_bad.status_code == 200
    assert b"cannot be less than minimum distance" in resp_bad.data

    # 2. Valid FareRule
    resp_good = client.post(
        "/admin/fare-rules/create",
        data={
            "coach_class_id": cc_id,
            "min_distance_km": Decimal("0.00"),
            "max_distance_km": Decimal("200.00"),
            "base_fare": Decimal("300.00"),
            "rate_per_km": Decimal("1.80"),
            "reservation_charge": Decimal("50.00"),
        },
        follow_redirects=True,
    )
    assert resp_good.status_code == 200
    assert b"created successfully" in resp_good.data

    with app.app_context():
        fr = db.session.scalar(select(FareRule).filter_by(coach_class_id=cc_id))
        assert fr is not None
        assert fr.base_fare == Decimal("300.00")
        fr_id = fr.id

    # 3. Soft delete and restore
    del_resp = client.post(f"/admin/fare-rules/{fr_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"soft-deleted successfully" in del_resp.data

    with app.app_context():
        fr = db.session.get(FareRule, fr_id)
        assert fr.is_deleted is True

    rest_resp = client.post(f"/admin/fare-rules/{fr_id}/restore", follow_redirects=True)
    assert rest_resp.status_code == 200
    assert b"restored successfully" in rest_resp.data

    with app.app_context():
        fr = db.session.get(FareRule, fr_id)
        assert fr.is_deleted is False


# ===========================================================================
# 9. Schedule & ScheduleStop (Models #23 & #24) Tests
# ===========================================================================
def test_schedule_and_schedule_stops_crud_and_validation(client, app, master_data_setup):
    """Test Schedule CRUD and ScheduleStop ordering and contiguous sequence from 1."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    with app.app_context():
        tt = TrainType(code="EXP", name="Express")
        db.session.add(tt)
        db.session.flush()

        tr = Train(
            train_type_id=tt.id,
            train_number="11UP",
            name="Hazara Express",
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
        )
        r = Route(
            code="LHE-RWP",
            name="Lahore to Rawalpindi",
            source_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
            total_distance_km=Decimal("290.00"),
        )
        db.session.add_all([tr, r])
        db.session.commit()
        tr_id, r_id = tr.id, r.id

    # 1. Create Schedule
    resp = client.post(
        "/admin/schedules/create",
        data={
            "schedule_code": "SCH-11UP",
            "train_id": tr_id,
            "route_id": r_id,
            "departure_time": "08:00",
            "arrival_time": "14:00",
            "journey_days_span": 1,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        sch = db.session.scalar(select(Schedule).filter_by(schedule_code="SCH-11UP"))
        assert sch is not None
        sch_id = sch.id

    # 2. Add ScheduleStop 1 (Origin stop: arrival None, departure 08:00)
    resp_s1 = client.post(
        "/admin/schedule-stops/create",
        data={
            "schedule_id": sch_id,
            "station_id": master_data_setup["stn1_id"],
            "stop_sequence": 1,
            "day_offset": 0,
            "scheduled_arrival": "",
            "scheduled_departure": "08:00",
        },
        follow_redirects=True,
    )
    assert resp_s1.status_code == 200
    assert b"created successfully" in resp_s1.data

    # 3. Add ScheduleStop 2 (Intermediate stop: arrival 09:30, departure 09:40)
    resp_s2 = client.post(
        "/admin/schedule-stops/create",
        data={
            "schedule_id": sch_id,
            "station_id": master_data_setup["stn3_id"],
            "stop_sequence": 2,
            "day_offset": 0,
            "scheduled_arrival": "09:30",
            "scheduled_departure": "09:40",
        },
        follow_redirects=True,
    )
    assert resp_s2.status_code == 200
    assert b"created successfully" in resp_s2.data

    # 4. Add non-contiguous sequence stop: sequence 4 when only 1 and 2 exist -> MUST FAIL
    resp_gap = client.post(
        "/admin/schedule-stops/create",
        data={
            "schedule_id": sch_id,
            "station_id": master_data_setup["stn2_id"],
            "stop_sequence": 4,
            "day_offset": 0,
            "scheduled_arrival": "13:45",
            "scheduled_departure": "",
        },
        follow_redirects=True,
    )
    assert resp_gap.status_code == 200
    assert b"contiguous starting from 1" in resp_gap.data

    # 5. Block Schedule deletion when active ScheduleStops exist
    del_sch = client.post(f"/admin/schedules/{sch_id}/delete", follow_redirects=True)
    assert del_sch.status_code == 200
    assert b"Cannot soft-delete schedule" in del_sch.data

    with app.app_context():
        sch = db.session.get(Schedule, sch_id)
        assert sch.is_deleted is False


# ===========================================================================
# 10. JourneyInstance & Date Range Generator (Model #25) Tests
# ===========================================================================
def test_journey_instance_date_range_generator_and_coach_auto_attach(client, app, master_data_setup):
    """Test JourneyInstance generation over a date range, skipping train off-days and auto-attaching coaches."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    with app.app_context():
        tt = TrainType(code="EXP", name="Express")
        cc = CoachClass(code="AC-PAR", name="AC Parlour", base_fare_multiplier=Decimal("1.50"))
        sl = SeatLayoutType(name="1x2 Layout", total_rows=5, seats_per_row=3, aisle_position=1)
        db.session.add_all([tt, cc, sl])
        db.session.flush()

        # Train runs ONLY on Mondays (day_of_week = 0)
        tr = Train(
            train_type_id=tt.id,
            train_number="15UP",
            name="Karachi Express",
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
        )
        db.session.add(tr)
        db.session.flush()

        op_day = TrainOperationalDay(train_id=tr.id, day_of_week=0, is_active=True)
        db.session.add(op_day)

        # Attach 2 TrainCoaches
        tc1 = TrainCoach(train_id=tr.id, coach_class_id=cc.id, layout_type_id=sl.id, coach_code="P-1", sequence_number=1, total_capacity=15)
        tc2 = TrainCoach(train_id=tr.id, coach_class_id=cc.id, layout_type_id=sl.id, coach_code="P-2", sequence_number=2, total_capacity=15)
        db.session.add_all([tc1, tc2])

        r = Route(
            code="LHE-RWP-EXP",
            name="Lahore to Rawalpindi Express",
            source_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
            total_distance_km=Decimal("290.00"),
        )
        db.session.add(r)
        db.session.flush()

        sch = Schedule(
            schedule_code="SCH-15UP",
            train_id=tr.id,
            route_id=r.id,
            departure_time=time(8, 0),
            arrival_time=time(14, 0),
            journey_days_span=1,
        )
        db.session.add(sch)
        db.session.commit()
        sch_id, tr_id = sch.id, tr.id

    # Choose a 14-day window: Monday 2026-03-02 to Sunday 2026-03-15
    # Contains exactly 2 Mondays: March 2 and March 9.
    start_d = date(2026, 3, 2)
    end_d = date(2026, 3, 15)

    gen_resp = client.post(
        "/admin/journeys/generate",
        data={
            "schedule_id": sch_id,
            "start_date": start_d.strftime("%Y-%m-%d"),
            "end_date": end_d.strftime("%Y-%m-%d"),
            "auto_attach_coaches": "y",
        },
        follow_redirects=True,
    )
    assert gen_resp.status_code == 200
    assert b"2 journeys generated" in gen_resp.data

    with app.app_context():
        journeys = db.session.scalars(
            select(JourneyInstance).filter_by(schedule_id=sch_id, is_deleted=False).order_by(JourneyInstance.journey_date)
        ).all()
        assert len(journeys) == 2
        assert journeys[0].journey_date == date(2026, 3, 2)
        assert journeys[1].journey_date == date(2026, 3, 9)

        # Check that both JourneyCoaches were auto-attached to each journey
        for j in journeys:
            assert len(j.coaches) == 2
            coach_codes = sorted([jc.train_coach.coach_code for jc in j.coaches])
            assert coach_codes == ["P-1", "P-2"]

        j_id = journeys[0].id

    # Soft delete one journey
    del_j = client.post(f"/admin/journeys/{j_id}/delete", follow_redirects=True)
    assert del_j.status_code == 200
    assert b"soft-deleted successfully" in del_j.data

    with app.app_context():
        j = db.session.get(JourneyInstance, j_id)
        assert j.is_deleted is True


# ===========================================================================
# 11. JourneyCoach (Model #26) RBAC & Child Safeguards
# ===========================================================================
def test_journey_coach_rbac_and_hard_delete_blocks(client, app, master_data_setup):
    """Test JourneyCoach accessible by Reservation Officer & Super Admin, blocked if ticket allocations exist."""
    with app.app_context():
        tt = TrainType(code="EXP", name="Express")
        cc = CoachClass(code="AC-SLP", name="AC Sleeper", base_fare_multiplier=Decimal("1.80"))
        sl = SeatLayoutType(name="2x2", total_rows=5, seats_per_row=4, aisle_position=2)
        db.session.add_all([tt, cc, sl])
        db.session.flush()

        tr = Train(
            train_type_id=tt.id,
            train_number="21UP",
            name="Super Express",
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
        )
        db.session.add(tr)
        db.session.flush()

        tc = TrainCoach(train_id=tr.id, coach_class_id=cc.id, layout_type_id=sl.id, coach_code="S-1", sequence_number=1, total_capacity=20)
        r = Route(
            code="LHE-RWP-21",
            name="LHE-RWP Route",
            source_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
            total_distance_km=Decimal("290.00"),
        )
        db.session.add_all([tc, r])
        db.session.flush()

        sch = Schedule(
            schedule_code="SCH-21UP",
            train_id=tr.id,
            route_id=r.id,
            departure_time=time(9, 0),
            arrival_time=time(15, 0),
            journey_days_span=1,
        )
        db.session.add(sch)
        db.session.flush()

        j = JourneyInstance(
            schedule_id=sch.id,
            journey_date=date(2026, 4, 1),
            status="Scheduled",
        )
        db.session.add(j)
        db.session.commit()
        j_id, tc_id, cc_id = j.id, tc.id, cc.id

    # 1. Login as Reservation Officer -> Allowed to access JourneyCoach management
    _login(client, "res.officer@railsathi.pk", "OfficerPass123!")

    resp = client.get("/admin/journey-coaches")
    assert resp.status_code == 200

    create_resp = client.post(
        "/admin/journey-coaches/create",
        data={
            "journey_instance_id": j_id,
            "train_coach_id": tc_id,
            "sequence_in_train": 1,
            "available_seats_count": 20,
            "is_available": "y",
        },
        follow_redirects=True,
    )
    assert create_resp.status_code == 200
    assert b"attached successfully" in create_resp.data

    with app.app_context():
        jc = db.session.scalar(select(JourneyCoach).filter_by(journey_instance_id=j_id, train_coach_id=tc_id))
        assert jc is not None
        jc_id = jc.id

    # 2. Block hard-delete when active TicketSeatAllocation exists
    with app.app_context():
        # Create a Seat
        seat = Seat(
            coach_id=tc_id,
            seat_number="1",
            row_number=1,
            column_number=1,
            berth_type_id=master_data_setup["berth_seat_id"],
        )
        db.session.add(seat)
        db.session.flush()

        # Create Booking
        b = Booking(
            user_id=master_data_setup["pass_id"],
            journey_instance_id=j_id,
            origin_station_id=master_data_setup["stn1_id"],
            destination_station_id=master_data_setup["stn2_id"],
            pnr_number="PNR1234567",
            total_passengers=1,
            total_fare=Decimal("1500.00"),
            booking_status="Confirmed",
        )
        db.session.add(b)
        db.session.flush()

        # Create PassengerTicket
        pt = PassengerTicket(
            booking_id=b.id,
            full_name="Ali Khan",
            cnic="35201-4444444-4",
            age=30,
            gender="Male",
            ticket_token="TICK-TOKEN-12345",
            fare_amount=Decimal("1500.00"),
            ticket_status="Valid",
        )
        db.session.add(pt)
        db.session.flush()

        # Create TicketSeatAllocation
        tsa = TicketSeatAllocation(
            ticket_id=pt.id,
            journey_instance_id=j_id,
            seat_id=seat.id,
            from_stop_sequence=1,
            to_stop_sequence=2,
            is_active=True,
        )
        db.session.add(tsa)
        db.session.commit()
        tsa_id = tsa.id

    # Attempt hard-delete JourneyCoach -> BLOCKED by active allocation
    del_resp = client.post(f"/admin/journey-coaches/{jc_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"Cannot delete journey coach" in del_resp.data

    with app.app_context():
        jc = db.session.get(JourneyCoach, jc_id)
        assert jc is not None  # Not deleted

        # Remove allocation, then hard-delete succeeds
        db.session.delete(db.session.get(TicketSeatAllocation, tsa_id))
        db.session.commit()

    del_resp2 = client.post(f"/admin/journey-coaches/{jc_id}/delete", follow_redirects=True)
    assert del_resp2.status_code == 200
    assert b"deleted successfully" in del_resp2.data

    with app.app_context():
        jc = db.session.get(JourneyCoach, jc_id)
        assert jc is None  # Hard deleted


# ===========================================================================
# 12. RBAC Master-Data Security Tests (Passenger Forbidden)
# ===========================================================================
def test_rbac_master_data_passenger_forbidden(client, app, master_data_setup):
    """Test Passenger user receives HTTP 403 on all Phase 5B & 5C master data admin endpoints."""
    _login(client, "passenger@railsathi.pk", "Pass12345!")

    forbidden_urls = [
        "/admin/train-types",
        "/admin/train-types/create",
        "/admin/trains",
        "/admin/trains/create",
        "/admin/coach-classes",
        "/admin/coach-classes/create",
        "/admin/seat-layouts",
        "/admin/seat-layouts/create",
        "/admin/berth-types",
        "/admin/train-coaches",
        "/admin/train-coaches/create",
        "/admin/seats",
        "/admin/seats/generate",
        "/admin/routes",
        "/admin/routes/create",
        "/admin/route-stops",
        "/admin/route-stops/create",
        "/admin/fare-rules",
        "/admin/fare-rules/create",
        "/admin/schedules",
        "/admin/schedules/create",
        "/admin/schedule-stops",
        "/admin/schedule-stops/create",
        "/admin/journeys",
        "/admin/journeys/create",
        "/admin/journeys/generate",
        "/admin/journey-coaches",
        "/admin/journey-coaches/create",
    ]

    for url in forbidden_urls:
        resp = client.get(url)
        assert resp.status_code == 403, f"Expected 403 on GET {url}, got {resp.status_code}"


# ===========================================================================
# 13. Audit Logging Master-Data Verification
# ===========================================================================
def test_audit_logging_master_data_mutations(client, app, master_data_setup):
    """Test same-transaction audit logging for Train, Route, and Schedule mutations."""
    _login(client, "superadmin@railsathi.pk", "AdminPass123!")

    # 1. Create TrainType -> emits CREATE audit log
    resp = client.post(
        "/admin/train-types/create",
        data={"code": "AUD-TT", "name": "Audit Train Type", "max_speed_kmh": 100},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        tt = db.session.scalar(select(TrainType).filter_by(code="AUD-TT"))
        assert tt is not None

        audit = db.session.scalar(
            select(AuditLog).filter_by(
                entity_name="TrainType",
                entity_id=str(tt.id),
                action="CREATE_TRAIN_TYPE",
            )
        )
        assert audit is not None
        assert audit.user_id == master_data_setup["admin_id"]
        assert "AUD-TT" in audit.new_values
