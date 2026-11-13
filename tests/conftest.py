import os
import pytest
from sqlalchemy import text
from app import create_app
from app.config import TestingConfig
from app.extensions import db

TRUNCATE_ROOT_TABLES_SQL = """
TRUNCATE TABLE 
    users, 
    roles, 
    station_divisions, 
    facility_categories, 
    train_types, 
    coach_classes, 
    seat_layout_types, 
    berth_types, 
    payment_methods, 
    complaint_categories, 
    lost_found_categories, 
    assistance_types, 
    notification_templates, 
    audit_logs 
RESTART IDENTITY CASCADE;
"""


@pytest.fixture(scope="session")
def session_app():
    """Create session-scoped Flask application and initialize isolated PostgreSQL schema once."""
    test_url = os.environ.get("TEST_DATABASE_URL")
    main_url = os.environ.get("DATABASE_URL")

    if not test_url:
        pytest.fail(
            "CRITICAL: TEST_DATABASE_URL is not set. A real PostgreSQL test database URL is required."
        )

    if main_url and test_url.strip() == main_url.strip():
        pytest.fail(
            "REFUSED: DATABASE_URL and TEST_DATABASE_URL point to the exact same database! "
            "Tests must run on an isolated test database to protect development data."
        )

    test_app = create_app(TestingConfig)

    with test_app.app_context():
        # Schema is created ONCE per test session
        db.drop_all()
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def app(session_app):
    """Provide function-scoped app fixture with rapid single-statement cascade truncation."""
    with session_app.app_context():
        yield session_app
        db.session.remove()
        try:
            with db.engine.connect() as conn:
                conn.execute(text(TRUNCATE_ROOT_TABLES_SQL))
                conn.commit()
        except Exception:
            db.session.rollback()


@pytest.fixture
def client(app):
    """Provide a test client for simulating HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Provide a test CLI runner for testing CLI commands."""
    return app.test_cli_runner()
