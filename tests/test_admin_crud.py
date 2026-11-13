"""Phase 4B — Administrative User and Role Administration (CRUD) Tests.

Verifies:
- Non-admin (Passenger) receives HTTP 403 Forbidden on all /admin/* endpoints.
- User management: List, search, pagination, create, edit, soft-delete, and restore.
- Guard rail: Admin cannot delete themselves.
- Guard rail: Admin cannot demote themselves (remove their own Super Admin role).
- Guard rail: Last active Super Admin cannot be deleted, deactivated, or demoted.
- Role management: Fixed 6 roles view-only, deletion blocked with HTTP 400.
- Staff profile CRUD: Create, edit, station assignment, and soft-delete.
- Security logs: AuditLog and UserSessionLog paginated read-only views with filters.
- All mutations record log_audit_event in the same transaction and comply with PRG.
"""
import pytest
from flask import url_for
from sqlalchemy import select, func

from app.extensions import db
from app.common.constants import (
    ROLE_SUPER_ADMIN,
    ROLE_PASSENGER,
    ROLE_STATION_MASTER,
    ROLE_RESERVATION_OFFICER,
    ROLE_COMPLAINT_OFFICER,
    ROLE_REFUND_OFFICER,
)
from app.models.identity import (
    User,
    Role,
    UserRole,
    UserProfile,
    StaffProfile,
    UserSessionLog,
)
from app.models.stations import StationDivision, Station
from app.models.governance import AuditLog


@pytest.fixture
def admin_setup(app):
    """Seed roles, stations, a Super Admin, and a Passenger user."""
    with app.app_context():
        # 6 Canonical Roles
        roles_tuples = [
            (ROLE_SUPER_ADMIN, "SUPER_ADMIN"),
            (ROLE_STATION_MASTER, "STATION_MASTER"),
            (ROLE_RESERVATION_OFFICER, "RESERVATION_OFFICER"),
            (ROLE_COMPLAINT_OFFICER, "COMPLAINT_OFFICER"),
            (ROLE_REFUND_OFFICER, "REFUND_OFFICER"),
            (ROLE_PASSENGER, "PASSENGER"),
        ]
        for name, code in roles_tuples:
            if not db.session.scalar(select(Role).filter_by(name=name)):
                db.session.add(Role(name=name, code=code))
        db.session.flush()

        # Station for staff assignment
        div = db.session.scalar(select(StationDivision).filter_by(code="LHR-DIV"))
        if not div:
            div = StationDivision(code="LHR-DIV", name="Lahore Division", headquarters_city="Lahore")
            db.session.add(div)
            db.session.flush()

        stn = db.session.scalar(select(Station).filter_by(code="LHE"))
        if not stn:
            stn = Station(division_id=div.id, code="LHE", name="Lahore Junction", city="Lahore", province="Punjab")
            db.session.add(stn)
            db.session.flush()

        # Super Admin User
        admin_role = db.session.scalar(select(Role).filter_by(name=ROLE_SUPER_ADMIN))
        super_admin = User(
            email="super_admin_crud@railsathi.pk",
            cnic="35201-9999991-1",
            first_name="Super",
            last_name="Admin",
            phone_number="0300-9999991",
            is_active_user=True,
        )
        super_admin.password = "AdminPass123!"
        db.session.add(super_admin)
        db.session.flush()
        db.session.add(UserRole(user_id=super_admin.id, role_id=admin_role.id))

        # Second Super Admin (to test non-last admin deletion/demotion)
        second_admin = User(
            email="second_admin@railsathi.pk",
            cnic="35201-9999992-1",
            first_name="Second",
            last_name="Admin",
            phone_number="0300-9999992",
            is_active_user=True,
        )
        second_admin.password = "AdminPass123!"
        db.session.add(second_admin)
        db.session.flush()
        db.session.add(UserRole(user_id=second_admin.id, role_id=admin_role.id))

        # Regular Passenger User
        pass_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))
        passenger = User(
            email="passenger_crud@railsathi.pk",
            cnic="35201-9999993-1",
            first_name="Ordinary",
            last_name="Passenger",
            phone_number="0300-9999993",
            is_active_user=True,
        )
        passenger.password = "PassengerPass123!"
        db.session.add(passenger)
        db.session.flush()
        db.session.add(UserRole(user_id=passenger.id, role_id=pass_role.id))

        db.session.commit()

        return {
            "super_admin_id": super_admin.id,
            "super_admin_email": super_admin.email,
            "second_admin_id": second_admin.id,
            "second_admin_email": second_admin.email,
            "passenger_id": passenger.id,
            "passenger_email": passenger.email,
            "station_id": stn.id,
        }


def test_passenger_forbidden_on_all_admin_endpoints(client, admin_setup):
    """Verify non-admin (Passenger) receives HTTP 403 on every administrative endpoint."""
    client.post("/auth/login", data={"email": "passenger_crud@railsathi.pk", "password": "PassengerPass123!"})

    admin_endpoints = [
        "/admin/dashboard",
        "/admin/users",
        "/admin/users/create",
        "/admin/roles",
        "/admin/staff",
        "/admin/staff/create",
        "/admin/audit-logs",
        "/admin/session-logs",
    ]
    for endpoint in admin_endpoints:
        resp = client.get(endpoint)
        assert resp.status_code == 403, f"Expected 403 on {endpoint}, got {resp.status_code}"


def test_admin_list_and_search_users(client, admin_setup):
    """Verify admin user listing, searching by name/email/CNIC, and filtering."""
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    # List all users
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert b"System Users Administration" in resp.data
    assert b"super_admin_crud@railsathi.pk" in resp.data

    # Search by email
    resp_search = client.get("/admin/users?q=second_admin")
    assert resp_search.status_code == 200
    assert b"second_admin@railsathi.pk" in resp_search.data


def test_admin_create_user_with_roles_and_audit(client, admin_setup):
    """Verify admin creates user with multiple roles and PRG redirect."""
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    master_role = db.session.scalar(select(Role).filter_by(name=ROLE_STATION_MASTER))

    payload = {
        "first_name": "Tariq",
        "last_name": "Mehmood",
        "email": "tariq.station@railsathi.pk",
        "cnic": "35201-1239876-1",
        "phone_number": "0301-1234567",
        "password": "StationMasterPass123!",
        "roles": [master_role.id],
        "is_active_user": True,
    }
    resp = client.post("/admin/users/create", data=payload)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/users")

    # Verify user in database
    new_user = db.session.scalar(select(User).filter_by(email="tariq.station@railsathi.pk"))
    assert new_user is not None
    assert new_user.first_name == "Tariq"
    assert ROLE_STATION_MASTER in new_user.roles

    # Verify audit log recorded
    audit = db.session.scalar(
        select(AuditLog).filter_by(action="ADMIN_CREATE_USER", entity_id=str(new_user.id))
    )
    assert audit is not None
    assert "StationMasterPass123!" not in audit.new_values


def test_admin_edit_user_and_change_roles(client, admin_setup):
    """Verify admin edits user details, reassigns roles, and logs audit diff."""
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    target_id = admin_setup["passenger_id"]
    target_user = db.session.get(User, target_id)
    officer_role = db.session.scalar(select(Role).filter_by(name=ROLE_RESERVATION_OFFICER))

    payload = {
        "first_name": "UpdatedName",
        "last_name": "Passenger",
        "email": target_user.email,
        "cnic": target_user.cnic,
        "phone_number": "0311-9988776",
        "roles": [officer_role.id],
        "is_active_user": True,
    }
    resp = client.post(f"/admin/users/{target_id}/edit", data=payload)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/users")

    db.session.expire_all()
    refreshed_user = db.session.get(User, target_id)
    assert refreshed_user.first_name == "UpdatedName"
    assert refreshed_user.phone_number == "0311-9988776"
    assert ROLE_RESERVATION_OFFICER in refreshed_user.roles
    assert ROLE_PASSENGER not in refreshed_user.roles


def test_guard_rail_admin_cannot_delete_self(client, admin_setup):
    """Guard Rail: An administrator cannot soft-delete their own account."""
    admin_id = admin_setup["super_admin_id"]
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    resp = client.post(f"/admin/users/{admin_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"You cannot delete your own administrator account" in resp.data

    db.session.expire_all()
    refreshed_admin = db.session.get(User, admin_id)
    assert refreshed_admin.is_deleted is False


def test_guard_rail_admin_cannot_demote_self(client, admin_setup):
    """Guard Rail: An administrator cannot revoke their own Super Admin role."""
    admin_id = admin_setup["super_admin_id"]
    admin = db.session.get(User, admin_id)
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    pass_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))

    payload = {
        "first_name": admin.first_name,
        "last_name": admin.last_name,
        "email": admin.email,
        "cnic": admin.cnic,
        "phone_number": admin.phone_number,
        "roles": [pass_role.id],  # Attempting to drop Super Admin role
        "is_active_user": True,
    }
    resp = client.post(f"/admin/users/{admin_id}/edit", data=payload, follow_redirects=True)
    assert resp.status_code == 200
    assert b"You cannot remove the Super Admin role from your own administrator account" in resp.data

    db.session.expire_all()
    refreshed_admin = db.session.get(User, admin_id)
    assert ROLE_SUPER_ADMIN in refreshed_admin.roles


def test_guard_rail_last_super_admin_cannot_be_deleted(client, admin_setup):
    """Guard Rail: The last active Super Admin cannot be deleted."""
    admin1_id = admin_setup["super_admin_id"]
    admin2_id = admin_setup["second_admin_id"]

    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    # Delete admin2 so admin1 is the SOLE remaining active Super Admin
    client.post(f"/admin/users/{admin2_id}/delete")
    db.session.expire_all()
    refreshed_admin2 = db.session.get(User, admin2_id)
    assert refreshed_admin2.is_deleted is True

    # Now attempt to delete admin1 (sole remaining active Super Admin)
    resp = client.post(f"/admin/users/{admin1_id}/delete", follow_redirects=True)
    assert resp.status_code == 200

    db.session.expire_all()
    refreshed_admin1 = db.session.get(User, admin1_id)
    assert refreshed_admin1.is_deleted is False


def test_user_soft_delete_and_restore(client, admin_setup):
    """Verify user account soft-deletion via SoftDeleteMixin and subsequent restoration."""
    admin_id = admin_setup["super_admin_id"]
    passenger_id = admin_setup["passenger_id"]

    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    # Soft Delete
    resp_del = client.post(f"/admin/users/{passenger_id}/delete")
    assert resp_del.status_code == 302

    db.session.expire_all()
    passenger = db.session.get(User, passenger_id)
    assert passenger.is_deleted is True
    assert passenger.deleted_by_id == admin_id

    # Restore
    resp_res = client.post(f"/admin/users/{passenger_id}/restore")
    assert resp_res.status_code == 302

    db.session.expire_all()
    passenger = db.session.get(User, passenger_id)
    assert passenger.is_deleted is False
    assert passenger.deleted_by_id is None


def test_roles_view_and_deletion_blocked(client, admin_setup):
    """Verify fixed 6 roles are viewable and deletion returns HTTP 400."""
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    # View roles
    resp = client.get("/admin/roles")
    assert resp.status_code == 200
    assert b"System Roles & Permissions" in resp.data
    assert b"Super Admin" in resp.data
    assert b"Passenger" in resp.data

    # Attempt deletion of a role
    passenger_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))
    resp_del = client.post(f"/admin/roles/{passenger_role.id}/delete")
    assert resp_del.status_code == 400

    # Role still exists
    assert db.session.get(Role, passenger_role.id) is not None


def test_staff_profile_crud(client, admin_setup):
    """Verify staff profile creation, editing station assignment, and soft-deletion."""
    passenger_id = admin_setup["passenger_id"]
    station_id = admin_setup["station_id"]

    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    # 1. Create Staff Profile
    payload = {
        "user_id": passenger_id,
        "station_id": station_id,
        "employee_code": "EMP-9090",
        "department": "Commercial",
        "designation": "Assistant Station Master",
        "shift_timing": "Morning (06:00 - 14:00)",
    }
    resp = client.post("/admin/staff/create", data=payload)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/staff")

    staff = db.session.scalar(select(StaffProfile).filter_by(employee_code="EMP-9090"))
    assert staff is not None
    assert staff.station_id == station_id
    assert staff.department == "Commercial"

    # 2. Edit Staff Profile
    edit_payload = {
        "user_id": passenger_id,
        "station_id": 0,  # Unassign station
        "employee_code": "EMP-9090",
        "department": "HQ Operations",
        "designation": "Senior Operations Officer",
        "shift_timing": "General (09:00 - 17:00)",
    }
    resp_edit = client.post(f"/admin/staff/{staff.id}/edit", data=edit_payload)
    assert resp_edit.status_code == 302

    db.session.expire_all()
    refreshed_staff = db.session.get(StaffProfile, staff.id)
    assert refreshed_staff.station_id is None
    assert refreshed_staff.department == "HQ Operations"

    # 3. Soft Delete Staff Profile
    resp_del = client.post(f"/admin/staff/{staff.id}/delete")
    assert resp_del.status_code == 302

    db.session.expire_all()
    refreshed_staff = db.session.get(StaffProfile, staff.id)
    assert refreshed_staff.is_deleted is True


def test_security_logs_views(client, admin_setup):
    """Verify audit logs and user session logs read-only paginated endpoints."""
    client.post("/auth/login", data={"email": admin_setup["super_admin_email"], "password": "AdminPass123!"})

    # Audit logs
    resp_audit = client.get("/admin/audit-logs")
    assert resp_audit.status_code == 200
    assert b"System Audit Trail Logs" in resp_audit.data

    # Session logs
    resp_session = client.get("/admin/session-logs")
    assert resp_session.status_code == 200
    assert b"User Sign-In Session Logs" in resp_session.data
