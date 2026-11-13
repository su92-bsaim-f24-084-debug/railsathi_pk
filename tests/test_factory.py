from flask import abort
import pytest
from app import create_app
from app.config import TestingConfig


def test_app_creation(app):
    """Verify application factory initializes with correct settings."""
    assert app is not None
    assert app.config["TESTING"] is True
    assert app.config["WTF_CSRF_ENABLED"] is False


def test_home_page_response(client):
    """Verify home page loads successfully with HTTP 200 and branded header."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"RailSathi" in response.data
    assert b"Pakistan Railways" in response.data
    assert b"Train Search Preview" in response.data


def test_healthz_endpoint(client):
    """Verify /healthz probe returns healthy status with HTTP 200."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["app"] == "RailSathi PK"
    assert "database" in data


def test_404_error_page(client):
    """Verify non-existent route renders custom 404 template with HTTP 404."""
    response = client.get("/non-existent-railway-route-999")
    assert response.status_code == 404
    assert b"404" in response.data
    assert b"Station or Record Not Found" in response.data


def test_403_error_page():
    """Verify HTTP 403 Forbidden renders custom 403 template."""
    test_app = create_app(TestingConfig)

    @test_app.route("/test-forbidden-route")
    def trigger_forbidden():
        abort(403)

    test_client = test_app.test_client()
    response = test_client.get("/test-forbidden-route")
    assert response.status_code == 403
    assert b"403" in response.data
    assert b"Access Restricted" in response.data


def test_auth_routes_load_cleanly(client):
    """Verify auth blueprint routes render registration and login templates."""
    res_login = client.get("/auth/login")
    assert res_login.status_code == 200
    assert b"Sign In to RailSathi" in res_login.data

    res_reg = client.get("/auth/register")
    assert res_reg.status_code == 200
    assert b"Passenger Account Registration" in res_reg.data

