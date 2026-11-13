"""Tests for Models #26 through #50 and database seeding in RailSathi PK."""

import pytest
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.common.pnr import generate_pnr, generate_ticket_token
from app.seed import seed_all
from app.models.identity import User, Role
from app.models.stations import StationDivision, Station
from app.models.trains import TrainType, Train, CoachClass, SeatLayoutType, BerthType, TrainCoach, Seat
from app.models.routes import Route, RouteStop
from app.models.schedules import Schedule, ScheduleStop, JourneyInstance
from app.models.bookings import (
    JourneyCoach,
    SeatReservationLock,
    Booking,
    PassengerTicket,
    TicketSeatAllocation,
    BookingStatusHistory,
)
from app.models.payments import PaymentMethod, PaymentTransaction, RefundRequest, RefundAuditTrail
from app.models.operations import TrainDelayLog, JourneyStationActual, ServiceAlert
from app.models.complaints import ComplaintCategory, Complaint, ComplaintTimeline, FeedbackRating
from app.models.lost_found import LostFoundCategory, LostFoundReport, LostFoundClaim
from app.models.services import AssistanceType, SpecialAssistanceRequest
from app.models.governance import NotificationTemplate, Notification, AuditLog


@pytest.fixture
def base_journey_setup(app):
    """Fixture providing foundational objects (User, Stations, Train, Coach, Seat, Schedule, Journey)."""
    # 1. User
    user = User(
        email="passenger1@railsathi.pk",
        first_name="Ahmed",
        last_name="Khan",
        phone_number="+923001112233",
        cnic="35201-1112233-1",
        is_active_user=True,
    )
    user.password = "Secret123!"
    db.session.add(user)

    # 2. Division & Stations
    div = StationDivision(code="LHR", name="Lahore Division", headquarters_city="Lahore")
    db.session.add(div)
    db.session.flush()

    st1 = Station(division_id=div.id, code="LHE", name="Lahore Jn", city="Lahore", province="Punjab")
    st2 = Station(division_id=div.id, code="RWP", name="Rawalpindi", city="Rawalpindi", province="Punjab")
    st3 = Station(division_id=div.id, code="GUJ", name="Gujrat", city="Gujrat", province="Punjab")
    db.session.add_all([st1, st2, st3])
    db.session.flush()

    # 3. Train & Rolling stock
    ttype = TrainType(code="EXP", name="Express Train")
    cclass = CoachClass(code="AC_BIZ", name="AC Business", base_fare_multiplier=Decimal("2.00"))
    layout = SeatLayoutType(name="Standard 2x2", total_rows=10, seats_per_row=4, aisle_position=2)
    berth = BerthType(code="WINDOW", name="Window")
    db.session.add_all([ttype, cclass, layout, berth])
    db.session.flush()

    train = Train(
        train_type_id=ttype.id,
        train_number="101UP",
        name="Subak Kharam",
        origin_station_id=st1.id,
        destination_station_id=st2.id,
    )
    db.session.add(train)
    db.session.flush()

    coach = TrainCoach(
        train_id=train.id,
        coach_class_id=cclass.id,
        layout_type_id=layout.id,
        coach_code="C-1",
        sequence_number=1,
        total_capacity=40,
    )
    db.session.add(coach)
    db.session.flush()

    seat = Seat(
        coach_id=coach.id,
        berth_type_id=berth.id,
        seat_number="12",
        row_number=3,
        column_number=1,
        is_window=True,
    )
    db.session.add(seat)

    # 4. Route & Schedule
    route = Route(
        code="RT-101",
        name="Lahore to Rawalpindi",
        source_station_id=st1.id,
        destination_station_id=st2.id,
        total_distance_km=Decimal("290.00"),
    )
    db.session.add(route)
    db.session.flush()

    sch = Schedule(
        train_id=train.id,
        route_id=route.id,
        schedule_code="SCH-101UP",
        departure_time=time(7, 30),
        arrival_time=time(12, 0),
        journey_days_span=1,
    )
    db.session.add(sch)
    db.session.flush()

    # 5. JourneyInstance
    journey = JourneyInstance(
        schedule_id=sch.id,
        journey_date=date(2026, 11, 20),
        status="Scheduled",
    )
    db.session.add(journey)
    db.session.flush()

    # 6. JourneyCoach
    jcoach = JourneyCoach(
        journey_instance_id=journey.id,
        train_coach_id=coach.id,
        available_seats_count=40,
        is_available=True,
    )
    db.session.add(jcoach)
    db.session.commit()

    return {
        "user": user,
        "st1": st1,
        "st2": st2,
        "st3": st3,
        "train": train,
        "coach": coach,
        "seat": seat,
        "journey": journey,
        "jcoach": jcoach,
        "cclass": cclass,
    }


def test_seat_reservation_lock_check_constraint(app, base_journey_setup):
    """Verify SeatReservationLock validates stop sequence ordering with CheckConstraint."""
    ctx = base_journey_setup
    now = datetime.now(timezone.utc)

    # Valid lock: from_stop_sequence (1) < to_stop_sequence (3)
    valid_lock = SeatReservationLock(
        journey_instance_id=ctx["journey"].id,
        seat_id=ctx["seat"].id,
        user_id=ctx["user"].id,
        from_stop_sequence=1,
        to_stop_sequence=3,
        lock_token="valid-lock-token-123",
        expires_at=now + timedelta(minutes=10),
    )
    db.session.add(valid_lock)
    db.session.commit()
    assert valid_lock.id is not None

    # Invalid lock: from_stop_sequence (4) >= to_stop_sequence (2) -> must violate CheckConstraint
    invalid_lock = SeatReservationLock(
        journey_instance_id=ctx["journey"].id,
        seat_id=ctx["seat"].id,
        user_id=ctx["user"].id,
        from_stop_sequence=4,
        to_stop_sequence=2,
        lock_token="invalid-lock-token-456",
        expires_at=now + timedelta(minutes=10),
    )
    db.session.add(invalid_lock)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_booking_constraints_and_pnr_generation(app, base_journey_setup):
    """Verify Booking PNR format, uniqueness, and origin != destination CheckConstraint."""
    ctx = base_journey_setup
    pnr = generate_pnr()
    assert len(pnr) == 10
    assert pnr.isalnum()

    # Valid booking
    booking = Booking(
        pnr_number=pnr,
        user_id=ctx["user"].id,
        journey_instance_id=ctx["journey"].id,
        origin_station_id=ctx["st1"].id,
        destination_station_id=ctx["st2"].id,
        total_fare=Decimal("1500.00"),
        booking_status="Confirmed",
    )
    db.session.add(booking)
    db.session.commit()
    assert booking.id is not None

    # Invalid booking: origin == destination -> must violate CheckConstraint
    invalid_booking = Booking(
        pnr_number=generate_pnr(),
        user_id=ctx["user"].id,
        journey_instance_id=ctx["journey"].id,
        origin_station_id=ctx["st1"].id,
        destination_station_id=ctx["st1"].id,
        total_fare=Decimal("500.00"),
        booking_status="Pending",
    )
    db.session.add(invalid_booking)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_passenger_ticket_and_seat_allocation(app, base_journey_setup):
    """Verify PassengerTicket creation and TicketSeatAllocation segment validation."""
    ctx = base_journey_setup

    booking = Booking(
        pnr_number=generate_pnr(),
        user_id=ctx["user"].id,
        journey_instance_id=ctx["journey"].id,
        origin_station_id=ctx["st1"].id,
        destination_station_id=ctx["st2"].id,
        total_fare=Decimal("2000.00"),
        booking_status="Confirmed",
    )
    db.session.add(booking)
    db.session.flush()

    ticket_token = generate_ticket_token()
    ticket = PassengerTicket(
        booking_id=booking.id,
        full_name="Fatima Zahra",
        cnic="35201-9876543-2",
        age=28,
        gender="Female",
        fare_amount=Decimal("2000.00"),
        ticket_token=ticket_token,
        ticket_status="Valid",
    )
    db.session.add(ticket)
    db.session.flush()

    # Valid allocation: from_stop_sequence (1) < to_stop_sequence (2)
    alloc = TicketSeatAllocation(
        ticket_id=ticket.id,
        seat_id=ctx["seat"].id,
        journey_instance_id=ctx["journey"].id,
        from_stop_sequence=1,
        to_stop_sequence=2,
    )
    db.session.add(alloc)
    db.session.commit()
    assert alloc.id is not None

    # Invalid allocation: from_stop_sequence (3) >= to_stop_sequence (3)
    invalid_alloc = TicketSeatAllocation(
        ticket_id=ticket.id,
        seat_id=ctx["seat"].id,
        journey_instance_id=ctx["journey"].id,
        from_stop_sequence=3,
        to_stop_sequence=3,
    )
    db.session.add(invalid_alloc)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_payments_and_refunds_audit_flow(app, base_journey_setup):
    """Verify PaymentMethod, PaymentTransaction, RefundRequest, and RefundAuditTrail."""
    ctx = base_journey_setup

    pm = PaymentMethod(code="JAZZCASH_DEMO", name="JazzCash Sandbox", instructions="Simulated", is_active=True)
    db.session.add(pm)
    db.session.flush()

    booking = Booking(
        pnr_number=generate_pnr(),
        user_id=ctx["user"].id,
        journey_instance_id=ctx["journey"].id,
        origin_station_id=ctx["st1"].id,
        destination_station_id=ctx["st2"].id,
        total_fare=Decimal("1800.00"),
        booking_status="Confirmed",
    )
    db.session.add(booking)
    db.session.flush()

    tx = PaymentTransaction(
        booking_id=booking.id,
        payment_method_id=pm.id,
        transaction_reference="TXN-DEMO-998877",
        amount=Decimal("1800.00"),
        currency="PKR",
        status="Success",
        simulated_account="03001234567",
    )
    db.session.add(tx)
    db.session.flush()

    # Refund request
    refund = RefundRequest(
        booking_id=booking.id,
        requested_by_user_id=ctx["user"].id,
        original_amount=Decimal("1800.00"),
        deduction_amount=Decimal("300.00"),
        refundable_amount=Decimal("1500.00"),
        reason="Passenger personal emergency",
        status="Pending",
    )
    db.session.add(refund)
    db.session.flush()

    audit = RefundAuditTrail(
        refund_request_id=refund.id,
        action_taken="STATUS_CHANGE",
        performed_by_id=ctx["user"].id,
        remarks="Approved per cancellation policy",
    )
    db.session.add(audit)
    db.session.commit()

    assert tx.id is not None
    assert refund.id is not None
    assert audit.id is not None
    assert not hasattr(tx, "is_deleted")
    assert not hasattr(audit, "is_deleted")


def test_complaints_and_feedback(app, base_journey_setup):
    """Verify ComplaintCategory, Complaint, ComplaintTimeline, and FeedbackRating."""
    ctx = base_journey_setup

    cat = ComplaintCategory(name="Coach Air Conditioning", sla_hours=24, is_active=True)
    db.session.add(cat)
    db.session.flush()

    complaint = Complaint(
        category_id=cat.id,
        user_id=ctx["user"].id,
        train_id=ctx["train"].id,
        tracking_number="CMP-2026-0001",
        subject="AC not working in AC Business",
        description="Cooling failed after departure from Lahore",
        priority="High",
        status="Submitted",
    )
    db.session.add(complaint)
    db.session.flush()

    timeline = ComplaintTimeline(
        complaint_id=complaint.id,
        author_id=ctx["user"].id,
        previous_status="Submitted",
        new_status="InReview",
        remarks="Maintenance technician dispatched at Gujrat halt",
    )
    db.session.add(timeline)
    db.session.flush()

    feedback = FeedbackRating(
        complaint_id=complaint.id,
        rating=4,
        comment="Issue was handled promptly at the next station",
    )
    db.session.add(feedback)
    db.session.commit()

    assert complaint.id is not None
    assert timeline.id is not None
    assert feedback.id is not None


def test_lost_and_found_claim_workflow(app, base_journey_setup):
    """Verify LostFoundCategory, LostFoundReport, and LostFoundClaim."""
    ctx = base_journey_setup

    cat = LostFoundCategory(name="Laptops & Tablets", description="Portable computers")
    db.session.add(cat)
    db.session.flush()

    report = LostFoundReport(
        category_id=cat.id,
        reported_by_id=ctx["user"].id,
        station_id=ctx["st1"].id,
        report_type="Lost",
        item_name="Silver Dell XPS Laptop",
        item_description="Left on seat 12 of coach C-1",
        lost_found_date=date(2026, 11, 20),
        status="Reported",
    )
    db.session.add(report)
    db.session.flush()

    claim = LostFoundClaim(
        report_id=report.id,
        claimant_id=ctx["user"].id,
        proof_description="Has railway sticker on outer shell and initials AK",
        status="UnderReview",
    )
    db.session.add(claim)
    db.session.commit()

    assert report.id is not None
    assert claim.id is not None
    assert not hasattr(claim, "is_deleted")


def test_special_assistance_and_notifications(app, base_journey_setup):
    """Verify AssistanceType, SpecialAssistanceRequest, NotificationTemplate, and Notification."""
    ctx = base_journey_setup

    assist = AssistanceType(
        name="Wheelchair Platform Escort",
        standard_fee=Decimal("0.00"),
        requires_advance_booking_hours=2,
        description="Station porter assistance from entrance to seat",
    )
    db.session.add(assist)
    db.session.flush()

    req = SpecialAssistanceRequest(
        user_id=ctx["user"].id,
        assistance_type_id=assist.id,
        station_id=ctx["st1"].id,
        service_datetime=datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc),
        special_instructions="Assistance needed from Gate 2 to platform 1",
        status="Requested",
    )
    db.session.add(req)
    db.session.flush()

    tmpl = NotificationTemplate(
        code="TEST_ALERT",
        title_template="Notice: {train}",
        body_template="Train {train} update: {msg}",
        is_active=True,
    )
    db.session.add(tmpl)
    db.session.flush()

    notif = Notification(
        user_id=ctx["user"].id,
        template_id=tmpl.id,
        title="Notice: Subak Kharam",
        message="Train Subak Kharam is departing on time from Platform 1",
        is_read=False,
    )
    db.session.add(notif)
    db.session.commit()

    assert req.id is not None
    assert notif.id is not None


def test_seed_script_idempotency_in_test_db(app):
    """Verify that seed_all() executes idempotently in a fresh test database."""
    res1 = seed_all()
    assert res1["stations_seeded"] == 15

    # Run seed_all a second time
    res2 = seed_all()
    assert res2["stations_seeded"] == 15

    # Query counts to ensure zero duplication
    user_count = db.session.scalar(select(func.count(User.id)))
    role_count = db.session.scalar(select(func.count(Role.id)))
    station_count = db.session.scalar(select(func.count(Station.id)))
    train_count = db.session.scalar(select(func.count(Train.id)))

    assert user_count == 1
    assert role_count == 6
    assert station_count == 15
    assert train_count == 3
