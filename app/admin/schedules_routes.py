"""Administrative routes for Timetable Schedules & Journey Instance Operations (Phase 5C).

Models:
- Model #23: Schedule (Super Admin)
- Model #24: ScheduleStop (Super Admin)
- Model #25: JourneyInstance (Super Admin, single CRUD + Date Range Generator)
- Model #26: JourneyCoach (Super Admin & Reservation Officer)
"""
from datetime import timedelta
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from sqlalchemy import select, func, or_

from app.admin import admin_bp
from app.admin.crud_helper import (
    render_admin_list,
    handle_admin_soft_delete,
    handle_admin_restore,
    handle_admin_hard_delete,
)
from app.admin.schedules_forms import (
    ScheduleForm,
    ScheduleStopForm,
    JourneyInstanceForm,
    JourneyGenerateForm,
    JourneyCoachForm,
)
from app.common.decorators import roles_required
from app.common.constants import ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER
from app.common.audit import log_audit_event
from app.extensions import db
from app.models.schedules import Schedule, ScheduleStop, JourneyInstance
from app.models.trains import Train, TrainCoach, Seat
from app.models.routes import Route
from app.models.stations import Station
from app.models.bookings import JourneyCoach, Booking, TicketSeatAllocation, SeatReservationLock


# ---------------------------------------------------------------------------
# 1. Schedule (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/schedules")
@roles_required(ROLE_SUPER_ADMIN)
def schedules():
    """List and paginate timetable schedule blueprints."""
    filter_train_id = request.args.get("train_id", type=int)
    base_filter = None
    if filter_train_id:
        base_filter = (Schedule.train_id == filter_train_id)

    trains_list = db.session.scalars(select(Train).filter_by(is_deleted=False).order_by(Train.train_number)).all()

    return render_admin_list(
        model=Schedule,
        template_name="admin/schedules/schedules_index.html",
        search_columns=[Schedule.schedule_code],
        base_filter=base_filter,
        context_extra={
            "trains": trains_list,
            "selected_train_id": filter_train_id,
        },
    )


@admin_bp.route("/schedules/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_create():
    """Create a new timetable schedule."""
    form = ScheduleForm()
    trains_list = db.session.scalars(select(Train).filter_by(is_deleted=False).order_by(Train.train_number)).all()
    form.train_id.choices = [(t.id, f"{t.name} ({t.train_number})") for t in trains_list]

    routes_list = db.session.scalars(select(Route).filter_by(is_deleted=False).order_by(Route.code)).all()
    form.route_id.choices = [(r.id, f"{r.name} ({r.code})") for r in routes_list]

    if form.validate_on_submit():
        sch = Schedule(
            train_id=form.train_id.data,
            route_id=form.route_id.data,
            schedule_code=form.schedule_code.data.strip().upper(),
            departure_time=form.departure_time.data,
            arrival_time=form.arrival_time.data,
            journey_days_span=form.journey_days_span.data,
            is_active=form.is_active.data,
        )
        db.session.add(sch)
        db.session.flush()

        log_audit_event(
            action="CREATE_SCHEDULE",
            entity_name="Schedule",
            entity_id=sch.id,
            user_id=current_user.id,
            new_values={
                "code": sch.schedule_code,
                "train_id": sch.train_id,
                "route_id": sch.route_id,
                "departure": str(sch.departure_time),
                "arrival": str(sch.arrival_time),
            },
        )
        db.session.commit()

        flash(f"Schedule '{sch.schedule_code}' created successfully.", "success")
        return redirect(url_for("admin.schedules"))

    return render_template("admin/schedules/schedules_form.html", form=form, title="Create Timetable Schedule")


@admin_bp.route("/schedules/<int:sch_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_edit(sch_id: int):
    """Edit timetable schedule."""
    sch = db.session.get(Schedule, sch_id)
    if not sch:
        abort(404)

    form = ScheduleForm(original_id=sch.id)
    trains_list = db.session.scalars(select(Train).filter_by(is_deleted=False).order_by(Train.train_number)).all()
    form.train_id.choices = [(t.id, f"{t.name} ({t.train_number})") for t in trains_list]

    routes_list = db.session.scalars(select(Route).filter_by(is_deleted=False).order_by(Route.code)).all()
    form.route_id.choices = [(r.id, f"{r.name} ({r.code})") for r in routes_list]

    if request.method == "GET":
        form.train_id.data = sch.train_id
        form.route_id.data = sch.route_id
        form.schedule_code.data = sch.schedule_code
        form.departure_time.data = sch.departure_time
        form.arrival_time.data = sch.arrival_time
        form.journey_days_span.data = sch.journey_days_span
        form.is_active.data = sch.is_active

    if form.validate_on_submit():
        old_val = {"code": sch.schedule_code, "dep": str(sch.departure_time), "arr": str(sch.arrival_time)}
        sch.train_id = form.train_id.data
        sch.route_id = form.route_id.data
        sch.schedule_code = form.schedule_code.data.strip().upper()
        sch.departure_time = form.departure_time.data
        sch.arrival_time = form.arrival_time.data
        sch.journey_days_span = form.journey_days_span.data
        sch.is_active = form.is_active.data

        log_audit_event(
            action="EDIT_SCHEDULE",
            entity_name="Schedule",
            entity_id=sch.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"code": sch.schedule_code, "dep": str(sch.departure_time), "arr": str(sch.arrival_time)},
        )
        db.session.commit()

        flash(f"Schedule '{sch.schedule_code}' updated successfully.", "success")
        return redirect(url_for("admin.schedules"))

    return render_template("admin/schedules/schedules_form.html", form=form, title=f"Edit Schedule: {sch.schedule_code}", target_obj=sch)


@admin_bp.route("/schedules/<int:sch_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_delete(sch_id: int):
    """Soft delete schedule with active stops and journey instances guard."""
    sch = db.session.get(Schedule, sch_id)
    if not sch:
        abort(404)

    def block_check():
        active_stops = db.session.scalar(select(func.count(ScheduleStop.id)).filter_by(schedule_id=sch.id, is_deleted=False))
        active_journeys = db.session.scalar(select(func.count(JourneyInstance.id)).filter_by(schedule_id=sch.id, is_deleted=False))
        if active_stops > 0 or active_journeys > 0:
            return f"Cannot soft-delete schedule '{sch.schedule_code}' because {active_stops} active stop(s) and {active_journeys} active calendar journey(s) depend on it."
        return None

    return handle_admin_soft_delete(
        instance=sch,
        redirect_url=url_for("admin.schedules"),
        entity_name="Schedule",
        identifier_str=sch.schedule_code,
        block_check=block_check,
    )


@admin_bp.route("/schedules/<int:sch_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_restore(sch_id: int):
    """Restore soft-deleted schedule."""
    sch = db.session.get(Schedule, sch_id)
    if not sch:
        abort(404)
    return handle_admin_restore(
        instance=sch,
        redirect_url=url_for("admin.schedules"),
        entity_name="Schedule",
        identifier_str=sch.schedule_code,
    )


# ---------------------------------------------------------------------------
# 2. ScheduleStop (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/schedule-stops")
@roles_required(ROLE_SUPER_ADMIN)
def schedule_stops():
    """List stops for a schedule."""
    filter_schedule_id = request.args.get("schedule_id", type=int)
    base_filter = None
    if filter_schedule_id:
        base_filter = (ScheduleStop.schedule_id == filter_schedule_id)

    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()

    return render_admin_list(
        model=ScheduleStop,
        template_name="admin/schedules/stops_index.html",
        search_columns=[],
        base_filter=base_filter,
        order_by_col=ScheduleStop.stop_sequence.asc(),
        context_extra={
            "schedules": schedules_list,
            "selected_schedule_id": filter_schedule_id,
        },
    )


@admin_bp.route("/schedule-stops/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_stop_create():
    """Add a stop with arrival/departure timings to a schedule."""
    form = ScheduleStopForm()
    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()
    form.schedule_id.choices = [(s.id, f"{s.schedule_code} (Train: {s.train.train_number if s.train else '—'})") for s in schedules_list]

    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.station_id.choices = [(st.id, f"{st.name} ({st.code})") for st in stns]

    if request.method == "GET" and request.args.get("schedule_id", type=int):
        form.schedule_id.data = request.args.get("schedule_id", type=int)

    if form.validate_on_submit():
        ss = ScheduleStop(
            schedule_id=form.schedule_id.data,
            station_id=form.station_id.data,
            stop_sequence=form.stop_sequence.data,
            scheduled_arrival=form.scheduled_arrival.data,
            scheduled_departure=form.scheduled_departure.data,
            day_offset=form.day_offset.data,
        )
        db.session.add(ss)
        db.session.flush()

        log_audit_event(
            action="CREATE_SCHEDULE_STOP",
            entity_name="ScheduleStop",
            entity_id=ss.id,
            user_id=current_user.id,
            new_values={
                "schedule_id": ss.schedule_id,
                "station_id": ss.station_id,
                "seq": ss.stop_sequence,
                "arr": str(ss.scheduled_arrival),
                "dep": str(ss.scheduled_departure),
            },
        )
        db.session.commit()

        flash(f"Schedule stop #{ss.stop_sequence} created successfully.", "success")
        return redirect(url_for("admin.schedule_stops", schedule_id=ss.schedule_id))

    return render_template("admin/schedules/stops_form.html", form=form, title="Add Schedule Timetable Stop")


@admin_bp.route("/schedule-stops/<int:stop_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_stop_edit(stop_id: int):
    """Edit schedule stop timings and sequence."""
    ss = db.session.get(ScheduleStop, stop_id)
    if not ss:
        abort(404)

    form = ScheduleStopForm(original_id=ss.id)
    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()
    form.schedule_id.choices = [(s.id, f"{s.schedule_code} (Train: {s.train.train_number if s.train else '—'})") for s in schedules_list]

    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.station_id.choices = [(st.id, f"{st.name} ({st.code})") for st in stns]

    if request.method == "GET":
        form.schedule_id.data = ss.schedule_id
        form.station_id.data = ss.station_id
        form.stop_sequence.data = ss.stop_sequence
        form.scheduled_arrival.data = ss.scheduled_arrival
        form.scheduled_departure.data = ss.scheduled_departure
        form.day_offset.data = ss.day_offset

    if form.validate_on_submit():
        old_val = {"seq": ss.stop_sequence, "arr": str(ss.scheduled_arrival), "dep": str(ss.scheduled_departure)}
        ss.schedule_id = form.schedule_id.data
        ss.station_id = form.station_id.data
        ss.stop_sequence = form.stop_sequence.data
        ss.scheduled_arrival = form.scheduled_arrival.data
        ss.scheduled_departure = form.scheduled_departure.data
        ss.day_offset = form.day_offset.data

        log_audit_event(
            action="EDIT_SCHEDULE_STOP",
            entity_name="ScheduleStop",
            entity_id=ss.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"seq": ss.stop_sequence, "arr": str(ss.scheduled_arrival), "dep": str(ss.scheduled_departure)},
        )
        db.session.commit()

        flash(f"Schedule stop #{ss.stop_sequence} updated successfully.", "success")
        return redirect(url_for("admin.schedule_stops", schedule_id=ss.schedule_id))

    return render_template("admin/schedules/stops_form.html", form=form, title=f"Edit Schedule Stop #{ss.stop_sequence}", target_obj=ss)


@admin_bp.route("/schedule-stops/<int:stop_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_stop_delete(stop_id: int):
    """Soft delete schedule stop."""
    ss = db.session.get(ScheduleStop, stop_id)
    if not ss:
        abort(404)
    return handle_admin_soft_delete(
        instance=ss,
        redirect_url=url_for("admin.schedule_stops", schedule_id=ss.schedule_id),
        entity_name="ScheduleStop",
        identifier_str=f"Stop #{ss.stop_sequence}",
    )


@admin_bp.route("/schedule-stops/<int:stop_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def schedule_stop_restore(stop_id: int):
    """Restore soft-deleted schedule stop."""
    ss = db.session.get(ScheduleStop, stop_id)
    if not ss:
        abort(404)
    return handle_admin_restore(
        instance=ss,
        redirect_url=url_for("admin.schedule_stops", schedule_id=ss.schedule_id),
        entity_name="ScheduleStop",
        identifier_str=f"Stop #{ss.stop_sequence}",
    )


# ---------------------------------------------------------------------------
# 3. JourneyInstance (Super Admin, Single + Date Range Generator)
# ---------------------------------------------------------------------------
@admin_bp.route("/journeys")
@roles_required(ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER)
def journeys():
    """List operational train journey instances with filtering."""
    filter_sch_id = request.args.get("schedule_id", type=int)
    filter_status = request.args.get("status_val")
    base_filter = None

    filters = []
    if filter_sch_id:
        filters.append(JourneyInstance.schedule_id == filter_sch_id)
    if filter_status:
        filters.append(JourneyInstance.status == filter_status)

    if filters:
        base_filter = db.and_(*filters)

    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()

    return render_admin_list(
        model=JourneyInstance,
        template_name="admin/schedules/journeys_index.html",
        search_columns=[],
        base_filter=base_filter,
        order_by_col=JourneyInstance.journey_date.desc(),
        context_extra={
            "schedules": schedules_list,
            "selected_schedule_id": filter_sch_id,
            "selected_status_val": filter_status,
        },
    )


@admin_bp.route("/journeys/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def journey_create():
    """Manually instantiate a single journey run for a specific date."""
    form = JourneyInstanceForm()
    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()
    form.schedule_id.choices = [(s.id, f"{s.schedule_code} (Train: {s.train.train_number if s.train else '—'})") for s in schedules_list]

    if form.validate_on_submit():
        j = JourneyInstance(
            schedule_id=form.schedule_id.data,
            journey_date=form.journey_date.data,
            status=form.status.data,
            current_delay_minutes=form.current_delay_minutes.data,
            is_booking_open=form.is_booking_open.data,
            cancellation_reason=form.cancellation_reason.data.strip() if form.cancellation_reason.data else None,
        )
        db.session.add(j)
        db.session.flush()

        # Attach active train coaches
        sch = db.session.get(Schedule, j.schedule_id)
        if sch and sch.train:
            for tc in sch.train.coaches:
                if not tc.is_deleted:
                    db.session.add(
                        JourneyCoach(
                            journey_instance_id=j.id,
                            train_coach_id=tc.id,
                            sequence_in_train=tc.sequence_number,
                            available_seats_count=tc.total_capacity,
                            is_available=True,
                        )
                    )

        log_audit_event(
            action="CREATE_JOURNEY_INSTANCE",
            entity_name="JourneyInstance",
            entity_id=j.id,
            user_id=current_user.id,
            new_values={"schedule_id": j.schedule_id, "date": str(j.journey_date), "status": j.status},
        )
        db.session.commit()

        flash(f"Journey on {j.journey_date} created successfully.", "success")
        return redirect(url_for("admin.journeys", schedule_id=j.schedule_id))

    return render_template("admin/schedules/journeys_form.html", form=form, title="Create Journey Instance")


@admin_bp.route("/journeys/generate", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def journey_generate():
    """Batch journey generator for date range, respecting TrainOperationalDays."""
    form = JourneyGenerateForm()
    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()
    form.schedule_id.choices = [(s.id, f"{s.schedule_code} (Train: {s.train.train_number if s.train else '—'})") for s in schedules_list]

    if request.method == "GET" and request.args.get("schedule_id", type=int):
        form.schedule_id.data = request.args.get("schedule_id", type=int)

    if form.validate_on_submit():
        sch_id = form.schedule_id.data
        sch = db.session.get(Schedule, sch_id)
        if not sch:
            abort(404)

        start = form.start_date.data
        end = form.end_date.data
        auto_coaches = form.auto_attach_coaches.data

        # Find operational days for this train (0=Mon, 6=Sun)
        train = sch.train
        allowed_days = {d.day_of_week for d in train.operational_days if d.is_active} if train else set(range(7))

        cur = start
        created_count = 0
        skipped_days_count = 0
        already_exist_count = 0

        while cur <= end:
            # Check day of week (Python date.weekday(): 0=Mon .. 6=Sun)
            if cur.weekday() not in allowed_days:
                skipped_days_count += 1
                cur += timedelta(days=1)
                continue

            # Check if active journey already exists
            exists = db.session.scalar(select(JourneyInstance).filter_by(schedule_id=sch_id, journey_date=cur, is_deleted=False))
            if exists:
                already_exist_count += 1
                cur += timedelta(days=1)
                continue

            j = JourneyInstance(
                schedule_id=sch_id,
                journey_date=cur,
                status="Scheduled",
                is_booking_open=True,
            )
            db.session.add(j)
            db.session.flush()

            if auto_coaches and train:
                for tc in train.coaches:
                    if not tc.is_deleted:
                        db.session.add(
                            JourneyCoach(
                                journey_instance_id=j.id,
                                train_coach_id=tc.id,
                                sequence_in_train=tc.sequence_number,
                                available_seats_count=tc.total_capacity,
                                is_available=True,
                            )
                        )

            created_count += 1
            cur += timedelta(days=1)

        log_audit_event(
            action="BATCH_GENERATE_JOURNEYS",
            entity_name="JourneyInstance",
            entity_id=sch_id,
            user_id=current_user.id,
            new_values={
                "schedule_id": sch_id,
                "range": f"{start} to {end}",
                "generated": created_count,
                "skipped_off_days": skipped_days_count,
            },
        )
        db.session.commit()

        flash(
            f"Batch generation completed: {created_count} journeys generated, "
            f"{skipped_days_count} dates skipped (non-operational days), {already_exist_count} already existed.",
            "success",
        )
        return redirect(url_for("admin.journeys", schedule_id=sch_id))

    return render_template("admin/schedules/journeys_generate.html", form=form, title="Batch Journey Generator")


@admin_bp.route("/journeys/<int:journey_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER)
def journey_edit(journey_id: int):
    """Edit journey instance status, delay, and booking state."""
    j = db.session.get(JourneyInstance, journey_id)
    if not j:
        abort(404)

    form = JourneyInstanceForm(original_id=j.id)
    schedules_list = db.session.scalars(select(Schedule).filter_by(is_deleted=False).order_by(Schedule.schedule_code)).all()
    form.schedule_id.choices = [(s.id, f"{s.schedule_code} (Train: {s.train.train_number if s.train else '—'})") for s in schedules_list]

    if request.method == "GET":
        form.schedule_id.data = j.schedule_id
        form.journey_date.data = j.journey_date
        form.status.data = j.status
        form.current_delay_minutes.data = j.current_delay_minutes
        form.is_booking_open.data = j.is_booking_open
        form.cancellation_reason.data = j.cancellation_reason

    if form.validate_on_submit():
        old_val = {"status": j.status, "delay": j.current_delay_minutes, "open": j.is_booking_open}
        j.schedule_id = form.schedule_id.data
        j.journey_date = form.journey_date.data
        j.status = form.status.data
        j.current_delay_minutes = form.current_delay_minutes.data
        j.is_booking_open = form.is_booking_open.data
        j.cancellation_reason = form.cancellation_reason.data.strip() if form.cancellation_reason.data else None

        log_audit_event(
            action="EDIT_JOURNEY_INSTANCE",
            entity_name="JourneyInstance",
            entity_id=j.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"status": j.status, "delay": j.current_delay_minutes, "open": j.is_booking_open},
        )
        db.session.commit()

        flash(f"Journey on {j.journey_date} updated successfully.", "success")
        return redirect(url_for("admin.journeys", schedule_id=j.schedule_id))

    return render_template("admin/schedules/journeys_form.html", form=form, title=f"Edit Journey: {j.journey_date}", target_obj=j)


@admin_bp.route("/journeys/<int:journey_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def journey_delete(journey_id: int):
    """Soft delete journey with active bookings guard."""
    j = db.session.get(JourneyInstance, journey_id)
    if not j:
        abort(404)

    def block_check():
        active_bookings = db.session.scalar(select(func.count(Booking.id)).filter_by(journey_instance_id=j.id))
        if active_bookings > 0:
            return f"Cannot soft-delete journey '{j.journey_date}' because {active_bookings} booking(s) exist for it."
        return None

    return handle_admin_soft_delete(
        instance=j,
        redirect_url=url_for("admin.journeys", schedule_id=j.schedule_id),
        entity_name="JourneyInstance",
        identifier_str=str(j.journey_date),
        block_check=block_check,
    )


@admin_bp.route("/journeys/<int:journey_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def journey_restore(journey_id: int):
    """Restore soft-deleted journey."""
    j = db.session.get(JourneyInstance, journey_id)
    if not j:
        abort(404)
    return handle_admin_restore(
        instance=j,
        redirect_url=url_for("admin.journeys", schedule_id=j.schedule_id),
        entity_name="JourneyInstance",
        identifier_str=str(j.journey_date),
    )


# ---------------------------------------------------------------------------
# 4. JourneyCoach (Super Admin & Reservation Officer)
# ---------------------------------------------------------------------------
@admin_bp.route("/journey-coaches")
@roles_required(ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER)
def journey_coaches():
    """List operational carriages on a journey run."""
    filter_journey_id = request.args.get("journey_id", type=int)
    base_filter = None
    if filter_journey_id:
        base_filter = (JourneyCoach.journey_instance_id == filter_journey_id)

    journeys_list = db.session.scalars(select(JourneyInstance).filter_by(is_deleted=False).order_by(JourneyInstance.journey_date.desc())).all()

    return render_admin_list(
        model=JourneyCoach,
        template_name="admin/schedules/journey_coaches_index.html",
        search_columns=[],
        base_filter=base_filter,
        order_by_col=JourneyCoach.sequence_in_train.asc(),
        context_extra={
            "journeys": journeys_list,
            "selected_journey_id": filter_journey_id,
        },
    )


@admin_bp.route("/journey-coaches/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER)
def journey_coach_create():
    """Attach coach carriage to a journey instance."""
    form = JourneyCoachForm()
    journeys_list = db.session.scalars(select(JourneyInstance).filter_by(is_deleted=False).order_by(JourneyInstance.journey_date.desc())).all()
    form.journey_instance_id.choices = [
        (j.id, f"{j.journey_date} — {j.schedule.schedule_code if j.schedule else '—'}")
        for j in journeys_list
    ]

    coaches_list = db.session.scalars(select(TrainCoach).filter_by(is_deleted=False).order_by(TrainCoach.coach_code)).all()
    form.train_coach_id.choices = [(c.id, f"{c.coach_code} ({c.coach_class.name if c.coach_class else '—'})") for c in coaches_list]

    if request.method == "GET" and request.args.get("journey_id", type=int):
        form.journey_instance_id.data = request.args.get("journey_id", type=int)

    if form.validate_on_submit():
        jc = JourneyCoach(
            journey_instance_id=form.journey_instance_id.data,
            train_coach_id=form.train_coach_id.data,
            sequence_in_train=form.sequence_in_train.data,
            available_seats_count=form.available_seats_count.data,
            is_available=form.is_available.data,
        )
        db.session.add(jc)
        db.session.flush()

        log_audit_event(
            action="CREATE_JOURNEY_COACH",
            entity_name="JourneyCoach",
            entity_id=jc.id,
            user_id=current_user.id,
            new_values={
                "journey_id": jc.journey_instance_id,
                "coach_id": jc.train_coach_id,
                "seats": jc.available_seats_count,
            },
        )
        db.session.commit()

        flash("Journey coach attached successfully.", "success")
        return redirect(url_for("admin.journey_coaches", journey_id=jc.journey_instance_id))

    return render_template("admin/schedules/journey_coaches_form.html", form=form, title="Attach Journey Coach")


@admin_bp.route("/journey-coaches/<int:jc_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER)
def journey_coach_edit(jc_id: int):
    """Edit journey coach capacity and reservation availability."""
    jc = db.session.get(JourneyCoach, jc_id)
    if not jc:
        abort(404)

    form = JourneyCoachForm(original_id=jc.id)
    journeys_list = db.session.scalars(select(JourneyInstance).filter_by(is_deleted=False).order_by(JourneyInstance.journey_date.desc())).all()
    form.journey_instance_id.choices = [
        (j.id, f"{j.journey_date} — {j.schedule.schedule_code if j.schedule else '—'}")
        for j in journeys_list
    ]

    coaches_list = db.session.scalars(select(TrainCoach).filter_by(is_deleted=False).order_by(TrainCoach.coach_code)).all()
    form.train_coach_id.choices = [(c.id, f"{c.coach_code} ({c.coach_class.name if c.coach_class else '—'})") for c in coaches_list]

    if request.method == "GET":
        form.journey_instance_id.data = jc.journey_instance_id
        form.train_coach_id.data = jc.train_coach_id
        form.sequence_in_train.data = jc.sequence_in_train
        form.available_seats_count.data = jc.available_seats_count
        form.is_available.data = jc.is_available

    if form.validate_on_submit():
        old_val = {"seats": jc.available_seats_count, "avail": jc.is_available}
        jc.journey_instance_id = form.journey_instance_id.data
        jc.train_coach_id = form.train_coach_id.data
        jc.sequence_in_train = form.sequence_in_train.data
        jc.available_seats_count = form.available_seats_count.data
        jc.is_available = form.is_available.data

        log_audit_event(
            action="EDIT_JOURNEY_COACH",
            entity_name="JourneyCoach",
            entity_id=jc.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"seats": jc.available_seats_count, "avail": jc.is_available},
        )
        db.session.commit()

        flash("Journey coach updated successfully.", "success")
        return redirect(url_for("admin.journey_coaches", journey_id=jc.journey_instance_id))

    return render_template("admin/schedules/journey_coaches_form.html", form=form, title="Edit Journey Coach", target_obj=jc)


@admin_bp.route("/journey-coaches/<int:jc_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_RESERVATION_OFFICER)
def journey_coach_delete(jc_id: int):
    """Hard delete journey coach with active booking allocations guard."""
    jc = db.session.get(JourneyCoach, jc_id)
    if not jc:
        abort(404)

    def block_check():
        active_alloc = db.session.scalar(
            select(func.count(TicketSeatAllocation.id))
            .join(Seat, TicketSeatAllocation.seat_id == Seat.id)
            .filter(
                TicketSeatAllocation.journey_instance_id == jc.journey_instance_id,
                Seat.coach_id == jc.train_coach_id,
            )
        )
        if active_alloc > 0:
            return f"Cannot delete journey coach because {active_alloc} passenger ticket seat allocation(s) exist for it."
        return None

    return handle_admin_hard_delete(
        instance=jc,
        redirect_url=url_for("admin.journey_coaches", journey_id=jc.journey_instance_id),
        entity_name="JourneyCoach",
        identifier_str=f"Coach #{jc.sequence_in_train}",
        block_check=block_check,
    )

