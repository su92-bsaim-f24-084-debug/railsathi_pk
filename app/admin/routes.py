"""Administrative routes for user and staff management, roles, and security logs."""
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from sqlalchemy import select, func, or_, desc

from app.admin import admin_bp
from app.admin.forms import (
    AdminUserCreateForm,
    AdminUserEditForm,
    StaffProfileForm,
    EmptyActionForm,
)
from app.common.decorators import roles_required
from app.common.constants import (
    ROLE_SUPER_ADMIN,
    ROLE_PASSENGER,
    ALL_SYSTEM_ROLES,
)
from app.common.audit import log_audit_event
from app.common.formatters import normalize_phone_number
from app.extensions import db
from app.models.identity import (
    User,
    Role,
    UserRole,
    UserProfile,
    StaffProfile,
    UserSessionLog,
)
from app.models.stations import Station
from app.models.trains import Train
from app.models.bookings import Booking
from app.models.governance import AuditLog
from app.models.base import utc_now


def is_last_super_admin(target_user: User) -> bool:
    """Verify if target user is the sole remaining active Super Admin in the system."""
    if not target_user.has_role(ROLE_SUPER_ADMIN):
        return False
    active_super_admins_count = db.session.scalar(
        select(func.count(UserRole.id))
        .join(User, UserRole.user_id == User.id)
        .join(Role, UserRole.role_id == Role.id)
        .filter(
            Role.name == ROLE_SUPER_ADMIN,
            User.is_deleted == False,
        )
    )
    return active_super_admins_count <= 1


# ---------------------------------------------------------------------------
# 1. Admin Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/dashboard")
@roles_required(ROLE_SUPER_ADMIN)
def dashboard():
    """Administrative dashboard shell providing system statistics."""
    total_users = db.session.scalar(select(func.count(User.id)).filter_by(is_deleted=False)) or 0
    total_trains = db.session.scalar(select(func.count(Train.id)).filter_by(is_deleted=False)) or 0
    total_stations = db.session.scalar(select(func.count(Station.id)).filter_by(is_deleted=False)) or 0
    total_bookings = db.session.scalar(select(func.count(Booking.id)).filter_by(is_deleted=False)) or 0
    total_staff = db.session.scalar(select(func.count(StaffProfile.id)).filter_by(is_deleted=False)) or 0

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_trains=total_trains,
        total_stations=total_stations,
        total_bookings=total_bookings,
        total_staff=total_staff,
    )


# ---------------------------------------------------------------------------
# 2. User Management CRUD
# ---------------------------------------------------------------------------
@admin_bp.route("/users")
@roles_required(ROLE_SUPER_ADMIN)
def users():
    """Search, filter, and paginate system users."""
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all")

    stmt = select(User).order_by(User.id.asc())

    if status_filter == "active":
        stmt = stmt.filter(User.is_deleted == False)
    elif status_filter == "deleted":
        stmt = stmt.filter(User.is_deleted == True)

    if search_query:
        like_expr = f"%{search_query}%"
        stmt = stmt.filter(
            or_(
                User.first_name.ilike(like_expr),
                User.last_name.ilike(like_expr),
                User.email.ilike(like_expr),
                User.cnic.ilike(like_expr),
                User.phone_number.ilike(like_expr),
            )
        )

    pagination = db.paginate(stmt, page=page, per_page=15, error_out=False)
    action_form = EmptyActionForm()

    return render_template(
        "admin/users/index.html",
        pagination=pagination,
        search_query=search_query,
        status_filter=status_filter,
        action_form=action_form,
        extra_args={"q": search_query, "status": status_filter},
    )


@admin_bp.route("/users/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def user_create():
    """Create a new system user with assigned roles."""
    form = AdminUserCreateForm()
    roles_list = db.session.scalars(select(Role).order_by(Role.id)).all()
    form.roles.choices = [(r.id, r.name) for r in roles_list]

    if form.validate_on_submit():
        normalized_phone = normalize_phone_number(form.phone_number.data.strip())
        user = User(
            email=form.email.data.strip().lower(),
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            phone_number=normalized_phone,
            cnic=form.cnic.data.strip(),
            is_active_user=form.is_active_user.data,
            is_verified=True,
        )
        user.password = form.password.data.strip()
        db.session.add(user)
        db.session.flush()

        # Assign selected roles (or default to Passenger if none selected)
        selected_role_ids = form.roles.data or []
        if not selected_role_ids:
            passenger_role = db.session.scalar(select(Role).filter_by(name=ROLE_PASSENGER))
            if passenger_role:
                selected_role_ids = [passenger_role.id]

        for rid in selected_role_ids:
            db.session.add(UserRole(user_id=user.id, role_id=rid))

        # Create basic profile
        db.session.add(UserProfile(user_id=user.id, created_at=utc_now(), updated_at=utc_now()))

        # Log audit event
        assigned_role_names = [r.name for r in roles_list if r.id in selected_role_ids]
        log_audit_event(
            action="ADMIN_CREATE_USER",
            entity_name="User",
            entity_id=user.id,
            user_id=current_user.id,
            new_values={
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "cnic": user.cnic,
                "phone_number": user.phone_number,
                "roles": assigned_role_names,
                "password": "***REDACTED***",
            },
        )
        db.session.commit()

        flash(f"User account for '{user.email}' created successfully.", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/users/form.html", form=form, title="Create System User")


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def user_edit(user_id: int):
    """Edit existing user account, details, and role assignments."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        abort(404)

    form = AdminUserEditForm(original_user_id=target_user.id)
    roles_list = db.session.scalars(select(Role).order_by(Role.id)).all()
    form.roles.choices = [(r.id, r.name) for r in roles_list]

    super_admin_role = db.session.scalar(select(Role).filter_by(name=ROLE_SUPER_ADMIN))

    if request.method == "GET":
        form.first_name.data = target_user.first_name
        form.last_name.data = target_user.last_name
        form.email.data = target_user.email
        form.cnic.data = target_user.cnic
        form.phone_number.data = target_user.phone_number
        form.is_active_user.data = target_user.is_active_user
        form.roles.data = [ur.role_id for ur in target_user.user_roles]

    if form.validate_on_submit():
        selected_role_ids = form.roles.data or []

        # Guard Rail 1: Admin cannot demote themselves
        if target_user.id == current_user.id:
            if super_admin_role and super_admin_role.id not in selected_role_ids:
                flash("You cannot remove the Super Admin role from your own administrator account.", "danger")
                return redirect(url_for("admin.user_edit", user_id=target_user.id))

        # Guard Rail 2: Cannot demote or deactivate the last Super Admin
        if is_last_super_admin(target_user):
            if super_admin_role and super_admin_role.id not in selected_role_ids:
                flash("Cannot revoke the Super Admin role from the sole remaining active Super Admin.", "danger")
                return redirect(url_for("admin.user_edit", user_id=target_user.id))
            if not form.is_active_user.data:
                flash("Cannot deactivate the sole remaining active Super Admin account.", "danger")
                return redirect(url_for("admin.user_edit", user_id=target_user.id))

        old_values = {
            "first_name": target_user.first_name,
            "last_name": target_user.last_name,
            "email": target_user.email,
            "cnic": target_user.cnic,
            "phone_number": target_user.phone_number,
            "is_active_user": target_user.is_active_user,
            "roles": target_user.roles,
        }

        normalized_phone = normalize_phone_number(form.phone_number.data.strip())
        target_user.first_name = form.first_name.data.strip()
        target_user.last_name = form.last_name.data.strip()
        target_user.email = form.email.data.strip().lower()
        target_user.cnic = form.cnic.data.strip()
        target_user.phone_number = normalized_phone
        target_user.is_active_user = form.is_active_user.data

        if form.password.data and form.password.data.strip():
            target_user.password = form.password.data.strip()

        # Update role associations
        current_role_ids = {ur.role_id for ur in target_user.user_roles}
        new_role_ids = set(selected_role_ids)

        # Remove unselected roles
        for ur in list(target_user.user_roles):
            if ur.role_id not in new_role_ids:
                db.session.delete(ur)

        # Add newly selected roles
        for rid in new_role_ids - current_role_ids:
            db.session.add(UserRole(user_id=target_user.id, role_id=rid))

        db.session.flush()

        new_values = {
            "first_name": target_user.first_name,
            "last_name": target_user.last_name,
            "email": target_user.email,
            "cnic": target_user.cnic,
            "phone_number": target_user.phone_number,
            "is_active_user": target_user.is_active_user,
            "roles": target_user.roles,
            "password_reset": bool(form.password.data and form.password.data.strip()),
        }

        log_audit_event(
            action="ADMIN_EDIT_USER",
            entity_name="User",
            entity_id=target_user.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values=new_values,
        )
        db.session.commit()

        flash(f"User account for '{target_user.email}' updated successfully.", "success")
        return redirect(url_for("admin.users"))

    return render_template(
        "admin/users/form.html",
        form=form,
        title=f"Edit User: {target_user.email}",
        target_user=target_user,
    )


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def user_delete(user_id: int):
    """Soft delete user account with guard rail protection."""
    form = EmptyActionForm()
    if not form.validate_on_submit():
        flash("Invalid security token.", "danger")
        return redirect(url_for("admin.users"))

    target_user = db.session.get(User, user_id)
    if not target_user:
        abort(404)

    # Guard Rail 1: Admin cannot delete themselves
    if target_user.id == current_user.id:
        flash("You cannot delete your own administrator account.", "danger")
        return redirect(url_for("admin.users"))

    # Guard Rail 2: Cannot delete the last Super Admin
    if is_last_super_admin(target_user):
        flash("Cannot delete the last active Super Admin account. Another Super Admin must exist first.", "danger")
        return redirect(url_for("admin.users"))

    target_user.soft_delete(user_id=current_user.id)

    log_audit_event(
        action="ADMIN_SOFT_DELETE_USER",
        entity_name="User",
        entity_id=target_user.id,
        user_id=current_user.id,
        old_values={"email": target_user.email, "is_deleted": False},
        new_values={"is_deleted": True, "deleted_by_id": current_user.id},
    )
    db.session.commit()

    flash(f"User '{target_user.email}' has been soft-deleted successfully.", "warning")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def user_restore(user_id: int):
    """Restore soft-deleted user account."""
    form = EmptyActionForm()
    if not form.validate_on_submit():
        flash("Invalid security token.", "danger")
        return redirect(url_for("admin.users"))

    target_user = db.session.get(User, user_id)
    if not target_user:
        abort(404)

    target_user.restore()

    log_audit_event(
        action="ADMIN_RESTORE_USER",
        entity_name="User",
        entity_id=target_user.id,
        user_id=current_user.id,
        old_values={"email": target_user.email, "is_deleted": True},
        new_values={"is_deleted": False},
    )
    db.session.commit()

    flash(f"User '{target_user.email}' has been restored successfully.", "success")
    return redirect(url_for("admin.users"))


# ---------------------------------------------------------------------------
# 3. Roles Management (View Only, Deletion Blocked)
# ---------------------------------------------------------------------------
@admin_bp.route("/roles")
@roles_required(ROLE_SUPER_ADMIN)
def roles():
    """View fixed system roles and assigned user counts."""
    stmt = (
        select(Role, func.count(UserRole.id).label("user_count"))
        .outerjoin(UserRole, Role.id == UserRole.role_id)
        .group_by(Role.id)
        .order_by(Role.id.asc())
    )
    roles_with_counts = db.session.execute(stmt).all()
    return render_template("admin/roles/index.html", roles_with_counts=roles_with_counts)


@admin_bp.route("/roles/<int:role_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def role_delete(role_id: int):
    """Deletion of fixed canonical system roles is strictly prohibited."""
    flash("Core system roles are permanent reference records and cannot be deleted.", "danger")
    return redirect(url_for("admin.roles")), 400


# ---------------------------------------------------------------------------
# 4. Staff Profiles Management CRUD
# ---------------------------------------------------------------------------
@admin_bp.route("/staff")
@roles_required(ROLE_SUPER_ADMIN)
def staff():
    """List and paginate railway operational staff profiles."""
    page = request.args.get("page", 1, type=int)
    stmt = (
        select(StaffProfile)
        .order_by(StaffProfile.id.asc())
    )
    pagination = db.paginate(stmt, page=page, per_page=15, error_out=False)
    action_form = EmptyActionForm()

    return render_template(
        "admin/staff/index.html",
        pagination=pagination,
        action_form=action_form,
    )


@admin_bp.route("/staff/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def staff_create():
    """Create a new staff profile linking a user to a railway station."""
    form = StaffProfileForm()

    # User choices: active users
    users_list = db.session.scalars(
        select(User).filter_by(is_deleted=False).order_by(User.first_name)
    ).all()
    form.user_id.choices = [(u.id, f"{u.full_name} ({u.email})") for u in users_list]

    # Station choices
    stations_list = db.session.scalars(
        select(Station).filter_by(is_deleted=False).order_by(Station.name)
    ).all()
    form.station_id.choices = [(0, "No Station Assigned")] + [(s.id, f"{s.name} ({s.code})") for s in stations_list]

    if form.validate_on_submit():
        # Check if user already has a staff profile
        existing_profile = db.session.scalar(select(StaffProfile).filter_by(user_id=form.user_id.data))
        if existing_profile:
            flash("The selected user account already has an attached staff profile.", "danger")
            return redirect(url_for("admin.staff_create"))

        # Check unique employee code
        code_exists = db.session.scalar(
            select(StaffProfile).filter_by(employee_code=form.employee_code.data.strip(), is_deleted=False)
        )
        if code_exists:
            flash(f"Employee code '{form.employee_code.data.strip()}' is already in use.", "danger")
            return redirect(url_for("admin.staff_create"))

        station_id_val = form.station_id.data if form.station_id.data != 0 else None
        staff_prof = StaffProfile(
            user_id=form.user_id.data,
            station_id=station_id_val,
            employee_code=form.employee_code.data.strip(),
            department=form.department.data.strip(),
            designation=form.designation.data.strip(),
            shift_timing=form.shift_timing.data if form.shift_timing.data else None,
        )
        db.session.add(staff_prof)
        db.session.flush()

        log_audit_event(
            action="ADMIN_CREATE_STAFF_PROFILE",
            entity_name="StaffProfile",
            entity_id=staff_prof.id,
            user_id=current_user.id,
            new_values={
                "user_id": staff_prof.user_id,
                "employee_code": staff_prof.employee_code,
                "department": staff_prof.department,
                "designation": staff_prof.designation,
                "station_id": staff_prof.station_id,
            },
        )
        db.session.commit()

        flash(f"Staff profile for employee '{staff_prof.employee_code}' created successfully.", "success")
        return redirect(url_for("admin.staff"))

    return render_template("admin/staff/form.html", form=form, title="Create Staff Profile")


@admin_bp.route("/staff/<int:profile_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def staff_edit(profile_id: int):
    """Edit existing staff profile and station assignment."""
    staff_prof = db.session.get(StaffProfile, profile_id)
    if not staff_prof:
        abort(404)

    form = StaffProfileForm()
    users_list = db.session.scalars(select(User).filter_by(id=staff_prof.user_id)).all()
    form.user_id.choices = [(u.id, f"{u.full_name} ({u.email})") for u in users_list]

    stations_list = db.session.scalars(
        select(Station).filter_by(is_deleted=False).order_by(Station.name)
    ).all()
    form.station_id.choices = [(0, "No Station Assigned")] + [(s.id, f"{s.name} ({s.code})") for s in stations_list]

    if request.method == "GET":
        form.user_id.data = staff_prof.user_id
        form.station_id.data = staff_prof.station_id or 0
        form.employee_code.data = staff_prof.employee_code
        form.department.data = staff_prof.department
        form.designation.data = staff_prof.designation
        form.shift_timing.data = staff_prof.shift_timing or ""

    if form.validate_on_submit():
        # Check employee code uniqueness if changed
        new_code = form.employee_code.data.strip()
        if new_code != staff_prof.employee_code:
            code_conflict = db.session.scalar(
                select(StaffProfile).filter(
                    StaffProfile.employee_code == new_code,
                    StaffProfile.is_deleted == False,
                    StaffProfile.id != staff_prof.id,
                )
            )
            if code_conflict:
                flash(f"Employee code '{new_code}' is already assigned to another staff member.", "danger")
                return redirect(url_for("admin.staff_edit", profile_id=staff_prof.id))

        old_values = {
            "employee_code": staff_prof.employee_code,
            "department": staff_prof.department,
            "designation": staff_prof.designation,
            "station_id": staff_prof.station_id,
            "shift_timing": staff_prof.shift_timing,
        }

        station_id_val = form.station_id.data if form.station_id.data != 0 else None
        staff_prof.employee_code = new_code
        staff_prof.department = form.department.data.strip()
        staff_prof.designation = form.designation.data.strip()
        staff_prof.station_id = station_id_val
        staff_prof.shift_timing = form.shift_timing.data if form.shift_timing.data else None

        new_values = {
            "employee_code": staff_prof.employee_code,
            "department": staff_prof.department,
            "designation": staff_prof.designation,
            "station_id": staff_prof.station_id,
            "shift_timing": staff_prof.shift_timing,
        }

        log_audit_event(
            action="ADMIN_EDIT_STAFF_PROFILE",
            entity_name="StaffProfile",
            entity_id=staff_prof.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values=new_values,
        )
        db.session.commit()

        flash(f"Staff profile for employee '{staff_prof.employee_code}' updated successfully.", "success")
        return redirect(url_for("admin.staff"))

    return render_template(
        "admin/staff/form.html",
        form=form,
        title=f"Edit Staff Profile: {staff_prof.employee_code}",
        staff_prof=staff_prof,
    )


@admin_bp.route("/staff/<int:profile_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def staff_delete(profile_id: int):
    """Soft delete staff profile."""
    form = EmptyActionForm()
    if not form.validate_on_submit():
        flash("Invalid security token.", "danger")
        return redirect(url_for("admin.staff"))

    staff_prof = db.session.get(StaffProfile, profile_id)
    if not staff_prof:
        abort(404)

    staff_prof.soft_delete(user_id=current_user.id)

    log_audit_event(
        action="ADMIN_SOFT_DELETE_STAFF_PROFILE",
        entity_name="StaffProfile",
        entity_id=staff_prof.id,
        user_id=current_user.id,
        old_values={"employee_code": staff_prof.employee_code, "is_deleted": False},
        new_values={"is_deleted": True, "deleted_by_id": current_user.id},
    )
    db.session.commit()

    flash(f"Staff profile '{staff_prof.employee_code}' soft-deleted successfully.", "warning")
    return redirect(url_for("admin.staff"))


# ---------------------------------------------------------------------------
# 5. Security Logs (Audit Logs & User Session Logs - Read Only)
# ---------------------------------------------------------------------------
@admin_bp.route("/audit-logs")
@roles_required(ROLE_SUPER_ADMIN)
def audit_logs():
    """View and filter immutable system audit trails."""
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "").strip()
    entity_filter = request.args.get("entity", "").strip()

    stmt = select(AuditLog).order_by(desc(AuditLog.id))

    if action_filter:
        stmt = stmt.filter(AuditLog.action.ilike(f"%{action_filter}%"))
    if entity_filter:
        stmt = stmt.filter(AuditLog.entity_name.ilike(f"%{entity_filter}%"))

    pagination = db.paginate(stmt, page=page, per_page=20, error_out=False)

    return render_template(
        "admin/logs/audit_logs.html",
        pagination=pagination,
        action_filter=action_filter,
        entity_filter=entity_filter,
        extra_args={"action": action_filter, "entity": entity_filter},
    )


@admin_bp.route("/session-logs")
@roles_required(ROLE_SUPER_ADMIN)
def session_logs():
    """View and paginate user sign-in session logs."""
    page = request.args.get("page", 1, type=int)
    ip_filter = request.args.get("ip", "").strip()

    stmt = select(UserSessionLog).order_by(desc(UserSessionLog.id))

    if ip_filter:
        stmt = stmt.filter(UserSessionLog.ip_address.ilike(f"%{ip_filter}%"))

    pagination = db.paginate(stmt, page=page, per_page=20, error_out=False)

    return render_template(
        "admin/logs/session_logs.html",
        pagination=pagination,
        ip_filter=ip_filter,
        extra_args={"ip": ip_filter},
    )
