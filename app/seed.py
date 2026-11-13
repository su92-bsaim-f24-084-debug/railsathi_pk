"""Database seeding module for RailSathi PK.

Provides seed_all() which populates the database idempotently with:
- 6 standard roles
- 1 Super Admin user (configurable via ADMIN_EMAIL / ADMIN_PASSWORD)
- Reference taxonomies (berth types, coach classes, layout types, train types,
  payment methods, categories, assistance types, notification templates)
- Realistic Pakistan Railways network (~15 stations, divisions, platforms)
- 3 realistic trains with coaches, seats, routes, route stops, schedules, schedule stops, fare rules
- 14 days of JourneyInstances with attached JourneyCoaches
"""
import os
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal
from werkzeug.security import generate_password_hash
from sqlalchemy import select

from app.extensions import db
from app.models.identity import User, Role, UserRole, UserProfile
from app.models.stations import (
    StationDivision, Station, StationPlatform, FacilityCategory, StationFacility
)
from app.models.trains import (
    TrainType, Train, TrainOperationalDay, CoachClass, SeatLayoutType,
    BerthType, TrainCoach, Seat
)
from app.models.routes import Route, RouteStop, FareRule
from app.models.schedules import Schedule, ScheduleStop, JourneyInstance
from app.models.bookings import JourneyCoach
from app.models.payments import PaymentMethod
from app.models.complaints import ComplaintCategory
from app.models.lost_found import LostFoundCategory
from app.models.services import AssistanceType
from app.models.governance import NotificationTemplate


def get_or_create(model, filter_kwargs, create_kwargs=None):
    """Retrieve existing row matching filter_kwargs or create a new instance."""
    stmt = select(model).filter_by(**filter_kwargs)
    instance = db.session.scalar(stmt)
    if instance:
        return instance, False
    params = dict(filter_kwargs)
    if create_kwargs:
        params.update(create_kwargs)
    instance = model(**params)
    db.session.add(instance)
    db.session.flush()
    return instance, True


from app.common.constants import (
    ROLE_SUPER_ADMIN,
    ROLE_STATION_MASTER,
    ROLE_RESERVATION_OFFICER,
    ROLE_COMPLAINT_OFFICER,
    ROLE_REFUND_OFFICER,
    ROLE_PASSENGER,
)


def seed_roles():
    """Seed 6 standard system roles using canonical constants."""
    roles_data = [
        {"code": "SUPER_ADMIN", "name": ROLE_SUPER_ADMIN, "description": "Full system access and governance"},
        {"code": "STATION_MASTER", "name": ROLE_STATION_MASTER, "description": "Station operational oversight and logs"},
        {"code": "RESERVATION_OFFICER", "name": ROLE_RESERVATION_OFFICER, "description": "Ticket booking and reservation counter operations"},
        {"code": "COMPLAINT_OFFICER", "name": ROLE_COMPLAINT_OFFICER, "description": "Passenger complaint management and escalation"},
        {"code": "REFUND_OFFICER", "name": ROLE_REFUND_OFFICER, "description": "Refund audit and processing approval"},
        {"code": "PASSENGER", "name": ROLE_PASSENGER, "description": "Registered passenger booking and profile access"},
    ]
    created = 0
    for r in roles_data:
        _, is_new = get_or_create(Role, {"code": r["code"]}, {"name": r["name"], "description": r["description"]})
        if is_new:
            created += 1
    db.session.flush()
    return created


def seed_super_admin():
    """Seed default Super Admin user strictly from environment variables."""
    email = os.environ.get("ADMIN_EMAIL")
    raw_password = os.environ.get("ADMIN_PASSWORD")

    if not email or not raw_password:
        print("[WARNING] ADMIN_EMAIL or ADMIN_PASSWORD environment variable not set. Skipping Super Admin user creation.")
        return None, False

    email = email.strip().lower()
    raw_password = raw_password.strip()

    stmt = select(User).filter_by(email=email)
    admin = db.session.scalar(stmt)
    is_new = False
    if not admin:
        admin = User(
            email=email,
            password_hash=generate_password_hash(raw_password),
            first_name="Super",
            last_name="Administrator",
            phone_number="+923001234567",
            cnic="35201-1234567-1",
            is_active_user=True,
            is_verified=True,
        )
        db.session.add(admin)
        db.session.flush()
        is_new = True

        profile = UserProfile(
            user_id=admin.id,
            city="Islamabad",
            province="Federal Capital Territory",
            address="Pakistan Railways Headquarters / Ministry of Railways",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(profile)

    # Ensure admin has SUPER_ADMIN role
    super_admin_role = db.session.scalar(select(Role).filter_by(code="SUPER_ADMIN"))
    if super_admin_role:
        user_role = db.session.scalar(select(UserRole).filter_by(user_id=admin.id, role_id=super_admin_role.id))
        if not user_role:
            db.session.add(UserRole(user_id=admin.id, role_id=super_admin_role.id))

    db.session.flush()
    return admin, is_new


def seed_taxonomies():
    """Seed berth types, coach classes, seat layout types, train types, payment methods, categories, etc."""
    # Berth types
    berths = [
        {"code": "LOWER", "name": "Lower Berth", "description": "Ground level berth with window view"},
        {"code": "MIDDLE", "name": "Middle Berth", "description": "Foldable mid-tier sleeping berth"},
        {"code": "UPPER", "name": "Upper Berth", "description": "Top tier sleeping berth with luggage access"},
        {"code": "WINDOW", "name": "Window Seat", "description": "Chair car window seat"},
        {"code": "AISLE", "name": "Aisle Seat", "description": "Chair car aisle walkway seat"},
    ]
    for b in berths:
        get_or_create(BerthType, {"code": b["code"]}, {"name": b["name"], "description": b["description"]})

    # Coach classes
    classes = [
        {"code": "AC_SLEEPER", "name": "AC Sleeper", "base_fare_multiplier": Decimal("2.50"), "description": "Luxury private 2/4-berth air-conditioned sleeper"},
        {"code": "AC_BUSINESS", "name": "AC Business", "base_fare_multiplier": Decimal("2.00"), "description": "Comfortable air-conditioned compartment sleeper"},
        {"code": "AC_STANDARD", "name": "AC Standard", "base_fare_multiplier": Decimal("1.50"), "description": "Economical air-conditioned semi-sleeper and chair car"},
        {"code": "ECONOMY", "name": "Economy Class", "base_fare_multiplier": Decimal("1.00"), "description": "Standard affordable non-AC passenger seating and open berths"},
    ]
    for c in classes:
        get_or_create(CoachClass, {"code": c["code"]}, {"name": c["name"], "base_fare_multiplier": c["base_fare_multiplier"], "description": c["description"]})

    # Seat layout types
    layouts = [
        {"name": "2x2 Chair Car", "total_rows": 18, "seats_per_row": 4, "aisle_position": 2, "description": "Two seats on each side of the central aisle"},
        {"name": "3x2 Economy Chair", "total_rows": 16, "seats_per_row": 5, "aisle_position": 3, "description": "Three seats on left, two on right"},
        {"name": "6-Berth Sleeper", "total_rows": 10, "seats_per_row": 6, "aisle_position": 4, "description": "Standard 6-berth compartment layout"},
    ]
    for l in layouts:
        get_or_create(SeatLayoutType, {"name": l["name"]}, {"total_rows": l["total_rows"], "seats_per_row": l["seats_per_row"], "aisle_position": l["aisle_position"], "description": l["description"]})

    # Train types
    ttypes = [
        {"code": "PREMIUM_EXPRESS", "name": "Premium Express", "description": "High-priority luxury long-distance train with minimal stops"},
        {"code": "EXPRESS", "name": "Express Train", "description": "Standard scheduled express inter-city passenger service"},
        {"code": "MAIL_PASSENGER", "name": "Mail Passenger", "description": "Regional mail and passenger train serving all major junctions"},
    ]
    for t in ttypes:
        get_or_create(TrainType, {"code": t["code"]}, {"name": t["name"], "description": t["description"]})

    # Payment methods
    pmethods = [
        {"code": "JAZZCASH_SANDBOX", "name": "JazzCash Mobile Account (Sandbox)", "instructions": "Simulated instant debit from JazzCash sandbox wallet"},
        {"code": "EASYPAISA_SANDBOX", "name": "Easypaisa Wallet (Sandbox)", "instructions": "Simulated instant debit from Easypaisa sandbox wallet"},
        {"code": "TEST_BANK_CARD", "name": "Pakistani Debit/Credit Card (1LINK Demo)", "instructions": "Simulated 1LINK card payment verification"},
        {"code": "RAILSATHI_WALLET", "name": "RailSathi Digital Demo Wallet", "instructions": "Internal pre-funded passenger test credit balance"},
    ]
    for p in pmethods:
        get_or_create(PaymentMethod, {"code": p["code"]}, {"name": p["name"], "instructions": p["instructions"], "is_active": True})

    # Facility categories
    fac_cats = [
        {"name": "Waiting Lounge", "icon_class": "bi-clock-history", "description": "Air-conditioned and general waiting halls"},
        {"name": "Ticketing Counter", "icon_class": "bi-ticket-perforated", "description": "Current and advance ticket reservation counters"},
        {"name": "Refreshment & Dining", "icon_class": "bi-cup-hot", "description": "Food stalls, tea shops, and station restaurants"},
        {"name": "Restrooms & Washrooms", "icon_class": "bi-droplet", "description": "Clean passenger toilets and wash facilities"},
        {"name": "Prayer Room", "icon_class": "bi-house-heart", "description": "Designated prayer areas and mosques"},
        {"name": "Cloakroom & Luggage", "icon_class": "bi-bag-check", "description": "Secure passenger luggage storage"},
        {"name": "Medical & First Aid", "icon_class": "bi-plus-circle", "description": "Emergency station first aid and medical post"},
    ]
    for fc in fac_cats:
        get_or_create(FacilityCategory, {"name": fc["name"]}, fc)

    # Complaint categories
    comp_cats = [
        {"name": "Cleanliness & Sanitation", "sla_hours": 24},
        {"name": "Air Conditioning & Electrical", "sla_hours": 12},
        {"name": "Food & Catering Quality", "sla_hours": 24},
        {"name": "Staff Behavior", "sla_hours": 48},
        {"name": "Train Delay & Punctuality", "sla_hours": 48},
        {"name": "Security & Lost Items", "sla_hours": 24},
        {"name": "Ticketing & Fare Issues", "sla_hours": 24},
        {"name": "General Inquiries & Others", "sla_hours": 72},
    ]
    for cc in comp_cats:
        get_or_create(ComplaintCategory, {"name": cc["name"]}, {"sla_hours": cc["sla_hours"], "is_active": True})

    # Lost & Found categories
    lf_cats = [
        {"name": "Electronics", "description": "Laptops, phones, chargers, smartwatches"},
        {"name": "Bags & Luggage", "description": "Suitcases, backpacks, briefcases, holdalls"},
        {"name": "Documents & Wallets", "description": "CNIC, passports, wallets, railway tickets"},
        {"name": "Clothing & Apparel", "description": "Jackets, shawls, caps, footwear"},
        {"name": "Jewelry & Valuables", "description": "Watches, gold items, cash envelopes"},
        {"name": "Keys & Small Accessories", "description": "Vehicle and home keys, glasses, umbrellas"},
        {"name": "Other Belongings", "description": "Books, toys, medication boxes"},
    ]
    for lc in lf_cats:
        get_or_create(LostFoundCategory, {"name": lc["name"]}, lc)

    # Assistance types
    assist_types = [
        {"name": "Wheelchair Support", "standard_fee": Decimal("0.00"), "requires_advance_booking_hours": 4, "description": "Station porter and wheelchair ramp assistance"},
        {"name": "Senior Citizen Porter Assistance", "standard_fee": Decimal("100.00"), "requires_advance_booking_hours": 2, "description": "Help carrying luggage for elderly passengers"},
        {"name": "Stretcher Support", "standard_fee": Decimal("0.00"), "requires_advance_booking_hours": 6, "description": "Station ambulance and stretcher boarding transfer"},
        {"name": "Visual Impairment Guide", "standard_fee": Decimal("0.00"), "requires_advance_booking_hours": 2, "description": "Station assistant to guide to seat and platform"},
    ]
    for at in assist_types:
        get_or_create(AssistanceType, {"name": at["name"]}, at)

    # Notification templates
    templates = [
        {"code": "BOOKING_CONFIRMATION", "title_template": "RailSathi PK — Booking Confirmed", "body_template": "Dear {passenger_name}, your booking on train {train_name} from {origin} to {destination} for date {departure_date} is confirmed. PNR: {pnr}."},
        {"code": "TRAIN_DELAY_ALERT", "title_template": "RailSathi PK — Schedule Update", "body_template": "Passenger notice: Train {train_name} is currently running {delay_minutes} minutes behind schedule. Estimated departure from {station}: {estimated_time}."},
        {"code": "COMPLAINT_UPDATE", "title_template": "RailSathi PK — Complaint Tracking", "body_template": "Dear Passenger, your complaint regarding '{category}' is now {status}. Remarks: {remarks}."},
        {"code": "REFUND_PROCESSED", "title_template": "RailSathi PK — Refund Notification", "body_template": "Your refund request of PKR {refund_amount} for PNR {pnr} has been approved and processed to your payment method."},
    ]
    for nt in templates:
        get_or_create(NotificationTemplate, {"code": nt["code"]}, {"title_template": nt["title_template"], "body_template": nt["body_template"], "is_active": True})

    db.session.flush()


def seed_stations_and_network():
    """Seed ~15 realistic Pakistan railway stations, divisions, platforms, and facilities."""
    # Divisions
    divs = [
        {"code": "LHR-DIV", "name": "Lahore Division", "headquarters_city": "Lahore"},
        {"code": "KHI-DIV", "name": "Karachi Division", "headquarters_city": "Karachi"},
        {"code": "RWP-DIV", "name": "Rawalpindi Division", "headquarters_city": "Rawalpindi"},
        {"code": "MUL-DIV", "name": "Multan Division", "headquarters_city": "Multan"},
        {"code": "SKR-DIV", "name": "Sukkur Division", "headquarters_city": "Sukkur"},
        {"code": "PES-DIV", "name": "Peshawar Division", "headquarters_city": "Peshawar"},
        {"code": "QTA-DIV", "name": "Quetta Division", "headquarters_city": "Quetta"},
    ]
    div_map = {}
    for d in divs:
        obj, _ = get_or_create(StationDivision, {"code": d["code"]}, d)
        div_map[d["code"]] = obj
    db.session.flush()

    # 15 Realistic Stations
    stations_data = [
        {"code": "KC", "name": "Karachi Cantt", "city": "Karachi", "province": "Sindh", "division": "KHI-DIV", "latitude": Decimal("24.8510"), "longitude": Decimal("67.0428"), "junction": False, "platforms": 6, "contact": "+92-21-99206072"},
        {"code": "HYD", "name": "Hyderabad Junction", "city": "Hyderabad", "province": "Sindh", "division": "KHI-DIV", "latitude": Decimal("25.3969"), "longitude": Decimal("68.3772"), "junction": True, "platforms": 4, "contact": "+92-22-9200123"},
        {"code": "ROH", "name": "Rohri Junction", "city": "Rohri", "province": "Sindh", "division": "SKR-DIV", "latitude": Decimal("27.6784"), "longitude": Decimal("68.8943"), "junction": True, "platforms": 5, "contact": "+92-71-5804100"},
        {"code": "SKR", "name": "Sukkur", "city": "Sukkur", "province": "Sindh", "division": "SKR-DIV", "latitude": Decimal("27.7052"), "longitude": Decimal("68.8574"), "junction": False, "platforms": 2, "contact": "+92-71-5622345"},
        {"code": "BWN", "name": "Bahawalpur", "city": "Bahawalpur", "province": "Punjab", "division": "MUL-DIV", "latitude": Decimal("29.3956"), "longitude": Decimal("71.6836"), "junction": False, "platforms": 3, "contact": "+92-62-9250100"},
        {"code": "MUX", "name": "Multan Cantt", "city": "Multan", "province": "Punjab", "division": "MUL-DIV", "latitude": Decimal("30.1984"), "longitude": Decimal("71.4687"), "junction": True, "platforms": 6, "contact": "+92-61-9200340"},
        {"code": "KWL", "name": "Khanewal Junction", "city": "Khanewal", "province": "Punjab", "division": "MUL-DIV", "latitude": Decimal("30.3017"), "longitude": Decimal("71.9321"), "junction": True, "platforms": 4, "contact": "+92-65-2551200"},
        {"code": "SWL", "name": "Sahiwal", "city": "Sahiwal", "province": "Punjab", "division": "LHR-DIV", "latitude": Decimal("30.6682"), "longitude": Decimal("73.1114"), "junction": False, "platforms": 2, "contact": "+92-40-9200050"},
        {"code": "LHE", "name": "Lahore Junction", "city": "Lahore", "province": "Punjab", "division": "LHR-DIV", "latitude": Decimal("31.5794"), "longitude": Decimal("74.3353"), "junction": True, "platforms": 9, "contact": "+92-42-99201760"},
        {"code": "GRW", "name": "Gujranwala", "city": "Gujranwala", "province": "Punjab", "division": "LHR-DIV", "latitude": Decimal("32.1877"), "longitude": Decimal("74.1945"), "junction": False, "platforms": 2, "contact": "+92-55-9200110"},
        {"code": "FSD", "name": "Faisalabad", "city": "Faisalabad", "province": "Punjab", "division": "MUL-DIV", "latitude": Decimal("31.4187"), "longitude": Decimal("73.0791"), "junction": True, "platforms": 4, "contact": "+92-41-9200234"},
        {"code": "RWP", "name": "Rawalpindi", "city": "Rawalpindi", "province": "Punjab", "division": "RWP-DIV", "latitude": Decimal("33.6007"), "longitude": Decimal("73.0679"), "junction": True, "platforms": 5, "contact": "+92-51-9270834"},
        {"code": "ATK", "name": "Attock City Junction", "city": "Attock", "province": "Punjab", "division": "RWP-DIV", "latitude": Decimal("33.7667"), "longitude": Decimal("72.3667"), "junction": True, "platforms": 3, "contact": "+92-57-9316100"},
        {"code": "PSC", "name": "Peshawar Cantt", "city": "Peshawar", "province": "Khyber Pakhtunkhwa", "division": "PES-DIV", "latitude": Decimal("34.0084"), "longitude": Decimal("71.5542"), "junction": True, "platforms": 4, "contact": "+92-91-9212001"},
        {"code": "UET", "name": "Quetta", "city": "Quetta", "province": "Balochistan", "division": "QTA-DIV", "latitude": Decimal("30.1798"), "longitude": Decimal("66.9750"), "junction": True, "platforms": 4, "contact": "+92-81-9201400"},
    ]

    station_map = {}
    for s in stations_data:
        division_obj = div_map.get(s["division"])
        st_obj, _ = get_or_create(
            Station,
            {"code": s["code"]},
            {
                "name": s["name"],
                "city": s["city"],
                "province": s["province"],
                "division_id": division_obj.id if division_obj else None,
                "latitude": s["latitude"],
                "longitude": s["longitude"],
                "contact_number": s["contact"],
                "is_junction": s["junction"],
            }
        )
        station_map[s["code"]] = st_obj

        # Platforms
        for pnum in range(1, s["platforms"] + 1):
            get_or_create(
                StationPlatform,
                {"station_id": st_obj.id, "platform_number": str(pnum)},
                {"length_meters": 450, "has_disabled_access": True, "is_operational": True}
            )

    db.session.flush()
    return station_map


def seed_trains_routes_and_instances(station_map):
    """Seed 3 iconic Pakistan trains, coaches, seats, routes, schedule stops, fare rules, and 14 days of JourneyInstances."""
    # Lookup reference types
    ac_sleeper = db.session.scalar(select(CoachClass).filter_by(code="AC_SLEEPER"))
    ac_business = db.session.scalar(select(CoachClass).filter_by(code="AC_BUSINESS"))
    ac_standard = db.session.scalar(select(CoachClass).filter_by(code="AC_STANDARD"))
    economy = db.session.scalar(select(CoachClass).filter_by(code="ECONOMY"))

    layout_chair = db.session.scalar(select(SeatLayoutType).filter_by(name="2x2 Chair Car"))
    layout_econ = db.session.scalar(select(SeatLayoutType).filter_by(name="3x2 Economy Chair"))
    layout_sleeper = db.session.scalar(select(SeatLayoutType).filter_by(name="6-Berth Sleeper"))

    berth_lower = db.session.scalar(select(BerthType).filter_by(code="LOWER"))
    berth_window = db.session.scalar(select(BerthType).filter_by(code="WINDOW"))
    berth_aisle = db.session.scalar(select(BerthType).filter_by(code="AISLE"))

    t_premium = db.session.scalar(select(TrainType).filter_by(code="PREMIUM_EXPRESS"))
    t_express = db.session.scalar(select(TrainType).filter_by(code="EXPRESS"))

    # 1. Green Line Express (05UP, Karachi Cantt -> Rawalpindi)
    t_green, _ = get_or_create(
        Train,
        {"train_number": "05UP"},
        {
            "name": "Green Line Express",
            "train_type_id": t_premium.id,
            "origin_station_id": station_map["KC"].id,
            "destination_station_id": station_map["RWP"].id,
            "is_active": True,
        }
    )

    # 2. Karakoram Express (41UP, Karachi Cantt -> Lahore Jn)
    t_karakoram, _ = get_or_create(
        Train,
        {"train_number": "41UP"},
        {
            "name": "Karakoram Express",
            "train_type_id": t_express.id,
            "origin_station_id": station_map["KC"].id,
            "destination_station_id": station_map["LHE"].id,
            "is_active": True,
        }
    )

    # 3. Tezgam Express (07UP, Karachi Cantt -> Rawalpindi)
    t_tezgam, _ = get_or_create(
        Train,
        {"train_number": "07UP"},
        {
            "name": "Tezgam Express",
            "train_type_id": t_express.id,
            "origin_station_id": station_map["KC"].id,
            "destination_station_id": station_map["RWP"].id,
            "is_active": True,
        }
    )
    db.session.flush()

    trains = [t_green, t_karakoram, t_tezgam]

    # Operational days (all 7 days for daily trains)
    for tr in trains:
        for day_int in range(7):
            get_or_create(TrainOperationalDay, {"train_id": tr.id, "day_of_week": day_int}, {"is_active": True})

    # Coaches & physical seats for each train (4 coaches per train: AC Business, AC Standard, 2 Economy)
    coach_templates = [
        {"coach_code": "AC-1", "coach_class": ac_business, "layout": layout_sleeper, "capacity": 36, "berth": berth_lower},
        {"coach_code": "AC-2", "coach_class": ac_standard, "layout": layout_chair, "capacity": 54, "berth": berth_window},
        {"coach_code": "EC-1", "coach_class": economy, "layout": layout_econ, "capacity": 60, "berth": berth_aisle},
        {"coach_code": "EC-2", "coach_class": economy, "layout": layout_econ, "capacity": 60, "berth": berth_window},
    ]

    for tr in trains:
        for seq_idx, ct in enumerate(coach_templates, start=1):
            coach, c_new = get_or_create(
                TrainCoach,
                {"train_id": tr.id, "coach_code": ct["coach_code"]},
                {
                    "coach_class_id": ct["coach_class"].id,
                    "layout_type_id": ct["layout"].id,
                    "sequence_number": seq_idx,
                    "total_capacity": ct["capacity"],
                }
            )
            if c_new:
                # Create physical seats for this coach
                seats_to_add = []
                for s_num in range(1, ct["capacity"] + 1):
                    row = (s_num - 1) // 4 + 1
                    col = ((s_num - 1) % 4) + 1
                    seats_to_add.append(
                        Seat(
                            coach_id=coach.id,
                            seat_number=str(s_num),
                            row_number=row,
                            column_number=col,
                            berth_type_id=ct["berth"].id,
                            is_window=ct["berth"].code == "WINDOW",
                            is_ladies_quota=False,
                        )
                    )
                db.session.add_all(seats_to_add)

    db.session.flush()

    # Routes and route stops
    # Route 1: Karachi Cantt to Rawalpindi (Green Line)
    route_gl, _ = get_or_create(
        Route,
        {"code": "RT-GL-05UP"},
        {
            "name": "Main Line 1 Express Route (KC to RWP)",
            "source_station_id": station_map["KC"].id,
            "destination_station_id": station_map["RWP"].id,
            "total_distance_km": Decimal("1580.00"),
        }
    )
    gl_stops = [
        ("KC", 1, Decimal("0.00")),
        ("HYD", 2, Decimal("180.00")),
        ("ROH", 3, Decimal("500.00")),
        ("MUX", 4, Decimal("950.00")),
        ("LHE", 5, Decimal("1280.00")),
        ("RWP", 6, Decimal("1580.00")),
    ]
    for st_code, seq, dist in gl_stops:
        get_or_create(
            RouteStop,
            {"route_id": route_gl.id, "stop_sequence": seq},
            {"station_id": station_map[st_code].id, "distance_from_origin_km": dist, "standard_halt_minutes": 5}
        )

    # Route 2: Karachi to Lahore (Karakoram Express)
    route_kk, _ = get_or_create(
        Route,
        {"code": "RT-KK-41UP"},
        {
            "name": "Karachi to Lahore Express Route",
            "source_station_id": station_map["KC"].id,
            "destination_station_id": station_map["LHE"].id,
            "total_distance_km": Decimal("1280.00"),
        }
    )
    kk_stops = [
        ("KC", 1, Decimal("0.00")),
        ("HYD", 2, Decimal("180.00")),
        ("ROH", 3, Decimal("500.00")),
        ("BWN", 4, Decimal("850.00")),
        ("MUX", 5, Decimal("950.00")),
        ("KWL", 6, Decimal("995.00")),
        ("SWL", 7, Decimal("1130.00")),
        ("LHE", 8, Decimal("1280.00")),
    ]
    for st_code, seq, dist in kk_stops:
        get_or_create(
            RouteStop,
            {"route_id": route_kk.id, "stop_sequence": seq},
            {"station_id": station_map[st_code].id, "distance_from_origin_km": dist, "standard_halt_minutes": 5}
        )

    # Fare rules per coach class (every seeded coach class has a FareRule)
    fare_tiers = [
        (ac_sleeper, Decimal("3000.00"), Decimal("5.00"), Decimal("300.00")),
        (ac_business, Decimal("2000.00"), Decimal("3.80"), Decimal("200.00")),
        (ac_standard, Decimal("1200.00"), Decimal("2.20"), Decimal("100.00")),
        (economy, Decimal("500.00"), Decimal("1.25"), Decimal("50.00")),
    ]
    for c_cls, base, rate, resv in fare_tiers:
        get_or_create(
            FareRule,
            {"coach_class_id": c_cls.id, "min_distance_km": Decimal("0.00")},
            {
                "max_distance_km": Decimal("2500.00"),
                "base_fare": base,
                "rate_per_km": rate,
                "reservation_charge": resv,
            }
        )

    # Schedules & Schedule Stops
    # Schedule for Green Line 05UP
    sch_gl, _ = get_or_create(
        Schedule,
        {"train_id": t_green.id, "schedule_code": "SCH-GL-05UP"},
        {
            "route_id": route_gl.id,
            "departure_time": time(22, 0),
            "arrival_time": time(19, 30),
            "journey_days_span": 2,
            "is_active": True,
        }
    )
    gl_sched_stops = [
        (1, "KC", None, time(22, 0), 0),
        (2, "HYD", time(0, 15), time(0, 25), 1),
        (3, "ROH", time(4, 30), time(4, 45), 1),
        (4, "MUX", time(10, 15), time(10, 35), 1),
        (5, "LHE", time(15, 0), time(15, 30), 1),
        (6, "RWP", time(19, 30), None, 1),
    ]
    for seq, st_code, arr, dep, day_off in gl_sched_stops:
        get_or_create(
            ScheduleStop,
            {"schedule_id": sch_gl.id, "stop_sequence": seq},
            {
                "station_id": station_map[st_code].id,
                "scheduled_arrival": arr,
                "scheduled_departure": dep,
                "day_offset": day_off,
            }
        )

    # Schedule for Karakoram 41UP
    sch_kk, _ = get_or_create(
        Schedule,
        {"train_id": t_karakoram.id, "schedule_code": "SCH-KK-41UP"},
        {
            "route_id": route_kk.id,
            "departure_time": time(15, 0),
            "arrival_time": time(9, 30),
            "journey_days_span": 2,
            "is_active": True,
        }
    )
    kk_sched_stops = [
        (1, "KC", None, time(15, 0), 0),
        (2, "HYD", time(17, 10), time(17, 20), 0),
        (3, "ROH", time(21, 30), time(21, 50), 0),
        (4, "BWN", time(1, 45), time(2, 0), 1),
        (5, "MUX", time(3, 40), time(4, 0), 1),
        (6, "KWL", time(4, 45), time(4, 55), 1),
        (7, "SWL", time(6, 30), time(6, 40), 1),
        (8, "LHE", time(9, 30), None, 1),
    ]
    for seq, st_code, arr, dep, day_off in kk_sched_stops:
        get_or_create(
            ScheduleStop,
            {"schedule_id": sch_kk.id, "stop_sequence": seq},
            {
                "station_id": station_map[st_code].id,
                "scheduled_arrival": arr,
                "scheduled_departure": dep,
                "day_offset": day_off,
            }
        )

    # Route 3 & Schedule for Tezgam Express 07UP
    route_tg, _ = get_or_create(
        Route,
        {"code": "RT-TG-07UP"},
        {
            "name": "Tezgam Main Line Corridor (KC to RWP via Multan)",
            "source_station_id": station_map["KC"].id,
            "destination_station_id": station_map["RWP"].id,
            "total_distance_km": Decimal("1580.00"),
        }
    )
    tg_stops = [
        ("KC", 1, Decimal("0.00")),
        ("HYD", 2, Decimal("180.00")),
        ("ROH", 3, Decimal("500.00")),
        ("BWN", 4, Decimal("850.00")),
        ("MUX", 5, Decimal("950.00")),
        ("SWL", 6, Decimal("1130.00")),
        ("LHE", 7, Decimal("1280.00")),
        ("GRW", 8, Decimal("1342.00")),
        ("RWP", 9, Decimal("1580.00")),
    ]
    for st_code, seq, dist in tg_stops:
        get_or_create(
            RouteStop,
            {"route_id": route_tg.id, "stop_sequence": seq},
            {"station_id": station_map[st_code].id, "distance_from_origin_km": dist, "standard_halt_minutes": 5}
        )

    sch_tg, _ = get_or_create(
        Schedule,
        {"train_id": t_tezgam.id, "schedule_code": "SCH-TG-07UP"},
        {
            "route_id": route_tg.id,
            "departure_time": time(17, 30),
            "arrival_time": time(19, 0),
            "journey_days_span": 2,
            "is_active": True,
        }
    )
    tg_sched_stops = [
        (1, "KC", None, time(17, 30), 0),
        (2, "HYD", time(19, 50), time(20, 0), 0),
        (3, "ROH", time(1, 15), time(1, 35), 1),
        (4, "BWN", time(6, 10), time(6, 25), 1),
        (5, "MUX", time(8, 30), time(8, 50), 1),
        (6, "SWL", time(11, 45), time(11, 55), 1),
        (7, "LHE", time(14, 40), time(15, 10), 1),
        (8, "GRW", time(16, 15), time(16, 25), 1),
        (9, "RWP", time(19, 0), None, 1),
    ]
    for seq, st_code, arr, dep, day_off in tg_sched_stops:
        get_or_create(
            ScheduleStop,
            {"schedule_id": sch_tg.id, "stop_sequence": seq},
            {
                "station_id": station_map[st_code].id,
                "scheduled_arrival": arr,
                "scheduled_departure": dep,
                "day_offset": day_off,
            }
        )

    db.session.flush()

    # 14 days of JourneyInstances for all 3 trains (Green Line, Karakoram, and Tezgam)
    today = date.today()
    gl_coaches = db.session.scalars(select(TrainCoach).filter_by(train_id=t_green.id)).all()
    kk_coaches = db.session.scalars(select(TrainCoach).filter_by(train_id=t_karakoram.id)).all()
    tg_coaches = db.session.scalars(select(TrainCoach).filter_by(train_id=t_tezgam.id)).all()

    for offset in range(14):
        j_date = today + timedelta(days=offset)

        # 1. Green Line Instance
        j_gl, is_new_gl = get_or_create(
            JourneyInstance,
            {"schedule_id": sch_gl.id, "journey_date": j_date},
            {
                "status": "Scheduled",
                "current_delay_minutes": 0,
                "is_booking_open": True,
            }
        )
        if is_new_gl:
            for c in gl_coaches:
                get_or_create(
                    JourneyCoach,
                    {"journey_instance_id": j_gl.id, "train_coach_id": c.id},
                    {
                        "sequence_in_train": c.sequence_number,
                        "available_seats_count": c.total_capacity,
                        "is_available": True,
                    }
                )

        # 2. Karakoram Instance
        j_kk, is_new_kk = get_or_create(
            JourneyInstance,
            {"schedule_id": sch_kk.id, "journey_date": j_date},
            {
                "status": "Scheduled",
                "current_delay_minutes": 0,
                "is_booking_open": True,
            }
        )
        if is_new_kk:
            for c in kk_coaches:
                get_or_create(
                    JourneyCoach,
                    {"journey_instance_id": j_kk.id, "train_coach_id": c.id},
                    {
                        "sequence_in_train": c.sequence_number,
                        "available_seats_count": c.total_capacity,
                        "is_available": True,
                    }
                )

        # 3. Tezgam Instance
        j_tg, is_new_tg = get_or_create(
            JourneyInstance,
            {"schedule_id": sch_tg.id, "journey_date": j_date},
            {
                "status": "Scheduled",
                "current_delay_minutes": 0,
                "is_booking_open": True,
            }
        )
        if is_new_tg:
            for c in tg_coaches:
                get_or_create(
                    JourneyCoach,
                    {"journey_instance_id": j_tg.id, "train_coach_id": c.id},
                    {
                        "sequence_in_train": c.sequence_number,
                        "available_seats_count": c.total_capacity,
                        "is_available": True,
                    }
                )

    db.session.flush()


def seed_all():
    """Main entrypoint: executes all seed steps within a managed transaction."""
    print("Beginning RailSathi PK database seed...")
    roles_created = seed_roles()
    admin_user, admin_is_new = seed_super_admin()
    seed_taxonomies()
    st_map = seed_stations_and_network()
    seed_trains_routes_and_instances(st_map)
    db.session.commit()
    print("RailSathi PK database seed completed successfully!")
    return {
        "roles_created": roles_created,
        "admin_created": admin_is_new,
        "stations_seeded": len(st_map),
    }
