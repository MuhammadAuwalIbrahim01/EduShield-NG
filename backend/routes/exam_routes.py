"""
backend/routes/exam_routes.py — Examination Engine Routes
===========================================================
Routes:
  GET  /exam/dashboard          → student home + exam list
  GET  /exam/available          → all published exams
  GET  /exam/start/<exam_id>    → pre-exam instructions page
  POST /exam/begin/<exam_id>    → create ExamSession, serve questions
  GET  /exam/take/<session_token> → the live exam interface
  POST /api/exam/save-answer    → auto-save a single answer
  POST /api/exam/submit         → final submission
  GET  /exam/result/<result_id> → result breakdown page
  GET  /exam/my-results         → all past results for student

Security on every route:
  - @login_required: must be authenticated
  - @require_role('student'): admins cannot take exams
  - Session token validation: every answer/submit must carry valid token
  - Server-side deadline: we never trust the client timer
"""

import json
import random
import secrets
import logging
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, jsonify, abort, session
)
from flask_login import login_required, current_user

from backend.models.models import db, Exam, Question, Result, ExamSession, CheatLog
from backend.utils.security import require_role, log_security_event, log_security_event_with_evidence

exam_bp = Blueprint("exam", __name__)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# STUDENT DASHBOARD
# ─────────────────────────────────────────────

@exam_bp.route("/dashboard")
@login_required
@require_role("student")
def student_dashboard():
    """
    Student home page.
    Shows: welcome stats, available exams, recent results.
    """
    # Get all published exams (potentially filtered by institution)
    available_exams = Exam.query.filter_by(status="published").order_by(
        Exam.created_at.desc()
    ).all()

    # Filter by availability window
    available_exams = [e for e in available_exams if e.is_available()]

    # Get student's recent results (last 5)
    recent_results = (
        Result.query
        .filter_by(student_id=current_user.id)
        .filter(Result.status.in_(["submitted", "auto_submitted"]))
        .order_by(Result.submitted_at.desc())
        .limit(5)
        .all()
    )

    # Check for any in-progress exam session (student may have refreshed)
    active_session = ExamSession.query.filter_by(
        student_id=current_user.id,
        is_active=True
    ).first()

    # Quick stats
    total_taken = Result.query.filter_by(
        student_id=current_user.id
    ).filter(Result.status.in_(["submitted", "auto_submitted"])).count()

    passed_count = Result.query.filter_by(
        student_id=current_user.id, passed=True
    ).count()

    pass_rate = round((passed_count / total_taken * 100)) if total_taken > 0 else 0

    return render_template(
        "exam/dashboard.html",
        title="Student Dashboard",
        available_exams=available_exams,
        recent_results=recent_results,
        active_session=active_session,
        stats={
            "total_taken": total_taken,
            "passed": passed_count,
            "pass_rate": pass_rate,
            "available": len(available_exams),
        }
    )


# ─────────────────────────────────────────────
# AVAILABLE EXAMS LIST
# ─────────────────────────────────────────────

@exam_bp.route("/available")
@login_required
@require_role("student")
def available_exams():
    """Full list of available exams with search/filter."""
    subject_filter = request.args.get("subject", "")
    search_query   = request.args.get("q", "").strip()

    query = Exam.query.filter_by(status="published")

    if subject_filter:
        query = query.filter_by(subject=subject_filter)

    if search_query:
        query = query.filter(
            Exam.title.ilike(f"%{search_query}%") |
            Exam.subject.ilike(f"%{search_query}%")
        )

    exams = query.order_by(Exam.created_at.desc()).all()
    exams = [e for e in exams if e.is_available()]

    # All unique subjects for filter dropdown
    subjects = db.session.query(Exam.subject).filter_by(
        status="published"
    ).distinct().all()
    subjects = [s[0] for s in subjects]

    # Find exams this student has already completed
    completed_ids = {
        r.exam_id for r in Result.query.filter_by(
            student_id=current_user.id
        ).filter(Result.status.in_(["submitted", "auto_submitted"])).all()
    }

    return render_template(
        "exam/available.html",
        title="Available Exams",
        exams=exams,
        subjects=subjects,
        completed_ids=completed_ids,
        subject_filter=subject_filter,
        search_query=search_query,
    )


# ─────────────────────────────────────────────
# PRE-EXAM INSTRUCTIONS PAGE
# ─────────────────────────────────────────────

@exam_bp.route("/api/my-face-descriptor")
@login_required
@require_role("student")
def my_face_descriptor():
    """
    AJAX endpoint: returns the CURRENT student's own calibrated face
    descriptor so face_monitor.js can compare it against live frames
    during the exam.

    Security note: this only ever returns the descriptor belonging to
    current_user (never accepts a student_id parameter) — a student
    can only ever fetch their OWN reference, never someone else's.

    Returns JSON: {"descriptor": [128 floats]} or {"descriptor": null}
    """
    descriptor = current_user.get_face_descriptor()
    return jsonify({"descriptor": descriptor})


@exam_bp.route("/calibrate/<int:exam_id>")
@login_required
@require_role("student")
def calibrate_face(exam_id):
    """
    Face calibration page.
    Shown BEFORE the instructions page if the exam requires webcam
    AND the student has not yet calibrated their face descriptor.

    The student looks at the camera, the page captures a face
    descriptor via face-api.js, and POSTs it to save_calibration().
    """
    exam = Exam.query.get_or_404(exam_id)

    if not exam.webcam_required:
        # No calibration needed — skip straight to instructions
        return redirect(url_for("exam.start_exam", exam_id=exam_id))

    if current_user.has_face_calibration():
        # Already calibrated — skip straight to instructions
        return redirect(url_for("exam.start_exam", exam_id=exam_id))

    return render_template(
        "exam/calibrate.html",
        title="Face Calibration",
        exam=exam,
        no_index=True,
    )


@exam_bp.route("/api/save-calibration", methods=["POST"])
@login_required
@require_role("student")
def save_calibration():
    """
    AJAX endpoint: save the student's face descriptor after calibration.

    Expected JSON:
      {
        "descriptor": [0.0123, -0.0456, ... 128 floats ...],
        "exam_id": 5
      }

    Returns JSON: {"status": "saved", "redirect_url": "..."}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data received"}), 400

    descriptor = data.get("descriptor")
    exam_id    = data.get("exam_id")

    # Validate: must be a list of exactly 128 floats
    # (face-api.js FaceRecognitionNet always outputs 128-dimension vectors)
    if not isinstance(descriptor, list) or len(descriptor) != 128:
        logger.warning(
            f"Invalid face descriptor from user {current_user.id}: "
            f"type={type(descriptor)}, len={len(descriptor) if isinstance(descriptor, list) else 'n/a'}"
        )
        return jsonify({"error": "Invalid descriptor format"}), 400

    # Validate all elements are numeric and within a sane range
    # (face-api.js descriptors are typically between -1 and 1)
    try:
        descriptor = [float(x) for x in descriptor]
        if any(abs(x) > 10 for x in descriptor):
            raise ValueError("Descriptor value out of expected range")
    except (TypeError, ValueError) as e:
        logger.warning(f"Malformed descriptor values from user {current_user.id}: {e}")
        return jsonify({"error": "Malformed descriptor values"}), 400

    current_user.set_face_descriptor(descriptor)
    db.session.commit()

    logger.info(f"Face calibration saved for student {current_user.id}")

    redirect_url = url_for("exam.start_exam", exam_id=exam_id) if exam_id else url_for("exam.student_dashboard")

    return jsonify({
        "status": "saved",
        "redirect_url": redirect_url,
    })


@exam_bp.route("/api/recalibrate", methods=["POST"])
@login_required
@require_role("student")
def recalibrate_face():
    """
    Allow a student to clear their calibration and redo it.
    Useful if lighting conditions changed drastically or they
    got a new device/camera.
    """
    current_user.face_descriptor_json = None
    current_user.face_calibrated_at = None
    db.session.commit()
    flash("Face calibration cleared. You will be asked to recalibrate before your next exam.", "info")
    return redirect(url_for("auth.profile"))


@exam_bp.route("/start/<int:exam_id>")
@login_required
@require_role("student")
def start_exam(exam_id):
    """
    Show exam instructions before starting.
    Student must click 'I Understand, Begin Exam' to actually start.

    This page:
    - Shows rules, duration, question count
    - Warns about webcam requirement
    - Lists anti-cheat rules
    - Checks for existing active session (resume warning)
    """
    exam = Exam.query.get_or_404(exam_id)

    if not exam.is_available():
        flash("This exam is not currently available.", "warning")
        return redirect(url_for("exam.student_dashboard"))

    # Redirect to calibration first if webcam is required and not yet calibrated
    if exam.webcam_required and not current_user.has_face_calibration():
        return redirect(url_for("exam.calibrate_face", exam_id=exam_id))

    # Check if student already has an active session for this exam
    existing_session = ExamSession.query.filter_by(
        student_id=current_user.id,
        exam_id=exam_id,
        is_active=True
    ).first()

    # Check if student already completed this exam
    existing_result = Result.query.filter_by(
        student_id=current_user.id,
        exam_id=exam_id,
    ).filter(Result.status.in_(["submitted", "auto_submitted"])).first()

    if existing_result:
        flash("You have already completed this exam.", "info")
        return redirect(url_for("exam.view_result", result_id=existing_result.id))

    return render_template(
        "exam/start.html",
        title=f"Start: {exam.title}",
        exam=exam,
        existing_session=existing_session,
        no_index=True,  # Don't let search engines index exam pages
    )


# ─────────────────────────────────────────────
# BEGIN EXAM — Create Session
# ─────────────────────────────────────────────

@exam_bp.route("/begin/<int:exam_id>", methods=["POST"])
@login_required
@require_role("student")
def begin_exam(exam_id):
    """
    POST: Student confirmed they understand the rules.
    We now:
      1. Validate exam is available
      2. Check for existing session (resume) or create new
      3. Shuffle questions (if configured)
      4. Create ExamSession with server deadline
      5. Create Result row (status='in_progress')
      6. Redirect to take_exam
    """
    exam = Exam.query.get_or_404(exam_id)

    if not exam.is_available():
        flash("This exam is no longer available.", "danger")
        return redirect(url_for("exam.student_dashboard"))

    # Check if already completed
    existing_result = Result.query.filter_by(
        student_id=current_user.id, exam_id=exam_id,
    ).filter(Result.status.in_(["submitted", "auto_submitted"])).first()

    if existing_result:
        flash("You have already completed this exam.", "info")
        return redirect(url_for("exam.view_result", result_id=existing_result.id))

    # Resume existing in-progress session
    existing_session = ExamSession.query.filter_by(
        student_id=current_user.id, exam_id=exam_id, is_active=True
    ).first()

    if existing_session and not existing_session.is_expired():
        logger.info(
            f"Student {current_user.id} resuming exam {exam_id} "
            f"(session {existing_session.session_token[:8]}...)"
        )
        return redirect(url_for("exam.take_exam",
                                session_token=existing_session.session_token))

    # If old session is expired, deactivate it
    if existing_session:
        existing_session.is_active = False
        existing_result_ip = Result.query.get(existing_session.result_id)
        if existing_result_ip:
            existing_result_ip.status = "auto_submitted"
            existing_result_ip.submitted_at = datetime.utcnow()
        db.session.commit()
        flash("Your previous session expired. Starting a new attempt.", "warning")

    # ── Create new exam session ──────────────────────
    questions = exam.questions.order_by(Question.order_index).all()

    if not questions:
        flash("This exam has no questions yet. Please contact admin.", "warning")
        return redirect(url_for("exam.student_dashboard"))

    # Shuffle question order (server-side — student cannot manipulate)
    question_ids = [q.id for q in questions]
    if exam.shuffle_questions:
        random.shuffle(question_ids)

    # Generate a cryptographically secure session token
    # This token must accompany every answer submission
    token = secrets.token_hex(32)

    # Server-side deadline — NOT a client timer
    start_time = datetime.utcnow()
    deadline   = start_time + timedelta(minutes=exam.duration_minutes)

    # Create a Result row immediately (status = in_progress)
    # We do this NOW so auto-save has a result_id to update
    new_result = Result(
        student_id=current_user.id,
        exam_id=exam_id,
        status="in_progress",
        started_at=start_time,
        total_marks=exam.total_marks(),
        answers_json="{}",
    )
    db.session.add(new_result)
    db.session.flush()  # Gets new_result.id without full commit

    # Create the ExamSession
    exam_session = ExamSession(
        student_id=current_user.id,
        exam_id=exam_id,
        result_id=new_result.id,
        start_time=start_time,
        deadline=deadline,
        session_token=token,
        question_order_json=json.dumps(question_ids),
        is_active=True,
    )
    db.session.add(exam_session)
    db.session.commit()

    logger.info(
        f"Exam started: student={current_user.id} exam={exam_id} "
        f"token={token[:8]}... deadline={deadline}"
    )

    return redirect(url_for("exam.take_exam", session_token=token))


# ─────────────────────────────────────────────
# TAKE EXAM — Live Interface
# ─────────────────────────────────────────────

@exam_bp.route("/take/<session_token>")
@login_required
@require_role("student")
def take_exam(session_token):
    """
    The live exam page.
    Validates the session token belongs to this student,
    loads questions in the shuffled order,
    passes server deadline to the browser (for JS timer).
    """
    exam_session = ExamSession.query.filter_by(
        session_token=session_token,
        student_id=current_user.id,
        is_active=True,
    ).first()

    if not exam_session:
        flash("Invalid or expired exam session.", "danger")
        return redirect(url_for("exam.student_dashboard"))

    if exam_session.is_expired():
        # Auto-submit the exam
        _auto_submit(exam_session)
        flash("Your exam time has expired. Your answers have been submitted.", "warning")
        result = Result.query.get(exam_session.result_id)
        return redirect(url_for("exam.view_result", result_id=result.id))

    exam   = Exam.query.get(exam_session.exam_id)
    result = Result.query.get(exam_session.result_id)

    # Load questions in the server-determined shuffled order
    question_order = json.loads(exam_session.question_order_json)

    # Fetch all questions for this exam, then sort by our shuffled order
    questions_map = {
        q.id: q for q in exam.questions.all()
    }
    ordered_questions = [questions_map[qid] for qid in question_order
                         if qid in questions_map]

    # Shuffle options within each question (if exam is configured for this)
    if exam.shuffle_options:
        for q in ordered_questions:
            options = list(q.get_options().items())
            random.shuffle(options)
            # Store shuffled option order on the question object (not in DB)
            q.shuffled_options = options
    else:
        for q in ordered_questions:
            q.shuffled_options = list(q.get_options().items())

    # Current saved answers (so student sees their previous selections on resume)
    saved_answers = json.loads(result.answers_json or "{}")

    return render_template(
        "exam/take.html",
        title=f"Exam: {exam.title}",
        exam=exam,
        exam_session=exam_session,
        questions=ordered_questions,
        saved_answers=saved_answers,
        seconds_remaining=exam_session.seconds_remaining(),
        no_index=True,
    )


# ─────────────────────────────────────────────
# API: SAVE SINGLE ANSWER (Auto-Save)
# ─────────────────────────────────────────────

@exam_bp.route("/api/save-answer", methods=["POST"])
@login_required
@require_role("student")
def save_answer():
    """
    AJAX endpoint: save one answer without submitting the exam.
    Called every time the student selects a radio button.

    Expected JSON body:
      {
        "session_token": "abc123...",
        "question_id": 42,
        "answer": "B"
      }

    Returns JSON:
      {"status": "saved", "seconds_remaining": 1234}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data received"}), 400

    token       = data.get("session_token", "")
    question_id = data.get("question_id")
    answer      = data.get("answer", "").upper().strip()

    # Validate answer is a valid option letter
    if answer not in ("A", "B", "C", "D"):
        return jsonify({"error": "Invalid answer"}), 400

    # Validate session
    exam_session = ExamSession.query.filter_by(
        session_token=token,
        student_id=current_user.id,
        is_active=True,
    ).first()

    if not exam_session:
        return jsonify({"error": "Invalid session"}), 403

    if exam_session.is_expired():
        _auto_submit(exam_session)
        return jsonify({"error": "Session expired", "redirect": True}), 403

    # Validate question belongs to this exam
    question = Question.query.filter_by(
        id=question_id, exam_id=exam_session.exam_id
    ).first()

    if not question:
        return jsonify({"error": "Invalid question"}), 400

    # Update the answers JSON in the Result row
    result = Result.query.get(exam_session.result_id)
    answers = json.loads(result.answers_json or "{}")
    answers[str(question_id)] = answer
    result.answers_json = json.dumps(answers)

    db.session.commit()

    return jsonify({
        "status": "saved",
        "seconds_remaining": exam_session.seconds_remaining(),
        "answers_count": len(answers),
    })


# ─────────────────────────────────────────────
# API: SUBMIT EXAM
# ─────────────────────────────────────────────

@exam_bp.route("/api/submit", methods=["POST"])
@login_required
@require_role("student")
def submit_exam():
    """
    AJAX endpoint: final exam submission.
    Called when student clicks 'Submit Exam' or timer expires.

    Expected JSON body:
      {
        "session_token": "abc123...",
        "answers": {"1": "A", "2": "C", ...},
        "tab_switches": 2,
        "face_absent_count": 1
      }

    Returns JSON:
      {"status": "submitted", "result_id": 42, "redirect_url": "..."}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data received"}), 400

    token = data.get("session_token", "")

    exam_session = ExamSession.query.filter_by(
        session_token=token,
        student_id=current_user.id,
        is_active=True,
    ).first()

    if not exam_session:
        return jsonify({"error": "Invalid or already submitted session"}), 403

    # Merge client-side final answers with server-saved answers
    # Server answers are authoritative — client answers are merged on top
    result = Result.query.get(exam_session.result_id)
    server_answers = json.loads(result.answers_json or "{}")

    client_answers = data.get("answers", {})
    # Validate and merge — only accept A/B/C/D values
    for qid, ans in client_answers.items():
        if str(ans).upper() in ("A", "B", "C", "D"):
            server_answers[str(qid)] = str(ans).upper()

    result.answers_json = json.dumps(server_answers)

    # Anti-cheat stats from browser
    result.tab_switches          = min(int(data.get("tab_switches", 0)), 999)
    result.face_absent_count     = min(int(data.get("face_absent_count", 0)), 999)
    result.multiple_faces_count  = min(int(data.get("multiple_faces_count", 0)), 999)

    # Flag for malpractice if thresholds exceeded
    exam = Exam.query.get(exam_session.exam_id)
    if result.tab_switches >= exam.max_tab_switches:
        result.flagged_for_malpractice = True
        result.malpractice_notes = (
            f"Exceeded tab switch limit ({result.tab_switches} switches). "
        )

    if result.multiple_faces_count > 3:
        result.flagged_for_malpractice = True
        result.malpractice_notes = (result.malpractice_notes or "") + (
            f"Multiple faces detected {result.multiple_faces_count} times. "
        )

    # Calculate score
    questions = exam.questions.all()
    result.calculate_score(questions)

    # Determine submission type
    submitted_at = datetime.utcnow()
    is_auto = exam_session.is_expired()
    result.status       = "auto_submitted" if is_auto else "submitted"
    result.submitted_at = submitted_at
    result.time_taken_seconds = int(
        (submitted_at - exam_session.start_time).total_seconds()
    )

    # Deactivate the exam session
    exam_session.is_active = False

    db.session.commit()

    logger.info(
        f"Exam submitted: student={current_user.id} exam={exam.id} "
        f"score={result.score}/{result.total_marks} "
        f"({result.percentage}%) status={result.status}"
    )

    return jsonify({
        "status": "submitted",
        "result_id": result.id,
        "redirect_url": url_for("exam.view_result", result_id=result.id),
    })


# ─────────────────────────────────────────────
# RESULT PAGE
# ─────────────────────────────────────────────

@exam_bp.route("/result/<int:result_id>")
@login_required
def view_result(result_id):
    """
    Show detailed exam result.
    Students can only view their own results.
    Admins can view any result.
    """
    result = Result.query.get_or_404(result_id)

    # Security: students can only see their own results
    if not current_user.is_admin() and result.student_id != current_user.id:
        abort(403)

    # Only show results for completed exams
    if result.status == "in_progress":
        flash("This exam is still in progress.", "warning")
        return redirect(url_for("exam.student_dashboard"))

    exam      = Exam.query.get(result.exam_id)
    questions = exam.questions.order_by(Question.order_index).all()
    answers   = json.loads(result.answers_json or "{}")

    # Build a per-question breakdown for the result page
    breakdown = []
    for q in questions:
        given   = answers.get(str(q.id))
        correct = q.correct_answer
        breakdown.append({
            "question":        q,
            "given_answer":    given,
            "correct_answer":  correct,
            "is_correct":      given == correct if given else False,
            "marks_earned":    q.marks if given == correct else 0,
            "marks_possible":  q.marks,
            "options":         q.get_options(),
        })

    return render_template(
        "exam/result.html",
        title=f"Result: {exam.title}",
        result=result,
        exam=exam,
        breakdown=breakdown,
        answers=answers,
        no_index=True,
    )


# ─────────────────────────────────────────────
# MY RESULTS — History
# ─────────────────────────────────────────────

@exam_bp.route("/my-results")
@login_required
@require_role("student")
def my_results():
    """All past exam attempts for the current student."""
    results = (
        Result.query
        .filter_by(student_id=current_user.id)
        .filter(Result.status.in_(["submitted", "auto_submitted"]))
        .order_by(Result.submitted_at.desc())
        .all()
    )

    return render_template(
        "exam/my_results.html",
        title="My Results",
        results=results,
    )


# ─────────────────────────────────────────────
# API: LOG CHEAT EVENT (from browser anti-cheat JS)
# ─────────────────────────────────────────────

@exam_bp.route("/api/log-event", methods=["POST"])
@login_required
@require_role("student")
def log_cheat_event():
    """
    Called by browser-side anti-cheat JS when a suspicious
    event is detected (tab switch, right-click, etc.).

    Expected JSON:
      {
        "session_token": "abc...",
        "event_type": "tab_switch",
        "description": "Student switched to another tab",
        "severity": "high",
        "snapshot": "data:image/jpeg;base64,...",   (optional)
        "face_match_distance": 0.72                  (optional, face_mismatch only)
      }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False}), 400

    token = data.get("session_token", "")
    exam_session = ExamSession.query.filter_by(
        session_token=token,
        student_id=current_user.id,
        is_active=True,
    ).first()

    if not exam_session:
        return jsonify({"ok": False}), 403

    # Allowlist of valid event types (never trust client strings directly)
    VALID_EVENTS = {
        "tab_switch", "window_blur", "copy_attempt", "paste_attempt",
        "right_click", "keyboard_shortcut", "fullscreen_exit",
        "face_absent", "multiple_faces", "face_detected", "face_mismatch",
    }
    event_type = data.get("event_type", "")
    if event_type not in VALID_EVENTS:
        return jsonify({"ok": False, "error": "Unknown event type"}), 400

    # ── Snapshot handling (only for high-severity events) ──
    snapshot = None
    severity = data.get("severity", "medium")
    if severity == "high" and event_type in ("multiple_faces", "face_mismatch"):
        raw_snapshot = data.get("snapshot", "")
        # Validate it's a proper data URI and not oversized
        # (base64 JPEG thumbnail at ~150x110px should be well under 50KB)
        if (isinstance(raw_snapshot, str) and
                raw_snapshot.startswith("data:image/jpeg;base64,") and
                len(raw_snapshot) < 80_000):
            snapshot = raw_snapshot
        elif raw_snapshot:
            logger.warning(
                f"Rejected oversized/malformed snapshot from user {current_user.id} "
                f"(length={len(raw_snapshot)})"
            )

    # ── Face match distance (face_mismatch events only) ──
    face_distance = None
    if event_type == "face_mismatch":
        try:
            face_distance = float(data.get("face_match_distance", 0))
            face_distance = max(0.0, min(2.0, face_distance))  # clamp sane range
        except (TypeError, ValueError):
            face_distance = None

    log_security_event_with_evidence(
        student_id=current_user.id,
        exam_id=exam_session.exam_id,
        event_type=event_type,
        description=str(data.get("description", ""))[:300],
        severity=severity,
        result_id=exam_session.result_id,
        snapshot_base64=snapshot,
        face_match_distance=face_distance,
    )

    # Update in-memory counters on the Result row for quick access
    result = Result.query.get(exam_session.result_id)
    if event_type == "tab_switch":
        result.tab_switches += 1
        if result.tab_switches >= exam_session.exam.max_tab_switches:
            db.session.commit()
            _auto_submit(exam_session, reason="Exceeded maximum tab switches")
            return jsonify({
                "ok": True,
                "action": "auto_submit",
                "message": "Exam auto-submitted due to excessive tab switching",
            })
    elif event_type == "face_absent":
        result.face_absent_count += 1
    elif event_type == "multiple_faces":
        result.multiple_faces_count += 1
    elif event_type == "face_mismatch":
        result.flagged_for_malpractice = True
        result.malpractice_notes = (result.malpractice_notes or "") + (
            f"Face mismatch detected (distance={face_distance}). "
        )

    db.session.commit()

    return jsonify({
        "ok": True,
        "tab_switches": result.tab_switches,
        "max_allowed": exam_session.exam.max_tab_switches,
        "warnings_left": max(
            0, exam_session.exam.max_tab_switches - result.tab_switches
        ),
    })


# ─────────────────────────────────────────────
# PRIVATE HELPER
# ─────────────────────────────────────────────

def _auto_submit(exam_session, reason="Time expired"):
    """
    Forcefully submit an exam session.
    Called when: timer expires on server-side check, or
                 student exceeds max tab switches.
    """
    result = Result.query.get(exam_session.result_id)
    if not result or result.status != "in_progress":
        return  # Already submitted

    exam      = Exam.query.get(exam_session.exam_id)
    questions = exam.questions.all()
    result.calculate_score(questions)

    result.status           = "auto_submitted"
    result.submitted_at     = datetime.utcnow()
    result.time_taken_seconds = int(
        (result.submitted_at - exam_session.start_time).total_seconds()
    )
    result.malpractice_notes = (result.malpractice_notes or "") + f"Auto-submitted: {reason}."

    exam_session.is_active = False
    db.session.commit()

    logger.info(
        f"Auto-submitted: student={exam_session.student_id} "
        f"exam={exam_session.exam_id} reason={reason}"
    )
