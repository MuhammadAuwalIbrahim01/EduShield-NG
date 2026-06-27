"""
config.py — EduShield NG Application Configuration
====================================================
This file defines three configuration classes:
  - BaseConfig: shared settings for all environments
  - DevelopmentConfig: local development (SQLite, debug on)
  - ProductionConfig: Render/cloud (PostgreSQL, strict security)

We use Python classes (not a flat dict) so settings can inherit
and override cleanly. Flask reads the class chosen by FLASK_ENV.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load the .env file into environment variables
# This must happen before we read os.environ below
load_dotenv()


class BaseConfig:
    """
    Settings shared across ALL environments.
    Child classes inherit these and may override individual keys.
    """

    # --- Core Flask ---
    # SECRET_KEY encrypts session cookies and CSRF tokens.
    # If an attacker learns this key, they can forge any session.
    # We read it from .env so it never appears in source code.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-in-prod")

    # --- Database ---
    # SQLAlchemy connection string. Defaults to SQLite for local work.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///edushield.db"
    )
    # Disable modification tracking (saves memory; we don't need it)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Echo SQL queries to console in dev (set False in prod)
    SQLALCHEMY_ECHO = False

    # --- Session Security ---
    # Sessions expire after 2 hours of inactivity
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    # HttpOnly: JS cannot read the session cookie (blocks XSS theft)
    SESSION_COOKIE_HTTPONLY = True
    # SameSite=Lax: cookie not sent on cross-site requests (CSRF defense)
    SESSION_COOKIE_SAMESITE = "Lax"
    # Name our cookie something non-obvious (minor security-through-obscurity)
    SESSION_COOKIE_NAME = "edu_session"

    # --- CSRF Protection ---
    # Flask-WTF generates a hidden token in every form.
    # An attacker on a different site cannot read our token, so their
    # forged form submission will fail the check.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # Token valid for 1 hour

    # --- Rate Limiting ---
    # Prevents brute-force login attacks. Uses in-memory storage by default;
    # switch to Redis in production for persistence across workers.
    RATELIMIT_DEFAULT = "200 per day;50 per hour;10 per minute"
    RATELIMIT_STORAGE_URI = "memory://"

    # --- File Uploads ---
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB max upload size

    # --- Application-specific ---
    # Maximum number of tab-switch warnings before auto-submit
    MAX_TAB_SWITCHES = 3
    # Maximum face-absent seconds before flagging
    MAX_FACE_ABSENT_SECONDS = 30
    # Supported languages
    SUPPORTED_LANGUAGES = ["en", "ha", "yo", "ig"]


class DevelopmentConfig(BaseConfig):
    """
    Local development settings.
    Debug mode ON so Flask shows full error pages.
    SQLite so you need no external DB server.
    """
    DEBUG = True
    TESTING = False
    # SQLite file lives at the project root
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///edushield_dev.db"
    )
    # Echo SQL so we can learn what queries are being generated
    SQLALCHEMY_ECHO = True
    # Cookies don't need HTTPS in dev (localhost is HTTP)
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    """
    Production settings for Render deployment.
    Debug MUST be False — otherwise error pages leak source code.
    PostgreSQL for real persistence and concurrency.
    HTTPS cookies required.
    """
    DEBUG = False
    TESTING = False

    # Render sets DATABASE_URL automatically when you attach PostgreSQL.
    #
    # CRITICAL FIX: some PostgreSQL providers (including older Render
    # connection strings, and Heroku historically) hand out URLs starting
    # with "postgres://" rather than "postgresql://". SQLAlchemy 1.4+
    # (we use 2.0.31) REJECTS the "postgres://" scheme outright — calling
    # create_engine() on it raises immediately, which means the app would
    # crash on every single startup in production with no clear error
    # surfaced to the dashboard beyond "deploy failed". We defensively
    # rewrite the scheme here so this never bites us, regardless of which
    # exact format the database provider hands back.
    _raw_database_url = os.environ.get("DATABASE_URL", "")
    if _raw_database_url.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = _raw_database_url.replace(
            "postgres://", "postgresql://", 1
        )
    else:
        SQLALCHEMY_DATABASE_URI = _raw_database_url

    SQLALCHEMY_ECHO = False
    # Secure=True means cookie is ONLY sent over HTTPS
    SESSION_COOKIE_SECURE = True
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

class TestingConfig(BaseConfig):
    """
    Used by our automated tests (pytest).
    Separate in-memory SQLite DB — wiped after every test run.
    CSRF disabled so test client can POST without tokens.
    """
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # Tests don't submit real HTML forms


# Map string names to classes so we can do:
#   app.config.from_object(config_map["development"])
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
