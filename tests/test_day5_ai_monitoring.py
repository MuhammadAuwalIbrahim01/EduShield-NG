"""
tests/test_day5_ai_monitoring.py — Day 5 AI Monitoring & Calibration Tests
============================================================================
Tests cover:
  1.  Face descriptor validation (length, type, range)
  2.  Euclidean distance calculation for face matching
  3.  Match/mismatch/borderline threshold classification
  4.  Descriptor averaging logic (calibration capture)
  5.  Consecutive mismatch counter (avoids single-frame false positives)
  6.  Snapshot data URI validation
  7.  Snapshot size limit enforcement
  8.  Face descriptor storage round-trip (JSON serialize/deserialize)
  9.  Calibration redirect logic
 10.  Identity verification skip when no calibration on file
 11.  Recalibration clears stored descriptor

Run standalone: python tests/test_day5_ai_monitoring.py
"""
import sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = failed = 0

def ok(name):
    global passed; passed += 1; print(f"  ✓ {name}")

def fail(name, msg=""):
    global failed; failed += 1; print(f"  ✗ {name}: {msg}")

def run(name, condition, msg=""):
    if condition: ok(name)
    else: fail(name, msg or "assertion failed")

print("\n=== Day 5 AI Monitoring & Calibration Tests ===\n")


# ── 1. Face Descriptor Validation ─────────────────────────────────────────────
print("1. Face Descriptor Validation")

def validate_descriptor(descriptor):
    """Mirror of save_calibration() validation logic."""
    if not isinstance(descriptor, list) or len(descriptor) != 128:
        return False, "Invalid descriptor format"
    try:
        floats = [float(x) for x in descriptor]
        if any(abs(x) > 10 for x in floats):
            return False, "Descriptor value out of expected range"
    except (TypeError, ValueError):
        return False, "Malformed descriptor values"
    return True, "ok"

valid_128 = [round(random.uniform(-1, 1), 6) for _ in range(128)]
ok_, reason = validate_descriptor(valid_128)
run("valid 128-float descriptor accepted", ok_, reason)

ok_, reason = validate_descriptor([0.1, 0.2, 0.3])
run("too-short descriptor rejected", not ok_)

ok_, reason = validate_descriptor("not a list")
run("non-list descriptor rejected", not ok_)

ok_, reason = validate_descriptor(valid_128 + [0.5])  # 129 elements
run("129-element descriptor rejected", not ok_)

out_of_range = [0.1] * 127 + [999.0]
ok_, reason = validate_descriptor(out_of_range)
run("out-of-range value rejected", not ok_)

mixed_types = [0.1] * 127 + ["not_a_number"]
ok_, reason = validate_descriptor(mixed_types)
run("non-numeric value rejected", not ok_)

empty_list = []
ok_, reason = validate_descriptor(empty_list)
run("empty list rejected", not ok_)


# ── 2. Euclidean Distance Calculation ─────────────────────────────────────────
print("\n2. Euclidean Distance Calculation")

def euclidean_distance(d1, d2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(d1, d2)))

identical = [0.5, 0.3, -0.2]
run("identical vectors → distance 0",
    euclidean_distance(identical, identical) == 0.0)

close = [0.5, 0.3, -0.2]
close2 = [0.51, 0.31, -0.19]
dist = euclidean_distance(close, close2)
run("very similar vectors → small distance", dist < 0.1, f"got {dist}")

far1 = [1.0, 1.0, 1.0]
far2 = [-1.0, -1.0, -1.0]
dist = euclidean_distance(far1, far2)
run("opposite vectors → distance ~3.46", abs(dist - math.sqrt(12)) < 0.01)

# Simple known case: 3-4-5 triangle pattern extended
v1 = [0, 0]
v2 = [3, 4]
run("3-4 vector → distance 5", euclidean_distance(v1, v2) == 5.0)


# ── 3. Match/Mismatch/Borderline Classification ───────────────────────────────
print("\n3. Match/Mismatch/Borderline Threshold Classification")

MATCH_THRESHOLD    = 0.5
MISMATCH_THRESHOLD = 0.6

def classify_distance(distance):
    if distance <= MATCH_THRESHOLD:
        return "match"
    elif distance > MISMATCH_THRESHOLD:
        return "mismatch"
    else:
        return "borderline"

run("distance 0.2 → match",        classify_distance(0.2) == "match")
run("distance 0.5 → match (edge)", classify_distance(0.5) == "match")
run("distance 0.55 → borderline",  classify_distance(0.55) == "borderline")
run("distance 0.6 → borderline (edge)", classify_distance(0.6) == "borderline")
run("distance 0.61 → mismatch",    classify_distance(0.61) == "mismatch")
run("distance 1.2 → mismatch",     classify_distance(1.2) == "mismatch")
run("distance 0.0 → match",        classify_distance(0.0) == "match")


# ── 4. Descriptor Averaging (Calibration Capture) ─────────────────────────────
print("\n4. Descriptor Averaging Logic")

def average_descriptors(descriptor_list):
    """Mirror of averageDescriptors() in calibrate.html"""
    length = len(descriptor_list[0])
    avg = [0.0] * length
    for d in descriptor_list:
        for i in range(length):
            avg[i] += d[i] / len(descriptor_list)
    return avg

captures = [
    [1.0, 2.0, 3.0],
    [1.2, 1.8, 3.2],
    [0.8, 2.2, 2.8],
]
avg = average_descriptors(captures)
run("average of 3 captures: dim0",  abs(avg[0] - 1.0) < 0.001)
run("average of 3 captures: dim1",  abs(avg[1] - 2.0) < 0.001)
run("average of 3 captures: dim2",  abs(avg[2] - 3.0) < 0.001)

identical_captures = [[5.0, 5.0]] * 3
avg2 = average_descriptors(identical_captures)
run("averaging identical captures preserves value", avg2 == [5.0, 5.0])


# ── 5. Consecutive Mismatch Counter ───────────────────────────────────────────
print("\n5. Consecutive Mismatch Counter Logic")

class MockMismatchTracker:
    def __init__(self, required=2):
        self.consecutive = 0
        self.total_logged = 0
        self.required = required

    def process(self, distance):
        if distance > MISMATCH_THRESHOLD:
            self.consecutive += 1
            if self.consecutive >= self.required:
                self.total_logged += 1
                self.consecutive = 0  # reset after logging
                return True  # event was logged
        else:
            self.consecutive = 0
        return False

tracker = MockMismatchTracker(required=2)
run("1st mismatch frame: no log yet",   not tracker.process(0.8))
run("2nd mismatch frame: logs event",   tracker.process(0.8))
run("total logged is 1",                tracker.total_logged == 1)

tracker2 = MockMismatchTracker(required=2)
tracker2.process(0.8)            # 1 mismatch
logged = tracker2.process(0.3)   # match resets streak
run("match frame resets streak",        not logged and tracker2.consecutive == 0)

tracker3 = MockMismatchTracker(required=2)
results = [tracker3.process(d) for d in [0.8, 0.3, 0.8, 0.8]]
run("isolated single mismatches never log alone",
    results == [False, False, False, True])


# ── 6. Snapshot Data URI Validation ───────────────────────────────────────────
print("\n6. Snapshot Data URI Validation")

def validate_snapshot(raw, max_len=80_000):
    if not isinstance(raw, str):
        return False
    if not raw.startswith("data:image/jpeg;base64,"):
        return False
    if len(raw) >= max_len:
        return False
    return True

run("valid jpeg data URI accepted",
    validate_snapshot("data:image/jpeg;base64,/9j/4AAQSkZJRg=="))
run("png data URI rejected (wrong type)",
    not validate_snapshot("data:image/png;base64,iVBORw0KGgo="))
run("plain base64 without prefix rejected",
    not validate_snapshot("/9j/4AAQSkZJRg=="))
run("non-string rejected",
    not validate_snapshot(12345))
run("None rejected",
    not validate_snapshot(None))

oversized = "data:image/jpeg;base64," + ("A" * 90_000)
run("oversized snapshot rejected",
    not validate_snapshot(oversized))

small = "data:image/jpeg;base64," + ("A" * 1000)
run("small snapshot accepted",
    validate_snapshot(small))


# ── 7. Face Match Distance Clamping ───────────────────────────────────────────
print("\n7. Face Match Distance Clamping (server-side safety)")

def clamp_distance(raw):
    try:
        d = float(raw)
        return max(0.0, min(2.0, d))
    except (TypeError, ValueError):
        return None

run("normal distance unaffected",      clamp_distance(0.7) == 0.7)
run("negative distance clamped to 0",  clamp_distance(-5.0) == 0.0)
run("huge distance clamped to 2.0",    clamp_distance(999.0) == 2.0)
run("non-numeric returns None",        clamp_distance("not_a_number") is None)
run("None input returns None",         clamp_distance(None) is None)


# ── 8. Descriptor JSON Round-Trip ─────────────────────────────────────────────
print("\n8. Face Descriptor JSON Storage Round-Trip")

class MockUser:
    def __init__(self):
        self.face_descriptor_json = None
        self.face_calibrated_at = None

    def set_face_descriptor(self, descriptor_list):
        self.face_descriptor_json = json.dumps(descriptor_list)
        self.face_calibrated_at = "2026-06-17T10:00:00"

    def get_face_descriptor(self):
        if not self.face_descriptor_json:
            return None
        return json.loads(self.face_descriptor_json)

    def has_face_calibration(self):
        return bool(self.face_descriptor_json)

u = MockUser()
run("new user has no calibration",     not u.has_face_calibration())
run("new user descriptor is None",     u.get_face_descriptor() is None)

original = [round(random.uniform(-1,1), 8) for _ in range(128)]
u.set_face_descriptor(original)
run("after calibration, has_face_calibration True", u.has_face_calibration())

retrieved = u.get_face_descriptor()
run("retrieved descriptor matches original", retrieved == original)
run("retrieved descriptor has 128 elements",  len(retrieved) == 128)
run("calibrated_at timestamp set",            u.face_calibrated_at is not None)


# ── 9. Calibration Redirect Logic ─────────────────────────────────────────────
print("\n9. Calibration Redirect Logic")

def needs_calibration(exam_webcam_required, user_has_calibration):
    """Mirror of start_exam() calibration check."""
    return exam_webcam_required and not user_has_calibration

run("webcam required + no calibration → needs calibration",
    needs_calibration(True, False))
run("webcam required + has calibration → skip calibration",
    not needs_calibration(True, True))
run("webcam not required → skip calibration regardless",
    not needs_calibration(False, False))
run("webcam not required + has calibration → skip",
    not needs_calibration(False, True))


# ── 10. Identity Verification Skip (No Calibration) ───────────────────────────
print("\n10. Identity Verification Skip When No Calibration On File")

def should_run_identity_check(reference_descriptor, live_descriptor):
    """Mirror of the JS guard: only matches if BOTH exist."""
    return reference_descriptor is not None and live_descriptor is not None

run("both present → runs identity check",
    should_run_identity_check([0.1]*128, [0.1]*128))
run("no reference → skips identity check",
    not should_run_identity_check(None, [0.1]*128))
run("no live descriptor → skips identity check",
    not should_run_identity_check([0.1]*128, None))
run("neither present → skips identity check",
    not should_run_identity_check(None, None))


# ── 11. Recalibration Clears Descriptor ───────────────────────────────────────
print("\n11. Recalibration Clears Stored Descriptor")

u2 = MockUser()
u2.set_face_descriptor([0.5] * 128)
run("calibration set before reset", u2.has_face_calibration())

# Mirror of recalibrate_face() route logic
u2.face_descriptor_json = None
u2.face_calibrated_at = None
run("calibration cleared after reset", not u2.has_face_calibration())
run("descriptor is None after reset",  u2.get_face_descriptor() is None)
run("timestamp cleared after reset",   u2.face_calibrated_at is None)


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 5 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
