"""Administrative routes for Routes & Pricing Master-Data (Phase 5B).

Models:
- Model #20: Route (Super Admin)
- Model #21: RouteStop (Super Admin)
- Model #22: FareRule (Super Admin)
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
from app.admin.routes_forms import (
    RouteForm,
    RouteStopForm,
    FareRuleForm,
)
from app.common.decorators import roles_required
from app.common.constants import ROLE_SUPER_ADMIN
from app.common.audit import log_audit_event
from app.extensions import db
from app.models.routes import Route, RouteStop, FareRule
from app.models.stations import Station
from app.models.trains import CoachClass
from app.models.schedules import Schedule, ScheduleStop


# ---------------------------------------------------------------------------
# 1. Route (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/routes")
@roles_required(ROLE_SUPER_ADMIN)
def routes():
    """List and paginate mainline and branch railway corridors."""
    return render_admin_list(
        model=Route,
        template_name="admin/routes/routes_index.html",
        search_columns=[Route.code, Route.name],
    )


@admin_bp.route("/routes/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_create():
    """Create a new railway corridor route."""
    form = RouteForm()
    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.source_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]
    form.destination_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if form.validate_on_submit():
        r = Route(
            code=form.code.data.strip().upper(),
            name=form.name.data.strip(),
            source_station_id=form.source_station_id.data,
            destination_station_id=form.destination_station_id.data,
            total_distance_km=form.total_distance_km.data,
        )
        db.session.add(r)
        db.session.flush()

        log_audit_event(
            action="CREATE_ROUTE",
            entity_name="Route",
            entity_id=r.id,
            user_id=current_user.id,
            new_values={
                "code": r.code,
                "name": r.name,
                "source_id": r.source_station_id,
                "destination_id": r.destination_station_id,
                "distance": str(r.total_distance_km),
            },
        )
        db.session.commit()

        flash(f"Route '{r.name}' ({r.code}) created successfully.", "success")
        return redirect(url_for("admin.routes"))

    return render_template("admin/routes/routes_form.html", form=form, title="Create Railway Route")


@admin_bp.route("/routes/<int:route_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_edit(route_id: int):
    """Edit corridor route details."""
    r = db.session.get(Route, route_id)
    if not r:
        abort(404)

    form = RouteForm(original_id=r.id)
    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.source_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]
    form.destination_station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if request.method == "GET":
        form.code.data = r.code
        form.name.data = r.name
        form.source_station_id.data = r.source_station_id
        form.destination_station_id.data = r.destination_station_id
        form.total_distance_km.data = r.total_distance_km

    if form.validate_on_submit():
        old_val = {"code": r.code, "name": r.name, "distance": str(r.total_distance_km)}
        r.code = form.code.data.strip().upper()
        r.name = form.name.data.strip()
        r.source_station_id = form.source_station_id.data
        r.destination_station_id = form.destination_station_id.data
        r.total_distance_km = form.total_distance_km.data

        log_audit_event(
            action="EDIT_ROUTE",
            entity_name="Route",
            entity_id=r.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"code": r.code, "name": r.name, "distance": str(r.total_distance_km)},
        )
        db.session.commit()

        flash(f"Route '{r.name}' updated successfully.", "success")
        return redirect(url_for("admin.routes"))

    return render_template("admin/routes/routes_form.html", form=form, title=f"Edit Route: {r.code}", target_obj=r)


@admin_bp.route("/routes/<int:route_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_delete(route_id: int):
    """Soft delete route with active stops and schedules guard."""
    r = db.session.get(Route, route_id)
    if not r:
        abort(404)

    def block_check():
        active_stops = db.session.scalar(select(func.count(RouteStop.id)).filter_by(route_id=r.id, is_deleted=False))
        active_sch = db.session.scalar(select(func.count(Schedule.id)).filter_by(route_id=r.id, is_deleted=False))
        if active_stops > 0 or active_sch > 0:
            return f"Cannot soft-delete route '{r.name}' because {active_stops} active stop(s) and {active_sch} active schedule(s) depend on it."
        return None

    return handle_admin_soft_delete(
        instance=r,
        redirect_url=url_for("admin.routes"),
        entity_name="Route",
        identifier_str=r.code,
        block_check=block_check,
    )


@admin_bp.route("/routes/<int:route_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_restore(route_id: int):
    """Restore soft-deleted route."""
    r = db.session.get(Route, route_id)
    if not r:
        abort(404)
    return handle_admin_restore(
        instance=r,
        redirect_url=url_for("admin.routes"),
        entity_name="Route",
        identifier_str=r.code,
    )


# ---------------------------------------------------------------------------
# 2. RouteStop (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/route-stops")
@roles_required(ROLE_SUPER_ADMIN)
def route_stops():
    """List sequential stops for a route."""
    filter_route_id = request.args.get("route_id", type=int)
    base_filter = None
    if filter_route_id:
        base_filter = (RouteStop.route_id == filter_route_id)

    routes_list = db.session.scalars(select(Route).filter_by(is_deleted=False).order_by(Route.code)).all()

    return render_admin_list(
        model=RouteStop,
        template_name="admin/routes/stops_index.html",
        search_columns=[],
        base_filter=base_filter,
        order_by_col=RouteStop.stop_sequence.asc(),
        context_extra={
            "routes": routes_list,
            "selected_route_id": filter_route_id,
        },
    )


@admin_bp.route("/route-stops/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_stop_create():
    """Add a sequential station stop to a route."""
    form = RouteStopForm()
    routes_list = db.session.scalars(select(Route).filter_by(is_deleted=False).order_by(Route.code)).all()
    form.route_id.choices = [(r.id, f"{r.name} ({r.code})") for r in routes_list]

    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if request.method == "GET" and request.args.get("route_id", type=int):
        form.route_id.data = request.args.get("route_id", type=int)

    if form.validate_on_submit():
        rs = RouteStop(
            route_id=form.route_id.data,
            station_id=form.station_id.data,
            stop_sequence=form.stop_sequence.data,
            distance_from_origin_km=form.distance_from_origin_km.data,
            standard_halt_minutes=form.standard_halt_minutes.data,
        )
        db.session.add(rs)
        db.session.flush()

        log_audit_event(
            action="CREATE_ROUTE_STOP",
            entity_name="RouteStop",
            entity_id=rs.id,
            user_id=current_user.id,
            new_values={
                "route_id": rs.route_id,
                "station_id": rs.station_id,
                "sequence": rs.stop_sequence,
                "distance": str(rs.distance_from_origin_km),
            },
        )
        db.session.commit()

        flash(f"Route stop #{rs.stop_sequence} added successfully.", "success")
        return redirect(url_for("admin.route_stops", route_id=rs.route_id))

    return render_template("admin/routes/stops_form.html", form=form, title="Add Route Stop")


@admin_bp.route("/route-stops/<int:stop_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_stop_edit(stop_id: int):
    """Edit route stop sequence or distance."""
    rs = db.session.get(RouteStop, stop_id)
    if not rs:
        abort(404)

    form = RouteStopForm(original_id=rs.id)
    routes_list = db.session.scalars(select(Route).filter_by(is_deleted=False).order_by(Route.code)).all()
    form.route_id.choices = [(r.id, f"{r.name} ({r.code})") for r in routes_list]

    stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
    form.station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if request.method == "GET":
        form.route_id.data = rs.route_id
        form.station_id.data = rs.station_id
        form.stop_sequence.data = rs.stop_sequence
        form.distance_from_origin_km.data = rs.distance_from_origin_km
        form.standard_halt_minutes.data = rs.standard_halt_minutes

    if form.validate_on_submit():
        old_val = {"seq": rs.stop_sequence, "distance": str(rs.distance_from_origin_km)}
        rs.route_id = form.route_id.data
        rs.station_id = form.station_id.data
        rs.stop_sequence = form.stop_sequence.data
        rs.distance_from_origin_km = form.distance_from_origin_km.data
        rs.standard_halt_minutes = form.standard_halt_minutes.data

        log_audit_event(
            action="EDIT_ROUTE_STOP",
            entity_name="RouteStop",
            entity_id=rs.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"seq": rs.stop_sequence, "distance": str(rs.distance_from_origin_km)},
        )
        db.session.commit()

        flash(f"Route stop #{rs.stop_sequence} updated successfully.", "success")
        return redirect(url_for("admin.route_stops", route_id=rs.route_id))

    return render_template("admin/routes/stops_form.html", form=form, title=f"Edit Route Stop #{rs.stop_sequence}", target_obj=rs)


@admin_bp.route("/route-stops/<int:stop_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_stop_delete(stop_id: int):
    """Soft delete route stop with active schedule stops guard."""
    rs = db.session.get(RouteStop, stop_id)
    if not rs:
        abort(404)

    def block_check():
        active_sch_stops = db.session.scalar(
            select(func.count(ScheduleStop.id)).filter_by(station_id=rs.station_id, is_deleted=False)
        )
        if active_sch_stops > 0:
            return f"Cannot soft-delete route stop at '{rs.station.name if rs.station else rs.station_id}' because active schedule stops reference it."
        return None

    return handle_admin_soft_delete(
        instance=rs,
        redirect_url=url_for("admin.route_stops", route_id=rs.route_id),
        entity_name="RouteStop",
        identifier_str=f"Stop #{rs.stop_sequence}",
        block_check=block_check,
    )


@admin_bp.route("/route-stops/<int:stop_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def route_stop_restore(stop_id: int):
    """Restore soft-deleted route stop."""
    rs = db.session.get(RouteStop, stop_id)
    if not rs:
        abort(404)
    return handle_admin_restore(
        instance=rs,
        redirect_url=url_for("admin.route_stops", route_id=rs.route_id),
        entity_name="RouteStop",
        identifier_str=f"Stop #{rs.stop_sequence}",
    )


# ---------------------------------------------------------------------------
# 3. FareRule (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/fare-rules")
@roles_required(ROLE_SUPER_ADMIN)
def fare_rules():
    """List distance-bracketed pricing rules."""
    filter_class_id = request.args.get("coach_class_id", type=int)
    base_filter = None
    if filter_class_id:
        base_filter = (FareRule.coach_class_id == filter_class_id)

    classes_list = db.session.scalars(select(CoachClass).filter_by(is_deleted=False).order_by(CoachClass.name)).all()

    return render_admin_list(
        model=FareRule,
        template_name="admin/routes/fares_index.html",
        search_columns=[],
        base_filter=base_filter,
        order_by_col=FareRule.min_distance_km.asc(),
        context_extra={
            "classes": classes_list,
            "selected_class_id": filter_class_id,
        },
    )


@admin_bp.route("/fare-rules/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def fare_rule_create():
    """Create a new fare rule."""
    form = FareRuleForm()
    classes_list = db.session.scalars(select(CoachClass).filter_by(is_deleted=False).order_by(CoachClass.name)).all()
    form.coach_class_id.choices = [(c.id, f"{c.name} ({c.code})") for c in classes_list]

    if request.method == "GET" and request.args.get("coach_class_id", type=int):
        form.coach_class_id.data = request.args.get("coach_class_id", type=int)

    if form.validate_on_submit():
        fr = FareRule(
            coach_class_id=form.coach_class_id.data,
            min_distance_km=form.min_distance_km.data,
            max_distance_km=form.max_distance_km.data,
            base_fare=form.base_fare.data,
            rate_per_km=form.rate_per_km.data,
            reservation_charge=form.reservation_charge.data,
        )
        db.session.add(fr)
        db.session.flush()

        log_audit_event(
            action="CREATE_FARE_RULE",
            entity_name="FareRule",
            entity_id=fr.id,
            user_id=current_user.id,
            new_values={
                "class_id": fr.coach_class_id,
                "range": f"{fr.min_distance_km}-{fr.max_distance_km}",
                "base": str(fr.base_fare),
                "per_km": str(fr.rate_per_km),
            },
        )
        db.session.commit()

        flash("Fare pricing rule created successfully.", "success")
        return redirect(url_for("admin.fare_rules", coach_class_id=fr.coach_class_id))

    return render_template("admin/routes/fares_form.html", form=form, title="Create Fare Pricing Rule")


@admin_bp.route("/fare-rules/<int:rule_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def fare_rule_edit(rule_id: int):
    """Edit fare pricing rule."""
    fr = db.session.get(FareRule, rule_id)
    if not fr:
        abort(404)

    form = FareRuleForm()
    classes_list = db.session.scalars(select(CoachClass).filter_by(is_deleted=False).order_by(CoachClass.name)).all()
    form.coach_class_id.choices = [(c.id, f"{c.name} ({c.code})") for c in classes_list]

    if request.method == "GET":
        form.coach_class_id.data = fr.coach_class_id
        form.min_distance_km.data = fr.min_distance_km
        form.max_distance_km.data = fr.max_distance_km
        form.base_fare.data = fr.base_fare
        form.rate_per_km.data = fr.rate_per_km
        form.reservation_charge.data = fr.reservation_charge

    if form.validate_on_submit():
        old_val = {"base": str(fr.base_fare), "rate": str(fr.rate_per_km)}
        fr.coach_class_id = form.coach_class_id.data
        fr.min_distance_km = form.min_distance_km.data
        fr.max_distance_km = form.max_distance_km.data
        fr.base_fare = form.base_fare.data
        fr.rate_per_km = form.rate_per_km.data
        fr.reservation_charge = form.reservation_charge.data

        log_audit_event(
            action="EDIT_FARE_RULE",
            entity_name="FareRule",
            entity_id=fr.id,
            user_id=current_user.id,
            old_values=old_val,
            new_values={"base": str(fr.base_fare), "rate": str(fr.rate_per_km)},
        )
        db.session.commit()

        flash("Fare pricing rule updated successfully.", "success")
        return redirect(url_for("admin.fare_rules", coach_class_id=fr.coach_class_id))

    return render_template("admin/routes/fares_form.html", form=form, title="Edit Fare Rule", target_obj=fr)


@admin_bp.route("/fare-rules/<int:rule_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def fare_rule_delete(rule_id: int):
    """Soft delete fare rule."""
    fr = db.session.get(FareRule, rule_id)
    if not fr:
        abort(404)
    return handle_admin_soft_delete(
        instance=fr,
        redirect_url=url_for("admin.fare_rules", coach_class_id=fr.coach_class_id),
        entity_name="FareRule",
        identifier_str=f"Rule #{fr.id}",
    )


@admin_bp.route("/fare-rules/<int:rule_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def fare_rule_restore(rule_id: int):
    """Restore soft-deleted fare rule."""
    fr = db.session.get(FareRule, rule_id)
    if not fr:
        abort(404)
    return handle_admin_restore(
        instance=fr,
        redirect_url=url_for("admin.fare_rules", coach_class_id=fr.coach_class_id),
        entity_name="FareRule",
        identifier_str=f"Rule #{fr.id}",
    )

