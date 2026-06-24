"""
tests/test_day3_exam_engine.py — Day 3 Exam Engine Tests
==========================================================
Tests cover:
  1. ExamSession timer logic (server-side deadline)
  2. Score calculation correctness
  3. Answer JSON merge logic
  4. Shuffling produces valid orderings
  5. Auto-submit conditions
  6. Cheat log event type validation
  7. Exam availability checks
  8. Question correct-answer verification
  9. Result percentage calculation
 10. Token uniqueness for exam sessions

Run standalone: python tests/test_day3_exam_engine.py
"""

import sys, os, json, secrets, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = failed = 0

def ok(name):
    global passed; passed += 1
    print(f"  ✓ {name}")

def fail(name, msg=""):
    global failed; failed += 1
    print(f"  ✗ {name}: {msg}")

def run(name, condition, msg=""):
    if condition: ok(name)
    else: fail(name, msg or "assertion failed")


print("\n=== Day 3 Exam Engine Tests ===\n")


# ── 1. Server-Side Timer Logic ─────────────────────────────────────────────────
print("1. Server-Side Timer Logic")

class MockSession:
    def __init__(self, deadline):
        self.deadline = deadline
    def is_expired(self):
        return datetime.utcnow() > self.deadline
    def seconds_remaining(self):
        delta = self.deadline - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

future = MockSession(datetime.utcnow() + timedelta(hours=1))
past   = MockSession(datetime.utcnow() - timedelta(minutes=5))
exact  = MockSession(datetime.utcnow() - timedelta(seconds=1))

run("future session not expired",          not future.is_expired())
run("past session is expired",             past.is_expired())
run("just-expired session is expired",     exact.is_expired())
run("future session has positive time",    future.seconds_remaining() > 0)
run("past session returns 0 not negative", past.seconds_remaining() == 0)
run("60-min session has ~3600s",           3590 <= future.seconds_remaining() <= 3601)


# ── 2. Score Calculation ───────────────────────────────────────────────────────
print("\n2. Score Calculation")

def calculate_score(answers_json, questions, pass_mark):
    """Mirror of Result.calculate_score()"""
    answers = json.loads(answers_json)
    score = 0; total = 0
    for q in questions:
        total += q['marks']
        given = answers.get(str(q['id']))
        if given and given.upper() == q['correct'].upper():
            score += q['marks']
    total_marks = total
    percentage = round((score / total * 100), 2) if total > 0 else 0.0
    passed_exam = percentage >= pass_mark
    return score, total_marks, percentage, passed_exam

questions = [
    {'id': 1, 'correct': 'A', 'marks': 2},
    {'id': 2, 'correct': 'C', 'marks': 1},
    {'id': 3, 'correct': 'B', 'marks': 2},
    {'id': 4, 'correct': 'D', 'marks': 1},
]

# All correct
answers_all_correct = json.dumps({'1':'A','2':'C','3':'B','4':'D'})
s, t, p, passed_exam = calculate_score(answers_all_correct, questions, 50)
run("all correct: score=6", s == 6)
run("all correct: total=6", t == 6)
run("all correct: pct=100%", p == 100.0)
run("all correct: passed=True", passed_exam is True)

# All wrong
answers_all_wrong = json.dumps({'1':'B','2':'A','3':'C','4':'B'})
s, t, p, passed_exam = calculate_score(answers_all_wrong, questions, 50)
run("all wrong: score=0", s == 0)
run("all wrong: pct=0%", p == 0.0)
run("all wrong: passed=False", passed_exam is False)

# Partial — 3 out of 6 marks (50%)
answers_partial = json.dumps({'1':'A','2':'C','3':'C','4':'B'})  # Q1+Q2 correct
s, t, p, passed_exam = calculate_score(answers_partial, questions, 50)
run("partial: score=3", s == 3)
run("partial: pct=50%", p == 50.0)
run("partial: exactly 50% passes", passed_exam is True)

# No answers given
answers_none = json.dumps({})
s, t, p, passed_exam = calculate_score(answers_none, questions, 50)
run("no answers: score=0", s == 0)
run("no answers: passed=False", passed_exam is False)

# Case-insensitive matching
answers_lower = json.dumps({'1':'a','2':'c','3':'b','4':'d'})
s, t, p, _ = calculate_score(answers_lower, questions, 50)
run("lowercase answers accepted", s == 6)


# ── 3. Answer JSON Merge Logic ─────────────────────────────────────────────────
print("\n3. Answer JSON Merge Logic")

def merge_answers(server_json, client_dict):
    """Mirror of submit_exam() merge logic"""
    server = json.loads(server_json)
    for qid, ans in client_dict.items():
        if str(ans).upper() in ('A','B','C','D'):
            server[str(qid)] = str(ans).upper()
    return server

# Client adds new answer
merged = merge_answers('{"1":"A"}', {'2': 'B'})
run("client adds new answer", merged.get('2') == 'B')
run("server answer preserved", merged.get('1') == 'A')

# Client updates existing answer
merged = merge_answers('{"1":"A"}', {'1': 'C'})
run("client updates answer", merged.get('1') == 'C')

# Invalid client answer rejected
merged = merge_answers('{"1":"A"}', {'2': 'X'})
run("invalid answer X rejected", '2' not in merged)

merged = merge_answers('{"1":"A"}', {'2': 'inject'})
run("injection attempt rejected", '2' not in merged)

# Empty client dict — server answers preserved
merged = merge_answers('{"1":"A","2":"B"}', {})
run("empty client keeps server answers", len(merged) == 2)


# ── 4. Question Shuffling ──────────────────────────────────────────────────────
print("\n4. Question Shuffling")

def shuffle_questions(question_ids):
    ids = list(question_ids)
    random.shuffle(ids)
    return ids

original = list(range(1, 21))  # 20 questions

# Run 10 shuffles and collect results
shuffles = [shuffle_questions(original) for _ in range(10)]

run("shuffle preserves all IDs",
    all(sorted(s) == sorted(original) for s in shuffles))
run("shuffle preserves count",
    all(len(s) == len(original) for s in shuffles))
# With 20 items, the chance all 10 shuffles equal original is astronomically small
run("shuffle produces different orders",
    not all(s == original for s in shuffles))
run("shuffle is not always same",
    len(set(tuple(s) for s in shuffles)) > 1)


# ── 5. Auto-Submit Conditions ─────────────────────────────────────────────────
print("\n5. Auto-Submit Conditions")

class MockResult:
    def __init__(self, tab_switches=0, status="in_progress"):
        self.tab_switches = tab_switches
        self.status = status
    def should_auto_submit(self, max_tabs):
        if self.status != "in_progress": return False, "already_done"
        if self.tab_switches >= max_tabs: return True, "tab_limit"
        return False, None

r1 = MockResult(tab_switches=0)
r2 = MockResult(tab_switches=3)
r3 = MockResult(tab_switches=3, status="submitted")

should, reason = r1.should_auto_submit(3)
run("0 switches: no auto-submit", not should)

should, reason = r2.should_auto_submit(3)
run("3 switches at limit=3: auto-submit", should)
run("reason is tab_limit", reason == "tab_limit")

should, reason = r3.should_auto_submit(3)
run("already submitted: no auto-submit", not should)

# Edge cases
r4 = MockResult(tab_switches=2)
should, _ = r4.should_auto_submit(3)
run("2 switches at limit=3: no auto-submit", not should)

r5 = MockResult(tab_switches=10)
should, _ = r5.should_auto_submit(3)
run("10 switches at limit=3: auto-submit", should)


# ── 6. Cheat Event Type Validation ────────────────────────────────────────────
print("\n6. Cheat Event Type Validation")

VALID_EVENTS = {
    'tab_switch', 'window_blur', 'copy_attempt', 'paste_attempt',
    'right_click', 'keyboard_shortcut', 'fullscreen_exit',
    'face_absent', 'multiple_faces', 'face_detected',
}

def is_valid_event(event_type):
    return event_type in VALID_EVENTS

run("tab_switch is valid",           is_valid_event("tab_switch"))
run("face_absent is valid",          is_valid_event("face_absent"))
run("multiple_faces is valid",       is_valid_event("multiple_faces"))
run("right_click is valid",          is_valid_event("right_click"))
run("malicious_payload rejected",    not is_valid_event("'; DROP TABLE--"))
run("sql_injection rejected",        not is_valid_event("1=1"))
run("empty string rejected",         not is_valid_event(""))
run("unknown_event rejected",        not is_valid_event("unknown_event"))
run("xss_attempt rejected",          not is_valid_event("<script>"))


# ── 7. Exam Availability Checks ────────────────────────────────────────────────
print("\n7. Exam Availability Checks")

class MockExam:
    def __init__(self, status="published", start=None, end=None):
        self.status = status
        self.start_time = start
        self.end_time = end
    def is_available(self):
        if self.status != "published": return False
        now = datetime.utcnow()
        if self.start_time and now < self.start_time: return False
        if self.end_time   and now > self.end_time:   return False
        return True

run("published exam available",
    MockExam("published").is_available())
run("draft exam not available",
    not MockExam("draft").is_available())
run("closed exam not available",
    not MockExam("closed").is_available())

# Time window checks
past_start  = datetime.utcnow() - timedelta(hours=1)
future_end  = datetime.utcnow() + timedelta(hours=1)
past_end    = datetime.utcnow() - timedelta(minutes=5)
future_start= datetime.utcnow() + timedelta(minutes=30)

run("in window: available",
    MockExam("published", past_start, future_end).is_available())
run("past end: not available",
    not MockExam("published", past_start, past_end).is_available())
run("future start: not available",
    not MockExam("published", future_start, future_end).is_available())
run("no window: always available",
    MockExam("published", None, None).is_available())


# ── 8. Question Correct-Answer Verification ────────────────────────────────────
print("\n8. Question Correct-Answer Verification")

class MockQuestion:
    def __init__(self, correct):
        self.correct_answer = correct
    def is_correct(self, answer):
        if not answer: return False
        return answer.upper() == self.correct_answer.upper()

q = MockQuestion("B")
run("correct answer B matches",    q.is_correct("B"))
run("lowercase b matches",         q.is_correct("b"))
run("wrong answer A rejects",      not q.is_correct("A"))
run("wrong answer C rejects",      not q.is_correct("C"))
run("empty string rejects",        not q.is_correct(""))
run("None rejects",                not q.is_correct(None))


# ── 9. Percentage Rounding ─────────────────────────────────────────────────────
print("\n9. Percentage Calculation & Rounding")

def calc_pct(score, total):
    if total == 0: return 0.0
    return round((score / total * 100), 2)

run("3/5 = 60.00%",       calc_pct(3, 5)  == 60.0)
run("1/3 = 33.33%",       calc_pct(1, 3)  == 33.33)
run("2/3 = 66.67%",       calc_pct(2, 3)  == 66.67)
run("0/10 = 0.00%",       calc_pct(0, 10) == 0.0)
run("10/10 = 100.00%",    calc_pct(10,10) == 100.0)
run("0/0 = 0.00%",        calc_pct(0, 0)  == 0.0)
run("7/14 = 50.00%",      calc_pct(7, 14) == 50.0)


# ── 10. Session Token Uniqueness ──────────────────────────────────────────────
print("\n10. Exam Session Token Uniqueness")

tokens = [secrets.token_hex(32) for _ in range(200)]
run("200 tokens all unique",         len(set(tokens)) == 200)
run("each token is 64 chars",        all(len(t) == 64 for t in tokens))
run("tokens are hex strings",        all(
    all(c in '0123456789abcdef' for c in t) for t in tokens
))
run("no sequential pattern",
    tokens[0] != tokens[1] and tokens[1] != tokens[2])


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 3 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
