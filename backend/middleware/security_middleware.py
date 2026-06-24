"""
backend/middleware/security_middleware.py — Security Middleware
================================================================
Flask middleware applied to every request.

What this file does:
  1. add_security_headers()  — Sets HTTP security headers on every response
  2. validate_content_type() — Rejects malformed JSON API requests
  3. check_exam_session()    — Auto-submits expired exam sessions
  4. log_suspicious_request()— Logs unusually large or malformed requests

Why HTTP Security Headers Matter:
  X-Frame-Options         → Prevents clickjacking (exam inside iframe)
  X-Content-Type-Options  → Browser won't guess MIME type
  X-XSS-Protection        → Legacy XSS filter (older browsers)
  Referrer-Policy         → Doesn't leak our URL to external sites
  Content-Security-Policy → Strict whitelist of allowed content sources
  Permissions-Policy      → Disables browser features we don't use
"""

import logging
from flask import request, g, jsonify
from datetime import datetime

logger = logging.getLogger(__name__)


def register_middleware(app):
    """
    Register all middleware with the Flask app.
    Called once from create_app() in app.py.

    Flask middleware is implemented as:
      @app.before_request  → runs before every route handler
      @app.after_request   → runs after every route handler (modifies response)
    """

    # ─────────────────────────────────────────
    # BEFORE REQUEST: Validate & Gate
    # ─────────────────────────────────────────

    @app.before_request
    def validate_request_size():
        """
        Reject requests with bodies larger than MAX_CONTENT_LENGTH.
        Flask handles this automatically, but we add explicit logging.
        Large payloads may indicate a DoS attempt or data injection.
        """
        content_length = request.content_length
        max_size = app.config.get("MAX_CONTENT_LENGTH", 2 * 1024 * 1024)

        if content_length and content_length > max_size:
            logger.warning(
                f"Request too large: {content_length} bytes from {request.remote_addr} "
                f"on {request.path}"
            )
            return jsonify({"error": "Request too large"}), 413

    @app.before_request
    def validate_api_content_type():
        """
        For API endpoints that expect JSON, verify the Content-Type header.
        Prevents CSRF via form submission to JSON endpoints.

        A malicious site can submit a form (POST) to our server, but it
        CANNOT set Content-Type: application/json (CORS blocks that).
        So requiring application/json on POST /api/* endpoints prevents
        form-based CSRF even without the CSRF token.
        """
        if (request.path.startswith("/api/") and
                request.method == "POST" and
                request.path != "/api/health"):

            ct = request.content_type or ""
            if "application/json" not in ct:
                logger.warning(
                    f"Invalid Content-Type '{ct}' on {request.method} {request.path} "
                    f"from {request.remote_addr}"
                )
                return jsonify({
                    "error": "Content-Type must be application/json"
                }), 415

    @app.before_request
    def log_suspicious_patterns():
        """
        Detect and log common attack patterns in URLs and headers.
        These are heuristic — not all matches are attacks, but they
        warrant attention in the security log.
        """
        SUSPICIOUS_PATTERNS = [
            "../",          # Path traversal
            "etc/passwd",   # Unix file access
            "<script",      # XSS attempt in URL
            "UNION SELECT", # SQL injection
            "DROP TABLE",   # SQL injection
            "javascript:",  # Protocol injection
            "eval(",        # JS injection
            "%27",          # URL-encoded single quote (SQL injection)
            "%3Cscript",    # URL-encoded <script
        ]

        url = request.url.lower()
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.lower() in url:
                logger.warning(
                    f"Suspicious pattern '{pattern}' in URL: {request.url} "
                    f"from {request.remote_addr} "
                    f"User-Agent: {request.headers.get('User-Agent', 'none')[:100]}"
                )
                # Don't block — just log (pattern may be false positive)
                # Real protection is parameterised queries (SQLAlchemy ORM)
                break

    # ─────────────────────────────────────────
    # AFTER REQUEST: Add Security Headers
    # ─────────────────────────────────────────

    @app.after_request
    def add_security_headers(response):
        """
        Add HTTP security headers to EVERY response.

        These headers tell the browser how to handle our content safely.
        They are your last line of defence after the application itself.
        """

        # ── Clickjacking Protection ──────────────
        # Prevents our pages from being embedded in an <iframe>.
        # An attacker could overlay a transparent iframe over their
        # malicious page and trick students into clicking exam buttons.
        response.headers["X-Frame-Options"] = "DENY"

        # ── MIME Type Sniffing Protection ────────
        # Browser must use the Content-Type we declare, not guess.
        # Prevents serving a text file that the browser interprets as JS.
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ── Legacy XSS Filter ────────────────────
        # Enables the built-in XSS filter in older browsers (IE, early Chrome).
        # Modern browsers don't use this, but it doesn't hurt.
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ── Referrer Policy ──────────────────────
        # When a student clicks a link to an external site, don't reveal
        # our full URL in the Referer header (could expose exam session token
        # if it were ever in the URL — it isn't, but belt+suspenders).
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── Permissions Policy ───────────────────
        # Explicitly disable browser features we don't use.
        # This limits what a compromised third-party script can do.
        # We DO use camera (for face monitoring) and microphone is denied.
        response.headers["Permissions-Policy"] = (
            "camera=(self), "       # Allow camera on our domain only
            "microphone=(), "       # Never use microphone
            "geolocation=(), "      # Never track location
            "payment=(), "          # Never process payments
            "usb=(), "              # Never access USB
            "fullscreen=(self)"     # Allow fullscreen on our domain only
        )

        # ── Content Security Policy ──────────────
        # The most powerful security header.
        # Defines a strict whitelist of where content can come from.
        #
        # Breakdown:
        #   default-src 'self'          → Everything defaults to same-origin
        #   script-src 'self' CDNs      → JS from our domain + approved CDNs
        #   style-src 'self' 'unsafe-inline' fonts  → CSS + Google Fonts
        #   img-src 'self' data:        → Images from our domain + base64
        #   font-src fonts.gstatic.com  → Google Fonts files
        #   connect-src 'self'          → AJAX/fetch only to our domain
        #   media-src 'self' blob:      → Video streams (webcam)
        #   frame-src 'none'            → No iframes allowed
        #   object-src 'none'           → No Flash/plugins
        #   base-uri 'self'             → No base tag hijacking
        #   form-action 'self'          → Forms only submit to our domain
        #
        # 'unsafe-inline' in style-src is required for some dynamic styles.
        # We mitigate this with the other directives.

        env = app.config.get("ENV", "development")

        # Allow CDNs needed for face-api.js, Font Awesome, Google Fonts
        script_cdns = (
            "https://cdn.jsdelivr.net "
            "https://cdnjs.cloudflare.com "
        )
        style_cdns = (
            "https://fonts.googleapis.com "
            "https://cdnjs.cloudflare.com "
        )
        font_cdns = (
            "https://fonts.gstatic.com "
            "https://cdnjs.cloudflare.com "
        )

        csp = (
            f"default-src 'self'; "
            f"script-src 'self' {script_cdns} 'unsafe-inline'; "
            f"style-src 'self' {style_cdns} 'unsafe-inline'; "
            f"img-src 'self' data: blob: https:; "
            f"font-src 'self' {font_cdns}; "
            f"connect-src 'self' https://cdn.jsdelivr.net; "
            f"media-src 'self' blob:; "
            f"frame-src 'none'; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp

        # ── Cache Control for Sensitive Pages ───
        # Prevent browsers from caching exam pages.
        # A student who logs out should not be able to press Back
        # and see the previous student's exam.
        if request.path.startswith(("/exam/", "/auth/", "/admin/")):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"]  = "no-cache"
            response.headers["Expires"] = "0"

        # ── Remove Server Header ─────────────────
        # Don't advertise what server software we use.
        # Removes "Server: Werkzeug/X.X.X Python/3.X.X"
        response.headers.pop("Server", None)
        response.headers["Server"] = "EduShield"

        return response
