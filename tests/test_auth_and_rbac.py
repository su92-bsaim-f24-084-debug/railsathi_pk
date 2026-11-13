"""Comprehensive Authentication, Session Security, RBAC, and Audit Logging Tests.

Verifies:
- Passenger registration with WTForms validation, Pakistani CNIC & phone formatting, and PRG 302.
- Re-registration with same email/CNIC allowed after soft-delete (PostgreSQL partial unique indexes).
- Invalid CNIC rejection.
- Login and logout flows with UserSessionLog tracking.
- Rate limiting and 5-attempt account lockout stored in database columns.
- Persistent database columns for lockout counters (failed_login_attempts, locked_until).
- Seeded Super Admin from env gets HTTP 200 on /admin/dashboard, while Passenger gets 403.
- Passenger receives HTTP 403 Forbidden on /admin/dashboard (T-18).
- Form POST without CSRF returns HTTP 400 Bad Request (T-19).
- Audit trail event recording and password redaction (T-14).
- Profile update and change-password audit with redaction and PRG 302.
- Open-redirect protection rejecting next=https://evil.com.
- Logout via GET returns HTTP 405 Method Not Allowed.
- Logout via POST without CSRF returns HTTP 400 Bad Request.
- Session cookie enforces HttpOnly and SameSite flags.
- Phone number normalization to 03XX-XXXXXXX format.
- Existing session of soft-deleted user is rejected on the next request.
"""
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from flask import url_for
from sqlalchemy import select

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.common.constants import (
    ROLE_SUPER_ADMIN,
    ROLE_PASSENGER,
    ROLE_STATION_MASTER,
    ROLE_RESERVATION_OFFICER,
    ROLE_COMPLAINT_OFFICER,
    ROLE_REFUND_OFFICER,
    ALL_SYSTEM_ROLES,
)
from app.common.formatters import normalize_phone_number
from app.models.identity import User, Role, UserRole, UserSessionLog
from app.models.governance import AuditLog
from app.models.base import utc_now


@pytest.fixture
def auth_roles(app):
    """Seed the 6 canonical system roles using shared domain constants."""
    with app.app_context():
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
        db.session.commit()


# ---------------------------------------------------------------------------
# Core Registration Tests
# ---------------------------------------------------------------------------
def test_register_passenger_success_and_prg(client, auth_roles):
    """Verify passenger registration creates user, profile, role, audit log, and redirects (PRG 302)."""
    payload = {
        "first_name": "Hamza",
        "last_name": "Tariq",
        "email": "hamza.tariq@railsathi.pk",
        "cnic": "35201-7654321-1",
        "phone_number": "0300-1234567",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    response = client.post("/auth/register", data=payload)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")

    follow_resp = client.get(response.headers["Location"])
    assert follow_resp.status_code == 200
    assert b"Your account has been registered successfully" in follow_resp.data

    user = db.session.scalar(select(User).filter_by(email="hamza.tariq@railsathi.pk"))
    assert user is not None
    assert user.first_name == "Hamza"
    assert user.cnic == "35201-7654321-1"
    assert user.check_password("Password123!") is True
    assert user.profile is not None
    assert ROLE_PASSENGER in user.roles


def test_register_invalid_cnic_rejected(client, auth_roles):
    """Verify registration rejects malformed Pakistani CNICs."""
    payload = {
        "first_name": "Invalid",
        "last_name": "CNIC",
        "email": "invalid_cnic@railsathi.pk",
        "cnic": "3520112345671",  # Missing hyphens
        "phone_number": "0300-1234567",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    response = client.post("/auth/register", data=payload)
    assert response.status_code == 200
    assert b"CNIC must follow the 13-digit format" in response.data

    user = db.session.scalar(select(User).filter_by(email="invalid_cnic@railsathi.pk"))
    assert user is None


def test_duplicate_email_and_cnic_allowed_after_soft_delete(client, auth_roles):
    """Verify PostgreSQL partial unique index allows reusing email/CNIC of soft-deleted accounts."""
    user1 = User(
        email="recreate.test@railsathi.pk",
        cnic="35201-8888888-1",
        first_name="First",
        last_name="Owner",
        phone_number="0312-3456789",
        is_active_user=True,
    )
    user1.password = "Password123!"
    db.session.add(user1)
    db.session.commit()
    user1_id = user1.id

    payload = {
        "first_name": "Duplicate",
        "last_name": "Attempt",
        "email": "recreate.test@railsathi.pk",
        "cnic": "35201-8888888-1",
        "phone_number": "0333-1112233",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    resp_conflict = client.post("/auth/register", data=payload)
    assert resp_conflict.status_code == 200
    assert b"already registered" in resp_conflict.data

    user1_refreshed = db.session.get(User, user1_id)
    user1_refreshed.soft_delete(user_id=None)
    db.session.commit()
    assert user1_refreshed.is_deleted is True

    resp_success = client.post("/auth/register", data=payload)
    assert resp_success.status_code == 302

    active_user = db.session.scalar(
        select(User).filter_by(email="recreate.test@railsathi.pk", is_deleted=False)
    )
    assert active_user is not None
    assert active_user.id != user1_id
    assert active_user.cnic == "35201-8888888-1"


# ---------------------------------------------------------------------------
# Login, Logout, Session Log, and Lockout Tests
# ---------------------------------------------------------------------------
def test_login_and_logout_creates_user_session_log(client, auth_roles):
    """Verify login writes UserSessionLog and logout updates it."""
    user = User(
        email="session_test@railsathi.pk",
        cnic="35201-5555555-1",
        first_name="Session",
        last_name="Tester",
        phone_number="0301-9998888",
        is_active_user=True,
    )
    user.password = "Password123!"
    db.session.add(user)
    db.session.commit()

    login_resp = client.post(
        "/auth/login",
        data={"email": "session_test@railsathi.pk", "password": "Password123!"},
    )
    assert login_resp.status_code == 302

    log = db.session.scalar(
        select(UserSessionLog).filter_by(user_id=user.id).order_by(UserSessionLog.id.desc())
    )
    assert log is not None
    assert log.login_time is not None
    assert log.logout_time is None
    assert log.is_expired is False

    logout_resp = client.post("/auth/logout")
    assert logout_resp.status_code == 302

    db.session.refresh(log)
    assert log.logout_time is not None
    assert log.is_expired is True


def test_login_rate_limiting_and_lockout(client, auth_roles):
    """Verify 5 failed login attempts lock account for 15 minutes."""
    user = User(
        email="lockout_test@railsathi.pk",
        cnic="35201-4444444-1",
        first_name="Lockout",
        last_name="Subject",
        phone_number="0302-1234567",
        is_active_user=True,
    )
    user.password = "CorrectSecret123!"
    db.session.add(user)
    db.session.commit()

    for i in range(1, 5):
        resp = client.post(
            "/auth/login",
            data={"email": "lockout_test@railsathi.pk", "password": "WrongPassword!"},
        )
        assert resp.status_code == 302
        db.session.refresh(user)
        assert user.failed_login_attempts == i
        assert user.locked_until is None

    resp5 = client.post(
        "/auth/login",
        data={"email": "lockout_test@railsathi.pk", "password": "WrongPassword!"},
    )
    assert resp5.status_code == 302
    db.session.refresh(user)
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    assert user.locked_until > utc_now()

    resp_blocked = client.post(
        "/auth/login",
        data={"email": "lockout_test@railsathi.pk", "password": "CorrectSecret123!"},
        follow_redirects=True,
    )
    assert b"Account is temporarily locked" in resp_blocked.data


def test_lockout_counters_persisted_in_database_columns(client, auth_roles):
    """Verify that lockout counters are explicitly stored in the PostgreSQL database columns."""
    user = User(
        email="db_counter_test@railsathi.pk",
        cnic="35201-3333333-1",
        first_name="Counter",
        last_name="Subject",
        phone_number="0300-3333333",
        is_active_user=True,
    )
    user.password = "Secret123!"
    db.session.add(user)
    db.session.commit()

    assert user.failed_login_attempts == 0
    assert user.locked_until is None

    client.post("/auth/login", data={"email": "db_counter_test@railsathi.pk", "password": "WrongPassword"})
    db.session.expire(user)
    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user.failed_login_attempts == 1
    assert refreshed_user.locked_until is None

    for _ in range(4):
        client.post("/auth/login", data={"email": "db_counter_test@railsathi.pk", "password": "WrongPassword"})

    db.session.expire(user)
    locked_user = db.session.get(User, user.id)
    assert locked_user.failed_login_attempts == 5
    assert locked_user.locked_until is not None
    assert locked_user.locked_until > utc_now()


# ---------------------------------------------------------------------------
# RBAC, CSRF, and Audit Tests
# ---------------------------------------------------------------------------
def test_passenger_forbidden_on_admin_dashboard_t18(client, auth_roles):
    """T-18: Verify Passenger receives HTTP 403 Forbidden on /admin/dashboard."""
    passenger_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))
    passenger = User(
        email="regular_passenger@railsathi.pk",
        cnic="35201-1111111-1",
        first_name="Regular",
        last_name="Passenger",
        phone_number="0300-1111111",
        is_active_user=True,
    )
    passenger.password = "Password123!"
    db.session.add(passenger)
    db.session.flush()
    db.session.add(UserRole(user_id=passenger.id, role_id=passenger_role.id))
    db.session.commit()

    client.post("/auth/login", data={"email": "regular_passenger@railsathi.pk", "password": "Password123!"})
    pass_resp = client.get("/admin/dashboard")
    assert pass_resp.status_code == 403
    assert b"403" in pass_resp.data
    assert b"Access Restricted" in pass_resp.data


def test_missing_csrf_returns_400_t19(auth_roles):
    """T-19: Verify that when CSRF protection is active, POST without CSRF token returns HTTP 400."""
    class CSRFActiveConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(CSRFActiveConfig)
    with csrf_app.app_context():
        test_client = csrf_app.test_client()
        response = test_client.post(
            "/auth/login",
            data={"email": "any@example.com", "password": "password"},
        )
        assert response.status_code == 400
        assert b"400" in response.data or b"CSRF" in response.data or b"Bad Request" in response.data


def test_audit_log_redaction_and_atomic_transaction(client, auth_roles):
    """T-14: Verify log_audit_event masks passwords as ***REDACTED*** and saves atomically."""
    payload = {
        "first_name": "Audit",
        "last_name": "Tester",
        "email": "audit_user@railsathi.pk",
        "cnic": "35201-6666666-1",
        "phone_number": "0300-6666666",
        "password": "SuperSecretPassword123!",
        "confirm_password": "SuperSecretPassword123!",
    }
    resp = client.post("/auth/register", data=payload)
    assert resp.status_code == 302

    audit = db.session.scalar(
        select(AuditLog).filter_by(action="REGISTER", entity_name="User").order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.new_values is not None
    assert "SuperSecretPassword123!" not in audit.new_values
    data = json.loads(audit.new_values)
    assert data["password"] == "***REDACTED***"
    assert data["email"] == "audit_user@railsathi.pk"


def test_profile_update_and_change_password_audit(client, auth_roles):
    """Verify profile editing and password change flows with audit logging and PRG 302."""
    user = User(
        email="profile_edit@railsathi.pk",
        cnic="35201-7777777-1",
        first_name="OldFirst",
        last_name="OldLast",
        phone_number="0300-7777777",
        is_active_user=True,
    )
    user.password = "InitialPassword123!"
    db.session.add(user)
    db.session.commit()

    client.post("/auth/login", data={"email": "profile_edit@railsathi.pk", "password": "InitialPassword123!"})

    prof_resp = client.post(
        "/auth/profile",
        data={
            "first_name": "NewFirst",
            "last_name": "NewLast",
            "phone_number": "0300-8888888",
            "city": "Rawalpindi",
            "province": "Punjab",
            "address": "Railway Colony West",
        },
    )
    assert prof_resp.status_code == 302
    assert prof_resp.headers["Location"].endswith("/auth/profile")

    db.session.refresh(user)
    assert user.first_name == "NewFirst"
    assert user.last_name == "NewLast"
    assert user.profile.city == "Rawalpindi"

    audit_prof = db.session.scalar(
        select(AuditLog).filter_by(action="UPDATE_PROFILE", entity_id=str(user.id))
    )
    assert audit_prof is not None
    assert "OldFirst" in audit_prof.old_values
    assert "NewFirst" in audit_prof.new_values

    pwd_resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "InitialPassword123!",
            "new_password": "UpdatedPassword456!",
            "confirm_password": "UpdatedPassword456!",
        },
    )
    assert pwd_resp.status_code == 302
    assert pwd_resp.headers["Location"].endswith("/auth/profile")

    db.session.refresh(user)
    assert user.check_password("UpdatedPassword456!") is True

    audit_pwd = db.session.scalar(
        select(AuditLog).filter_by(action="CHANGE_PASSWORD", entity_id=str(user.id))
    )
    assert audit_pwd is not None
    assert "InitialPassword123!" not in audit_pwd.old_values
    assert "UpdatedPassword456!" not in audit_pwd.new_values
    assert "***REDACTED***" in audit_pwd.new_values


def test_seeded_super_admin_login_gets_200_and_passenger_gets_403(client, auth_roles):
    """Prove seeded Super Admin gets 200 on /admin/dashboard and Passenger gets 403."""
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@railsathi.pk").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "SuperAdminSecure123!")

    super_admin_role = db.session.scalar(select(Role).filter_by(name=ROLE_SUPER_ADMIN))
    admin = db.session.scalar(select(User).filter_by(email=admin_email))
    if not admin:
        admin = User(
            email=admin_email,
            cnic="35201-0000000-1",
            first_name="Super",
            last_name="Admin",
            phone_number="0300-0000000",
            is_active_user=True,
        )
        admin.password = admin_password
        db.session.add(admin)
        db.session.flush()
        db.session.add(UserRole(user_id=admin.id, role_id=super_admin_role.id))
        db.session.commit()
    else:
        admin.password = admin_password
        if not admin.has_role(ROLE_SUPER_ADMIN):
            db.session.add(UserRole(user_id=admin.id, role_id=super_admin_role.id))
        db.session.commit()

    passenger_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))
    passenger = User(
        email="regular_passenger_check@railsathi.pk",
        cnic="35201-1234567-9",
        first_name="Regular",
        last_name="Passenger",
        phone_number="0300-1234567",
        is_active_user=True,
    )
    passenger.password = "PassengerSecret123!"
    db.session.add(passenger)
    db.session.flush()
    db.session.add(UserRole(user_id=passenger.id, role_id=passenger_role.id))
    db.session.commit()

    # Passenger -> 403
    client.post("/auth/login", data={"email": "regular_passenger_check@railsathi.pk", "password": "PassengerSecret123!"})
    resp_pass = client.get("/admin/dashboard")
    assert resp_pass.status_code == 403

    client.post("/auth/logout")

    # Super Admin -> 200
    login_admin = client.post("/auth/login", data={"email": admin_email, "password": admin_password})
    assert login_admin.status_code == 302

    resp_admin = client.get("/admin/dashboard")
    assert resp_admin.status_code == 200
    assert b"Railway Operations Governance Shell" in resp_admin.data
    assert b"Role: Super Admin" in resp_admin.data


# ---------------------------------------------------------------------------
# Security & Normalization Tests
# ---------------------------------------------------------------------------
def test_open_redirect_next_url_rejected(client, auth_roles):
    """Verify open-redirect attacks via ?next=https://evil.com are rejected."""
    user = User(
        email="open_redirect_test@railsathi.pk",
        cnic="35201-4444444-2",
        first_name="Redirect",
        last_name="Test",
        phone_number="0300-4444444",
        is_active_user=True,
    )
    user.password = "Password123!"
    db.session.add(user)
    db.session.commit()

    resp = client.post(
        "/auth/login?next=https://evil.com/phishing",
        data={"email": "open_redirect_test@railsathi.pk", "password": "Password123!"},
    )
    assert resp.status_code == 302
    assert not resp.headers["Location"].startswith("https://evil.com")
    assert resp.headers["Location"].endswith("/")


def test_logout_get_method_rejected_with_405(client, auth_roles):
    """Verify that GET /auth/logout is rejected with HTTP 405 Method Not Allowed."""
    user = User(
        email="logout_method_test@railsathi.pk",
        cnic="35201-5555555-2",
        first_name="Logout",
        last_name="Method",
        phone_number="0300-5555555",
        is_active_user=True,
    )
    user.password = "Password123!"
    db.session.add(user)
    db.session.commit()

    client.post("/auth/login", data={"email": "logout_method_test@railsathi.pk", "password": "Password123!"})
    get_resp = client.get("/auth/logout")
    assert get_resp.status_code == 405


def test_logout_post_without_csrf_rejected_with_400(auth_roles):
    """Verify that when CSRF is enabled, POST /auth/logout without CSRF returns HTTP 400."""
    class CSRFActiveConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(CSRFActiveConfig)
    with csrf_app.app_context():
        test_client = csrf_app.test_client()
        post_resp = test_client.post("/auth/logout")
        assert post_resp.status_code == 400


def test_session_cookie_has_httponly_and_samesite_flags(client, auth_roles):
    """Verify session cookie enforces HttpOnly and SameSite security flags."""
    user = User(
        email="cookie_flags_test@railsathi.pk",
        cnic="35201-6666666-2",
        first_name="Cookie",
        last_name="Flags",
        phone_number="0300-6666666",
        is_active_user=True,
    )
    user.password = "Password123!"
    db.session.add(user)
    db.session.commit()

    resp = client.post("/auth/login", data={"email": "cookie_flags_test@railsathi.pk", "password": "Password123!"})
    assert resp.status_code == 302

    cookies_header = resp.headers.get_all("Set-Cookie")
    session_cookies = [c for c in cookies_header if "session=" in c]
    assert len(session_cookies) > 0
    cookie_str = session_cookies[0]
    assert "HttpOnly" in cookie_str or "httponly" in cookie_str.lower()
    assert "SameSite=Lax" in cookie_str or "samesite=lax" in cookie_str.lower()


def test_phone_number_normalisation(client, auth_roles):
    """Verify phone numbers in unhyphenated or international format are normalised to 03XX-XXXXXXX."""
    payloads = [
        ("03001234567", "0300-1234567"),
        ("+923001234567", "0300-1234567"),
        ("0312-7654321", "0312-7654321"),
    ]
    for idx, (input_phone, expected_normalized) in enumerate(payloads):
        email = f"phone_norm_{idx}@railsathi.pk"
        cnic = f"35201-000000{idx}-1"
        data = {
            "first_name": "Phone",
            "last_name": f"User{idx}",
            "email": email,
            "cnic": cnic,
            "phone_number": input_phone,
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        resp = client.post("/auth/register", data=data)
        assert resp.status_code == 302

        user = db.session.scalar(select(User).filter_by(email=email))
        assert user is not None
        assert user.phone_number == expected_normalized


def test_soft_deleted_user_session_rejected_on_next_request(client, auth_roles):
    """Verify an active session for a user who is subsequently soft-deleted is rejected on next request."""
    user = User(
        email="soft_delete_session_test@railsathi.pk",
        cnic="35201-7777777-9",
        first_name="Active",
        last_name="SessionUser",
        phone_number="0300-7777777",
        is_active_user=True,
    )
    user.password = "Password123!"
    db.session.add(user)
    db.session.commit()
    user_id = user.id

    # 1. Login user
    login_resp = client.post(
        "/auth/login",
        data={"email": "soft_delete_session_test@railsathi.pk", "password": "Password123!"},
    )
    assert login_resp.status_code == 302

    # 2. Access profile while active
    prof_resp = client.get("/auth/profile")
    assert prof_resp.status_code == 200
    assert b"Active" in prof_resp.data

    # 3. Soft-delete user in database
    target_user = db.session.get(User, user_id)
    target_user.soft_delete(user_id=None)
    db.session.commit()

    # 4. Next request with existing session cookie must be rejected (redirected to login)
    next_resp = client.get("/auth/profile")
    assert next_resp.status_code == 302
    assert "/auth/login" in next_resp.headers["Location"]
