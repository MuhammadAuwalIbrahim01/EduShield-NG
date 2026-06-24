"""
app.py — EduShield NG Flask Application Factory
=================================================
We use the Application Factory pattern:
  create_app() returns a configured Flask app.

Why a factory?
  1. We can call create_app("testing") for tests → isolated test DB
  2. We can call create_app("production") for deployment
  3. Extensions (db, login_manager) are initialized INSIDE the factory
     which avoids circular imports

Startup sequence:
  1. Create Flask app
  2. Load config (from config_map)
  3. Initialize extensions (db, login, csrf, limiter)
  4. Create database tables if they don't exist
  5. Register blueprints (auth, exam, admin, api routes)
  6. Register error handlers
  7. Return the ready-to-serve app
"""

import os
import logging
from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

from .config import config_map
from .models.models import db, User


# --- Extension Instances ---
# Created here without an app; bound to the app inside create_app()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def create_app(config_name: str = None) -> Flask:
    """
    Application factory.

    Args:
        config_name: 'development', 'production', or 'testing'.
                     Defaults to the FLASK_ENV environment variable,
                     falling back to 'development'.

    Returns:
        A fully configured Flask application instance.
    """

    # --- 1. Create the Flask app ---
    # template_folder points to our Jinja2 HTML files
    # static_folder points to CSS, JS, images
    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(__file__), "..", "frontend", "templates"
        ),
        static_folder=os.path.join(
            os.path.dirname(__file__), "..", "frontend", "static"
        ),
    )

    # --- 2. Load Configuration ---
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
    config_class = config_map.get(config_name, config_map["default"])
    app.config.from_object(config_class)

    # --- 3. Configure Logging ---
    if not app.debug:
        # In production, log to stdout so Render can capture it
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    app.logger.info(f"EduShield NG starting in '{config_name}' mode")

    # --- 4. Initialize Extensions ---
    _init_extensions(app)

    # --- 5. Create Database Tables ---
    with app.app_context():
        db.create_all()
        _seed_admin(app)  # Create default admin if none exists

    # --- 6. Register Security Middleware ---
    from .middleware.security_middleware import register_middleware
    register_middleware(app)

    # --- 7. Register Blueprints ---
    _register_blueprints(app)

    # --- 8. Register Error Handlers ---
    _register_error_handlers(app)

    # --- 9. Template Context Processors ---
    _register_context_processors(app)

    return app


def _register_context_processors(app: Flask):
    """
    Context processors inject variables into EVERY Jinja2 template
    automatically — no need to pass them manually in each route.

    After this, every template can use:
      {{ t('login_title') }}           → auto-detected language
      {{ t('question_of', n=3, total=10) }}
      {{ current_lang }}               → 'en', 'ha', 'yo', 'ig'
      {{ tts_locale }}                 → 'en-NG', 'ha', etc.
      {{ translations_json }}          → JSON blob for JavaScript
      {{ supported_languages }}        → dict of all languages
    """
    import json as _json
    from .utils.translations import (
        get_text, get_lang, get_tts_locale,
        get_all_translations_for_js, SUPPORTED_LANGUAGES
    )

    @app.context_processor
    def inject_translations():
        lang = get_lang()
        return {
            "t":                   lambda key, **kw: get_text(key, lang, **kw),
            "current_lang":        lang,
            "tts_locale":          get_tts_locale(lang),
            "translations_json":   _json.dumps(get_all_translations_for_js(lang)),
            "supported_languages": SUPPORTED_LANGUAGES,
        }

    @app.route("/set-language/<lang_code>")
    def set_language(lang_code):
        """
        Language switcher endpoint.
        Sets the user's language preference in the session,
        then redirects back to where they came from.
        """
        from flask import session, redirect, request as req
        if lang_code in SUPPORTED_LANGUAGES:
            session["language"] = lang_code
            # Also save to DB if student is logged in
            from flask_login import current_user
            if current_user.is_authenticated and current_user.is_student():
                current_user.preferred_language = lang_code
                db.session.commit()
        return redirect(req.referrer or "/")


def _init_extensions(app: Flask):
    """
    Bind all Flask extensions to the app.
    Each extension's init_app() method registers it with this specific app.
    """

    # SQLAlchemy — our ORM / database connection
    db.init_app(app)

    # Flask-Login — manages user sessions
    # Tells Flask-Login where to find the user by ID from the session cookie
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"          # redirect to login if not authenticated
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        """
        Called on every request to re-load the logged-in user from the DB.
        Flask-Login stores only the user ID in the cookie; this retrieves
        the full User object.
        Returns None if the user doesn't exist (triggers logout).
        """
        return User.query.get(int(user_id))

    # Flask-WTF CSRF Protection
    # Automatically injects {{ csrf_token() }} requirement into all forms
    csrf.init_app(app)

    # Flask-Limiter — rate limiting to prevent brute-force attacks
    # Key function = client's IP address (each IP gets its own counter)
    limiter.init_app(app)

    # Flask-CORS — allow cross-origin requests from Netlify frontend
    # In production, replace "*" with your Netlify domain
    CORS(app, resources={
        r"/api/*": {
            "origins": os.environ.get("ALLOWED_ORIGINS", "*"),
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "allow_headers": ["Content-Type", "X-CSRFToken"],
        }
    })


def _register_blueprints(app: Flask):
    """
    Blueprints group related routes.
    Think of each blueprint as a mini-Flask app with its own routes.
    """
    from .routes.auth_routes import auth_bp
    from .routes.exam_routes import exam_bp
    from .routes.admin_routes import admin_bp
    from .routes.api_routes import api_bp

    # url_prefix means all auth routes start with /auth/
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(exam_bp, url_prefix="/exam")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")

    # Root route — redirect to student dashboard or login
    @app.route("/")
    def index():
        from flask_login import current_user
        if current_user.is_authenticated:
            if current_user.is_admin():
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("exam.student_dashboard"))
        return redirect(url_for("auth.login"))


def _register_error_handlers(app: Flask):
    """
    Custom error pages instead of Flask's default white-page errors.
    These render templates that match our EduShield design system.
    """

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html", error=e), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html", error=e), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html", error=e), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        # Rate limiter triggered — too many requests from this IP
        return render_template("errors/429.html", error=e), 429

    @app.errorhandler(500)
    def internal_error(e):
        # Roll back any broken DB transaction
        db.session.rollback()
        app.logger.error(f"Internal error: {e}")
        return render_template("errors/500.html", error=e), 500


def _seed_admin(app: Flask):
    """
    Create a default admin account on first run if no admin exists.
    Credentials come from .env (ADMIN_EMAIL, ADMIN_PASSWORD).
    This runs inside app_context so we can touch the database.
    """
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@edushield.ng")
    if User.query.filter_by(email=admin_email).first():
        return  # Admin already exists, skip

    admin_password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
    admin = User(
        full_name="EduShield Admin",
        email=admin_email,
        role="admin",
        is_verified=True,
        is_active=True,
    )
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
    app.logger.warning(
        f"Default admin created: {admin_email} — CHANGE THE PASSWORD IMMEDIATELY"
    )
