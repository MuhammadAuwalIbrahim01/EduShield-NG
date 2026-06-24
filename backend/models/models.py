"""
models.py — EduShield NG Database Models
=========================================
Each class here maps to one database table via SQLAlchemy ORM.

SQLAlchemy ORM means we write Python classes instead of raw SQL.
SQLAlchemy translates them into CREATE TABLE statements and handles
INSERT, UPDATE, SELECT for us.

Security note: we NEVER store plain-text passwords.
We store only the bcrypt hash of the password (via Werkzeug).
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# db is the SQLAlchemy instance.
# We create it here (not in app.py) to avoid circular imports.
# app.py will call db.init_app(app) to connect them.
db = SQLAlchemy()


# =============================================================================
# USER MODEL
# =============================================================================

class User(UserMixin, db.Model):
    """
    Represents every person who can log into EduShield NG.

    UserMixin gives us:
      - is_authenticated (True after login)
      - is_active (can be set False to ban users)
      - get_id() — returns self.id as a string (Flask-Login requires this)

    Roles:
      'student'      — takes exams, sees own results
      'admin'        — manages exams, students, sees all results
      'invigilator'  — monitors live exams (future feature)
    """
    __tablename__ = "users"

    # Primary key — auto-incrementing integer ID
    id = db.Column(db.Integer, primary_key=True)

    # Full name — shown on result sheets
    full_name = db.Column(db.String(100), nullable=False)

    # Email is our login username — must be unique across the system
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    # index=True creates a B-tree index on email so login lookups are fast

    # We ONLY store the hash, never the real password
    # Column is long (256) because bcrypt hashes are ~60 chars but we allow room
    password_hash = db.Column(db.String(256), nullable=False)

    # Role determines what the user can see and do
    # CHECK constraint enforced at DB level too (see __table_args__)
    role = db.Column(db.String(20), nullable=False, default="student")

    # Student-specific fields (NULL for admin users)
    student_id = db.Column(db.String(50), unique=True, nullable=True)
    institution = db.Column(db.String(200), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)

    # Profile picture path (stored on disk, path in DB)
    profile_picture = db.Column(db.String(200), nullable=True)

    # Account status flags
    is_verified = db.Column(db.Boolean, default=False)    # email verified
    is_active = db.Column(db.Boolean, default=True)       # not banned
    is_flagged = db.Column(db.Boolean, default=False)     # flagged for review

    # Preferred language for TTS and UI
    preferred_language = db.Column(db.String(5), default="en")

    # ── Face Calibration (Day 5) ──────────────
    # Stores the 128-number face descriptor from face-api.js as a
    # JSON-encoded array string, e.g. "[0.0123, -0.0456, ...]"
    # This is NOT a photo — it's a mathematical fingerprint that
    # cannot be reversed back into an image.
    face_descriptor_json = db.Column(db.Text, nullable=True)
    face_calibrated_at   = db.Column(db.DateTime, nullable=True)

    # Accessibility preferences stored as comma-separated flags
    # e.g. "tts,high_contrast,large_font"
    accessibility_prefs = db.Column(db.String(200), default="")

    # Audit timestamps — auto-set by SQLAlchemy
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # --- Relationships ---
    # One user can have many exam results
    results = db.relationship("Result", backref="student", lazy="dynamic",
                              foreign_keys="Result.student_id")
    # One user can create many exams (admin only)
    created_exams = db.relationship("Exam", backref="creator", lazy="dynamic",
                                    foreign_keys="Exam.created_by")
    # One user can generate many cheat log entries
    cheat_logs = db.relationship("CheatLog", backref="student", lazy="dynamic",
                                 foreign_keys="CheatLog.student_id")

    # --- Password Methods ---
    def set_password(self, password):
        """
        Hash the password with bcrypt (via Werkzeug) and store the hash.
        NEVER call: self.password_hash = password  ← that would store plaintext!
        Werkzeug's generate_password_hash uses pbkdf2:sha256 by default.
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """
        Return True if the given password matches the stored hash.
        Werkzeug handles the comparison safely (timing-attack resistant).
        """
        return check_password_hash(self.password_hash, password)

    # --- Role Helpers ---
    def is_admin(self):
        """Quick check used in templates and route guards."""
        return self.role == "admin"

    def is_student(self):
        return self.role == "student"

    def get_accessibility_list(self):
        """Return accessibility prefs as a Python list."""
        if not self.accessibility_prefs:
            return []
        return self.accessibility_prefs.split(",")

    def has_face_calibration(self):
        """True if this student has completed face calibration."""
        return bool(self.face_descriptor_json)

    def get_face_descriptor(self):
        """Return the stored face descriptor as a Python list of floats."""
        import json
        if not self.face_descriptor_json:
            return None
        return json.loads(self.face_descriptor_json)

    def set_face_descriptor(self, descriptor_list):
        """
        Store a face descriptor (list of 128 floats from face-api.js).
        Called once during calibration, can be re-calibrated by admin
        if the student reports persistent false mismatches.
        """
        import json
        self.face_descriptor_json = json.dumps(descriptor_list)
        self.face_calibrated_at = datetime.utcnow()

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


# =============================================================================
# EXAM MODEL
# =============================================================================

class Exam(db.Model):
    """
    Represents one examination.
    An exam contains many Questions and generates many Results.
    """
    __tablename__ = "exams"

    id = db.Column(db.Integer, primary_key=True)

    # Human-readable exam title shown to students
    title = db.Column(db.String(200), nullable=False)

    # Optional description / instructions shown before the exam starts
    description = db.Column(db.Text, nullable=True)

    # Subject area e.g. "Mathematics", "English Language"
    subject = db.Column(db.String(100), nullable=False)

    # Duration in minutes — the countdown timer counts down from this
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)

    # Passing score as a percentage (0–100)
    pass_mark = db.Column(db.Integer, nullable=False, default=50)

    # Status controls visibility to students
    # 'draft' → only admin can see
    # 'published' → students can take it
    # 'closed' → no new attempts allowed
    status = db.Column(db.String(20), nullable=False, default="draft")

    # Anti-cheat configuration
    allow_navigation = db.Column(db.Boolean, default=False)  # can go back?
    shuffle_questions = db.Column(db.Boolean, default=True)
    shuffle_options = db.Column(db.Boolean, default=True)
    webcam_required = db.Column(db.Boolean, default=True)
    max_tab_switches = db.Column(db.Integer, default=3)

    # Who created this exam (FK → users.id)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Schedule window — exam is only accessible between these times
    # NULL means no restriction
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)

    # Institution/class targeting
    target_institution = db.Column(db.String(200), nullable=True)
    target_department = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # --- Relationships ---
    questions = db.relationship("Question", backref="exam", lazy="dynamic",
                                cascade="all, delete-orphan")
    results = db.relationship("Result", backref="exam", lazy="dynamic",
                              cascade="all, delete-orphan")

    # --- Helper Methods ---
    def question_count(self):
        """Return the number of questions in this exam."""
        return self.questions.count()

    def total_marks(self):
        """Sum of all question marks (each question has its own mark value)."""
        return sum(q.marks for q in self.questions.all())

    def is_available(self):
        """
        True if a student can currently take this exam.
        Must be published AND within the time window (if set).
        """
        if self.status != "published":
            return False
        now = datetime.utcnow()
        if self.start_time and now < self.start_time:
            return False
        if self.end_time and now > self.end_time:
            return False
        return True

    def __repr__(self):
        return f"<Exam {self.title!r} [{self.status}]>"


# =============================================================================
# QUESTION MODEL
# =============================================================================

class Question(db.Model):
    """
    One multiple-choice question belonging to an Exam.
    Stores the question text, four options, and the correct answer index.
    """
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)

    # FK links this question to its parent exam
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)

    # The question text (can be long, so we use Text not String)
    text = db.Column(db.Text, nullable=False)

    # Four answer options — stored as separate columns for simplicity
    # (Alternative: JSON column, but separate columns are easier to query)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)

    # Which option is correct: 'A', 'B', 'C', or 'D'
    correct_answer = db.Column(db.String(1), nullable=False)

    # How many marks this question is worth (default 1)
    marks = db.Column(db.Integer, default=1)

    # Optional explanation shown after the exam (learning tool)
    explanation = db.Column(db.Text, nullable=True)

    # Display order — admin can set the sequence
    order_index = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_options(self):
        """Return options as a dict for easy template iteration."""
        return {
            "A": self.option_a,
            "B": self.option_b,
            "C": self.option_c,
            "D": self.option_d,
        }

    def is_correct(self, answer):
        """Check if the given answer letter is the correct one."""
        return answer.upper() == self.correct_answer.upper()

    def __repr__(self):
        return f"<Question {self.id} (Exam {self.exam_id})>"


# =============================================================================
# RESULT MODEL
# =============================================================================

class Result(db.Model):
    """
    Records one student's attempt at one exam.
    Stores each answer, the final score, and timing information.
    """
    __tablename__ = "results"

    id = db.Column(db.Integer, primary_key=True)

    # Who took the exam
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Which exam was taken
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)

    # --- Scoring ---
    score = db.Column(db.Integer, default=0)          # raw marks earned
    total_marks = db.Column(db.Integer, default=0)    # max possible marks
    percentage = db.Column(db.Float, default=0.0)     # score/total * 100
    passed = db.Column(db.Boolean, default=False)     # met pass_mark?

    # --- Answers ---
    # Store each answer as JSON string: {"1": "A", "2": "C", ...}
    # Key = question ID, Value = answer given
    answers_json = db.Column(db.Text, default="{}")

    # --- Timing ---
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    # Actual time taken in seconds
    time_taken_seconds = db.Column(db.Integer, default=0)

    # --- Status ---
    # 'in_progress' | 'submitted' | 'auto_submitted' | 'flagged'
    status = db.Column(db.String(20), default="in_progress")

    # Anti-cheat summary
    tab_switches = db.Column(db.Integer, default=0)
    face_absent_count = db.Column(db.Integer, default=0)
    multiple_faces_count = db.Column(db.Integer, default=0)
    flagged_for_malpractice = db.Column(db.Boolean, default=False)
    malpractice_notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def calculate_score(self, questions):
        """
        Given a list of Question objects, calculate and store the score.
        Call this before setting status = 'submitted'.
        """
        import json
        answers = json.loads(self.answers_json or "{}")
        score = 0
        total = 0
        for q in questions:
            total += q.marks
            given = answers.get(str(q.id))
            if given and q.is_correct(given):
                score += q.marks
        self.score = score
        self.total_marks = total
        self.percentage = round((score / total * 100), 2) if total > 0 else 0.0
        # Get pass_mark from the related exam
        self.passed = self.percentage >= self.exam.pass_mark

    def __repr__(self):
        return f"<Result Student:{self.student_id} Exam:{self.exam_id} {self.percentage}%>"


# =============================================================================
# CHEAT LOG MODEL
# =============================================================================

class CheatLog(db.Model):
    """
    Records every suspicious event during an exam.
    Used by the admin to review integrity and make decisions.
    Each row = one event (one tab switch, one face absence, etc.)
    """
    __tablename__ = "cheat_logs"

    id = db.Column(db.Integer, primary_key=True)

    # The student who triggered the event
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Which exam attempt (links to results table)
    result_id = db.Column(db.Integer, db.ForeignKey("results.id"), nullable=True)

    # Exam reference (for quick queries without joining results)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)

    # Event type — what kind of suspicious thing happened
    # Values: 'tab_switch' | 'window_blur' | 'copy_attempt' | 'paste_attempt'
    #         | 'right_click' | 'face_absent' | 'multiple_faces'
    #         | 'keyboard_shortcut' | 'fullscreen_exit' | 'auto_submitted'
    event_type = db.Column(db.String(50), nullable=False)

    # Human-readable description
    description = db.Column(db.Text, nullable=True)

    # Severity: 'low' | 'medium' | 'high'
    severity = db.Column(db.String(10), default="medium")

    # When this event occurred (server-side timestamp — NOT client-side)
    # Never trust client-side times for security events
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Optional screenshot path (future feature)
    screenshot_path = db.Column(db.String(200), nullable=True)

    # ── Evidence Snapshot (Day 5) ──────────────
    # Base64-encoded JPEG thumbnail (small, ~150x110px) captured
    # at the moment of a high-severity violation. Stored inline
    # rather than on disk for simplicity at this project's scale.
    # NULL for low/medium severity events (we don't snapshot everything —
    # that would be excessive surveillance for minor events).
    snapshot_base64 = db.Column(db.Text, nullable=True)

    # Face match distance (0.0 = identical, 1.0+ = very different)
    # Only populated for face_mismatch events. NULL otherwise.
    face_match_distance = db.Column(db.Float, nullable=True)

    # Extra metadata as JSON (e.g. face confidence score)
    metadata_json = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<CheatLog {self.event_type} Student:{self.student_id}>"


# =============================================================================
# EXAM SESSION MODEL (server-side exam state)
# =============================================================================

class ExamSession(db.Model):
    """
    Tracks an active exam session for a student.
    Created when student clicks 'Start Exam', destroyed on submit.

    Why store this server-side?
    → A student cannot manipulate a server-side timer the way they could
      a JavaScript countdown. The server is the source of truth for time.
    """
    __tablename__ = "exam_sessions"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    result_id = db.Column(db.Integer, db.ForeignKey("results.id"), nullable=False)

    # Exact server time when the student pressed 'Start'
    start_time = db.Column(db.DateTime, default=datetime.utcnow)

    # Calculated deadline: start_time + duration_minutes
    deadline = db.Column(db.DateTime, nullable=False)

    # A random token stored in the user's session cookie.
    # Each API request must include this token so we know the
    # request is from the legitimate exam window (not a replay).
    session_token = db.Column(db.String(64), nullable=False, unique=True)

    # Shuffled question order (JSON list of question IDs)
    # Stored server-side so the student can't change their question order
    question_order_json = db.Column(db.Text, default="[]")

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_expired(self):
        """True if the deadline has passed."""
        return datetime.utcnow() > self.deadline

    def seconds_remaining(self):
        """How many seconds until this session expires."""
        delta = self.deadline - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    def __repr__(self):
        return f"<ExamSession Student:{self.student_id} Exam:{self.exam_id}>"
