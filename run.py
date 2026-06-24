"""
run.py — EduShield NG Development Server Entry Point
=====================================================
This file is only used for LOCAL DEVELOPMENT.
In production (Render), gunicorn uses wsgi.py instead.

Usage:
    python run.py

What it does:
    1. Calls create_app() to build the Flask application
    2. Starts Flask's built-in development server
    3. Enables auto-reload on code changes (debug=True in dev config)
"""

import os
from backend.app import create_app

# Create the app using the environment variable (default: development)
app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    # host="0.0.0.0" makes the server accessible on your local network
    # (useful for testing on your phone while developing)
    # port=5000 is Flask's default
    # debug comes from the config class (True in dev, False in prod)
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
    )
