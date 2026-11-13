"""Administrative routes for Trains & Rolling Stock Master-Data (Phase 5B).

Models:
- Model #12: TrainType (Super Admin)
- Model #13: Train (Super Admin) with TrainOperationalDay checkboxes (Model #14)
- Model #15: CoachClass (Super Admin)
- Model #16: SeatLayoutType (Super Admin)
- Model #17: BerthType (Super Admin, view/edit only, delete blocked)
- Model #18: TrainCoach (Super Admin)
- Model #19: Seat (Super Admin, batch generator + individual edit)
"""
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from sqlalchemy import select, func, or_

from app.admin import admin_bp
from app.admin.crud_helper import (
    render_admin_list,
    handle_admin_soft_delete,
    handle_admin_restore,
)
from app.admin.trains_forms import (
    TrainTypeForm,
    TrainForm,
    CoachClassForm,
    SeatLayoutTypeForm,
    BerthTypeForm,
    TrainCoachForm,
    SeatBatchGenerateForm,
    SeatForm,
)
from app.common.decorators import roles_required
from app.common.constants import ROLE_SUPER_ADMIN
from app.common.audit import log_audit_event
from app.extensions import db
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
from app.models.stations import Station
from app.models.routes import FareRule
from app.models.schedules import Schedule
from app.models.bookings import JourneyCoach, SeatReservationLock, TicketSeatAllocation


# ---------------------------------------------------------------------------
# 1. TrainType (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/train-types")
@roles_required(ROLE_SUPER_ADMIN)
def train_types():
    """List and paginate rolling stock categories."""
    return render_admin_list(
        model=TrainType,
        template_name="admin/trains/types_index.html",
        search_columns=[TrainType.code, TrainType.name, TrainType.description],
    )


@admin_bp.route("/train-types/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_type_create():
    """Create a new rolling stock category."""
    form = TrainTypeForm()
    if form.validate_on_submit():
        tt = TrainType(
            code=form.code.data.strip().upper(),
            name=form.name.data.strip(),
            max_speed_kmh=form.max_speed_kmh.data,
            description=form.description.data.strip() if form.description.data else None,
        )
        db.session.add(tt)
        db.session.flush()

        log_audit_event(
            action="CREATE_TRAIN_TYPE",
            entity_name="TrainType",
            entity_id=tt.id,
            user_id=current_user.id,
            new_values={"code": tt.code, "name": tt.name, "speed": tt.max_speed_kmh},
        )
        db.session.commit()

        flash(f"Train type '{tt.name}' ({tt.code}) created successfully.", "success")
        return redirect(url_for("admin.train_types"))

    return render_template("admin/trains/types_form.html", form=form, title="Create Train Type")


@admin_bp.route("/train-types/<int:type_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_type_edit(type_id: int):
    """Edit existing rolling stock category."""
    tt = db.session.get(TrainType, type_id)
    if not tt:
        abort(404)

    form = TrainTypeForm(original_id=tt.id)
    if request.method == "GET":
        form.code.data = tt.code
        form.name.data = tt.name
        form.max_speed_kmh.data = tt.max_speed_kmh
        form.description.data = tt.description

    if form.validate_on_submit():
        old_val = {"code": tt.code, "name": tt.name, "speed": tt.max_speed_kmh}
        tt.code = form.code.data.strip().upper()
        tt.name = form.name.data.strip()
        tt.max_speed_kmh = form.max_speed_kmh.data
        tt.description = form.description.data.strip() if form.description.data else None

        log_audit_event(
            action="EDIT_TRAIN_TYPE",
            entity_name="TrainType",
            entity_id=tt.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"code": tt.code, "name": tt.name, "speed": tt.max_speed_kmh},
        )
        db.session.commit()

        flash(f"Train type '{tt.name}' updated successfully.", "success")
        return redirect(url_for("admin.train_types"))

    return render_template("admin/trains/types_form.html", form=form, title=f"Edit Train Type: {tt.code}", target_obj=tt)


@admin_bp.route("/train-types/<int:type_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_type_delete(type_id: int):
    """Soft delete train type with active trains dependency guard."""
    tt = db.session.get(TrainType, type_id)
    if not tt:
        abort(404)

    def block_check():
        active_trains = db.session.scalar(select(func.count(Train.id)).filter_by(train_type_id=tt.id, is_deleted=False))
        if active_trains > 0:
            return f"Cannot soft-delete train type '{tt.name}' because {active_trains} active train(s) are assigned to it."
        return None

    return handle_admin_soft_delete(
        instance=tt,
        redirect_url=url_for("admin.train_types"),
        entity_name="TrainType",
        identifier_str=tt.code,
        block_check=block_check,
    )


@admin_bp.route("/train-types/<int:type_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_type_restore(type_id: int):
    """Restore soft-deleted train type."""
    tt = db.session.get(TrainType, type_id)
    if not tt:
        abort(404)
    return handle_admin_restore(
        instance=tt,
        redirect_url=url_for("admin.train_types"),
        entity_name="TrainType",
        identifier_str=tt.code,
    )


# ---------------------------------------------------------------------------
# 2. Train & TrainOperationalDay (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/trains")
@roles_required(ROLE_SUPER_ADMIN)
def trains():
    """List and paginate rolling stock train rakes."""
    return render_admin_list(
        model=Train,
        template_name="admin/trains/trains_index.html",
        search_columns=[Train.train_number, Train.name],
    )


@admin_bp.route("/trains/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_create():
    """Create a new train rake with operational day checkboxes."""
    form = TrainForm()
    tts = db.session.scalars(select(TrainType).filter_by(is_deleted=False).order_by(TrainType.name)).all()
    form.train_type_id.choices = [(t.id, f"{t.name} ({t.code})") for t in tts]

    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.origin_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]
    form.destination_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if form.validate_on_submit():
        t = Train(
            train_type_id=form.train_type_id.data,
            train_number=form.train_number.data.strip().upper(),
            name=form.name.data.strip(),
            origin_station_id=form.origin_station_id.data,
            destination_station_id=form.destination_station_id.data,
            is_active=form.is_active.data,
        )
        db.session.add(t)
        db.session.flush()

        # Operational days (0=Mon .. 6=Sun)
        selected_days = []
        for day_idx in range(7):
            cb_val = getattr(form, f"day_{day_idx}").data
            if cb_val:
                db.session.add(TrainOperationalDay(train_id=t.id, day_of_week=day_idx, is_active=True))
                selected_days.append(day_idx)

        log_audit_event(
            action="CREATE_TRAIN",
            entity_name="Train",
            entity_id=t.id,
            user_id=current_user.id,
            new_values={
                "train_number": t.train_number,
                "name": t.name,
                "origin_id": t.origin_station_id,
                "destination_id": t.destination_station_id,
                "operational_days": selected_days,
            },
        )
        db.session.commit()

        flash(f"Train '{t.name}' ({t.train_number}) created successfully.", "success")
        return redirect(url_for("admin.trains"))

    return render_template("admin/trains/trains_form.html", form=form, title="Create Train Rake")


@admin_bp.route("/trains/<int:train_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_edit(train_id: int):
    """Edit train rake and operational day schedule."""
    t = db.session.get(Train, train_id)
    if not t:
        abort(404)

    form = TrainForm(original_id=t.id)
    tts = db.session.scalars(select(TrainType).filter_by(is_deleted=False).order_by(TrainType.name)).all()
    form.train_type_id.choices = [(tt.id, f"{tt.name} ({tt.code})") for tt in tts]

    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.origin_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]
    form.destination_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if request.method == "GET":
        form.train_type_id.data = t.train_type_id
        form.train_number.data = t.train_number
        form.name.data = t.name
        form.origin_station_id.data = t.origin_station_id
        form.destination_station_id.data = t.destination_station_id
        form.is_active.data = t.is_active

        # Load operational days
        active_days = {d.day_of_week for d in t.operational_days if d.is_active}
        for day_idx in range(7):
            getattr(form, f"day_{day_idx}").data = (day_idx in active_days)

    if form.validate_on_submit():
        old_val = {"number": t.train_number, "name": t.name}
        t.train_type_id = form.train_type_id.data
        t.train_number = form.train_number.data.strip().upper()
        t.name = form.name.data.strip()
        t.origin_station_id = form.origin_station_id.data
        t.destination_station_id = form.destination_station_id.data
        t.is_active = form.is_active.data

        # Sync operational days
        existing_days_map = {d.day_of_week: d for d in t.operational_days}
        selected_days = []
        for day_idx in range(7):
            is_checked = getattr(form, f"day_{day_idx}").data
            if is_checked:
                selected_days.append(day_idx)
                if day_idx in existing_days_map:
                    existing_days_map[day_idx].is_active = True
                else:
                    db.session.add(TrainOperationalDay(train_id=t.id, day_of_week=day_idx, is_active=True))
            else:
                if day_idx in existing_days_map:
                    db.session.delete(existing_days_map[day_idx])

        log_audit_event(
            action="EDIT_TRAIN",
            entity_name="Train",
            entity_id=t.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={
                "number": t.train_number,
                "name": t.name,
                "operational_days": selected_days,
            },
        )
        db.session.commit()

        flash(f"Train '{t.name}' updated successfully.", "success")
        return redirect(url_for("admin.trains"))

    return render_template("admin/trains/trains_form.html", form=form, title=f"Edit Train: {t.train_number}", target_obj=t)


@admin_bp.route("/trains/<int:train_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_delete(train_id: int):
    """Soft delete train rake with active coaches and schedules guard."""
    t = db.session.get(Train, train_id)
    if not t:
        abort(404)

    def block_check():
        active_coaches = db.session.scalar(select(func.count(TrainCoach.id)).filter_by(train_id=t.id, is_deleted=False))
        active_schedules = db.session.scalar(select(func.count(Schedule.id)).filter_by(train_id=t.id, is_deleted=False))
        if active_coaches > 0 or active_schedules > 0:
            return f"Cannot soft-delete train '{t.name}' because it has {active_coaches} active coach(es) and {active_schedules} active schedule(s)."
        return None

    return handle_admin_soft_delete(
        instance=t,
        redirect_url=url_for("admin.trains"),
        entity_name="Train",
        identifier_str=t.train_number,
        block_check=block_check,
    )


@admin_bp.route("/trains/<int:train_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_restore(train_id: int):
    """Restore soft-deleted train rake."""
    t = db.session.get(Train, train_id)
    if not t:
        abort(404)
    return handle_admin_restore(
        instance=t,
        redirect_url=url_for("admin.trains"),
        entity_name="Train",
        identifier_str=t.train_number,
    )


# ---------------------------------------------------------------------------
# 3. CoachClass (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/coach-classes")
@roles_required(ROLE_SUPER_ADMIN)
def coach_classes():
    """List and paginate coach accommodation classes."""
    return render_admin_list(
        model=CoachClass,
        template_name="admin/trains/classes_index.html",
        search_columns=[CoachClass.code, CoachClass.name, CoachClass.description],
    )


@admin_bp.route("/coach-classes/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def coach_class_create():
    """Create a new accommodation class."""
    form = CoachClassForm()
    if form.validate_on_submit():
        cc = CoachClass(
            code=form.code.data.strip().upper(),
            name=form.name.data.strip(),
            base_fare_multiplier=form.base_fare_multiplier.data,
            description=form.description.data.strip() if form.description.data else None,
        )
        db.session.add(cc)
        db.session.flush()

        log_audit_event(
            action="CREATE_COACH_CLASS",
            entity_name="CoachClass",
            entity_id=cc.id,
            user_id=current_user.id,
            new_values={"code": cc.code, "name": cc.name, "multiplier": str(cc.base_fare_multiplier)},
        )
        db.session.commit()

        flash(f"Coach class '{cc.name}' ({cc.code}) created successfully.", "success")
        return redirect(url_for("admin.coach_classes"))

    return render_template("admin/trains/classes_form.html", form=form, title="Create Coach Class")


@admin_bp.route("/coach-classes/<int:class_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def coach_class_edit(class_id: int):
    """Edit existing coach class."""
    cc = db.session.get(CoachClass, class_id)
    if not cc:
        abort(404)

    form = CoachClassForm(original_id=cc.id)
    if request.method == "GET":
        form.code.data = cc.code
        form.name.data = cc.name
        form.base_fare_multiplier.data = cc.base_fare_multiplier
        form.description.data = cc.description

    if form.validate_on_submit():
        old_val = {"code": cc.code, "name": cc.name, "multiplier": str(cc.base_fare_multiplier)}
        cc.code = form.code.data.strip().upper()
        cc.name = form.name.data.strip()
        cc.base_fare_multiplier = form.base_fare_multiplier.data
        cc.description = form.description.data.strip() if form.description.data else None

        log_audit_event(
            action="EDIT_COACH_CLASS",
            entity_name="CoachClass",
            entity_id=cc.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"code": cc.code, "name": cc.name, "multiplier": str(cc.base_fare_multiplier)},
        )
        db.session.commit()

        flash(f"Coach class '{cc.name}' updated successfully.", "success")
        return redirect(url_for("admin.coach_classes"))

    return render_template("admin/trains/classes_form.html", form=form, title=f"Edit Coach Class: {cc.code}", target_obj=cc)


@admin_bp.route("/coach-classes/<int:class_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def coach_class_delete(class_id: int):
    """Soft delete coach class with active coaches/fare rules guard."""
    cc = db.session.get(CoachClass, class_id)
    if not cc:
        abort(404)

    def block_check():
        active_coaches = db.session.scalar(select(func.count(TrainCoach.id)).filter_by(coach_class_id=cc.id, is_deleted=False))
        active_rules = db.session.scalar(select(func.count(FareRule.id)).filter_by(coach_class_id=cc.id, is_deleted=False))
        if active_coaches > 0 or active_rules > 0:
            return f"Cannot soft-delete coach class '{cc.name}' because {active_coaches} active coach(es) and {active_rules} active fare rule(s) depend on it."
        return None

    return handle_admin_soft_delete(
        instance=cc,
        redirect_url=url_for("admin.coach_classes"),
        entity_name="CoachClass",
        identifier_str=cc.code,
        block_check=block_check,
    )


@admin_bp.route("/coach-classes/<int:class_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def coach_class_restore(class_id: int):
    """Restore soft-deleted coach class."""
    cc = db.session.get(CoachClass, class_id)
    if not cc:
        abort(404)
    return handle_admin_restore(
        instance=cc,
        redirect_url=url_for("admin.coach_classes"),
        entity_name="CoachClass",
        identifier_str=cc.code,
    )


# ---------------------------------------------------------------------------
# 4. SeatLayoutType (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/seat-layouts")
@roles_required(ROLE_SUPER_ADMIN)
def seat_layouts():
    """List and paginate coach seat layout templates."""
    return render_admin_list(
        model=SeatLayoutType,
        template_name="admin/trains/layouts_index.html",
        search_columns=[SeatLayoutType.name, SeatLayoutType.description],
    )


@admin_bp.route("/seat-layouts/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_layout_create():
    """Create a new seat layout template."""
    form = SeatLayoutTypeForm()
    if form.validate_on_submit():
        lt = SeatLayoutType(
            name=form.name.data.strip(),
            total_rows=form.total_rows.data,
            seats_per_row=form.seats_per_row.data,
            aisle_position=form.aisle_position.data,
            description=form.description.data.strip() if form.description.data else None,
        )
        db.session.add(lt)
        db.session.flush()

        log_audit_event(
            action="CREATE_SEAT_LAYOUT",
            entity_name="SeatLayoutType",
            entity_id=lt.id,
            user_id=current_user.id,
            new_values={"name": lt.name, "rows": lt.total_rows, "cols": lt.seats_per_row},
        )
        db.session.commit()

        flash(f"Seat layout '{lt.name}' created successfully.", "success")
        return redirect(url_for("admin.seat_layouts"))

    return render_template("admin/trains/layouts_form.html", form=form, title="Create Seat Layout")


@admin_bp.route("/seat-layouts/<int:layout_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_layout_edit(layout_id: int):
    """Edit existing seat layout template."""
    lt = db.session.get(SeatLayoutType, layout_id)
    if not lt:
        abort(404)

    form = SeatLayoutTypeForm(original_id=lt.id)
    if request.method == "GET":
        form.name.data = lt.name
        form.total_rows.data = lt.total_rows
        form.seats_per_row.data = lt.seats_per_row
        form.aisle_position.data = lt.aisle_position
        form.description.data = lt.description

    if form.validate_on_submit():
        old_val = {"name": lt.name, "rows": lt.total_rows, "cols": lt.seats_per_row}
        lt.name = form.name.data.strip()
        lt.total_rows = form.total_rows.data
        lt.seats_per_row = form.seats_per_row.data
        lt.aisle_position = form.aisle_position.data
        lt.description = form.description.data.strip() if form.description.data else None

        log_audit_event(
            action="EDIT_SEAT_LAYOUT",
            entity_name="SeatLayoutType",
            entity_id=lt.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"name": lt.name, "rows": lt.total_rows, "cols": lt.seats_per_row},
        )
        db.session.commit()

        flash(f"Seat layout '{lt.name}' updated successfully.", "success")
        return redirect(url_for("admin.seat_layouts"))

    return render_template("admin/trains/layouts_form.html", form=form, title=f"Edit Seat Layout: {lt.name}", target_obj=lt)


@admin_bp.route("/seat-layouts/<int:layout_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_layout_delete(layout_id: int):
    """Soft delete seat layout with active coaches guard."""
    lt = db.session.get(SeatLayoutType, layout_id)
    if not lt:
        abort(404)

    def block_check():
        active_coaches = db.session.scalar(select(func.count(TrainCoach.id)).filter_by(layout_type_id=lt.id, is_deleted=False))
        if active_coaches > 0:
            return f"Cannot soft-delete seat layout '{lt.name}' because {active_coaches} active coach(es) use it."
        return None

    return handle_admin_soft_delete(
        instance=lt,
        redirect_url=url_for("admin.seat_layouts"),
        entity_name="SeatLayoutType",
        identifier_str=lt.name,
        block_check=block_check,
    )


@admin_bp.route("/seat-layouts/<int:layout_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_layout_restore(layout_id: int):
    """Restore soft-deleted seat layout."""
    lt = db.session.get(SeatLayoutType, layout_id)
    if not lt:
        abort(404)
    return handle_admin_restore(
        instance=lt,
        redirect_url=url_for("admin.seat_layouts"),
        entity_name="SeatLayoutType",
        identifier_str=lt.name,
    )


# ---------------------------------------------------------------------------
# 5. BerthType (Super Admin, View/Edit Only, Deletion Blocked)
# ---------------------------------------------------------------------------
@admin_bp.route("/berth-types")
@roles_required(ROLE_SUPER_ADMIN)
def berth_types():
    """List static reference berth types."""
    return render_admin_list(
        model=BerthType,
        template_name="admin/trains/berths_index.html",
        search_columns=[BerthType.code, BerthType.name, BerthType.description],
    )


@admin_bp.route("/berth-types/<int:berth_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def berth_type_edit(berth_id: int):
    """Edit reference berth type details."""
    bt = db.session.get(BerthType, berth_id)
    if not bt:
        abort(404)

    form = BerthTypeForm(original_id=bt.id)
    if request.method == "GET":
        form.code.data = bt.code
        form.name.data = bt.name
        form.description.data = bt.description

    if form.validate_on_submit():
        old_val = {"code": bt.code, "name": bt.name}
        bt.code = form.code.data.strip().upper()
        bt.name = form.name.data.strip()
        bt.description = form.description.data.strip() if form.description.data else None

        log_audit_event(
            action="EDIT_BERTH_TYPE",
            entity_name="BerthType",
            entity_id=bt.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"code": bt.code, "name": bt.name},
        )
        db.session.commit()

        flash(f"Berth type '{bt.name}' updated successfully.", "success")
        return redirect(url_for("admin.berth_types"))

    return render_template("admin/trains/berths_form.html", form=form, title=f"Edit Berth Type: {bt.code}", target_obj=bt)


@admin_bp.route("/berth-types/<int:berth_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def berth_type_delete(berth_id: int):
    """Deletion blocked for static system reference berth types."""
    flash("Deletion of reference Berth Types is permanently disabled to ensure ticketing data integrity.", "danger")
    return redirect(url_for("admin.berth_types")), 400


# ---------------------------------------------------------------------------
# 6. TrainCoach (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/train-coaches")
@roles_required(ROLE_SUPER_ADMIN)
def train_coaches():
    """List and paginate coaches, with optional ?train_id= filtering."""
    filter_train_id = request.args.get("train_id", type=int)
    base_filter = None
    if filter_train_id:
        base_filter = (TrainCoach.train_id == filter_train_id)

    trains_list = db.session.scalars(select(Train).filter_by(is_deleted=False).order_by(Train.train_number)).all()

    return render_admin_list(
        model=TrainCoach,
        template_name="admin/trains/coaches_index.html",
        search_columns=[TrainCoach.coach_code],
        base_filter=base_filter,
        order_by_col=TrainCoach.sequence_number.asc(),
        context_extra={
            "trains": trains_list,
            "selected_train_id": filter_train_id,
        },
    )


@admin_bp.route("/train-coaches/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_coach_create():
    """Attach a new carriage to a train rake."""
    form = TrainCoachForm()
    trains_list = db.session.scalars(select(Train).filter_by(is_deleted=False).order_by(Train.train_number)).all()
    form.train_id.choices = [(t.id, f"{t.name} ({t.train_number})") for t in trains_list]

    classes_list = db.session.scalars(select(CoachClass).filter_by(is_deleted=False).order_by(CoachClass.name)).all()
    form.coach_class_id.choices = [(c.id, f"{c.name} ({c.code})") for c in classes_list]

    layouts_list = db.session.scalars(select(SeatLayoutType).filter_by(is_deleted=False).order_by(SeatLayoutType.name)).all()
    form.layout_type_id.choices = [(l.id, l.name) for l in layouts_list]

    # Pre-select train_id if provided in query params
    if request.method == "GET" and request.args.get("train_id", type=int):
        form.train_id.data = request.args.get("train_id", type=int)

    if form.validate_on_submit():
        tc = TrainCoach(
            train_id=form.train_id.data,
            coach_class_id=form.coach_class_id.data,
            layout_type_id=form.layout_type_id.data,
            coach_code=form.coach_code.data.strip().upper(),
            sequence_number=form.sequence_number.data,
            total_capacity=form.total_capacity.data,
        )
        db.session.add(tc)
        db.session.flush()

        log_audit_event(
            action="CREATE_TRAIN_COACH",
            entity_name="TrainCoach",
            entity_id=tc.id,
            user_id=current_user.id,
            new_values={
                "train_id": tc.train_id,
                "code": tc.coach_code,
                "sequence": tc.sequence_number,
                "capacity": tc.total_capacity,
            },
        )
        db.session.commit()

        flash(f"Coach '{tc.coach_code}' attached to train successfully.", "success")
        return redirect(url_for("admin.train_coaches", train_id=tc.train_id))

    return render_template("admin/trains/coaches_form.html", form=form, title="Attach Train Coach")


@admin_bp.route("/train-coaches/<int:coach_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_coach_edit(coach_id: int):
    """Edit coach configuration."""
    tc = db.session.get(TrainCoach, coach_id)
    if not tc:
        abort(404)

    form = TrainCoachForm(original_id=tc.id)
    trains_list = db.session.scalars(select(Train).filter_by(is_deleted=False).order_by(Train.train_number)).all()
    form.train_id.choices = [(t.id, f"{t.name} ({t.train_number})") for t in trains_list]

    classes_list = db.session.scalars(select(CoachClass).filter_by(is_deleted=False).order_by(CoachClass.name)).all()
    form.coach_class_id.choices = [(c.id, f"{c.name} ({c.code})") for c in classes_list]

    layouts_list = db.session.scalars(select(SeatLayoutType).filter_by(is_deleted=False).order_by(SeatLayoutType.name)).all()
    form.layout_type_id.choices = [(l.id, l.name) for l in layouts_list]

    if request.method == "GET":
        form.train_id.data = tc.train_id
        form.coach_class_id.data = tc.coach_class_id
        form.layout_type_id.data = tc.layout_type_id
        form.coach_code.data = tc.coach_code
        form.sequence_number.data = tc.sequence_number
        form.total_capacity.data = tc.total_capacity

    if form.validate_on_submit():
        old_val = {"code": tc.coach_code, "seq": tc.sequence_number, "cap": tc.total_capacity}
        tc.train_id = form.train_id.data
        tc.coach_class_id = form.coach_class_id.data
        tc.layout_type_id = form.layout_type_id.data
        tc.coach_code = form.coach_code.data.strip().upper()
        tc.sequence_number = form.sequence_number.data
        tc.total_capacity = form.total_capacity.data

        log_audit_event(
            action="EDIT_TRAIN_COACH",
            entity_name="TrainCoach",
            entity_id=tc.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"code": tc.coach_code, "seq": tc.sequence_number, "cap": tc.total_capacity},
        )
        db.session.commit()

        flash(f"Coach '{tc.coach_code}' updated successfully.", "success")
        return redirect(url_for("admin.train_coaches", train_id=tc.train_id))

    return render_template("admin/trains/coaches_form.html", form=form, title=f"Edit Coach: {tc.coach_code}", target_obj=tc)


@admin_bp.route("/train-coaches/<int:coach_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_coach_delete(coach_id: int):
    """Soft delete train coach with active seats / journey coaches guard."""
    tc = db.session.get(TrainCoach, coach_id)
    if not tc:
        abort(404)

    def block_check():
        active_seats = db.session.scalar(select(func.count(Seat.id)).filter_by(coach_id=tc.id, is_deleted=False))
        active_jc = db.session.scalar(select(func.count(JourneyCoach.id)).filter_by(train_coach_id=tc.id))
        if active_seats > 0 or active_jc > 0:
            return f"Cannot soft-delete coach '{tc.coach_code}' because {active_seats} active seat(s) and {active_jc} active journey coach(es) depend on it."
        return None

    return handle_admin_soft_delete(
        instance=tc,
        redirect_url=url_for("admin.train_coaches", train_id=tc.train_id),
        entity_name="TrainCoach",
        identifier_str=tc.coach_code,
        block_check=block_check,
    )


@admin_bp.route("/train-coaches/<int:coach_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def train_coach_restore(coach_id: int):
    """Restore soft-deleted coach."""
    tc = db.session.get(TrainCoach, coach_id)
    if not tc:
        abort(404)
    return handle_admin_restore(
        instance=tc,
        redirect_url=url_for("admin.train_coaches", train_id=tc.train_id),
        entity_name="TrainCoach",
        identifier_str=tc.coach_code,
    )


# ---------------------------------------------------------------------------
# 7. Seat & Seat Batch Generator (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/seats")
@roles_required(ROLE_SUPER_ADMIN)
def seats():
    """List seats, filtered by coach."""
    coach_id_arg = request.args.get("coach_id", type=int)
    base_filter = None
    if coach_id_arg:
        base_filter = (Seat.coach_id == coach_id_arg)

    coaches_list = db.session.scalars(select(TrainCoach).filter_by(is_deleted=False).order_by(TrainCoach.coach_code)).all()

    return render_admin_list(
        model=Seat,
        template_name="admin/trains/seats_index.html",
        search_columns=[Seat.seat_number],
        base_filter=base_filter,
        order_by_col=Seat.id.asc(),
        context_extra={
            "coaches": coaches_list,
            "selected_coach_id": coach_id_arg,
        },
    )


@admin_bp.route("/seats/generate", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_generate():
    """Batch seat generator for a coach (rows x columns grid)."""
    form = SeatBatchGenerateForm()
    coaches_list = db.session.scalars(select(TrainCoach).filter_by(is_deleted=False).order_by(TrainCoach.coach_code)).all()
    form.coach_id.choices = [(c.id, f"{c.coach_code} (Train: {c.train.train_number if c.train else '—'})") for c in coaches_list]

    berths = db.session.scalars(select(BerthType).order_by(BerthType.name)).all()
    form.default_berth_type_id.choices = [(b.id, f"{b.name} ({b.code})") for b in berths]

    if request.method == "GET" and request.args.get("coach_id", type=int):
        form.coach_id.data = request.args.get("coach_id", type=int)

    if form.validate_on_submit():
        c_id = form.coach_id.data
        coach = db.session.get(TrainCoach, c_id)
        if not coach:
            abort(404)

        if form.clear_existing.data:
            existing_seats = db.session.scalars(select(Seat).filter_by(coach_id=c_id, is_deleted=False)).all()
            for es in existing_seats:
                es.soft_delete(user_id=current_user.id)
            db.session.flush()

        # Parse window and ladies quota specifications
        window_cols = set()
        if form.window_columns.data:
            for part in form.window_columns.data.split(","):
                part_clean = part.strip()
                if part_clean.isdigit():
                    window_cols.add(int(part_clean))

        ladies_rows = set()
        if form.ladies_quota_rows.data:
            for part in form.ladies_quota_rows.data.split(","):
                part_clean = part.strip()
                if part_clean.isdigit():
                    ladies_rows.add(int(part_clean))

        num_rows = form.rows.data
        num_cols = form.columns.data
        b_type_id = form.default_berth_type_id.data

        created_count = 0
        seat_num = 1
        for r in range(1, num_rows + 1):
            for c in range(1, num_cols + 1):
                # Verify active seat doesn't already exist
                exists = db.session.scalar(select(Seat).filter_by(coach_id=c_id, seat_number=str(seat_num), is_deleted=False))
                if not exists:
                    s = Seat(
                        coach_id=c_id,
                        berth_type_id=b_type_id,
                        seat_number=str(seat_num),
                        row_number=r,
                        column_number=c,
                        is_window=(c in window_cols),
                        is_ladies_quota=(r in ladies_rows),
                    )
                    db.session.add(s)
                    created_count += 1
                seat_num += 1

        coach.total_capacity = seat_num - 1

        log_audit_event(
            action="BATCH_GENERATE_SEATS",
            entity_name="Seat",
            entity_id=c_id,
            user_id=current_user.id,
            new_values={"coach_id": c_id, "generated_count": created_count, "rows": num_rows, "cols": num_cols},
        )
        db.session.commit()

        flash(f"Successfully generated {created_count} seat(s) for coach '{coach.coach_code}'.", "success")
        return redirect(url_for("admin.seats", coach_id=c_id))

    return render_template("admin/trains/seats_generate.html", form=form, title="Batch Seat Generator")


@admin_bp.route("/seats/<int:seat_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_edit(seat_id: int):
    """Edit individual seat properties."""
    seat = db.session.get(Seat, seat_id)
    if not seat:
        abort(404)

    form = SeatForm(original_id=seat.id)
    coaches_list = db.session.scalars(select(TrainCoach).filter_by(is_deleted=False).order_by(TrainCoach.coach_code)).all()
    form.coach_id.choices = [(c.id, f"{c.coach_code} (Train: {c.train.train_number if c.train else '—'})") for c in coaches_list]

    berths = db.session.scalars(select(BerthType).order_by(BerthType.name)).all()
    form.berth_type_id.choices = [(b.id, f"{b.name} ({b.code})") for b in berths]

    if request.method == "GET":
        form.coach_id.data = seat.coach_id
        form.berth_type_id.data = seat.berth_type_id
        form.seat_number.data = seat.seat_number
        form.row_number.data = seat.row_number
        form.column_number.data = seat.column_number
        form.is_window.data = seat.is_window
        form.is_ladies_quota.data = seat.is_ladies_quota

    if form.validate_on_submit():
        old_val = {"number": seat.seat_number, "is_window": seat.is_window}
        seat.coach_id = form.coach_id.data
        seat.berth_type_id = form.berth_type_id.data
        seat.seat_number = form.seat_number.data.strip()
        seat.row_number = form.row_number.data
        seat.column_number = form.column_number.data
        seat.is_window = form.is_window.data
        seat.is_ladies_quota = form.is_ladies_quota.data

        log_audit_event(
            action="EDIT_SEAT",
            entity_name="Seat",
            entity_id=seat.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"number": seat.seat_number, "is_window": seat.is_window},
        )
        db.session.commit()

        flash(f"Seat '{seat.seat_number}' updated successfully.", "success")
        return redirect(url_for("admin.seats", coach_id=seat.coach_id))

    return render_template("admin/trains/seats_form.html", form=form, title=f"Edit Seat: {seat.seat_number}", target_obj=seat)


@admin_bp.route("/seats/<int:seat_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_delete(seat_id: int):
    """Soft delete seat with active locks / allocations guard."""
    seat = db.session.get(Seat, seat_id)
    if not seat:
        abort(404)

    def block_check():
        active_locks = db.session.scalar(select(func.count(SeatReservationLock.id)).filter_by(seat_id=seat.id, is_released=False))
        active_alloc = db.session.scalar(select(func.count(TicketSeatAllocation.id)).filter_by(seat_id=seat.id))
        if active_locks > 0 or active_alloc > 0:
            return f"Cannot soft-delete seat '{seat.seat_number}' because {active_locks} active lock(s) and {active_alloc} ticket allocation(s) are bound to it."
        return None

    return handle_admin_soft_delete(
        instance=seat,
        redirect_url=url_for("admin.seats", coach_id=seat.coach_id),
        entity_name="Seat",
        identifier_str=seat.seat_number,
        block_check=block_check,
    )


@admin_bp.route("/seats/<int:seat_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def seat_restore(seat_id: int):
    """Restore soft-deleted seat."""
    seat = db.session.get(Seat, seat_id)
    if not seat:
        abort(404)
    return handle_admin_restore(
        instance=seat,
        redirect_url=url_for("admin.seats", coach_id=seat.coach_id),
        entity_name="Seat",
        identifier_str=seat.seat_number,
    )

