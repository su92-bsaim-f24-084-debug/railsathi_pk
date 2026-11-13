import pytest
from app import create_app
from app.config import (
    DevelopmentConfig,
    TestingConfig,
    ProductionConfig,
    parse_bool,
    normalize_database_url,
)


def test_boolean_env_parsing():
    """Verify defensive boolean parsing handles truthy, falsy, and none values."""
    assert parse_bool("true") is True
    assert parse_bool("True") is True
    assert parse_bool("1") is True
    assert parse_bool("yes") is True
    assert parse_bool("t") is True
    assert parse_bool("false") is False
    assert parse_bool("False") is False
    assert parse_bool("0") is False
    assert parse_bool("no") is False
    assert parse_bool(None, default=True) is True
    assert parse_bool(None, default=False) is False
    assert parse_bool("unknown_string", default=False) is False


def test_database_url_normalization():
    """Verify legacy postgres:// URLs are converted to postgresql:// for SQLAlchemy 2.x."""
    legacy = "postgres://user:pass@host:5432/dbname"
    normalized = normalize_database_url(legacy)
    assert normalized == "postgresql://user:pass@host:5432/dbname"

    modern = "postgresql://user:pass@host:5432/dbname"
    assert normalize_database_url(modern) == modern

    # Rejection of None, empty, or non-PostgreSQL URLs
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_database_url(None)

    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_database_url("sqlite:///foo.db")


def test_development_config(monkeypatch):
    """Verify DevelopmentConfig settings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://railsathi_dev:railsathi_pass@localhost:5432/railsathi_db")
    app = create_app(DevelopmentConfig)
    assert app.config["DEBUG"] is True
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["WTF_CSRF_ENABLED"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql://")


def test_testing_config(monkeypatch):
    """Verify TestingConfig settings strictly use PostgreSQL."""
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test_user:test_pass@localhost:5432/railsathi_test")
    app = create_app(TestingConfig)
    assert app.config["TESTING"] is True
    assert app.config["DEBUG"] is False
    assert app.config["WTF_CSRF_ENABLED"] is False
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql://test_user:test_pass@localhost:5432/railsathi_test"


def test_production_config_rejects_missing_secret(monkeypatch):
    """Verify ProductionConfig raises ValueError if SECRET_KEY is not set."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="Production environment requires a secure"):
        create_app(ProductionConfig)


def test_production_config_rejects_placeholder_secret(monkeypatch):
    """Verify ProductionConfig raises ValueError if SECRET_KEY is a default placeholder."""
    monkeypatch.setenv("SECRET_KEY", "replace_with_a_secure_random_64_character_hex_string")
    with pytest.raises(ValueError, match="Production environment requires a secure"):
        create_app(ProductionConfig)

    monkeypatch.setenv("SECRET_KEY", "insecure-dev-fallback-key-change-in-prod")
    with pytest.raises(ValueError, match="Production environment requires a secure"):
        create_app(ProductionConfig)


def test_production_config_accepts_valid_secret(monkeypatch):
    """Verify ProductionConfig initializes successfully with a strong production key."""
    monkeypatch.setenv("SECRET_KEY", "7b92f7a0e3c15d86b51829e248b11c9e4726d1a938e5f204c3b7a1d5e6f80921")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    app = create_app(ProductionConfig)
    assert app.config["DEBUG"] is False
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["WTF_CSRF_ENABLED"] is True


def test_csrf_protection_enforcement():
    """Verify CSRF rejects unauthorized POST requests when enabled."""
    class CSRFActiveConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CSRFActiveConfig)

    @app.route("/test-csrf-post", methods=["POST"])
    def dummy_post():
        return "ok", 200

    client = app.test_client()
    # Sending POST without CSRF token should result in 400 Bad Request
    response = client.post("/test-csrf-post")
    assert response.status_code == 400
