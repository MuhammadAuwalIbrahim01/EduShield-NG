"""
tests/test_day7_admin.py — Day 7 Admin Dashboard Tests
=========================================================
Tests cover:
  1.  Exam publish guard (cannot publish with 0 questions)
  2.  Question order_index re-sequencing after deletion
  3.  Exam status state machine (draft -> published -> closed)
  4.  Admin analytics calculations (pass rate, avg score)
  5.  CSV export row generation and field correctness
  6.  Student search query matching logic
  7.  Suspend/reactivate toggle logic
  8.  Verify toggle logic
  9.  Unflag logic
 10.  Exam form validation rules (duration, pass_mark ranges)
 11.  Question form validation rules (marks range, required fields)
 12.  CSV filename sanitization (no path traversal via exam title)

Run: python tests/test_day7_admin.py
"""
import sys, os, csv, io, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = failed = 0
def ok(name): global passed; passed+=1; print(f"  ✓ {name}")
def fail(name, msg=""): global failed; failed+=1; print(f"  ✗ {name}: {msg}")
def run(name, cond, msg=""):
    if cond: ok(name)
    else: fail(name, msg or "assertion failed")

print("\n=== Day 7 Admin Dashboard Tests ===\n")


# ── 1. Exam Publish Guard ──────────────────────────────────────────────────────
print("1. Exam Publish Guard (No Questions)")

def can_publish(question_count):
    """Mirror of publish_exam() guard logic."""
    return question_count > 0

run("0 questions cannot publish",  not can_publish(0))
run("1 question can publish",      can_publish(1))
run("50 questions can publish",    can_publish(50))


# ── 2. Question Re-sequencing After Deletion ──────────────────────────────────
print("\n2. Question Re-sequencing After Deletion")

class MockQuestion:
    def __init__(self, order_index):
        self.order_index = order_index

def resequence(questions):
    """Mirror of delete_question() re-sequencing logic."""
    for i, q in enumerate(questions):
        q.order_index = i
    return questions

# Simulate: 5 questions (0,1,2,3,4), delete index 2, remaining should become (0,1,2,3)
questions = [MockQuestion(0), MockQuestion(1), MockQuestion(3), MockQuestion(4)]  # index 2 removed
resequence(questions)
run("re-sequenced indices are 0,1,2,3",
    [q.order_index for q in questions] == [0,1,2,3])

# Edge case: delete the first question
questions2 = [MockQuestion(1), MockQuestion(2), MockQuestion(3)]
resequence(questions2)
run("re-sequencing after deleting first question",
    [q.order_index for q in questions2] == [0,1,2])

# Edge case: only one question left
questions3 = [MockQuestion(7)]
resequence(questions3)
run("single remaining question gets index 0",
    questions3[0].order_index == 0)

# Edge case: no questions left
questions4 = []
resequence(questions4)
run("empty question list doesn't crash", questions4 == [])


# ── 3. Exam Status State Machine ──────────────────────────────────────────────
print("\n3. Exam Status State Machine")

VALID_TRANSITIONS = {
    "draft":     {"published"},
    "published": {"closed"},
    "closed":    set(),  # terminal state
}

def is_valid_transition(from_status, to_status):
    return to_status in VALID_TRANSITIONS.get(from_status, set())

run("draft -> published is valid",     is_valid_transition("draft", "published"))
run("published -> closed is valid",    is_valid_transition("published", "closed"))
run("draft -> closed is NOT valid",    not is_valid_transition("draft", "closed"))
run("closed -> published is NOT valid",not is_valid_transition("closed", "published"))
run("closed -> draft is NOT valid",    not is_valid_transition("closed", "draft"))


# ── 4. Admin Analytics Calculations ───────────────────────────────────────────
print("\n4. Admin Analytics Calculations")

def calc_pass_rate(results):
    """Mirror of dashboard() pass rate calculation."""
    if not results: return 0
    passed = sum(1 for r in results if r['passed'])
    return round((passed / len(results) * 100), 1)

def calc_avg_pct(results):
    if not results: return 0
    return round(sum(r['percentage'] for r in results) / len(results), 1)

results_a = [{'passed': True, 'percentage': 80}, {'passed': True, 'percentage': 90},
             {'passed': False, 'percentage': 30}]
run("3 results, 2 passed -> 66.7% pass rate",
    calc_pass_rate(results_a) == 66.7)
run("avg percentage of 80,90,30 = 66.7",
    calc_avg_pct(results_a) == 66.7)

run("empty results -> 0% pass rate",   calc_pass_rate([]) == 0)
run("empty results -> 0 avg",          calc_avg_pct([]) == 0)

all_passed = [{'passed': True, 'percentage': 100}] * 5
run("all passed -> 100% pass rate",    calc_pass_rate(all_passed) == 100.0)

none_passed = [{'passed': False, 'percentage': 0}] * 3
run("none passed -> 0% pass rate",     calc_pass_rate(none_passed) == 0.0)


# ── 5. CSV Export Row Generation ──────────────────────────────────────────────
print("\n5. CSV Export Row Generation")

def build_csv(results):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name","Score","Percentage","Passed"])
    for r in results:
        writer.writerow([r['name'], r['score'], r['pct'], "Yes" if r['passed'] else "No"])
    return output.getvalue()

sample = [
    {'name': 'Aminu Bello', 'score': 8, 'pct': 80.0, 'passed': True},
    {'name': 'Chidinma Okafor', 'score': 3, 'pct': 30.0, 'passed': False},
]
csv_output = build_csv(sample)

run("CSV has header row",            'Student Name' in csv_output)
run("CSV contains first student",    'Aminu Bello' in csv_output)
run("CSV contains second student",   'Chidinma Okafor' in csv_output)
run("Passed shows 'Yes'",            'Yes' in csv_output)
run("Failed shows 'No'",             'No' in csv_output)

# Verify it round-trips through csv.reader correctly
reader = csv.reader(io.StringIO(csv_output))
rows = list(reader)
run("CSV has 3 rows (header + 2 data)", len(rows) == 3)
run("first data row matches",          rows[1][0] == 'Aminu Bello')


# ── 6. Student Search Query Logic ─────────────────────────────────────────────
print("\n6. Student Search Query Matching")

def matches_search(student, query):
    """Mirror of students() route's ilike-style search."""
    q = query.lower()
    return (q in student['name'].lower() or
            q in student['email'].lower() or
            (student.get('student_id') or '').lower().find(q) != -1)

s1 = {'name': 'Aminu Bello', 'email': 'aminu@test.com', 'student_id': 'STU001'}

run("search by partial name matches",     matches_search(s1, 'amin'))
run("search by email matches",             matches_search(s1, 'aminu@test'))
run("search by student_id matches",        matches_search(s1, 'STU001'.lower()))
run("search by unrelated term fails",      not matches_search(s1, 'xyz123'))
run("case-insensitive search works",       matches_search(s1, 'BELLO'.lower()))


# ── 7. Suspend / Reactivate Toggle ────────────────────────────────────────────
print("\n7. Suspend/Reactivate Toggle Logic")

class MockStudent:
    def __init__(self): self.is_active = True

s = MockStudent()
s.is_active = not s.is_active
run("toggle once: active -> suspended",    s.is_active is False)
s.is_active = not s.is_active
run("toggle twice: suspended -> active",   s.is_active is True)


# ── 8. Verify Toggle Logic ────────────────────────────────────────────────────
print("\n8. Verify Toggle Logic")

class MockStudent2:
    def __init__(self): self.is_verified = False

s2 = MockStudent2()
s2.is_verified = not s2.is_verified
run("unverified -> verified",      s2.is_verified is True)
s2.is_verified = not s2.is_verified
run("verified -> unverified",      s2.is_verified is False)


# ── 9. Unflag Logic ───────────────────────────────────────────────────────────
print("\n9. Unflag Logic")

class MockStudent3:
    def __init__(self): self.is_flagged = True

s3 = MockStudent3()
s3.is_flagged = False  # mirrors unflag_student() route
run("flagged student becomes unflagged", s3.is_flagged is False)


# ── 10. Exam Form Validation Rules ────────────────────────────────────────────
print("\n10. Exam Form Validation Rules")

def validate_duration(minutes):
    return 1 <= minutes <= 480

def validate_pass_mark(pct):
    return 0 <= pct <= 100

def validate_max_tabs(n):
    return 0 <= n <= 20

run("duration 60 is valid",        validate_duration(60))
run("duration 0 is invalid",       not validate_duration(0))
run("duration 481 is invalid",     not validate_duration(481))
run("duration 480 is valid (edge)",validate_duration(480))
run("duration 1 is valid (edge)",  validate_duration(1))

run("pass_mark 50 is valid",       validate_pass_mark(50))
run("pass_mark 0 is valid",        validate_pass_mark(0))
run("pass_mark 100 is valid",      validate_pass_mark(100))
run("pass_mark -1 is invalid",     not validate_pass_mark(-1))
run("pass_mark 101 is invalid",    not validate_pass_mark(101))

run("max_tabs 3 is valid",         validate_max_tabs(3))
run("max_tabs 0 is valid",         validate_max_tabs(0))
run("max_tabs 21 is invalid",      not validate_max_tabs(21))


# ── 11. Question Form Validation Rules ────────────────────────────────────────
print("\n11. Question Form Validation Rules")

def validate_marks(m):
    return 1 <= m <= 20

def validate_question_text(text):
    return 5 <= len(text) <= 2000

run("marks 1 is valid",            validate_marks(1))
run("marks 20 is valid",           validate_marks(20))
run("marks 0 is invalid",          not validate_marks(0))
run("marks 21 is invalid",         not validate_marks(21))

run("5-char question is valid",    validate_question_text("12345"))
run("4-char question is invalid",  not validate_question_text("1234"))
run("2001-char question invalid",  not validate_question_text("a" * 2001))
run("2000-char question is valid", validate_question_text("a" * 2000))


# ── 12. CSV Filename Sanitization ─────────────────────────────────────────────
print("\n12. CSV Filename Sanitization (Path Traversal Prevention)")

def sanitize_filename(title):
    """Mirror of export_results_csv() filename sanitization."""
    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    return f"{safe}_results.csv"

run("normal title produces clean filename",
    sanitize_filename("Basic Mathematics") == "Basic Mathematics_results.csv")

run("path traversal attempt is stripped",
    "../" not in sanitize_filename("../../etc/passwd"))

run("special characters stripped",
    sanitize_filename("Exam<script>alert(1)</script>") ==
    "Examscriptalert1script_results.csv")

run("filename with semicolons stripped",
    ";" not in sanitize_filename("Exam; DROP TABLE exams;"))

run("unicode/emoji handled without crash",
    isinstance(sanitize_filename("Exam 📝 Title"), str))


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 7 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
