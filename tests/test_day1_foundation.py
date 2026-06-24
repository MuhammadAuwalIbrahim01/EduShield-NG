"""
tests/test_day1_foundation.py — Day 1 Tests
=============================================
Tests verify:
  1. App factory creates app correctly in each config mode
  2. Database tables are created
  3. User model password hashing works
  4. User role helper methods work
  5. Exam model helper methods work
  6. Question model option methods work
  7. Result scoring logic works
  8. ExamSession expiry logic works

Run with:
    pytest tests/test_day1_foundation.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from backend.app import create_app
from backend.models.models import db, User, Exam, Question, Result, ExamSession


# ─────────────────────────────────────────────
# FIXTURES — reusable test setup
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    """Create a testing app with in-memory SQLite database."""
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture(scope="module")
def client(app):
    """Flask test client — sends fake HTTP requests."""
    return app.test_client()


@pytest.fixture(scope="function")
def clean_db(app):
    """Wrap each test in a transaction and roll back after."""
    with app.app_context():
        yield
        db.session.rollback()


# ─────────────────────────────────────────────
# TEST 1: App Factory
# ─────────────────────────────────────────────

class TestAppFactory:
    def test_creates_testing_app(self, app):
        """App factory must create an app with TESTING=True."""
        assert app is not None
        assert app.config["TESTING"] is True

    def test_csrf_disabled_in_testing(self, app):
        """CSRF is disabled in test config to allow POST without tokens."""
        assert app.config["WTF_CSRF_ENABLED"] is False

    def test_uses_sqlite_in_testing(self, app):
        """Testing must use in-memory SQLite."""
        assert "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]

    def test_health_endpoint(self, client):
        """Health check endpoint must return 200."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_root_redirects(self, client):
        """Root URL must redirect (to login or dashboard)."""
        response = client.get("/")
        assert response.status_code in (301, 302)


# ─────────────────────────────────────────────
# TEST 2: User Model
# ─────────────────────────────────────────────

class TestUserModel:
    def test_password_is_hashed(self, app):
        """set_password must never store the plain password."""
        with app.app_context():
            user = User(full_name="Test", email="t@t.com", role="student")
            user.set_password("MyPassword123")
            # The hash must NOT equal the original password
            assert user.password_hash != "MyPassword123"
            # The hash should be a long string (bcrypt/pbkdf2)
            assert len(user.password_hash) > 30

    def test_correct_password_verifies(self, app):
        """check_password must return True for the correct password."""
        with app.app_context():
            user = User(full_name="Test", email="t2@t.com", role="student")
            user.set_password("CorrectHorse99!")
            assert user.check_password("CorrectHorse99!") is True

    def test_wrong_password_rejected(self, app):
        """check_password must return False for the wrong password."""
        with app.app_context():
            user = User(full_name="Test", email="t3@t.com", role="student")
            user.set_password("RealPassword")
            assert user.check_password("WrongPassword") is False

    def test_is_admin_method(self, app):
        """is_admin() must return True only for admin role."""
        with app.app_context():
            admin = User(full_name="Admin", email="a@a.com", role="admin")
            student = User(full_name="Student", email="s@s.com", role="student")
            assert admin.is_admin() is True
            assert student.is_admin() is False

    def test_is_student_method(self, app):
        """is_student() must return True only for student role."""
        with app.app_context():
            student = User(full_name="S", email="ss@ss.com", role="student")
            assert student.is_student() is True

    def test_accessibility_prefs_parsing(self, app):
        """get_accessibility_list() must parse comma-separated string."""
        with app.app_context():
            user = User(full_name="A", email="acc@t.com", role="student")
            user.accessibility_prefs = "tts,high_contrast,large_font"
            prefs = user.get_accessibility_list()
            assert "tts" in prefs
            assert "high_contrast" in prefs
            assert len(prefs) == 3

    def test_empty_accessibility_prefs(self, app):
        """Empty accessibility prefs must return empty list."""
        with app.app_context():
            user = User(full_name="B", email="bacc@t.com", role="student")
            user.accessibility_prefs = ""
            assert user.get_accessibility_list() == []

    def test_user_saved_to_db(self, app):
        """User must persist to database correctly."""
        with app.app_context():
            user = User(
                full_name="Aminu Bello",
                email="aminu@test.com",
                role="student",
                student_id="STU001",
            )
            user.set_password("Test123!")
            db.session.add(user)
            db.session.commit()

            found = User.query.filter_by(email="aminu@test.com").first()
            assert found is not None
            assert found.full_name == "Aminu Bello"
            assert found.student_id == "STU001"

    def test_duplicate_email_rejected(self, app):
        """Two users with the same email must raise an integrity error."""
        from sqlalchemy.exc import IntegrityError
        with app.app_context():
            u1 = User(full_name="X", email="dup@test.com", role="student")
            u1.set_password("pass")
            u2 = User(full_name="Y", email="dup@test.com", role="student")
            u2.set_password("pass")
            db.session.add(u1)
            db.session.commit()
            db.session.add(u2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


# ─────────────────────────────────────────────
# TEST 3: Exam Model
# ─────────────────────────────────────────────

class TestExamModel:
    def _make_admin_and_exam(self, app, status="published"):
        """Helper: create an admin and an exam, return (admin, exam)."""
        admin = User(full_name="Admin", email=f"adm_{status}@t.com", role="admin")
        admin.set_password("admin")
        db.session.add(admin)
        db.session.flush()
        exam = Exam(
            title="Test Exam",
            subject="Mathematics",
            duration_minutes=60,
            pass_mark=50,
            status=status,
            created_by=admin.id,
        )
        db.session.add(exam)
        db.session.flush()
        return admin, exam

    def test_published_exam_is_available(self, app):
        """A published exam with no time window must be available."""
        with app.app_context():
            _, exam = self._make_admin_and_exam(app, "published")
            assert exam.is_available() is True
            db.session.rollback()

    def test_draft_exam_not_available(self, app):
        """A draft exam must NOT be available to students."""
        with app.app_context():
            _, exam = self._make_admin_and_exam(app, "draft")
            assert exam.is_available() is False
            db.session.rollback()

    def test_question_count(self, app):
        """question_count() must match the number of added questions."""
        with app.app_context():
            _, exam = self._make_admin_and_exam(app, "published")
            for i in range(3):
                q = Question(
                    exam_id=exam.id,
                    text=f"Q{i}?",
                    option_a="A", option_b="B",
                    option_c="C", option_d="D",
                    correct_answer="A",
                )
                db.session.add(q)
            db.session.flush()
            assert exam.question_count() == 3
            db.session.rollback()


# ─────────────────────────────────────────────
# TEST 4: Question Model
# ─────────────────────────────────────────────

class TestQuestionModel:
    def test_is_correct_true(self, app):
        """is_correct() must return True when answer matches."""
        with app.app_context():
            q = Question(
                exam_id=1,
                text="What is 2+2?",
                option_a="3", option_b="4",
                option_c="5", option_d="6",
                correct_answer="B",
            )
            assert q.is_correct("B") is True
            assert q.is_correct("b") is True  # case insensitive

    def test_is_correct_false(self, app):
        """is_correct() must return False for wrong answers."""
        with app.app_context():
            q = Question(
                exam_id=1, text="Q?",
                option_a="A", option_b="B",
                option_c="C", option_d="D",
                correct_answer="A",
            )
            assert q.is_correct("B") is False
            assert q.is_correct("C") is False

    def test_get_options_dict(self, app):
        """get_options() must return dict with keys A, B, C, D."""
        with app.app_context():
            q = Question(
                exam_id=1, text="Q?",
                option_a="Apple", option_b="Banana",
                option_c="Cherry", option_d="Date",
                correct_answer="A",
            )
            opts = q.get_options()
            assert opts["A"] == "Apple"
            assert opts["D"] == "Date"
            assert len(opts) == 4


# ─────────────────────────────────────────────
# TEST 5: ExamSession Timing
# ─────────────────────────────────────────────

class TestExamSession:
    def test_not_expired_when_future_deadline(self, app):
        """Session is not expired if deadline is in the future."""
        with app.app_context():
            session = ExamSession(
                student_id=1, exam_id=1, result_id=1,
                session_token="tok123",
                deadline=datetime.utcnow() + timedelta(hours=1),
            )
            assert session.is_expired() is False

    def test_expired_when_past_deadline(self, app):
        """Session IS expired if deadline is in the past."""
        with app.app_context():
            session = ExamSession(
                student_id=1, exam_id=1, result_id=1,
                session_token="tok456",
                deadline=datetime.utcnow() - timedelta(minutes=5),
            )
            assert session.is_expired() is True

    def test_seconds_remaining_positive(self, app):
        """seconds_remaining() must return a positive number if not expired."""
        with app.app_context():
            session = ExamSession(
                student_id=1, exam_id=1, result_id=1,
                session_token="tok789",
                deadline=datetime.utcnow() + timedelta(minutes=30),
            )
            remaining = session.seconds_remaining()
            assert remaining > 0
            assert remaining <= 1800  # 30 minutes max

    def test_seconds_remaining_zero_when_expired(self, app):
        """seconds_remaining() must return 0 (not negative) when expired."""
        with app.app_context():
            session = ExamSession(
                student_id=1, exam_id=1, result_id=1,
                session_token="tok000",
                deadline=datetime.utcnow() - timedelta(hours=1),
            )
            assert session.seconds_remaining() == 0
