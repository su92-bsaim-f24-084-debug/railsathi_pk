"""Administrative routes for Railway Infrastructure & Station Master-Data (Phase 5A).

Manages:
- Model #7: StationDivision (Super Admin)
- Model #8: Station (Super Admin)
- Model #9: StationPlatform (Super Admin & Station Master scoped to assigned station)
- Model #10: FacilityCategory (Super Admin)
- Model #11: StationFacility (Super Admin & Station Master scoped to assigned station)
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
from app.admin.station_forms import (
    StationDivisionForm,
    StationForm,
    StationPlatformForm,
    FacilityCategoryForm,
    StationFacilityForm,
)
from app.common.decorators import roles_required
from app.common.constants import ROLE_SUPER_ADMIN, ROLE_STATION_MASTER
from app.common.audit import log_audit_event
from app.extensions import db
from app.models.stations import (
    StationDivision,
    Station,
    StationPlatform,
    FacilityCategory,
    StationFacility,
)
from app.models.routes import RouteStop


def get_station_master_assigned_station_id() -> int:
    """Return the assigned station_id for the current Station Master, or abort 403."""
    if current_user.has_role(ROLE_SUPER_ADMIN):
        return None
    if current_user.has_role(ROLE_STATION_MASTER):
        if current_user.staff_profile and current_user.staff_profile.station_id:
            return current_user.staff_profile.station_id
    abort(403)


# ---------------------------------------------------------------------------
# 1. StationDivision (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/divisions")
@roles_required(ROLE_SUPER_ADMIN)
def divisions():
    """List and paginate regional railway divisions."""
    return render_admin_list(
        model=StationDivision,
        template_name="admin/stations/divisions_index.html",
        search_columns=[StationDivision.code, StationDivision.name, StationDivision.headquarters_city],
    )


@admin_bp.route("/divisions/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def division_create():
    """Create a new administrative railway division."""
    form = StationDivisionForm()
    if form.validate_on_submit():
        div = StationDivision(
            code=form.code.data.strip().upper(),
            name=form.name.data.strip(),
            headquarters_city=form.headquarters_city.data.strip(),
        )
        db.session.add(div)
        db.session.flush()

        log_audit_event(
            action="CREATE_STATION_DIVISION",
            entity_name="StationDivision",
            entity_id=div.id,
            user_id=current_user.id,
            new_values={"code": div.code, "name": div.name, "city": div.headquarters_city},
        )
        db.session.commit()

        flash(f"Division '{div.name}' ({div.code}) created successfully.", "success")
        return redirect(url_for("admin.divisions"))

    return render_template("admin/stations/divisions_form.html", form=form, title="Create Railway Division")


@admin_bp.route("/divisions/<int:div_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def division_edit(div_id: int):
    """Edit existing railway division."""
    div = db.session.get(StationDivision, div_id)
    if not div:
        abort(404)

    form = StationDivisionForm(original_id=div.id)
    if request.method == "GET":
        form.code.data = div.code
        form.name.data = div.name
        form.headquarters_city.data = div.headquarters_city

    if form.validate_on_submit():
        old_values = {"code": div.code, "name": div.name, "city": div.headquarters_city}
        div.code = form.code.data.strip().upper()
        div.name = form.name.data.strip()
        div.headquarters_city = form.headquarters_city.data.strip()

        log_audit_event(
            action="EDIT_STATION_DIVISION",
            entity_name="StationDivision",
            entity_id=div.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values={"code": div.code, "name": div.name, "city": div.headquarters_city},
        )
        db.session.commit()

        flash(f"Division '{div.name}' updated successfully.", "success")
        return redirect(url_for("admin.divisions"))

    return render_template(
        "admin/stations/divisions_form.html",
        form=form,
        title=f"Edit Division: {div.code}",
        target_obj=div,
    )


@admin_bp.route("/divisions/<int:div_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def division_delete(div_id: int):
    """Soft delete railway division with active stations block."""
    div = db.session.get(StationDivision, div_id)
    if not div:
        abort(404)

    def block_check():
        active_stations_cnt = db.session.scalar(
            select(func.count(Station.id)).filter_by(division_id=div.id, is_deleted=False)
        )
        if active_stations_cnt > 0:
            return f"Cannot soft-delete division '{div.name}' because it contains {active_stations_cnt} active station(s). Reassign or soft-delete them first."
        return None

    return handle_admin_soft_delete(
        instance=div,
        redirect_url=url_for("admin.divisions"),
        entity_name="StationDivision",
        identifier_str=div.code,
        block_check=block_check,
    )


@admin_bp.route("/divisions/<int:div_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def division_restore(div_id: int):
    """Restore soft-deleted railway division."""
    div = db.session.get(StationDivision, div_id)
    if not div:
        abort(404)
    return handle_admin_restore(
        instance=div,
        redirect_url=url_for("admin.divisions"),
        entity_name="StationDivision",
        identifier_str=div.code,
    )


# ---------------------------------------------------------------------------
# 2. Station (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/stations")
@roles_required(ROLE_SUPER_ADMIN)
def stations():
    """List and paginate operational railway stations."""
    return render_admin_list(
        model=Station,
        template_name="admin/stations/stations_index.html",
        search_columns=[Station.code, Station.name, Station.city, Station.province],
    )


@admin_bp.route("/stations/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def station_create():
    """Create a new railway station."""
    form = StationForm()
    divs = db.session.scalars(select(StationDivision).filter_by(is_deleted=False).order_by(StationDivision.name)).all()
    form.division_id.choices = [(d.id, f"{d.name} ({d.code})") for d in divs]

    if form.validate_on_submit():
        stn = Station(
            division_id=form.division_id.data,
            code=form.code.data.strip().upper(),
            name=form.name.data.strip(),
            city=form.city.data.strip(),
            province=form.province.data,
            latitude=form.latitude.data,
            longitude=form.longitude.data,
            contact_number=form.contact_number.data.strip() if form.contact_number.data else None,
            is_junction=form.is_junction.data,
        )
        db.session.add(stn)
        db.session.flush()

        log_audit_event(
            action="CREATE_STATION",
            entity_name="Station",
            entity_id=stn.id,
            user_id=current_user.id,
            new_values={
                "code": stn.code,
                "name": stn.name,
                "division_id": stn.division_id,
                "city": stn.city,
                "province": stn.province,
                "is_junction": stn.is_junction,
            },
        )
        db.session.commit()

        flash(f"Station '{stn.name}' ({stn.code}) registered successfully.", "success")
        return redirect(url_for("admin.stations"))

    return render_template("admin/stations/stations_form.html", form=form, title="Register Railway Station")


@admin_bp.route("/stations/<int:station_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def station_edit(station_id: int):
    """Edit railway station details."""
    stn = db.session.get(Station, station_id)
    if not stn:
        abort(404)

    form = StationForm(original_id=stn.id)
    divs = db.session.scalars(select(StationDivision).filter_by(is_deleted=False).order_by(StationDivision.name)).all()
    form.division_id.choices = [(d.id, f"{d.name} ({d.code})") for d in divs]

    if request.method == "GET":
        form.division_id.data = stn.division_id
        form.code.data = stn.code
        form.name.data = stn.name
        form.city.data = stn.city
        form.province.data = stn.province
        form.latitude.data = stn.latitude
        form.longitude.data = stn.longitude
        form.contact_number.data = stn.contact_number
        form.is_junction.data = stn.is_junction

    if form.validate_on_submit():
        old_values = {
            "code": stn.code,
            "name": stn.name,
            "division_id": stn.division_id,
            "city": stn.city,
            "province": stn.province,
            "is_junction": stn.is_junction,
        }
        stn.division_id = form.division_id.data
        stn.code = form.code.data.strip().upper()
        stn.name = form.name.data.strip()
        stn.city = form.city.data.strip()
        stn.province = form.province.data
        stn.latitude = form.latitude.data
        stn.longitude = form.longitude.data
        stn.contact_number = form.contact_number.data.strip() if form.contact_number.data else None
        stn.is_junction = form.is_junction.data

        log_audit_event(
            action="EDIT_STATION",
            entity_name="Station",
            entity_id=stn.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values={
                "code": stn.code,
                "name": stn.name,
                "division_id": stn.division_id,
                "city": stn.city,
                "province": stn.province,
                "is_junction": stn.is_junction,
            },
        )
        db.session.commit()

        flash(f"Station '{stn.name}' updated successfully.", "success")
        return redirect(url_for("admin.stations"))

    return render_template(
        "admin/stations/stations_form.html",
        form=form,
        title=f"Edit Station: {stn.code}",
        target_obj=stn,
    )


@admin_bp.route("/stations/<int:station_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def station_delete(station_id: int):
    """Soft delete station with active platforms/facilities/route stops block."""
    stn = db.session.get(Station, station_id)
    if not stn:
        abort(404)

    def block_check():
        active_platforms_cnt = db.session.scalar(
            select(func.count(StationPlatform.id)).filter_by(station_id=stn.id, is_deleted=False)
        )
        active_facilities_cnt = db.session.scalar(
            select(func.count(StationFacility.id)).filter_by(station_id=stn.id, is_deleted=False)
        )
        active_stops_cnt = db.session.scalar(
            select(func.count(RouteStop.id)).filter_by(station_id=stn.id, is_deleted=False)
        )
        if active_platforms_cnt > 0 or active_facilities_cnt > 0 or active_stops_cnt > 0:
            return (
                f"Cannot soft-delete station '{stn.name}' because it has active dependencies: "
                f"{active_platforms_cnt} platform(s), {active_facilities_cnt} facility/facilities, "
                f"and {active_stops_cnt} route stop(s). Deactivate or reassign them first."
            )
        return None

    return handle_admin_soft_delete(
        instance=stn,
        redirect_url=url_for("admin.stations"),
        entity_name="Station",
        identifier_str=stn.code,
        block_check=block_check,
    )


@admin_bp.route("/stations/<int:station_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def station_restore(station_id: int):
    """Restore soft-deleted station."""
    stn = db.session.get(Station, station_id)
    if not stn:
        abort(404)
    return handle_admin_restore(
        instance=stn,
        redirect_url=url_for("admin.stations"),
        entity_name="Station",
        identifier_str=stn.code,
    )


# ---------------------------------------------------------------------------
# 3. FacilityCategory (Super Admin)
# ---------------------------------------------------------------------------
@admin_bp.route("/facility-categories")
@roles_required(ROLE_SUPER_ADMIN)
def facility_categories():
    """List and paginate amenity categories."""
    return render_admin_list(
        model=FacilityCategory,
        template_name="admin/stations/categories_index.html",
        search_columns=[FacilityCategory.name, FacilityCategory.description],
    )


@admin_bp.route("/facility-categories/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def facility_category_create():
    """Create a new amenity category."""
    form = FacilityCategoryForm()
    if form.validate_on_submit():
        cat = FacilityCategory(
            name=form.name.data.strip(),
            icon_class=form.icon_class.data.strip() if form.icon_class.data else None,
            description=form.description.data.strip() if form.description.data else None,
        )
        db.session.add(cat)
        db.session.flush()

        log_audit_event(
            action="CREATE_FACILITY_CATEGORY",
            entity_name="FacilityCategory",
            entity_id=cat.id,
            user_id=current_user.id,
            new_values={"name": cat.name, "icon": cat.icon_class},
        )
        db.session.commit()

        flash(f"Amenity category '{cat.name}' created successfully.", "success")
        return redirect(url_for("admin.facility_categories"))

    return render_template("admin/stations/categories_form.html", form=form, title="Create Amenity Category")


@admin_bp.route("/facility-categories/<int:cat_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN)
def facility_category_edit(cat_id: int):
    """Edit amenity category."""
    cat = db.session.get(FacilityCategory, cat_id)
    if not cat:
        abort(404)

    form = FacilityCategoryForm(original_id=cat.id)
    if request.method == "GET":
        form.name.data = cat.name
        form.icon_class.data = cat.icon_class
        form.description.data = cat.description

    if form.validate_on_submit():
        old_values = {"name": cat.name, "icon": cat.icon_class, "description": cat.description}
        cat.name = form.name.data.strip()
        cat.icon_class = form.icon_class.data.strip() if form.icon_class.data else None
        cat.description = form.description.data.strip() if form.description.data else None

        log_audit_event(
            action="EDIT_FACILITY_CATEGORY",
            entity_name="FacilityCategory",
            entity_id=cat.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values={"name": cat.name, "icon": cat.icon_class, "description": cat.description},
        )
        db.session.commit()

        flash(f"Amenity category '{cat.name}' updated successfully.", "success")
        return redirect(url_for("admin.facility_categories"))

    return render_template(
        "admin/stations/categories_form.html",
        form=form,
        title=f"Edit Category: {cat.name}",
        target_obj=cat,
    )


@admin_bp.route("/facility-categories/<int:cat_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def facility_category_delete(cat_id: int):
    """Soft delete facility category with active facilities block."""
    cat = db.session.get(FacilityCategory, cat_id)
    if not cat:
        abort(404)

    def block_check():
        active_facilities_cnt = db.session.scalar(
            select(func.count(StationFacility.id)).filter_by(category_id=cat.id, is_deleted=False)
        )
        if active_facilities_cnt > 0:
            return f"Cannot soft-delete facility category '{cat.name}' because {active_facilities_cnt} active facility/facilities are assigned to it."
        return None

    return handle_admin_soft_delete(
        instance=cat,
        redirect_url=url_for("admin.facility_categories"),
        entity_name="FacilityCategory",
        identifier_str=cat.name,
        block_check=block_check,
    )


@admin_bp.route("/facility-categories/<int:cat_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN)
def facility_category_restore(cat_id: int):
    """Restore soft-deleted facility category."""
    cat = db.session.get(FacilityCategory, cat_id)
    if not cat:
        abort(404)
    return handle_admin_restore(
        instance=cat,
        redirect_url=url_for("admin.facility_categories"),
        entity_name="FacilityCategory",
        identifier_str=cat.name,
    )


# ---------------------------------------------------------------------------
# 4. StationPlatform (Super Admin & Station Master)
# ---------------------------------------------------------------------------
@admin_bp.route("/platforms")
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def platforms():
    """List and paginate station platforms, scoped to assigned station for Station Masters."""
    assigned_station_id = get_station_master_assigned_station_id()
    filter_station_id = assigned_station_id or request.args.get("station_id", type=int)
    base_filter = None
    if filter_station_id:
        base_filter = (StationPlatform.station_id == filter_station_id)

    stations = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()

    return render_admin_list(
        model=StationPlatform,
        template_name="admin/stations/platforms_index.html",
        search_columns=[StationPlatform.platform_number],
        base_filter=base_filter,
        context_extra={
            "is_station_master": bool(assigned_station_id),
            "stations": stations,
            "selected_station_id": filter_station_id,
        },
    )


@admin_bp.route("/platforms/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def platform_create():
    """Create a new station platform."""
    assigned_station_id = get_station_master_assigned_station_id()
    form = StationPlatformForm(fixed_station_id=assigned_station_id)

    if assigned_station_id:
        # Station Master: Station locked to their assigned station
        stn = db.session.get(Station, assigned_station_id)
        form.station_id.choices = [(stn.id, f"{stn.name} ({stn.code})")]
        form.station_id.data = stn.id
    else:
        stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
        form.station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if form.validate_on_submit():
        stn_id = assigned_station_id or form.station_id.data
        plat = StationPlatform(
            station_id=stn_id,
            platform_number=form.platform_number.data.strip(),
            length_meters=form.length_meters.data,
            has_disabled_access=form.has_disabled_access.data,
            is_operational=form.is_operational.data,
        )
        db.session.add(plat)
        db.session.flush()

        log_audit_event(
            action="CREATE_STATION_PLATFORM",
            entity_name="StationPlatform",
            entity_id=plat.id,
            user_id=current_user.id,
            new_values={
                "station_id": plat.station_id,
                "platform_number": plat.platform_number,
                "length_meters": plat.length_meters,
            },
        )
        db.session.commit()

        flash(f"Platform #{plat.platform_number} created successfully.", "success")
        return redirect(url_for("admin.platforms"))

    return render_template(
        "admin/stations/platforms_form.html",
        form=form,
        title="Add Station Platform",
        is_station_master=bool(assigned_station_id),
    )


@admin_bp.route("/platforms/<int:plat_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def platform_edit(plat_id: int):
    """Edit platform with Station Master scope guard."""
    plat = db.session.get(StationPlatform, plat_id)
    if not plat:
        abort(404)

    assigned_station_id = get_station_master_assigned_station_id()
    if assigned_station_id and plat.station_id != assigned_station_id:
        abort(403)

    form = StationPlatformForm(original_id=plat.id, fixed_station_id=assigned_station_id)
    if assigned_station_id:
        stn = db.session.get(Station, assigned_station_id)
        form.station_id.choices = [(stn.id, f"{stn.name} ({stn.code})")]
    else:
        stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
        form.station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if request.method == "GET":
        form.station_id.data = plat.station_id
        form.platform_number.data = plat.platform_number
        form.length_meters.data = plat.length_meters
        form.has_disabled_access.data = plat.has_disabled_access
        form.is_operational.data = plat.is_operational

    if form.validate_on_submit():
        old_values = {
            "platform_number": plat.platform_number,
            "length_meters": plat.length_meters,
            "has_disabled_access": plat.has_disabled_access,
            "is_operational": plat.is_operational,
        }
        if not assigned_station_id:
            plat.station_id = form.station_id.data

        plat.platform_number = form.platform_number.data.strip()
        plat.length_meters = form.length_meters.data
        plat.has_disabled_access = form.has_disabled_access.data
        plat.is_operational = form.is_operational.data

        log_audit_event(
            action="EDIT_STATION_PLATFORM",
            entity_name="StationPlatform",
            entity_id=plat.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values={
                "platform_number": plat.platform_number,
                "length_meters": plat.length_meters,
                "has_disabled_access": plat.has_disabled_access,
                "is_operational": plat.is_operational,
            },
        )
        db.session.commit()

        flash(f"Platform #{plat.platform_number} updated successfully.", "success")
        return redirect(url_for("admin.platforms"))

    return render_template(
        "admin/stations/platforms_form.html",
        form=form,
        title=f"Edit Platform #{plat.platform_number}",
        target_obj=plat,
        is_station_master=bool(assigned_station_id),
    )


@admin_bp.route("/platforms/<int:plat_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def platform_delete(plat_id: int):
    """Soft delete platform with Station Master scope guard."""
    plat = db.session.get(StationPlatform, plat_id)
    if not plat:
        abort(404)

    assigned_station_id = get_station_master_assigned_station_id()
    if assigned_station_id and plat.station_id != assigned_station_id:
        abort(403)

    return handle_admin_soft_delete(
        instance=plat,
        redirect_url=url_for("admin.platforms"),
        entity_name="StationPlatform",
        identifier_str=f"Platform #{plat.platform_number}",
    )


@admin_bp.route("/platforms/<int:plat_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def platform_restore(plat_id: int):
    """Restore soft-deleted platform with Station Master scope guard."""
    plat = db.session.get(StationPlatform, plat_id)
    if not plat:
        abort(404)

    assigned_station_id = get_station_master_assigned_station_id()
    if assigned_station_id and plat.station_id != assigned_station_id:
        abort(403)

    return handle_admin_restore(
        instance=plat,
        redirect_url=url_for("admin.platforms"),
        entity_name="StationPlatform",
        identifier_str=f"Platform #{plat.platform_number}",
    )


# ---------------------------------------------------------------------------
# 5. StationFacility (Super Admin & Station Master)
# ---------------------------------------------------------------------------
@admin_bp.route("/facilities")
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def facilities():
    """List and paginate station amenities, scoped to assigned station for Station Masters."""
    assigned_station_id = get_station_master_assigned_station_id()
    filter_station_id = assigned_station_id or request.args.get("station_id", type=int)
    base_filter = None
    if filter_station_id:
        base_filter = (StationFacility.station_id == filter_station_id)

    stations = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()

    return render_admin_list(
        model=StationFacility,
        template_name="admin/stations/facilities_index.html",
        search_columns=[StationFacility.name, StationFacility.location_details],
        base_filter=base_filter,
        context_extra={
            "is_station_master": bool(assigned_station_id),
            "stations": stations,
            "selected_station_id": filter_station_id,
        },
    )


@admin_bp.route("/facilities/create", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def facility_create():
    """Create a new station amenity / facility."""
    assigned_station_id = get_station_master_assigned_station_id()
    form = StationFacilityForm(fixed_station_id=assigned_station_id)

    cats = db.session.scalars(select(FacilityCategory).filter_by(is_deleted=False).order_by(FacilityCategory.name)).all()
    form.category_id.choices = [(c.id, c.name) for c in cats]

    if assigned_station_id:
        stn = db.session.get(Station, assigned_station_id)
        form.station_id.choices = [(stn.id, f"{stn.name} ({stn.code})")]
        form.station_id.data = stn.id
    else:
        stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
        form.station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if form.validate_on_submit():
        stn_id = assigned_station_id or form.station_id.data
        fac = StationFacility(
            station_id=stn_id,
            category_id=form.category_id.data,
            name=form.name.data.strip(),
            location_details=form.location_details.data.strip() if form.location_details.data else None,
            is_free=form.is_free.data,
            fee_amount=form.fee_amount.data or 0.0,
            opening_hours=form.opening_hours.data.strip() if form.opening_hours.data else None,
        )
        db.session.add(fac)
        db.session.flush()

        log_audit_event(
            action="CREATE_STATION_FACILITY",
            entity_name="StationFacility",
            entity_id=fac.id,
            user_id=current_user.id,
            new_values={
                "station_id": fac.station_id,
                "category_id": fac.category_id,
                "name": fac.name,
                "fee_amount": str(fac.fee_amount),
            },
        )
        db.session.commit()

        flash(f"Facility '{fac.name}' added successfully.", "success")
        return redirect(url_for("admin.facilities"))

    return render_template(
        "admin/stations/facilities_form.html",
        form=form,
        title="Add Station Amenity",
        is_station_master=bool(assigned_station_id),
    )


@admin_bp.route("/facilities/<int:fac_id>/edit", methods=["GET", "POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def facility_edit(fac_id: int):
    """Edit station amenity with Station Master scope guard."""
    fac = db.session.get(StationFacility, fac_id)
    if not fac:
        abort(404)

    assigned_station_id = get_station_master_assigned_station_id()
    if assigned_station_id and fac.station_id != assigned_station_id:
        abort(403)

    form = StationFacilityForm(original_id=fac.id, fixed_station_id=assigned_station_id)
    cats = db.session.scalars(select(FacilityCategory).filter_by(is_deleted=False).order_by(FacilityCategory.name)).all()
    form.category_id.choices = [(c.id, c.name) for c in cats]

    if assigned_station_id:
        stn = db.session.get(Station, assigned_station_id)
        form.station_id.choices = [(stn.id, f"{stn.name} ({stn.code})")]
    else:
        stns = db.session.scalars(select(Station).filter_by(is_deleted=False).order_by(Station.name)).all()
        form.station_id.choices = [(s.id, f"{s.name} ({s.code})") for s in stns]

    if request.method == "GET":
        form.station_id.data = fac.station_id
        form.category_id.data = fac.category_id
        form.name.data = fac.name
        form.location_details.data = fac.location_details
        form.is_free.data = fac.is_free
        form.fee_amount.data = fac.fee_amount
        form.opening_hours.data = fac.opening_hours

    if form.validate_on_submit():
        old_values = {
            "name": fac.name,
            "category_id": fac.category_id,
            "is_free": fac.is_free,
            "fee_amount": str(fac.fee_amount),
        }
        if not assigned_station_id:
            fac.station_id = form.station_id.data

        fac.category_id = form.category_id.data
        fac.name = form.name.data.strip()
        fac.location_details = form.location_details.data.strip() if form.location_details.data else None
        fac.is_free = form.is_free.data
        fac.fee_amount = form.fee_amount.data or 0.0
        fac.opening_hours = form.opening_hours.data.strip() if form.opening_hours.data else None

        log_audit_event(
            action="EDIT_STATION_FACILITY",
            entity_name="StationFacility",
            entity_id=fac.id,
            user_id=current_user.id,
            old_values=old_values,
            new_values={
                "name": fac.name,
                "category_id": fac.category_id,
                "is_free": fac.is_free,
                "fee_amount": str(fac.fee_amount),
            },
        )
        db.session.commit()

        flash(f"Facility '{fac.name}' updated successfully.", "success")
        return redirect(url_for("admin.facilities"))

    return render_template(
        "admin/stations/facilities_form.html",
        form=form,
        title=f"Edit Facility: {fac.name}",
        target_obj=fac,
        is_station_master=bool(assigned_station_id),
    )


@admin_bp.route("/facilities/<int:fac_id>/delete", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def facility_delete(fac_id: int):
    """Soft delete station amenity with Station Master scope guard."""
    fac = db.session.get(StationFacility, fac_id)
    if not fac:
        abort(404)

    assigned_station_id = get_station_master_assigned_station_id()
    if assigned_station_id and fac.station_id != assigned_station_id:
        abort(403)

    return handle_admin_soft_delete(
        instance=fac,
        redirect_url=url_for("admin.facilities"),
        entity_name="StationFacility",
        identifier_str=fac.name,
    )


@admin_bp.route("/facilities/<int:fac_id>/restore", methods=["POST"])
@roles_required(ROLE_SUPER_ADMIN, ROLE_STATION_MASTER)
def facility_restore(fac_id: int):
    """Restore soft-deleted station amenity with Station Master scope guard."""
    fac = db.session.get(StationFacility, fac_id)
    if not fac:
        abort(404)

    assigned_station_id = get_station_master_assigned_station_id()
    if assigned_station_id and fac.station_id != assigned_station_id:
        abort(403)

    return handle_admin_restore(
        instance=fac,
        redirect_url=url_for("admin.facilities"),
        entity_name="StationFacility",
        identifier_str=fac.name,
    )
