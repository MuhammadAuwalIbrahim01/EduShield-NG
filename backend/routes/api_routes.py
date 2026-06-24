"""
backend/routes/api_routes.py — Public & Internal API Endpoints
================================================================
Routes:
  GET  /api/health              → Health check (used by Render)
  GET  /api/exam/time-check     → Returns seconds remaining for active session
  POST /api/exam/heartbeat      → Keeps session alive, returns time remaining
  GET  /api/stats/student       → Student's own stats (JSON)

All exam-specific API endpoints (save-answer, submit, log-event)
live in exam_routes.py alongside the page routes they serve.
"""

import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from backend.models.models import db, ExamSession, Result

api_bp  = Blueprint("api", __name__)
logger  = logging.getLogger(__name__)


@api_bp.route("/health")
def health():
    """
    Health check endpoint.
    Render pings this every 30s to verify the app is running.
    Returns 200 with JSON if healthy, 500 if DB is down.
    """
    try:
        # Quick DB check — try to count users
        from backend.models.models import User
        user_count = User.query.count()
        return jsonify({
            "status":    "ok",
            "service":   "EduShield NG",
            "timestamp": datetime.utcnow().isoformat(),
            "db":        "connected",
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status":  "error",
            "service": "EduShield NG",
            "db":      "disconnected",
            "error":   str(e),
        }), 500


@api_bp.route("/exam/time-check")
@login_required
def time_check():
    """
    Returns seconds remaining for the student's active exam session.
    Called by the JS timer every 60 seconds to re-sync with the server.

    This prevents timer drift — JS setInterval is not perfectly accurate
    and can be manipulated via DevTools.

    Returns JSON:
      {
        "seconds_remaining": 1234,
        "expired": false
      }
    """
    token = request.args.get("token", "")
    if not token:
        return jsonify({"error": "No token provided"}), 400

    exam_session = ExamSession.query.filter_by(
        session_token=token,
        student_id=current_user.id,
        is_active=True,
    ).first()

    if not exam_session:
        return jsonify({"expired": True, "seconds_remaining": 0}), 200

    expired = exam_session.is_expired()
    return jsonify({
        "expired":           expired,
        "seconds_remaining": exam_session.seconds_remaining(),
        "deadline_iso":      exam_session.deadline.isoformat(),
    }), 200


@api_bp.route("/exam/heartbeat", methods=["POST"])
@login_required
def heartbeat():
    """
    Called every 30 seconds by the exam page to:
      1. Confirm the server knows the student is still active
      2. Return updated time remaining (timer re-sync)
      3. Trigger auto-submit if time has expired

    Expected JSON: {"session_token": "abc..."}
    Returns JSON:  {"seconds_remaining": 1234, "status": "active"}
    """
    data = request.get_json(silent=True) or {}
    token = data.get("session_token", "")

    exam_session = ExamSession.query.filter_by(
        session_token=token,
        student_id=current_user.id,
        is_active=True,
    ).first()

    if not exam_session:
        return jsonify({"status": "invalid", "seconds_remaining": 0}), 200

    if exam_session.is_expired():
        # Server-side auto-submit
        from backend.routes.exam_routes import _auto_submit
        _auto_submit(exam_session, reason="Heartbeat detected expiry")
        result = Result.query.get(exam_session.result_id)
        return jsonify({
            "status":       "expired",
            "seconds_remaining": 0,
            "redirect_url": f"/exam/result/{result.id}" if result else "/exam/dashboard",
        }), 200

    return jsonify({
        "status":            "active",
        "seconds_remaining": exam_session.seconds_remaining(),
        "deadline_iso":      exam_session.deadline.isoformat(),
    }), 200


@api_bp.route("/stats/student")
@login_required
def student_stats():
    """
    Returns the current student's exam statistics as JSON.
    Used by the dashboard to populate stat cards via AJAX (future).
    """
    if not current_user.is_student():
        return jsonify({"error": "Students only"}), 403

    total = Result.query.filter_by(
        student_id=current_user.id
    ).filter(Result.status.in_(["submitted", "auto_submitted"])).count()

    passed = Result.query.filter_by(
        student_id=current_user.id, passed=True
    ).count()

    avg_result = db.session.query(
        db.func.avg(Result.percentage)
    ).filter_by(student_id=current_user.id).filter(
        Result.status.in_(["submitted", "auto_submitted"])
    ).scalar()

    return jsonify({
        "total_taken": total,
        "passed":      passed,
        "failed":      total - passed,
        "pass_rate":   round((passed / total * 100) if total else 0, 1),
        "average_pct": round(float(avg_result or 0), 1),
    }), 200
