from flask import render_template, jsonify, current_app
from sqlalchemy import text
from app.main import main_bp
from app.extensions import db


@main_bp.route("/")
def index():
    """RailSathi PK landing / home page."""
    return render_template("main/index.html")


@main_bp.route("/healthz")
def health_check():
    """
    Application & Database health check endpoint.
    Used by Render and orchestrators to verify service availability.
    """
    db_status = "connected"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception as e:
        current_app.logger.warning(f"Database health check probe degraded: {e}")
        db_status = "degraded"

    return jsonify({
        "status": "healthy",
        "app": "RailSathi PK",
        "version": "1.0.0-phase2",
        "database": db_status
    }), 200

