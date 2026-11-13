from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from app.admin import routes, station_routes, trains_routes, routes_routes, schedules_routes

