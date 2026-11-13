import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


def parse_bool(val: str | None, default: bool = False) -> bool:
    """Safely parse string environment variables into booleans."""
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "t", "yes", "y")


def normalize_database_url(url: str | None) -> str:
    """
    Normalizes PostgreSQL connection URL for SQLAlchemy 2.x compatibility.
    Replaces deprecated 'postgres://' with 'postgresql://'.
    Validates that PostgreSQL is strictly used (no SQLite fallback).
    """
    if not url:
        raise ValueError(
            "DATABASE_URL (or TEST_DATABASE_URL for tests) environment variable is required and must point to a PostgreSQL database."
        )
    url_stripped = url.strip()
    if url_stripped.startswith("postgres://"):
        url_stripped = url_stripped.replace("postgres://", "postgresql://", 1)
    if not (url_stripped.startswith("postgresql://") or url_stripped.startswith("postgresql+psycopg2://")):
        raise ValueError(
            f"Invalid database URI '{url}'. RailSathi PK strictly requires a PostgreSQL database (e.g., postgresql://user:pass@host:5432/dbname). SQLite fallback has been completely removed."
        )
    return url_stripped


class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-fallback-key-change-in-prod")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return normalize_database_url(os.environ.get("DATABASE_URL"))

    @property
    def SQLALCHEMY_ENGINE_OPTIONS(self) -> dict:
        options = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }
        db_uri = os.environ.get("DATABASE_URL", "")
        # If connecting to remote PostgreSQL (not localhost), require SSL
        if db_uri and "localhost" not in db_uri and "127.0.0.1" not in db_uri:
            options["connect_args"] = {"sslmode": "require"}
        return options

    # Security & Session Settings
    SESSION_COOKIE_SECURE = parse_bool(os.environ.get("SESSION_COOKIE_SECURE"), default=False)
    SESSION_COOKIE_HTTPONLY = parse_bool(os.environ.get("SESSION_COOKIE_HTTPONLY"), default=True)
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=int(os.environ.get("PERMANENT_SESSION_LIFETIME", 28800)))
    
    # CSRF Protection
    WTF_CSRF_ENABLED = parse_bool(os.environ.get("WTF_CSRF_ENABLED"), default=True)
    WTF_CSRF_TIME_LIMIT = int(os.environ.get("WTF_CSRF_TIME_LIMIT", 3600))


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key-for-testing-purposes-only"
    SESSION_COOKIE_SECURE = False

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        test_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not test_url:
            raise ValueError(
                "TEST_DATABASE_URL (or DATABASE_URL) environment variable is required for testing on PostgreSQL. SQLite fallback has been completely removed."
            )
        return normalize_database_url(test_url)

    @property
    def SQLALCHEMY_ENGINE_OPTIONS(self) -> dict:
        return {
            "pool_pre_ping": True,
        }


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = parse_bool(os.environ.get("SESSION_COOKIE_SECURE"), default=True)

    def __init__(self):
        super().__init__()
        # Ensure production has a valid, non-default, non-placeholder SECRET_KEY
        insecure_keys = {
            "",
            None,
            "insecure-dev-fallback-key-change-in-prod",
            "replace_with_a_secure_random_64_character_hex_string",
        }
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret.strip() in insecure_keys:
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: Production environment requires "
                "a secure, non-placeholder SECRET_KEY set via environment variables."
            )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}

