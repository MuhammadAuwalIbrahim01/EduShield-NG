"""
backend/utils/forms.py — EduShield NG Form Definitions
========================================================
WTForms provides:
  1. Field definitions (what inputs exist)
  2. Validators (rules each field must pass)
  3. CSRF token injection (auto via Flask-WTF)
  4. Error messages (shown back to the user)

Why WTForms instead of plain HTML?
  - Server-side validation cannot be bypassed (unlike JS validation)
  - CSRF token is automatic
  - Clean error handling
  - Re-renders form with user's data on validation failure
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, BooleanField,
    SelectField, TextAreaField, IntegerField, SubmitField
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo,
    ValidationError, NumberRange, Optional, Regexp
)
from backend.models.models import User


# ─────────────────────────────────────────────
# REGISTRATION FORM
# ─────────────────────────────────────────────

class RegistrationForm(FlaskForm):
    """
    Student self-registration form.
    All validators run server-side — client JS validation is extra,
    but the server never trusts the client.
    """

    full_name = StringField(
        "Full Name",
        validators=[
            DataRequired(message="Full name is required."),
            # Length: must be between 2 and 100 chars
            Length(min=2, max=100, message="Name must be 2–100 characters."),
            # Regex: only letters and spaces (no SQL injection via name)
            Regexp(
                r"^[A-Za-z\s\-']+$",
                message="Name can only contain letters, spaces, hyphens, and apostrophes.",
            ),
        ],
    )

    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Please enter a valid email address."),
            Length(max=150, message="Email too long."),
        ],
    )

    student_id = StringField(
        "Student ID / Matriculation Number",
        validators=[
            DataRequired(message="Student ID is required."),
            Length(min=3, max=50, message="Student ID must be 3–50 characters."),
            # Alphanumeric + common separators only
            Regexp(
                r"^[A-Za-z0-9\-/]+$",
                message="Student ID can only contain letters, numbers, hyphens, and slashes.",
            ),
        ],
    )

    institution = StringField(
        "Institution / School Name",
        validators=[
            DataRequired(message="Institution name is required."),
            Length(min=3, max=200),
        ],
    )

    department = StringField(
        "Department / Faculty",
        validators=[
            Optional(),
            Length(max=100),
        ],
    )

    phone = StringField(
        "Phone Number",
        validators=[
            Optional(),
            # Nigerian phone numbers: 080xxxxxxxx or +2348xxxxxxxx
            Regexp(
                r"^(\+234|0)[789][01]\d{8}$",
                message="Enter a valid Nigerian phone number (e.g. 08012345678).",
            ),
        ],
    )

    preferred_language = SelectField(
        "Preferred Language",
        choices=[
            ("en", "English"),
            ("ha", "Hausa"),
            ("yo", "Yoruba"),
            ("ig", "Igbo"),
        ],
        default="en",
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
            Length(
                min=8, max=128,
                message="Password must be at least 8 characters.",
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            # EqualTo checks that this field matches 'password' field
            EqualTo("password", message="Passwords do not match."),
        ],
    )

    agree_terms = BooleanField(
        "I agree to the Terms of Service and Academic Integrity Policy",
        validators=[
            DataRequired(message="You must agree to the terms to register."),
        ],
    )

    submit = SubmitField("Create Account")

    # ── Custom validators ──────────────────────────────
    # WTForms calls any method named validate_<fieldname> automatically

    def validate_email(self, email):
        """Ensure the email is not already registered."""
        user = User.query.filter_by(email=email.data.lower().strip()).first()
        if user:
            raise ValidationError(
                "This email is already registered. Please log in instead."
            )

    def validate_student_id(self, student_id):
        """Ensure the student ID is not already taken."""
        user = User.query.filter_by(
            student_id=student_id.data.upper().strip()
        ).first()
        if user:
            raise ValidationError(
                "This Student ID is already registered. Contact admin if this is an error."
            )

    def validate_password(self, password):
        """
        Enforce a strong password policy:
        - At least 1 uppercase letter
        - At least 1 lowercase letter
        - At least 1 digit
        """
        pw = password.data
        if not any(c.isupper() for c in pw):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in pw):
            raise ValidationError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in pw):
            raise ValidationError("Password must contain at least one number.")


# ─────────────────────────────────────────────
# LOGIN FORM
# ─────────────────────────────────────────────

class LoginForm(FlaskForm):
    """
    Login form for students AND admins.
    Intentionally minimal — we don't reveal WHICH field is wrong
    (never say "email not found" → tells attacker valid emails).
    """

    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Enter a valid email address."),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
        ],
    )

    remember_me = BooleanField("Keep me signed in for 2 hours")

    submit = SubmitField("Sign In")


# ─────────────────────────────────────────────
# PASSWORD CHANGE FORM (for logged-in users)
# ─────────────────────────────────────────────

class ChangePasswordForm(FlaskForm):
    """Allows a logged-in user to change their own password."""

    current_password = PasswordField(
        "Current Password",
        validators=[DataRequired()],
    )

    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=8, max=128),
        ],
    )

    confirm_new_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="New passwords do not match."),
        ],
    )

    submit = SubmitField("Change Password")

    def validate_new_password(self, new_password):
        pw = new_password.data
        if not any(c.isupper() for c in pw):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in pw):
            raise ValidationError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in pw):
            raise ValidationError("Password must contain at least one number.")


# ─────────────────────────────────────────────
# PROFILE UPDATE FORM
# ─────────────────────────────────────────────

class ProfileUpdateForm(FlaskForm):
    """Lets students update non-critical profile information."""

    full_name = StringField(
        "Full Name",
        validators=[
            DataRequired(),
            Length(min=2, max=100),
            Regexp(r"^[A-Za-z\s\-']+$", message="Letters and spaces only."),
        ],
    )

    institution = StringField(
        "Institution",
        validators=[Optional(), Length(max=200)],
    )

    department = StringField(
        "Department",
        validators=[Optional(), Length(max=100)],
    )

    phone = StringField(
        "Phone Number",
        validators=[
            Optional(),
            Regexp(
                r"^(\+234|0)[789][01]\d{8}$",
                message="Enter a valid Nigerian phone number.",
            ),
        ],
    )

    preferred_language = SelectField(
        "Preferred Language",
        choices=[("en", "English"), ("ha", "Hausa"), ("yo", "Yoruba"), ("ig", "Igbo")],
    )

    submit = SubmitField("Save Changes")


# ─────────────────────────────────────────────
# ADMIN: EXAM CREATION / EDIT FORM
# ─────────────────────────────────────────────

class ExamForm(FlaskForm):
    """
    Admin form for creating or editing an exam SHELL.
    Questions are added separately via QuestionForm after the
    exam shell exists (see ExamForm docstring in concept notes above).
    """

    title = StringField(
        "Exam Title",
        validators=[
            DataRequired(message="Exam title is required."),
            Length(min=3, max=200, message="Title must be 3–200 characters."),
        ],
    )

    description = TextAreaField(
        "Description / Instructions",
        validators=[Optional(), Length(max=2000)],
    )

    subject = StringField(
        "Subject",
        validators=[
            DataRequired(message="Subject is required."),
            Length(min=2, max=100),
        ],
    )

    duration_minutes = IntegerField(
        "Duration (minutes)",
        validators=[
            DataRequired(message="Duration is required."),
            NumberRange(min=1, max=480, message="Duration must be 1–480 minutes."),
        ],
    )

    pass_mark = IntegerField(
        "Pass Mark (%)",
        validators=[
            DataRequired(message="Pass mark is required."),
            NumberRange(min=0, max=100, message="Pass mark must be 0–100."),
        ],
    )

    # Anti-cheat configuration
    webcam_required = BooleanField("Require Webcam Monitoring", default=True)
    shuffle_questions = BooleanField("Shuffle Question Order", default=True)
    shuffle_options = BooleanField("Shuffle Answer Options", default=True)

    max_tab_switches = IntegerField(
        "Max Tab Switches Before Auto-Submit",
        validators=[
            DataRequired(),
            NumberRange(min=0, max=20, message="Must be 0–20."),
        ],
        default=3,
    )

    target_institution = StringField(
        "Target Institution (optional)",
        validators=[Optional(), Length(max=200)],
    )

    target_department = StringField(
        "Target Department (optional)",
        validators=[Optional(), Length(max=100)],
    )

    submit = SubmitField("Save Exam")


# ─────────────────────────────────────────────
# ADMIN: QUESTION CREATION FORM
# ─────────────────────────────────────────────

class QuestionForm(FlaskForm):
    """
    Admin form for adding ONE multiple-choice question to an exam.
    Submitted repeatedly — once per question — via the exam edit page.
    """

    text = TextAreaField(
        "Question Text",
        validators=[
            DataRequired(message="Question text is required."),
            Length(min=5, max=2000, message="Question must be 5–2000 characters."),
        ],
    )

    option_a = StringField(
        "Option A",
        validators=[DataRequired(message="Option A is required."), Length(max=500)],
    )
    option_b = StringField(
        "Option B",
        validators=[DataRequired(message="Option B is required."), Length(max=500)],
    )
    option_c = StringField(
        "Option C",
        validators=[DataRequired(message="Option C is required."), Length(max=500)],
    )
    option_d = StringField(
        "Option D",
        validators=[DataRequired(message="Option D is required."), Length(max=500)],
    )

    correct_answer = SelectField(
        "Correct Answer",
        choices=[("A", "Option A"), ("B", "Option B"), ("C", "Option C"), ("D", "Option D")],
        validators=[DataRequired()],
    )

    marks = IntegerField(
        "Marks",
        validators=[
            DataRequired(message="Marks value is required."),
            NumberRange(min=1, max=20, message="Marks must be 1–20."),
        ],
        default=1,
    )

    explanation = TextAreaField(
        "Explanation (shown to student after exam)",
        validators=[Optional(), Length(max=1000)],
    )

    submit = SubmitField("Add Question")
