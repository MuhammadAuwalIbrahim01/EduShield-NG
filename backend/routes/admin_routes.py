"""
backend/routes/admin_routes.py — Complete Admin Dashboard Routes
===================================================================
Routes:
  GET  /admin/dashboard                  → analytics overview
  GET  /admin/exams                      → list all exams
  GET  /admin/exams/new                  → create exam form
  POST /admin/exams/new                  → process exam creation
  GET  /admin/exams/<id>/edit            → edit exam shell + question list
  POST /admin/exams/<id>/edit            → process exam shell edits
  POST /admin/exams/<id>/add-question    → add a question
  POST /admin/exams/<id>/delete-question/<qid> → remove a question
  POST /admin/exams/<id>/publish         → flip draft → published
  POST /admin/exams/<id>/close           → flip published → closed
  POST /admin/exams/<id>/delete          → delete exam entirely
  GET  /admin/exams/<id>/results         → all results for one exam
  GET  /admin/exams/<id>/export-csv      → CSV download of results

  GET  /admin/students                   → list all students
  GET  /admin/students/<id>              → single student detail
  POST /admin/students/<id>/suspend      → toggle is_active
  POST /admin/students/<id>/verify       → toggle is_verified
  POST /admin/students/<id>/unflag       → clear is_flagged

  GET  /admin/cheat-logs                 → integrity monitoring (Day 4)
"""

import csv
import io
import logging
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, jsonify, Response
)
from flask_login import login_required, current_user

from backend.models.models import db, CheatLog, Exam, Question, User, Result
from backend.utils.security import require_role, sanitize_input
from backend.utils.forms import ExamForm, QuestionForm

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# DASHBOARD — ANALYTICS OVERVIEW
# ─────────────────────────────────────────────

@admin_bp.route("/dashboard")
@login_required
@require_role("admin")
def dashboard():
    """
    Admin analytics overview.
    Shows: total students, total exams, total attempts,
    overall pass rate, recent flagged results, exam-by-exam breakdown.
    """
    total_students = User.query.filter_by(role="student").count()
    total_exams    = Exam.query.count()
    published_exams= Exam.query.filter_by(status="published").count()

    completed_results = Result.query.filter(
        Result.status.in_(["submitted", "auto_submitted"])
    )
    total_attempts = completed_results.count()
    passed_count   = completed_results.filter_by(passed=True).count()
    overall_pass_rate = round((passed_count / total_attempts * 100), 1) if total_attempts else 0

    flagged_count = Result.query.filter_by(flagged_for_malpractice=True).count()

    # Per-exam breakdown: title, attempts, average score, pass rate
    exam_stats = []
    for exam in Exam.query.order_by(Exam.created_at.desc()).limit(10).all():
        exam_results = Result.query.filter_by(exam_id=exam.id).filter(
            Result.status.in_(["submitted", "auto_submitted"])
        ).all()
        if exam_results:
            avg_pct = round(sum(r.percentage for r in exam_results) / len(exam_results), 1)
            exam_passed = sum(1 for r in exam_results if r.passed)
            exam_pass_rate = round((exam_passed / len(exam_results) * 100), 1)
        else:
            avg_pct = 0
            exam_pass_rate = 0
        exam_stats.append({
            "exam": exam,
            "attempts": len(exam_results),
            "avg_pct": avg_pct,
            "pass_rate": exam_pass_rate,
        })

    # Recent flagged results needing review
    recent_flagged = (
        Result.query.filter_by(flagged_for_malpractice=True)
        .order_by(Result.submitted_at.desc())
        .limit(5)
        .all()
    )

    # Recent high-severity cheat log events
    recent_high_severity = (
        CheatLog.query.filter_by(severity="high")
        .order_by(CheatLog.timestamp.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        title="Admin Dashboard",
        stats={
            "total_students": total_students,
            "total_exams": total_exams,
            "published_exams": published_exams,
            "total_attempts": total_attempts,
            "overall_pass_rate": overall_pass_rate,
            "flagged_count": flagged_count,
        },
        exam_stats=exam_stats,
        recent_flagged=recent_flagged,
        recent_high_severity=recent_high_severity,
    )


# ─────────────────────────────────────────────
# EXAM MANAGEMENT
# ─────────────────────────────────────────────

@admin_bp.route("/exams")
@login_required
@require_role("admin")
def exams():
    """List all exams with quick stats."""
    all_exams = Exam.query.order_by(Exam.created_at.desc()).all()
    return render_template("admin/exams.html", title="Manage Exams", exams=all_exams)


@admin_bp.route("/exams/new", methods=["GET", "POST"])
@login_required
@require_role("admin")
def new_exam():
    """Create a new exam SHELL (no questions yet — added separately)."""
    form = ExamForm()

    if form.validate_on_submit():
        exam = Exam(
            title=sanitize_input(form.title.data.strip()),
            description=sanitize_input(form.description.data.strip()) if form.description.data else None,
            subject=sanitize_input(form.subject.data.strip()),
            duration_minutes=form.duration_minutes.data,
            pass_mark=form.pass_mark.data,
            status="draft",  # Always starts as draft — admin publishes explicitly
            created_by=current_user.id,
            webcam_required=form.webcam_required.data,
            shuffle_questions=form.shuffle_questions.data,
            shuffle_options=form.shuffle_options.data,
            max_tab_switches=form.max_tab_switches.data,
            target_institution=sanitize_input(form.target_institution.data.strip()) if form.target_institution.data else None,
            target_department=sanitize_input(form.target_department.data.strip()) if form.target_department.data else None,
        )
        db.session.add(exam)
        db.session.commit()

        logger.info(f"Exam created: {exam.id} '{exam.title}' by admin {current_user.id}")
        flash(f"Exam '{exam.title}' created as draft. Now add questions.", "success")
        return redirect(url_for("admin.edit_exam", exam_id=exam.id))

    return render_template("admin/exam_form.html", title="Create Exam", form=form, exam=None)


@admin_bp.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
@login_required
@require_role("admin")
def edit_exam(exam_id):
    """
    Edit an exam's shell settings AND view/manage its question list.
    This is the main exam-building screen.
    """
    exam = Exam.query.get_or_404(exam_id)
    form = ExamForm(obj=exam)
    question_form = QuestionForm()

    if form.validate_on_submit():
        exam.title = sanitize_input(form.title.data.strip())
        exam.description = sanitize_input(form.description.data.strip()) if form.description.data else None
        exam.subject = sanitize_input(form.subject.data.strip())
        exam.duration_minutes = form.duration_minutes.data
        exam.pass_mark = form.pass_mark.data
        exam.webcam_required = form.webcam_required.data
        exam.shuffle_questions = form.shuffle_questions.data
        exam.shuffle_options = form.shuffle_options.data
        exam.max_tab_switches = form.max_tab_switches.data
        exam.target_institution = sanitize_input(form.target_institution.data.strip()) if form.target_institution.data else None
        exam.target_department = sanitize_input(form.target_department.data.strip()) if form.target_department.data else None
        exam.updated_at = datetime.utcnow()
        db.session.commit()

        flash("Exam settings updated.", "success")
        return redirect(url_for("admin.edit_exam", exam_id=exam.id))

    questions = exam.questions.order_by(Question.order_index).all()

    return render_template(
        "admin/exam_form.html",
        title=f"Edit: {exam.title}",
        form=form,
        exam=exam,
        questions=questions,
        question_form=question_form,
    )


@admin_bp.route("/exams/<int:exam_id>/add-question", methods=["POST"])
@login_required
@require_role("admin")
def add_question(exam_id):
    """Add one multiple-choice question to an existing exam."""
    exam = Exam.query.get_or_404(exam_id)
    form = QuestionForm()

    if form.validate_on_submit():
        next_order = exam.questions.count()
        question = Question(
            exam_id=exam.id,
            text=sanitize_input(form.text.data.strip()),
            option_a=sanitize_input(form.option_a.data.strip()),
            option_b=sanitize_input(form.option_b.data.strip()),
            option_c=sanitize_input(form.option_c.data.strip()),
            option_d=sanitize_input(form.option_d.data.strip()),
            correct_answer=form.correct_answer.data,
            marks=form.marks.data,
            explanation=sanitize_input(form.explanation.data.strip()) if form.explanation.data else None,
            order_index=next_order,
        )
        db.session.add(question)
        db.session.commit()
        flash(f"Question {next_order + 1} added.", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "danger")

    return redirect(url_for("admin.edit_exam", exam_id=exam_id))


@admin_bp.route("/exams/<int:exam_id>/delete-question/<int:question_id>", methods=["POST"])
@login_required
@require_role("admin")
def delete_question(exam_id, question_id):
    """Remove a question from an exam."""
    question = Question.query.filter_by(id=question_id, exam_id=exam_id).first_or_404()
    db.session.delete(question)
    db.session.commit()

    # Re-sequence remaining questions' order_index
    remaining = Question.query.filter_by(exam_id=exam_id).order_by(Question.order_index).all()
    for i, q in enumerate(remaining):
        q.order_index = i
    db.session.commit()

    flash("Question removed.", "info")
    return redirect(url_for("admin.edit_exam", exam_id=exam_id))


@admin_bp.route("/exams/<int:exam_id>/publish", methods=["POST"])
@login_required
@require_role("admin")
def publish_exam(exam_id):
    """Flip an exam from draft to published — makes it visible to students."""
    exam = Exam.query.get_or_404(exam_id)

    if exam.question_count() == 0:
        flash("Cannot publish an exam with no questions.", "danger")
        return redirect(url_for("admin.edit_exam", exam_id=exam_id))

    exam.status = "published"
    exam.updated_at = datetime.utcnow()
    db.session.commit()

    logger.info(f"Exam published: {exam.id} by admin {current_user.id}")
    flash(f"'{exam.title}' is now published and visible to students.", "success")
    return redirect(url_for("admin.exams"))


@admin_bp.route("/exams/<int:exam_id>/close", methods=["POST"])
@login_required
@require_role("admin")
def close_exam(exam_id):
    """Flip an exam from published to closed — no new attempts allowed."""
    exam = Exam.query.get_or_404(exam_id)
    exam.status = "closed"
    exam.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f"'{exam.title}' is now closed.", "info")
    return redirect(url_for("admin.exams"))


@admin_bp.route("/exams/<int:exam_id>/delete", methods=["POST"])
@login_required
@require_role("admin")
def delete_exam(exam_id):
    """
    Permanently delete an exam and all its questions/results.
    cascade="all, delete-orphan" on the model relationships handles
    cleanup of related Questions and Results automatically.
    """
    exam = Exam.query.get_or_404(exam_id)
    title = exam.title
    db.session.delete(exam)
    db.session.commit()

    logger.warning(f"Exam DELETED: '{title}' (id={exam_id}) by admin {current_user.id}")
    flash(f"'{title}' has been permanently deleted.", "info")
    return redirect(url_for("admin.exams"))


# ─────────────────────────────────────────────
# EXAM RESULTS & EXPORT
# ─────────────────────────────────────────────

@admin_bp.route("/exams/<int:exam_id>/results")
@login_required
@require_role("admin")
def exam_results(exam_id):
    """View all student results for one specific exam."""
    exam = Exam.query.get_or_404(exam_id)
    results = (
        Result.query.filter_by(exam_id=exam_id)
        .filter(Result.status.in_(["submitted", "auto_submitted"]))
        .order_by(Result.percentage.desc())
        .all()
    )
    return render_template(
        "admin/exam_results.html",
        title=f"Results: {exam.title}",
        exam=exam,
        results=results,
    )


@admin_bp.route("/exams/<int:exam_id>/export-csv")
@login_required
@require_role("admin")
def export_results_csv(exam_id):
    """
    Generate a CSV file of all results for an exam and stream it
    as a file download. Used for institutional record-keeping.
    """
    exam = Exam.query.get_or_404(exam_id)
    results = (
        Result.query.filter_by(exam_id=exam_id)
        .filter(Result.status.in_(["submitted", "auto_submitted"]))
        .order_by(Result.percentage.desc())
        .all()
    )

    # Build CSV in memory (no temp file needed)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student Name", "Student ID", "Email", "Institution",
        "Score", "Total Marks", "Percentage", "Passed",
        "Tab Switches", "Face Absences", "Multiple Faces",
        "Flagged", "Status", "Time Taken (s)", "Submitted At",
    ])

    for r in results:
        writer.writerow([
            r.student.full_name,
            r.student.student_id or "",
            r.student.email,
            r.student.institution or "",
            r.score,
            r.total_marks,
            r.percentage,
            "Yes" if r.passed else "No",
            r.tab_switches,
            r.face_absent_count,
            r.multiple_faces_count,
            "Yes" if r.flagged_for_malpractice else "No",
            r.status,
            r.time_taken_seconds,
            r.submitted_at.isoformat() if r.submitted_at else "",
        ])

    csv_data = output.getvalue()
    output.close()

    safe_filename = "".join(c for c in exam.title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_filename}_results.csv"

    logger.info(f"CSV export: exam {exam_id} by admin {current_user.id}")

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────
# STUDENT MANAGEMENT
# ─────────────────────────────────────────────

@admin_bp.route("/students")
@login_required
@require_role("admin")
def students():
    """List all students with search."""
    search = request.args.get("q", "").strip()
    query = User.query.filter_by(role="student")

    if search:
        query = query.filter(
            User.full_name.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%") |
            User.student_id.ilike(f"%{search}%")
        )

    all_students = query.order_by(User.created_at.desc()).all()
    return render_template(
        "admin/students.html",
        title="Manage Students",
        students=all_students,
        search=search,
    )


@admin_bp.route("/students/<int:student_id>")
@login_required
@require_role("admin")
def student_detail(student_id):
    """Single student detail page: profile + exam history + cheat logs."""
    student = User.query.filter_by(id=student_id, role="student").first_or_404()

    results = Result.query.filter_by(student_id=student_id).filter(
        Result.status.in_(["submitted", "auto_submitted"])
    ).order_by(Result.submitted_at.desc()).all()

    cheat_logs = CheatLog.query.filter_by(student_id=student_id).order_by(
        CheatLog.timestamp.desc()
    ).limit(50).all()

    return render_template(
        "admin/student_detail.html",
        title=student.full_name,
        student=student,
        results=results,
        cheat_logs=cheat_logs,
    )


@admin_bp.route("/students/<int:student_id>/suspend", methods=["POST"])
@login_required
@require_role("admin")
def toggle_suspend(student_id):
    """Toggle a student's is_active flag (suspend/reactivate)."""
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.is_active = not student.is_active
    db.session.commit()

    action = "reactivated" if student.is_active else "suspended"
    logger.warning(f"Student {action}: {student.id} by admin {current_user.id}")
    flash(f"{student.full_name} has been {action}.", "success" if student.is_active else "warning")
    return redirect(request.referrer or url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/verify", methods=["POST"])
@login_required
@require_role("admin")
def toggle_verify(student_id):
    """Toggle a student's is_verified flag."""
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.is_verified = not student.is_verified
    db.session.commit()

    flash(f"{student.full_name} verification status updated.", "success")
    return redirect(request.referrer or url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/unflag", methods=["POST"])
@login_required
@require_role("admin")
def unflag_student(student_id):
    """Clear the is_flagged status after admin review."""
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.is_flagged = False
    db.session.commit()

    flash(f"{student.full_name} has been unflagged.", "success")
    return redirect(request.referrer or url_for("admin.students"))


# ─────────────────────────────────────────────
# CHEAT LOGS (Day 4 — unchanged)
# ─────────────────────────────────────────────

@admin_bp.route("/cheat-logs")
@login_required
@require_role("admin")
def cheat_logs():
    """Integrity monitoring — all cheat events with optional filters."""
    severity   = request.args.get("severity", "")
    event_type = request.args.get("event_type", "")

    query = CheatLog.query.order_by(CheatLog.timestamp.desc())

    if severity:
        query = query.filter_by(severity=severity)
    if event_type:
        query = query.filter_by(event_type=event_type)

    logs = query.limit(500).all()
    return render_template(
        "admin/cheat_logs.html",
        title="Integrity Logs",
        logs=logs,
    )
