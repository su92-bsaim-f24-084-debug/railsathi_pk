"""Authentication routes handling registration, login, logout, profile, and password changes."""
from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request, session, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import select

from app.auth import auth_bp
from app.auth.forms import RegistrationForm, LoginForm, ProfileForm, ChangePasswordForm
from app.common.audit import log_audit_event
from app.common.decorators import is_safe_url
from app.common.constants import ROLE_SUPER_ADMIN, ROLE_PASSENGER
from app.common.formatters import normalize_phone_number
from app.extensions import db
from app.models.identity import User, Role, UserRole, UserProfile, UserSessionLog
from app.models.base import utc_now


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Passenger registration with WTForms validation, audit logging, and PRG."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        normalized_phone = normalize_phone_number(form.phone_number.data.strip())
        user = User(
            email=form.email.data.strip().lower(),
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            phone_number=normalized_phone,
            cnic=form.cnic.data.strip(),
            is_active_user=True,
            is_verified=False,
        )
        user.password = form.password.data.strip()
        db.session.add(user)
        db.session.flush()

        # Assign canonical default 'Passenger' role
        passenger_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))
        if passenger_role:
            db.session.add(UserRole(user_id=user.id, role_id=passenger_role.id))

        # Create linked UserProfile
        profile = UserProfile(
            user_id=user.id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(profile)

        # Audit event logged in the same transaction
        log_audit_event(
            action="REGISTER",
            entity_name="User",
            entity_id=user.id,
            user_id=user.id,
            new_values={
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "cnic": user.cnic,
                "phone_number": user.phone_number,
                "role": ROLE_PASSENGER,
                "password": "***REDACTED***",
            },
        )
        db.session.commit()

        flash("Your account has been registered successfully! Please sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """User login with rate limiting/account lockout, session tracking, and PRG."""
    if current_user.is_authenticated:
        if current_user.has_role(ROLE_SUPER_ADMIN):
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        stmt = select(User).filter_by(email=email, is_deleted=False)
        user = db.session.scalar(stmt)

        now = utc_now()

        # Check account lockout from database columns
        if user and user.locked_until and user.locked_until > now:
            remaining_mins = max(1, int((user.locked_until - now).total_seconds() / 60))
            flash(
                f"Account is temporarily locked due to multiple failed login attempts. Please try again in {remaining_mins} minute(s).",
                "danger",
            )
            return redirect(url_for("auth.login"))

        # Verify credentials
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("This account has been deactivated. Please contact railway administration.", "danger")
                return redirect(url_for("auth.login"))

            # Reset database failed login counter and lockout timestamp
            user.failed_login_attempts = 0
            user.locked_until = None

            # Flask-Login authentication
            login_user(user, remember=form.remember_me.data)

            # Record UserSessionLog
            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()
            client_ip = (client_ip or "127.0.0.1")[:45]
            ua = (request.user_agent.string if request.user_agent else "Unknown")[:255]

            session_log = UserSessionLog(
                user_id=user.id,
                ip_address=client_ip,
                user_agent=ua,
                login_time=now,
                is_expired=False,
            )
            db.session.add(session_log)
            db.session.flush()
            session["session_log_id"] = session_log.id

            # Log audit event in the same transaction
            log_audit_event(
                action="LOGIN",
                entity_name="User",
                entity_id=user.id,
                user_id=user.id,
                new_values={
                    "ip_address": client_ip,
                    "user_agent": ua,
                },
            )
            db.session.commit()

            flash(f"Welcome back, {user.first_name}!", "success")

            # Validate next URL to prevent open redirect vulnerabilities
            next_url = request.args.get("next")
            if next_url and is_safe_url(next_url):
                return redirect(next_url)

            if user.has_role(ROLE_SUPER_ADMIN):
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("main.index"))
        else:
            # Login failed: increment persistent database counter if user exists
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = now + timedelta(minutes=15)
                    flash(
                        "Your account has been temporarily locked for 15 minutes due to 5 consecutive failed login attempts.",
                        "danger",
                    )
                else:
                    remaining_attempts = 5 - user.failed_login_attempts
                    flash(
                        f"Invalid email or password. {remaining_attempts} attempt(s) remaining before temporary lockout.",
                        "danger",
                    )
                db.session.commit()
            else:
                flash("Invalid email or password.", "danger")

            return redirect(url_for("auth.login"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """User logout, session termination, audit log recording, and PRG (POST only)."""
    now = utc_now()
    session_log_id = session.get("session_log_id")
    if session_log_id:
        s_log = db.session.get(UserSessionLog, session_log_id)
        if s_log:
            s_log.logout_time = now
            s_log.is_expired = True

    log_audit_event(
        action="LOGOUT",
        entity_name="User",
        entity_id=current_user.id,
        user_id=current_user.id,
    )
    db.session.commit()

    logout_user()
    session.pop("session_log_id", None)
    flash("You have been signed out successfully.", "info")

    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Passenger and staff profile view and edit."""
    form = ProfileForm()

    if request.method == "GET":
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.phone_number.data = current_user.phone_number
        if current_user.profile:
            form.city.data = current_user.profile.city
            form.province.data = current_user.profile.province or ""
            form.address.data = current_user.profile.address

    if form.validate_on_submit():
        normalized_phone = normalize_phone_number(form.phone_number.data.strip())
        old_values = {
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "phone_number": current_user.phone_number,
            "city": current_user.profile.city if current_user.profile else None,
            "province": current_user.profile.province if current_user.profile else None,
            "address": current_user.profile.address if current_user.profile else None,
        }

        current_user.first_name = form.first_name.data.strip()
        current_user.last_name = form.last_name.data.strip()
        current_user.phone_number = normalized_phone

        if not current_user.profile:
            current_user.profile = UserProfile(user_id=current_user.id)

        current_user.profile.city = form.city.data.strip() if form.city.data else None
        current_user.profile.province = form.province.data if form.province.data else None
        current_user.profile.address = form.address.data.strip() if form.address.data else None
        current_user.profile.updated_at = utc_now()

        new_values = {
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "phone_number": current_user.phone_number,
            "city": current_user.profile.city,
            "province": current_user.profile.province,
            "address": current_user.profile.address,
        }

        log_audit_event(
            action="UPDATE_PROFILE",
            entity_name="User",
            entity_id=current_user.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values=new_values,
        )
        db.session.commit()

        flash("Your profile details have been updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Password change workflow with current password verification and audit logging."""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password entered is incorrect.", "danger")
            return redirect(url_for("auth.change_password"))

        current_user.password = form.new_password.data.strip()

        log_audit_event(
            action="CHANGE_PASSWORD",
            entity_name="User",
            entity_id=current_user.id,
            user_id=current_user.id,
            old_values={"password": "***REDACTED***"},
            new_values={"password": "***REDACTED***"},
        )
        db.session.commit()

        flash("Your password has been changed successfully.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/change_password.html", form=form)
