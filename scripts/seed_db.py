"""
scripts/seed_db.py — Populate the database with sample data
=============================================================
Run this ONCE after setting up the project to create:
  - 1 admin account
  - 3 student accounts
  - 2 sample exams with questions

Usage:
    python scripts/seed_db.py

This script is safe to run multiple times — it checks if data
already exists before inserting.
"""

import sys
import os

# Add project root to Python path so we can import backend modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.models.models import db, User, Exam, Question


def seed_users(app):
    """Create sample admin and student accounts."""
    print("Seeding users...")

    users_data = [
        {
            "full_name": "EduShield Admin",
            "email": "admin@edushield.ng",
            "password": "Admin123!",
            "role": "admin",
            "is_verified": True,
        },
        {
            "full_name": "Aminu Bello",
            "email": "aminu.bello@student.ng",
            "password": "Student123!",
            "role": "student",
            "student_id": "STU001",
            "institution": "University of Lagos",
            "department": "Computer Science",
            "phone": "08012345678",
            "preferred_language": "ha",
            "is_verified": True,
        },
        {
            "full_name": "Chidinma Okafor",
            "email": "chidinma@student.ng",
            "password": "Student123!",
            "role": "student",
            "student_id": "STU002",
            "institution": "University of Lagos",
            "department": "Mathematics",
            "phone": "08023456789",
            "preferred_language": "ig",
            "is_verified": True,
        },
        {
            "full_name": "Taiwo Adeleke",
            "email": "taiwo@student.ng",
            "password": "Student123!",
            "role": "student",
            "student_id": "STU003",
            "institution": "University of Ibadan",
            "department": "Physics",
            "phone": "08034567890",
            "preferred_language": "yo",
            "is_verified": True,
        },
    ]

    with app.app_context():
        for data in users_data:
            if User.query.filter_by(email=data["email"]).first():
                print(f"  Skipping {data['email']} (already exists)")
                continue

            user = User(
                full_name=data["full_name"],
                email=data["email"],
                role=data["role"],
                student_id=data.get("student_id"),
                institution=data.get("institution"),
                department=data.get("department"),
                phone=data.get("phone"),
                preferred_language=data.get("preferred_language", "en"),
                is_verified=data.get("is_verified", False),
                is_active=True,
            )
            user.set_password(data["password"])
            db.session.add(user)
            print(f"  Created: {data['email']} [{data['role']}]")

        db.session.commit()
    print("Users seeded.\n")


def seed_exams(app):
    """Create sample exams with questions."""
    print("Seeding exams...")

    with app.app_context():
        admin = User.query.filter_by(role="admin").first()
        if not admin:
            print("  ERROR: No admin found. Run seed_users first.")
            return

        # --- Exam 1: Mathematics ---
        if not Exam.query.filter_by(title="Basic Mathematics").first():
            exam1 = Exam(
                title="Basic Mathematics",
                description="Test your knowledge of basic mathematics concepts.",
                subject="Mathematics",
                duration_minutes=30,
                pass_mark=50,
                status="published",
                created_by=admin.id,
                shuffle_questions=True,
                shuffle_options=True,
                webcam_required=True,
                max_tab_switches=3,
            )
            db.session.add(exam1)
            db.session.flush()  # Get exam1.id without full commit

            questions_math = [
                {
                    "text": "What is the value of 15 × 8?",
                    "option_a": "100",
                    "option_b": "110",
                    "option_c": "120",
                    "option_d": "130",
                    "correct_answer": "C",
                    "marks": 2,
                    "explanation": "15 × 8 = 120. You can calculate this as (10 × 8) + (5 × 8) = 80 + 40 = 120.",
                },
                {
                    "text": "Solve for x: 3x + 9 = 24",
                    "option_a": "3",
                    "option_b": "5",
                    "option_c": "7",
                    "option_d": "11",
                    "correct_answer": "B",
                    "marks": 2,
                    "explanation": "3x = 24 - 9 = 15, so x = 15 ÷ 3 = 5.",
                },
                {
                    "text": "What is 25% of 200?",
                    "option_a": "25",
                    "option_b": "40",
                    "option_c": "50",
                    "option_d": "75",
                    "correct_answer": "C",
                    "marks": 1,
                    "explanation": "25% = 25/100 = 1/4. So 1/4 × 200 = 50.",
                },
                {
                    "text": "Which of the following is a prime number?",
                    "option_a": "9",
                    "option_b": "15",
                    "option_c": "21",
                    "option_d": "29",
                    "correct_answer": "D",
                    "marks": 1,
                    "explanation": "29 is only divisible by 1 and 29, making it prime.",
                },
                {
                    "text": "What is the area of a rectangle with length 12cm and width 5cm?",
                    "option_a": "34 cm²",
                    "option_b": "60 cm²",
                    "option_c": "17 cm²",
                    "option_d": "70 cm²",
                    "correct_answer": "B",
                    "marks": 2,
                    "explanation": "Area = length × width = 12 × 5 = 60 cm².",
                },
            ]

            for i, q_data in enumerate(questions_math):
                q = Question(
                    exam_id=exam1.id,
                    text=q_data["text"],
                    option_a=q_data["option_a"],
                    option_b=q_data["option_b"],
                    option_c=q_data["option_c"],
                    option_d=q_data["option_d"],
                    correct_answer=q_data["correct_answer"],
                    marks=q_data["marks"],
                    explanation=q_data["explanation"],
                    order_index=i,
                )
                db.session.add(q)

            print("  Created exam: Basic Mathematics (5 questions)")

        # --- Exam 2: English Language ---
        if not Exam.query.filter_by(title="English Language Comprehension").first():
            exam2 = Exam(
                title="English Language Comprehension",
                description="Test your understanding of English grammar and comprehension.",
                subject="English Language",
                duration_minutes=45,
                pass_mark=60,
                status="published",
                created_by=admin.id,
                shuffle_questions=True,
                shuffle_options=False,
                webcam_required=True,
                max_tab_switches=3,
            )
            db.session.add(exam2)
            db.session.flush()

            questions_english = [
                {
                    "text": "Choose the correct form: 'She ___ to school every day.'",
                    "option_a": "go",
                    "option_b": "goes",
                    "option_c": "going",
                    "option_d": "gone",
                    "correct_answer": "B",
                    "marks": 1,
                    "explanation": "Third-person singular present tense uses 'goes'.",
                },
                {
                    "text": "What is the synonym of 'Benevolent'?",
                    "option_a": "Cruel",
                    "option_b": "Strict",
                    "option_c": "Kind",
                    "option_d": "Lazy",
                    "correct_answer": "C",
                    "marks": 1,
                    "explanation": "Benevolent means well-meaning and kind.",
                },
                {
                    "text": "Identify the noun in: 'The quick brown fox jumps.'",
                    "option_a": "quick",
                    "option_b": "brown",
                    "option_c": "fox",
                    "option_d": "jumps",
                    "correct_answer": "C",
                    "marks": 1,
                    "explanation": "'Fox' is the noun — a naming word for an animal.",
                },
                {
                    "text": "Which sentence is grammatically correct?",
                    "option_a": "He don't like mangoes.",
                    "option_b": "He doesn't likes mangoes.",
                    "option_c": "He doesn't like mangoes.",
                    "option_d": "He not like mangoes.",
                    "correct_answer": "C",
                    "marks": 2,
                    "explanation": "Third-person singular negative uses 'doesn't' + base verb.",
                },
            ]

            for i, q_data in enumerate(questions_english):
                q = Question(
                    exam_id=exam2.id,
                    text=q_data["text"],
                    option_a=q_data["option_a"],
                    option_b=q_data["option_b"],
                    option_c=q_data["option_c"],
                    option_d=q_data["option_d"],
                    correct_answer=q_data["correct_answer"],
                    marks=q_data["marks"],
                    explanation=q_data["explanation"],
                    order_index=i,
                )
                db.session.add(q)

            print("  Created exam: English Language Comprehension (4 questions)")

        db.session.commit()
    print("Exams seeded.\n")


if __name__ == "__main__":
    print("=" * 50)
    print("EduShield NG — Database Seeder")
    print("=" * 50)
    app = create_app("development")
    seed_users(app)
    seed_exams(app)
    print("Database seeding complete!")
    print("\nTest credentials:")
    print("  Admin:   admin@edushield.ng / Admin123!")
    print("  Student: aminu.bello@student.ng / Student123!")
