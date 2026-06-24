"""
wsgi.py — Production Entry Point
==================================
Render/gunicorn calls this file to start the server.

Command Render runs:
    gunicorn wsgi:app --workers 4 --bind 0.0.0.0:$PORT

'wsgi:app' means: from wsgi.py, use the variable named 'app'.
"""

import os
from backend.app import create_app

app = create_app("production")
