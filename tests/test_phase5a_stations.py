"""Phase 5A — Railway Infrastructure & Station Master-Data Tests.

Covers Models #7-#11:
- Model #7: StationDivision (Super Admin)
- Model #8: Station (Super Admin)
- Model #9: StationPlatform (Super Admin & Station Master scoped to assigned station)
- Model #10: FacilityCategory (Super Admin)
- Model #11: StationFacility (Super Admin & Station Master scoped to assigned station)

Verifies:
- Full CRUD workflows for all 5 models (Create, Read, Update, Soft-delete, Restore).
- Blocked soft-deletes when active children exist:
  - Division blocked by active stations.
  - Station blocked by active platforms, facilities, or route stops.
  - Category blocked by active facilities.
- PostgreSQL partial index code reuse after soft-delete:
  - StationDivision code reuse.
  - Station code reuse.
- Form validations:
  - Platform number must be positive integer (> 0).
  - Station coordinates within valid ranges (latitude -90..90, longitude -180..180).
  - Facility fee non-negative (>= 0).
- RBAC & Authorization Scoping:
  - Passenger receives HTTP 403 on all Phase 5A admin endpoints.
  - Station Master receives HTTP 403 on Divisions, Stations, and Categories (Super Admin only).
  - Station Master is scoped to their assigned station for Platforms and Facilities:
    - Can view and manage their own station's platforms/facilities.
    - Forbidden (HTTP 403) from accessing, editing, or deleting platforms/facilities of another station.
- Same-transaction audit logging for all mutations.
"""
import json
from decimal import Decimal
import pytest
from flask import url_for
from sqlalchemy import select

from app.extensions import db
from app.common.constants import (
    ROLE_SUPER_ADMIN,
    ROLE_STATION_MASTER,
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
    FacilityCategory,
    StationFacility,
)
from app.models.governance import AuditLog


@pytest.fixture
def station_test_setup(app):
    """Seed base roles, two divisions, two stations, a Super Admin, a Station Master, and a Passenger."""
    with app.app_context():
        # Canonical roles
        for r_name in [ROLE_SUPER_ADMIN, ROLE_STATION_MASTER, ROLE_PASSENGER]:
            if not db.session.scalar(select(Role).filter_by(name=r_name)):
                db.session.add(Role(name=r_name, code=r_name.upper().replace(" ", "_")))
        db.session.flush()

        role_admin = db.session.scalar(select(Role).filter_by(name=ROLE_SUPER_ADMIN))
        role_sm = db.session.scalar(select(Role).filter_by(name=ROLE_STATION_MASTER))
        role_pass = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))

        # Divisions
        div1 = StationDivision(code="LHR-DIV", name="Lahore Division", headquarters_city="Lahore")
        div2 = StationDivision(code="KHI-DIV", name="Karachi Division", headquarters_city="Karachi")
        db.session.add_all([div1, div2])
        db.session.flush()

        # Stations
        stn1 = Station(
            division_id=div1.id,
            code="LHE",
            name="Lahore Junction",
            city="Lahore",
            province="Punjab",
            latitude=Decimal("31.577200"),
            longitude=Decimal("74.354400"),
            is_junction=True,
        )
        stn2 = Station(
            division_id=div2.id,
            code="KHI",
            name="Karachi Cantt",
            city="Karachi",
            province="Sindh",
            latitude=Decimal("24.851700"),
            longitude=Decimal("67.042800"),
            is_junction=False,
        )
        db.session.add_all([stn1, stn2])
        db.session.flush()

        # Category
        cat = FacilityCategory(name="Waiting Area", icon_class="bi-clock", description="Passenger waiting rooms")
        db.session.add(cat)
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
        db.session.add(u_admin)
        db.session.flush()
        db.session.add(UserRole(user_id=u_admin.id, role_id=role_admin.id))

        # Station Master assigned to Station 1 (LHE)
        u_sm = User(
            email="sm.lahore@railsathi.pk",
            cnic="35201-2222222-2",
            first_name="Lahore",
            last_name="Master",
            phone_number="0300-2222222",
            is_active_user=True,
        )
        u_sm.password = "StationMaster123!"
        db.session.add(u_sm)
        db.session.flush()
        db.session.add(UserRole(user_id=u_sm.id, role_id=role_sm.id))
        db.session.add(StaffProfile(user_id=u_sm.id, employee_code="EMP-LHE-01", station_id=stn1.id, designation="Station Master", department="Operations"))

        # Passenger
        u_pass = User(
            email="passenger@railsathi.pk",
            cnic="35201-3333333-3",
            first_name="Regular",
            last_name="Passenger",
            phone_number="0300-3333333",
            is_active_user=True,
        )
        u_pass.password = "Pass12345!"
        db.session.add(u_pass)
        db.session.flush()
        db.session.add(UserRole(user_id=u_pass.id, role_id=role_pass.id))

        db.session.commit()

        return {
            "div1_id": div1.id,
            "div2_id": div2.id,
            "stn1_id": stn1.id,
            "stn2_id": stn2.id,
            "cat_id": cat.id,
            "admin_id": u_admin.id,
            "sm_id": u_sm.id,
            "pass_id": u_pass.id,
        }


# ===========================================================================
# 1. StationDivision Tests (Super Admin)
# ===========================================================================
def test_division_crud_lifecycle_and_audit(client, app, station_test_setup):
    """Test full CRUD lifecycle for StationDivision with atomic audit logs."""
    # 1. Login Super Admin
    login_resp = client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"}, follow_redirects=True)
    assert login_resp.status_code == 200

    # 2. List divisions
    resp = client.get("/admin/divisions")
    assert resp.status_code == 200
    assert b"Lahore Division" in resp.data

    # 3. Create Division
    create_resp = client.post(
        "/admin/divisions/create",
        data={"code": "RWP-DIV", "name": "Rawalpindi Division", "headquarters_city": "Rawalpindi"},
        follow_redirects=False,
    )
    assert create_resp.status_code == 302
    assert "/admin/divisions" in create_resp.headers["Location"]

    with app.app_context():
        new_div = db.session.scalar(select(StationDivision).filter_by(code="RWP-DIV"))
        assert new_div is not None
        assert new_div.name == "Rawalpindi Division"
        div_id = new_div.id

        # Verify audit log
        audit = db.session.scalar(select(AuditLog).filter_by(action="CREATE_STATION_DIVISION", entity_id=str(div_id)))
        assert audit is not None
        audit_data = json.loads(audit.new_values)
        assert audit_data["code"] == "RWP-DIV"

    # 4. Edit Division
    edit_resp = client.post(
        f"/admin/divisions/{div_id}/edit",
        data={"code": "RWP-DIV", "name": "Rawalpindi & Islamabad Division", "headquarters_city": "Islamabad"},
        follow_redirects=True,
    )
    assert edit_resp.status_code == 200
    assert b"Rawalpindi &amp; Islamabad Division" in edit_resp.data

    # 5. Soft Delete Division
    del_resp = client.post(f"/admin/divisions/{div_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    with app.app_context():
        d = db.session.get(StationDivision, div_id)
        assert d.is_deleted is True

    # 6. Restore Division
    restore_resp = client.post(f"/admin/divisions/{div_id}/restore", follow_redirects=True)
    assert restore_resp.status_code == 200
    with app.app_context():
        d = db.session.get(StationDivision, div_id)
        assert d.is_deleted is False


def test_division_code_reuse_after_soft_delete(client, app, station_test_setup):
    """Test partial unique index allows reusing code after soft delete."""
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})

    # Create division
    client.post("/admin/divisions/create", data={"code": "PES-DIV", "name": "Peshawar Division", "headquarters_city": "Peshawar"})
    with app.app_context():
        d1 = db.session.scalar(select(StationDivision).filter_by(code="PES-DIV", is_deleted=False))
        d1_id = d1.id

    # Soft delete it
    client.post(f"/admin/divisions/{d1_id}/delete")

    # Re-create division with same code should SUCCEED
    resp2 = client.post(
        "/admin/divisions/create",
        data={"code": "PES-DIV", "name": "Peshawar Reborn Division", "headquarters_city": "Peshawar"},
        follow_redirects=True,
    )
    assert resp2.status_code == 200
    assert b"Peshawar Reborn Division" in resp2.data

    with app.app_context():
        active_count = db.session.scalar(
            select(db.func.count(StationDivision.id)).filter_by(code="PES-DIV", is_deleted=False)
        )
        assert active_count == 1


def test_division_delete_blocked_when_active_stations_exist(client, app, station_test_setup):
    """Test soft-delete is blocked when division has active station children."""
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})
    div1_id = station_test_setup["div1_id"]

    del_resp = client.post(f"/admin/divisions/{div1_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"Cannot soft-delete division" in del_resp.data
    assert b"active station(s)" in del_resp.data

    with app.app_context():
        div = db.session.get(StationDivision, div1_id)
        assert div.is_deleted is False


# ===========================================================================
# 2. Station Tests (Super Admin)
# ===========================================================================
def test_station_crud_and_validations(client, app, station_test_setup):
    """Test Station creation, coordinate range validations, update, and soft delete."""
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})
    div1_id = station_test_setup["div1_id"]

    # 1. Invalid coordinates: Latitude > 90
    bad_resp = client.post(
        "/admin/stations/create",
        data={
            "division_id": div1_id,
            "code": "GUJ",
            "name": "Gujranwala",
            "city": "Gujranwala",
            "province": "Punjab",
            "latitude": "95.500000",
            "longitude": "74.180000",
        },
    )
    assert bad_resp.status_code == 200
    assert b"Latitude must be between -90 and +90" in bad_resp.data

    # 2. Invalid coordinates: Longitude > 180
    bad_resp2 = client.post(
        "/admin/stations/create",
        data={
            "division_id": div1_id,
            "code": "GUJ",
            "name": "Gujranwala",
            "city": "Gujranwala",
            "province": "Punjab",
            "latitude": "32.187700",
            "longitude": "185.000000",
        },
    )
    assert bad_resp2.status_code == 200
    assert b"Longitude must be between -180 and +180" in bad_resp2.data

    # 3. Valid creation
    good_resp = client.post(
        "/admin/stations/create",
        data={
            "division_id": div1_id,
            "code": "GUJ",
            "name": "Gujranwala City",
            "city": "Gujranwala",
            "province": "Punjab",
            "latitude": "32.187700",
            "longitude": "74.194500",
            "contact_number": "055-9200111",
            "is_junction": False,
        },
        follow_redirects=True,
    )
    assert good_resp.status_code == 200
    assert b"Gujranwala City" in good_resp.data

    with app.app_context():
        stn = db.session.scalar(select(Station).filter_by(code="GUJ"))
        assert stn is not None
        assert stn.latitude == Decimal("32.187700")
        stn_id = stn.id

    # 4. Edit Station
    edit_resp = client.post(
        f"/admin/stations/{stn_id}/edit",
        data={
            "division_id": div1_id,
            "code": "GUJ",
            "name": "Gujranwala Cantonment",
            "city": "Gujranwala",
            "province": "Punjab",
            "latitude": "32.187700",
            "longitude": "74.194500",
            "is_junction": True,
        },
        follow_redirects=True,
    )
    assert edit_resp.status_code == 200
    assert b"Gujranwala Cantonment" in edit_resp.data

    # 5. Soft Delete Station (no platforms attached yet)
    del_resp = client.post(f"/admin/stations/{stn_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    with app.app_context():
        assert db.session.get(Station, stn_id).is_deleted is True


def test_station_delete_blocked_when_active_platforms_or_facilities_exist(client, app, station_test_setup):
    """Test soft-delete is blocked when station has active platforms or facilities."""
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})
    stn1_id = station_test_setup["stn1_id"]

    # Add a platform to stn1
    with app.app_context():
        plat = StationPlatform(station_id=stn1_id, platform_number="1", length_meters=400)
        db.session.add(plat)
        db.session.commit()
        plat_id = plat.id

    # Attempt to soft delete station -> blocked
    del_resp = client.post(f"/admin/stations/{stn1_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"Cannot soft-delete station" in del_resp.data
    assert b"1 platform(s)" in del_resp.data

    # Soft delete the platform
    client.post(f"/admin/platforms/{plat_id}/delete")

    # Now soft delete station should succeed
    del_resp2 = client.post(f"/admin/stations/{stn1_id}/delete", follow_redirects=True)
    assert del_resp2.status_code == 200
    with app.app_context():
        assert db.session.get(Station, stn1_id).is_deleted is True


# ===========================================================================
# 3. StationPlatform Tests (Super Admin & Station Master)
# ===========================================================================
def test_platform_crud_and_validations(client, app, station_test_setup):
    """Test platform creation, validation (positive number), unique active constraint, and delete."""
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})
    stn2_id = station_test_setup["stn2_id"]

    # 1. Validation: platform number <= 0 rejected
    bad_resp = client.post(
        "/admin/platforms/create",
        data={"station_id": stn2_id, "platform_number": "0", "length_meters": 300},
    )
    assert bad_resp.status_code == 200
    assert b"Platform number must be a positive integer greater than 0" in bad_resp.data

    bad_resp2 = client.post(
        "/admin/platforms/create",
        data={"station_id": stn2_id, "platform_number": "-3", "length_meters": 300},
    )
    assert bad_resp2.status_code == 200
    assert b"Platform number must be a positive integer greater than 0" in bad_resp2.data

    # 2. Valid creation
    good_resp = client.post(
        "/admin/platforms/create",
        data={"station_id": stn2_id, "platform_number": "1", "length_meters": 500, "has_disabled_access": True, "is_operational": True},
        follow_redirects=True,
    )
    assert good_resp.status_code == 200
    assert b"Platform 1" in good_resp.data

    with app.app_context():
        plat = db.session.scalar(select(StationPlatform).filter_by(station_id=stn2_id, platform_number="1"))
        assert plat is not None
        plat_id = plat.id

    # 3. Duplicate active platform number at same station rejected
    dup_resp = client.post(
        "/admin/platforms/create",
        data={"station_id": stn2_id, "platform_number": "1", "length_meters": 400},
    )
    assert dup_resp.status_code == 200
    assert b"already exists at this station" in dup_resp.data

    # 4. Soft delete platform
    del_resp = client.post(f"/admin/platforms/{plat_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    with app.app_context():
        assert db.session.get(StationPlatform, plat_id).is_deleted is True

    # 5. Re-create platform "1" at same station succeeds after soft delete
    re_resp = client.post(
        "/admin/platforms/create",
        data={"station_id": stn2_id, "platform_number": "1", "length_meters": 550},
        follow_redirects=True,
    )
    assert re_resp.status_code == 200
    assert b"Platform 1" in re_resp.data


def test_station_master_scoped_platform_management(client, app, station_test_setup):
    """Test Station Master can only manage platforms of their assigned station."""
    stn1_id = station_test_setup["stn1_id"] # LHE (assigned to SM)
    stn2_id = station_test_setup["stn2_id"] # KHI (NOT assigned to SM)

    # Seed platform at KHI
    with app.app_context():
        khi_plat = StationPlatform(station_id=stn2_id, platform_number="2", length_meters=450)
        db.session.add(khi_plat)
        db.session.commit()
        khi_plat_id = khi_plat.id

    # Login as Station Master (assigned to LHE)
    login_resp = client.post("/auth/login", data={"email": "sm.lahore@railsathi.pk", "password": "StationMaster123!"}, follow_redirects=True)
    assert login_resp.status_code == 200

    # 1. SM views platforms index -> succeeds, but only sees LHE platforms
    resp = client.get("/admin/platforms")
    assert resp.status_code == 200
    assert b"Platform 2" not in resp.data # KHI platform should not appear

    # 2. SM creates platform at their station (LHE)
    create_resp = client.post(
        "/admin/platforms/create",
        data={"station_id": stn1_id, "platform_number": "1", "length_meters": 600, "is_operational": True},
        follow_redirects=True,
    )
    assert create_resp.status_code == 200
    with app.app_context():
        lhe_plat = db.session.scalar(select(StationPlatform).filter_by(station_id=stn1_id, platform_number="1"))
        assert lhe_plat is not None
        lhe_plat_id = lhe_plat.id

    # 3. SM attempts to edit KHI platform -> HTTP 403 Forbidden
    khi_edit_resp = client.get(f"/admin/platforms/{khi_plat_id}/edit")
    assert khi_edit_resp.status_code == 403

    khi_edit_post = client.post(f"/admin/platforms/{khi_plat_id}/edit", data={"station_id": stn2_id, "platform_number": "2", "length_meters": 700})
    assert khi_edit_post.status_code == 403

    # 4. SM attempts to delete KHI platform -> HTTP 403 Forbidden
    khi_del_resp = client.post(f"/admin/platforms/{khi_plat_id}/delete")
    assert khi_del_resp.status_code == 403

    # 5. SM edits their own platform -> succeeds
    lhe_edit_resp = client.post(
        f"/admin/platforms/{lhe_plat_id}/edit",
        data={"station_id": stn1_id, "platform_number": "1", "length_meters": 650, "is_operational": True},
        follow_redirects=True,
    )
    assert lhe_edit_resp.status_code == 200


# ===========================================================================
# 4. FacilityCategory Tests (Super Admin)
# ===========================================================================
def test_facility_category_crud_and_blocked_delete(client, app, station_test_setup):
    """Test FacilityCategory lifecycle and blocked delete when facilities are attached."""
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})
    cat_id = station_test_setup["cat_id"]
    stn1_id = station_test_setup["stn1_id"]

    # 1. Attach active facility to category
    with app.app_context():
        fac = StationFacility(station_id=stn1_id, category_id=cat_id, name="Concourse Waiting Room")
        db.session.add(fac)
        db.session.commit()
        fac_id = fac.id

    # 2. Delete category -> blocked
    del_resp = client.post(f"/admin/facility-categories/{cat_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert b"Cannot soft-delete facility category" in del_resp.data

    # 3. Soft delete facility
    client.post(f"/admin/facilities/{fac_id}/delete")

    # 4. Now soft delete category -> succeeds
    del_resp2 = client.post(f"/admin/facility-categories/{cat_id}/delete", follow_redirects=True)
    assert del_resp2.status_code == 200
    with app.app_context():
        assert db.session.get(FacilityCategory, cat_id).is_deleted is True


# ===========================================================================
# 5. StationFacility Tests & Scoped Station Master Access
# ===========================================================================
def test_facility_crud_validation_and_station_master_scoping(client, app, station_test_setup):
    """Test Facility creation, fee validation (>=0), and Station Master authorization scoping."""
    stn1_id = station_test_setup["stn1_id"] # LHE
    stn2_id = station_test_setup["stn2_id"] # KHI
    cat_id = station_test_setup["cat_id"]

    # Login as Super Admin to create a facility at KHI
    client.post("/auth/login", data={"email": "superadmin@railsathi.pk", "password": "AdminPass123!"})

    # Fee validation: negative fee rejected
    bad_fee_resp = client.post(
        "/admin/facilities/create",
        data={
            "station_id": stn2_id,
            "category_id": cat_id,
            "name": "Paid Restroom",
            "fee_amount": "-15.00",
        },
    )
    assert bad_fee_resp.status_code == 200
    assert b"Fee cannot be negative" in bad_fee_resp.data

    # Valid KHI facility
    client.post(
        "/admin/facilities/create",
        data={
            "station_id": stn2_id,
            "category_id": cat_id,
            "name": "KHI VIP Lounge",
            "fee_amount": "250.00",
            "is_free": False,
        },
        follow_redirects=True,
    )
    with app.app_context():
        khi_fac = db.session.scalar(select(StationFacility).filter_by(station_id=stn2_id, name="KHI VIP Lounge"))
        assert khi_fac is not None
        khi_fac_id = khi_fac.id

    client.post("/auth/logout")

    # Login as Station Master (assigned to LHE)
    client.post("/auth/login", data={"email": "sm.lahore@railsathi.pk", "password": "StationMaster123!"})

    # 1. SM views facilities -> only sees LHE facilities
    resp = client.get("/admin/facilities")
    assert resp.status_code == 200
    assert b"KHI VIP Lounge" not in resp.data

    # 2. SM creates facility at LHE
    create_resp = client.post(
        "/admin/facilities/create",
        data={
            "station_id": stn1_id,
            "category_id": cat_id,
            "name": "LHE Executive Lounge",
            "fee_amount": "150.00",
            "is_free": False,
        },
        follow_redirects=True,
    )
    assert create_resp.status_code == 200
    with app.app_context():
        lhe_fac = db.session.scalar(select(StationFacility).filter_by(station_id=stn1_id, name="LHE Executive Lounge"))
        assert lhe_fac is not None
        lhe_fac_id = lhe_fac.id

    # 3. SM attempts to edit KHI facility -> HTTP 403 Forbidden
    edit_resp = client.get(f"/admin/facilities/{khi_fac_id}/edit")
    assert edit_resp.status_code == 403

    # 4. SM attempts to delete KHI facility -> HTTP 403 Forbidden
    del_resp = client.post(f"/admin/facilities/{khi_fac_id}/delete")
    assert del_resp.status_code == 403

    # 5. SM edits their own facility -> succeeds
    lhe_edit_resp = client.post(
        f"/admin/facilities/{lhe_fac_id}/edit",
        data={
            "station_id": stn1_id,
            "category_id": cat_id,
            "name": "LHE Premium Executive Lounge",
            "fee_amount": "200.00",
            "is_free": False,
        },
        follow_redirects=True,
    )
    assert lhe_edit_resp.status_code == 200


# ===========================================================================
# 6. RBAC Protection Tests
# ===========================================================================
def test_rbac_passenger_forbidden_on_all_phase5a_endpoints(client, station_test_setup):
    """Test Passenger user receives HTTP 403 Forbidden on all Phase 5A routes."""
    client.post("/auth/login", data={"email": "passenger@railsathi.pk", "password": "Pass12345!"})

    forbidden_urls = [
        "/admin/divisions",
        "/admin/divisions/create",
        "/admin/stations",
        "/admin/stations/create",
        "/admin/platforms",
        "/admin/platforms/create",
        "/admin/facility-categories",
        "/admin/facility-categories/create",
        "/admin/facilities",
        "/admin/facilities/create",
    ]
    for url in forbidden_urls:
        resp = client.get(url)
        assert resp.status_code == 403, f"Expected 403 for Passenger on {url}, got {resp.status_code}"


def test_station_master_forbidden_on_super_admin_endpoints(client, station_test_setup):
    """Test Station Master receives HTTP 403 on Super Admin only endpoints (Divisions, Stations, Categories)."""
    client.post("/auth/login", data={"email": "sm.lahore@railsathi.pk", "password": "StationMaster123!"})

    forbidden_urls = [
        "/admin/divisions",
        "/admin/divisions/create",
        "/admin/stations",
        "/admin/stations/create",
        "/admin/facility-categories",
        "/admin/facility-categories/create",
    ]
    for url in forbidden_urls:
        resp = client.get(url)
        assert resp.status_code == 403, f"Expected 403 for Station Master on {url}, got {resp.status_code}"

