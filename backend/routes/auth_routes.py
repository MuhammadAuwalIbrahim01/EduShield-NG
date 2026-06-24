"""
backend/routes/auth_routes.py — Authentication Routes
=======================================================
All routes a user needs to manage their identity:

  GET  /auth/login           -> show login page
  POST /auth/login           -> process login
  GET  /auth/register        -> show registration page
  POST /auth/register        -> process registration
  GET  /auth/logout          -> log user out + clear session
  GET  /auth/profile         -> show profile page (login required)
  POST /auth/profile         -> update profile (login required)
  POST /auth/change-password -> change password (login required)
  GET  /auth/check-email     -> AJAX: check if email already exists
"""

import logging
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, jsonify, session
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)

from backend.models.models import db, User
from backend.utils.forms import (
    RegistrationForm, LoginForm, ChangePasswordForm, ProfileUpdateForm
)
from backend.utils.security import (
    sanitize_input, get_safe_next_url, check_password_strength
)

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """GET: Render login form. POST: Validate credentials, create session."""
    if current_user.is_authenticated:
        return _redirect_authenticated_user()

    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        password = form.password.data
        user = User.query.filter_by(email=email).first()

        login_failed_msg = "Invalid email or password. Please try again."

        if not user:
            from werkzeug.security import check_password_hash
            check_password_hash("dummy_hash_prevents_timing_attack", password)
            flash(login_failed_msg, "danger")
            logger.warning(f"Login attempt with unknown email: {email}")
            return render_template("auth/login.html", form=form, title="Login")

        if not user.check_password(password):
            flash(login_failed_msg, "danger")
            logger.warning(f"Failed login for user: {user.id} ({email})")
            return render_template("auth/login.html", form=form, title="Login")

        if not user.is_active:
            flash("Your account has been suspended. Contact admin.", "danger")
            return render_template("auth/login.html", form=form, title="Login")

        if not user.is_verified:
            flash("Your account is pending verification. Contact your institution.", "warning")
            return render_template("auth/login.html", form=form, title="Login")

        login_user(user, remember=form.remember_me.data)
        user.last_login = datetime.utcnow()
        db.session.commit()

        logger.info(f"User logged in: {user.id} ({user.email}) role={user.role}")
        first_name = user.full_name.split()[0]
        flash(f"Welcome back, {first_name}!", "success")

        next_url = get_safe_next_url(
            "admin.dashboard" if user.is_admin() else "exam.student_dashboard"
        )
        return redirect(next_url)

    return render_template("auth/login.html", form=form, title="Sign In")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """GET: Render registration form. POST: Create student account."""
    if current_user.is_authenticated:
        return _redirect_authenticated_user()

    form = RegistrationForm()

    if form.validate_on_submit():
        full_name   = sanitize_input(form.full_name.data.strip())
        email       = form.email.data.lower().strip()
        student_id  = form.student_id.data.upper().strip()
        institution = sanitize_input(form.institution.data.strip())
        department  = sanitize_input(form.department.data.strip()) if form.department.data else None
        phone       = form.phone.data.strip() if form.phone.data else None

        new_user = User(
            full_name=full_name,
            email=email,
            student_id=student_id,
            institution=institution,
            department=department,
            phone=phone,
            role="student",
            preferred_language=form.preferred_language.data,
            is_verified=True,
            is_active=True,
        )
        new_user.set_password(form.password.data)

        try:
            db.session.add(new_user)
            db.session.commit()
            logger.info(f"New student registered: {new_user.id} ({new_user.email})")
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {e}")
            flash("An error occurred. Please try again.", "danger")

    return render_template("auth/register.html", form=form, title="Create Account")


@auth_bp.route("/logout")
@login_required
def logout():
    """Log out and clear the session."""
    user_id = current_user.id
    user_email = current_user.email
    logout_user()
    session.clear()
    logger.info(f"User logged out: {user_id} ({user_email})")
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """GET: Show profile. POST: Save changes."""
    form = ProfileUpdateForm(obj=current_user)

    if form.validate_on_submit():
        current_user.full_name   = sanitize_input(form.full_name.data.strip())
        current_user.institution = sanitize_input(form.institution.data.strip()) if form.institution.data else None
        current_user.department  = sanitize_input(form.department.data.strip()) if form.department.data else None
        current_user.phone       = form.phone.data.strip() if form.phone.data else None
        current_user.preferred_language = form.preferred_language.data
        current_user.updated_at  = datetime.utcnow()

        try:
            db.session.commit()
            flash("Profile updated successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash("Failed to update profile. Please try again.", "danger")

        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", form=form, title="My Profile", user=current_user)


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Change the current user's password and force re-login."""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("auth.profile"))

        current_user.set_password(form.new_password.data)
        current_user.updated_at = datetime.utcnow()

        try:
            db.session.commit()
            logout_user()
            session.clear()
            flash("Password changed. Please sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            flash("Failed to change password. Please try again.", "danger")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, "danger")

    return redirect(url_for("auth.profile"))


@auth_bp.route("/check-email")
def check_email():
    """AJAX: Check if email is already registered."""
    email = request.args.get("email", "").lower().strip()
    if not email or len(email) > 150:
        return jsonify({"available": False, "error": "Invalid email"})
    exists = User.query.filter_by(email=email).first() is not None
    return jsonify({"available": not exists})


@auth_bp.route("/password-strength")
def password_strength():
    """AJAX: Return real-time password strength analysis."""
    password = request.args.get("password", "")
    if not password or len(password) > 128:
        return jsonify({"score": 0, "label": "Very Weak", "feedback": []})
    return jsonify(check_password_strength(password))


def _redirect_authenticated_user():
    if current_user.is_admin():
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("exam.student_dashboard"))
