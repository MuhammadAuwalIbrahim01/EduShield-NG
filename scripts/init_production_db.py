"""
scripts/init_production_db.py — Production Database Setup
=============================================================
Run this ONCE after your first successful Render deploy, via
Render's Shell tab (Dashboard > your service > Shell), to:

  1. Verify the PostgreSQL connection actually works
  2. Create all tables (db.create_all() — safe to re-run, no-ops
     on tables that already exist)
  3. Create the initial admin account from ADMIN_EMAIL/ADMIN_PASSWORD
     environment variables (same logic as backend/app.py's _seed_admin,
     exposed here as a standalone script for manual/CI use)

This does NOT seed sample students/exams (scripts/seed_db.py does that,
and you should NOT run sample data against a real production database —
seed_db.py is a development-only convenience).

Usage (from Render's Shell tab, or locally with DATABASE_URL pointed
at production — be careful doing the latter):

    python scripts/init_production_db.py

Exit codes:
    0 = success
    1 = database connection failed
    2 = table creation failed
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.models.models import db, User


def verify_connection(app):
    """
    Confirm we can actually talk to the database before attempting
    anything else. A clear, early failure here is much easier to
    debug than a confusing error three steps later.
    """
    print("Step 1/3: Verifying database connection...")
    try:
        with app.app_context():
            # A trivial query that will fail loudly if the connection
            # string is wrong, the database is unreachable, or
            # credentials are invalid
            db.session.execute(db.text("SELECT 1"))
            print(f"  ✓ Connected successfully.")
            print(f"  ✓ Database URI scheme: "
                  f"{app.config['SQLALCHEMY_DATABASE_URI'].split('://')[0]}://...")
            return True
    except Exception as e:
        print(f"  ✗ Connection FAILED: {e}")
        print()
        print("  Common causes:")
        print("    - DATABASE_URL environment variable not set")
        print("    - Database still provisioning (wait 1-2 minutes after creation)")
        print("    - Region mismatch between web service and database")
        return False


def create_tables(app):
    """Create all tables defined in backend/models/models.py."""
    print("\nStep 2/3: Creating database tables...")
    try:
        with app.app_context():
            db.create_all()
            # List what actually exists now, as confirmation
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"  ✓ Tables present: {', '.join(sorted(tables))}")
            return True
    except Exception as e:
        print(f"  ✗ Table creation FAILED: {e}")
        return False


def create_admin_if_missing(app):
    """
    Create the initial admin account from environment variables,
    if one doesn't already exist. Safe to re-run — does nothing
    if an admin with that email is already present.
    """
    print("\nStep 3/3: Checking for admin account...")
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@edushield.ng")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        print("  ⚠ ADMIN_PASSWORD not set in environment — skipping admin creation.")
        print("    Set it in Render's dashboard (Environment tab) and re-run this script,")
        print("    or create the admin manually via the Render Shell with a Python snippet.")
        return True  # Not a failure — just nothing to do

    with app.app_context():
        existing = User.query.filter_by(email=admin_email).first()
        if existing:
            print(f"  ✓ Admin already exists: {admin_email} — no action taken.")
            return True

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
        print(f"  ✓ Admin account created: {admin_email}")
        print("  ⚠ IMPORTANT: log in and change this password immediately via the UI.")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("EduShield NG — Production Database Initialization")
    print("=" * 60)

    app = create_app("production")

    if not verify_connection(app):
        sys.exit(1)

    if not create_tables(app):
        sys.exit(2)

    create_admin_if_missing(app)

    print("\n" + "=" * 60)
    print("Production database is ready.")
    print("=" * 60)
    sys.exit(0)
