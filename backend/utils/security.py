"""
backend/utils/security.py — Security Helper Functions
======================================================
Centralises security-sensitive operations so they are:
  - Easy to audit (all in one place)
  - Easy to test (pure functions, no Flask context needed)
  - Easy to update (change in one place, applies everywhere)

Functions:
  sanitize_input()       — Strip dangerous HTML/JS from text
  is_safe_redirect_url() — Prevent open redirect attacks
  generate_token()       — Cryptographically secure random tokens
  log_security_event()   — Write security events to cheat_logs
  require_role()         — Decorator for role-based route protection
  validate_exam_session()— Verify exam session token is valid
"""

import re
import secrets
import logging
from functools import wraps
from datetime import datetime
from flask import abort, request, redirect, url_for, session
from flask_login import current_user

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INPUT SANITIZATION
# ─────────────────────────────────────────────

# HTML tags that are DANGEROUS in user input — matches the FULL element
# including its content and closing tag for script/style (whose CONTENT
# is itself executable/injectable, not just the tag), and matches
# self-closing-style tags (img/link/meta/input/embed) as single units.
# DOTALL so `.` matches newlines too — scripts are often multi-line.
_DANGEROUS_PAIRED_TAGS = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Self-closing / single-tag dangerous elements (no meaningful "content" to strip,
# just the tag itself — but we still remove the matching closing tag if present,
# e.g. a malformed <iframe>...</iframe> or <form>...</form> wrapping injected content)
_DANGEROUS_WRAPPER_TAGS = re.compile(
    r"<(iframe|object|embed|form|svg)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Any remaining stray opening OR closing tags from the dangerous list
# (handles cases where there's no matching pair, e.g. just "<script>" alone,
# or a lone "</script>" left over from a stripped opening tag elsewhere)
#
# Includes svg/video/audio/base because all of these support event-handler
# attributes (onload=, onerror=, etc.) just like <img> does — <svg onload=...>
# is a well-known XSS vector that's easy to forget if you only think of
# <script> and <img> as "the dangerous tags".
_DANGEROUS_STRAY_TAGS = re.compile(
    r"</?(script|iframe|object|embed|form|input|link|meta|style|img"
    r"|svg|video|audio|base|details|marquee)\b[^>]*>",
    re.IGNORECASE,
)

# JavaScript event handlers like onclick=, onload=
_EVENT_HANDLERS = re.compile(r"\bon\w+\s*=", re.IGNORECASE)

# javascript: protocol in href/src attributes
_JS_PROTOCOL = re.compile(r"javascript\s*:", re.IGNORECASE)


def sanitize_input(text: str, max_length: int = 10000) -> str:
    """
    Remove XSS vectors from user-supplied text.

    This is a DEFENCE IN DEPTH measure — our primary protection is
    Jinja2's auto-escaping ({{ var }} not {{ var|safe }}).
    But for content stored in the DB and rendered elsewhere,
    we also strip dangerous patterns here.

    Order of operations matters:
      1. Strip <script>...</script> and <style>...</style> INCLUDING
         their content (the content itself is the dangerous part)
      2. Strip <iframe>/<object>/<embed>/<form> wrapper pairs including content
      3. Strip any remaining stray open/close tags from the dangerous list
         (catches unmatched tags, malformed HTML, single self-closing tags)
      4. Strip event handler attributes (onclick=, onerror=, etc.)
      5. Strip javascript: protocol references

    Args:
        text: The raw user input.
        max_length: Truncate if longer than this (prevents DoS via huge inputs).

    Returns:
        Cleaned string safe for storage.

    Example:
        sanitize_input('<script>alert(1)</script>Hello')
        → 'Hello'
        sanitize_input('<iframe src=evil.com></iframe>Safe text')
        → 'Safe text'
    """
    if not text:
        return ""

    # Truncate first (before regex — regex on huge strings is slow)
    text = str(text)[:max_length]

    # 1. Strip <script>/<style> tags AND their content (content is the danger)
    text = _DANGEROUS_PAIRED_TAGS.sub("", text)

    # 2. Strip <iframe>/<object>/<embed>/<form> wrapper pairs and their content
    text = _DANGEROUS_WRAPPER_TAGS.sub("", text)

    # 3. Strip any remaining stray tags (unmatched closes, self-closing img/link/etc.)
    text = _DANGEROUS_STRAY_TAGS.sub("", text)

    # 4. Remove event handlers (onclick=, onerror=, onload=, etc.)
    text = _EVENT_HANDLERS.sub("", text)

    # 5. Remove javascript: protocol references
    text = _JS_PROTOCOL.sub("", text)

    # Collapse multiple spaces/newlines left by removals
    text = re.sub(r"\s{3,}", "  ", text)

    return text.strip()


# ─────────────────────────────────────────────
# SAFE REDIRECT
# ─────────────────────────────────────────────

def is_safe_redirect_url(target: str) -> bool:
    """
    Prevent Open Redirect attacks.

    Open Redirect: attacker links to /auth/login?next=https://evil.com
    After login, a naive redirect would send the user to evil.com.

    We only allow redirects to URLs on the SAME host.

    Args:
        target: The URL from the 'next' query parameter.

    Returns:
        True if safe to redirect to, False otherwise.
    """
    from urllib.parse import urlparse, urljoin

    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))

    # Allow only same scheme (http/https) and same host
    return (
        redirect_url.scheme in ("http", "https")
        and host_url.netloc == redirect_url.netloc
    )


def get_safe_next_url(fallback_endpoint: str) -> str:
    """
    Get the 'next' URL from query params, validating it's safe.
    Returns url_for(fallback_endpoint) if 'next' is absent or unsafe.
    """
    next_url = request.args.get("next") or request.form.get("next")
    if next_url and is_safe_redirect_url(next_url):
        return next_url
    return url_for(fallback_endpoint)


# ─────────────────────────────────────────────
# TOKEN GENERATION
# ─────────────────────────────────────────────

def generate_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.

    Uses Python's secrets module which uses the OS random source
    (much more secure than random.random() which is predictable).

    Used for:
      - ExamSession.session_token
      - Password reset links (future)
      - Email verification links (future)

    Args:
        length: Number of bytes of randomness (hex string is 2× this).

    Returns:
        A hex string e.g. 'a3f8b12c...' (64 chars for length=32).
    """
    return secrets.token_hex(length)


# ─────────────────────────────────────────────
# ROLE-BASED ACCESS CONTROL DECORATOR
# ─────────────────────────────────────────────

def require_role(*roles):
    """
    Route decorator that restricts access to specific roles.

    Usage:
        @app.route('/admin/dashboard')
        @login_required          ← checks authentication first
        @require_role('admin')   ← then checks role
        def admin_dashboard():
            ...

    Args:
        *roles: One or more role strings ('admin', 'student', 'invigilator')

    Returns:
        403 Forbidden if the current user's role is not in the allowed list.
    """
    def decorator(f):
        @wraps(f)          # Preserves the original function's name/docstring
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                # Should be caught by @login_required but belt+suspenders
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                logger.warning(
                    f"Unauthorized access attempt: user {current_user.id} "
                    f"(role={current_user.role}) tried to access "
                    f"{request.path} (requires {roles})"
                )
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ─────────────────────────────────────────────
# SECURITY EVENT LOGGING
# ─────────────────────────────────────────────

def log_security_event(
    student_id: int,
    exam_id: int,
    event_type: str,
    description: str,
    severity: str = "medium",
    result_id: int = None,
    metadata: dict = None,
):
    """
    Write a security/cheat event to the cheat_logs table.
    (See log_security_event_with_evidence for the Day 5 version
    that supports snapshot evidence and face match distance.)
    """
    log_security_event_with_evidence(
        student_id=student_id,
        exam_id=exam_id,
        event_type=event_type,
        description=description,
        severity=severity,
        result_id=result_id,
        metadata=metadata,
    )


def log_security_event_with_evidence(
    student_id: int,
    exam_id: int,
    event_type: str,
    description: str,
    severity: str = "medium",
    result_id: int = None,
    metadata: dict = None,
    snapshot_base64: str = None,
    face_match_distance: float = None,
):
    """
    Write a security/cheat event to the cheat_logs table, with
    optional evidence snapshot and face-match distance (Day 5 additions).

    Args:
        student_id:          User.id of the student
        exam_id:              Exam.id being taken
        event_type:           One of the defined event type strings
        description:          Human-readable explanation
        severity:             'low' | 'medium' | 'high'
        result_id:            Result.id if available
        metadata:             Extra data as a dict (stored as JSON)
        snapshot_base64:      Base64 JPEG data URI captured at violation time
                               (only for high-severity face events — we don't
                               snapshot every minor event, that's excessive)
        face_match_distance:  Euclidean distance between calibrated and
                               live face descriptors (face_mismatch events)
    """
    import json
    from backend.models.models import db, CheatLog

    try:
        log = CheatLog(
            student_id=student_id,
            exam_id=exam_id,
            result_id=result_id,
            event_type=event_type,
            description=sanitize_input(description, max_length=500),
            severity=severity,
            timestamp=datetime.utcnow(),   # server time — not client time
            metadata_json=json.dumps(metadata) if metadata else None,
            snapshot_base64=snapshot_base64,
            face_match_distance=face_match_distance,
        )
        db.session.add(log)
        db.session.commit()
        logger.info(f"CheatLog: {event_type} | student={student_id} | exam={exam_id}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to write cheat log: {e}")


# ─────────────────────────────────────────────
# EXAM SESSION VALIDATION
# ─────────────────────────────────────────────

def validate_exam_session_token(token: str, student_id: int, exam_id: int):
    """
    Verify that a given token matches an active, non-expired exam session
    for the specified student and exam.

    Called before accepting any answer submission to prevent:
      - Replay attacks (submitting answers for an expired session)
      - Cross-session attacks (using another student's session token)

    Args:
        token:      The token from the request (cookie or header)
        student_id: Expected student ID
        exam_id:    Expected exam ID

    Returns:
        The ExamSession object if valid, None if invalid/expired.
    """
    from backend.models.models import ExamSession

    exam_session = ExamSession.query.filter_by(
        session_token=token,
        student_id=student_id,
        exam_id=exam_id,
        is_active=True,
    ).first()

    if not exam_session:
        logger.warning(
            f"Invalid exam session token for student={student_id} exam={exam_id}"
        )
        return None

    if exam_session.is_expired():
        logger.info(
            f"Expired exam session for student={student_id} exam={exam_id}"
        )
        return None

    return exam_session


# ─────────────────────────────────────────────
# PASSWORD STRENGTH CHECKER (for frontend feedback)
# ─────────────────────────────────────────────

def check_password_strength(password: str) -> dict:
    """
    Analyse password strength and return a score + feedback.
    Used by the registration API endpoint to give live feedback.

    Returns:
        {
            "score": 0–4,
            "label": "Weak" | "Fair" | "Good" | "Strong",
            "feedback": ["Has uppercase", "Missing number", ...]
        }
    """
    score = 0
    feedback = []

    if len(password) >= 8:
        score += 1
        feedback.append("✓ At least 8 characters")
    else:
        feedback.append("✗ Must be at least 8 characters")

    if any(c.isupper() for c in password):
        score += 1
        feedback.append("✓ Contains uppercase letter")
    else:
        feedback.append("✗ Add an uppercase letter")

    if any(c.islower() for c in password):
        score += 1
        feedback.append("✓ Contains lowercase letter")
    else:
        feedback.append("✗ Add a lowercase letter")

    if any(c.isdigit() for c in password):
        score += 1
        feedback.append("✓ Contains a number")
    else:
        feedback.append("✗ Add a number")

    labels = {0: "Very Weak", 1: "Weak", 2: "Fair", 3: "Good", 4: "Strong"}

    return {
        "score": score,
        "label": labels[score],
        "feedback": feedback,
    }
