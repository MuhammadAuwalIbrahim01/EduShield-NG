"""
tests/test_day2_auth.py — Day 2 Authentication Tests
Run standalone: python tests/test_day2_auth.py
"""
import sys, os, re, secrets
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Sanitize ──────────────────────────────────────────────────────────────────
def sanitize(text, max_length=10000):
    if not text: return ""
    text = str(text)[:max_length]
    text = re.sub(r'<(script|iframe|object|embed|form|input|link|meta|style|img)[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bon\w+\s*=', '', text, flags=re.IGNORECASE)
    text = re.sub(r'javascript\s*:', '', text, flags=re.IGNORECASE)
    return text.strip()

def pw_strength(pw):
    score = 0
    msgs = []
    if len(pw) >= 8: score += 1; msgs.append("✓ length")
    else: msgs.append("✗ length")
    if any(c.isupper() for c in pw): score += 1; msgs.append("✓ upper")
    else: msgs.append("✗ upper")
    if any(c.islower() for c in pw): score += 1; msgs.append("✓ lower")
    else: msgs.append("✗ lower")
    if any(c.isdigit() for c in pw): score += 1; msgs.append("✓ digit")
    else: msgs.append("✗ digit")
    return score, msgs

def passes_policy(pw):
    if len(pw) < 8: return False, "too_short"
    if not any(c.isupper() for c in pw): return False, "no_upper"
    if not any(c.islower() for c in pw): return False, "no_lower"
    if not any(c.isdigit() for c in pw): return False, "no_digit"
    return True, "ok"

def is_safe_redirect(target, host="http://localhost:5000"):
    from urllib.parse import urlparse, urljoin
    h = urlparse(host); r = urlparse(urljoin(host, target))
    return r.scheme in ("http","https") and h.netloc == r.netloc

def valid_ng_phone(phone):
    return bool(re.match(r'^(\+234|0)[789][01]\d{8}$', phone))

# ── Test runner ────────────────────────────────────────────────────────────────
passed = failed = 0
def ok(name): global passed; passed += 1; print(f"  ✓ {name}")
def fail(name, msg): global failed; failed += 1; print(f"  ✗ {name}: {msg}")

def run(name, condition, msg=""):
    if condition: ok(name)
    else: fail(name, msg or "assertion failed")

print("\n=== Day 2 Auth Tests ===\n")

# 1. Sanitization
print("1. Input Sanitization")
run("removes script tag", "<script>" not in sanitize('<script>alert(1)</script>Hello'))
run("preserves safe text",  sanitize("Hello Nigeria") == "Hello Nigeria")
run("removes onclick",      "onclick" not in sanitize('<div onclick="evil()">text</div>'))
run("removes javascript:",  "javascript:" not in sanitize('<a href="javascript:void(0)">'))
run("truncates at limit",   len(sanitize("A"*200, 100)) <= 100)
run("empty returns empty",  sanitize("") == "")
run("removes iframe",       "<iframe" not in sanitize('<iframe src="bad.com"></iframe>ok'))
run("removes img onerror",  "<img" not in sanitize('<img src="x" onerror="evil()">'))

# 2. Password Strength
print("\n2. Password Strength")
score, _ = pw_strength("Ab1ddddd"); run("strong pw scores 4",   score == 4)
score, _ = pw_strength("abc");       run("weak pw scores <=2",  score <= 2)
score, _ = pw_strength("UPPER123");  run("no lower scores 3",   score == 3)
score, _ = pw_strength("lower123");  run("no upper scores 3",   score == 3)
score, _ = pw_strength("NoDigits"); run("no digit scores 3",    score == 3)

# 3. Password Hashing
print("\n3. Password Hashing")
from werkzeug.security import generate_password_hash, check_password_hash
h = generate_password_hash("Test123!")
run("hash != plaintext",          h != "Test123!")
run("correct pw verifies",        check_password_hash(h, "Test123!") is True)
run("wrong pw rejected",          check_password_hash(h, "Wrong!") is False)
run("hash is long",               len(h) > 50)
h1 = generate_password_hash("Same123!"); h2 = generate_password_hash("Same123!")
run("different hashes per call",  h1 != h2)

# 4. Token Generation
print("\n4. Token Generation")
tokens = [secrets.token_hex(32) for _ in range(50)]
run("tokens are unique",          len(set(tokens)) == 50)
run("token is 64 chars",          len(tokens[0]) == 64)
run("token is hex",               all(c in '0123456789abcdef' for c in tokens[0]))

# 5. Safe Redirect
print("\n5. Safe Redirect")
run("relative path is safe",      is_safe_redirect("/exam/dashboard"))
run("external URL is unsafe",     not is_safe_redirect("https://evil.com"))
run("similar domain is unsafe",   not is_safe_redirect("https://edushield.evil.com"))
run("javascript: is unsafe",      not is_safe_redirect("javascript:alert(1)"))
run("same-origin path is safe",   is_safe_redirect("/auth/profile"))

# 6. Password Policy
print("\n6. Password Policy")
ok_vals = ["Nigeria2024!", "EduShield123", "SecureExam99"]
for pw in ok_vals:
    ok_, r = passes_policy(pw)
    run(f"'{pw}' passes policy", ok_, r)
run("too short fails",    passes_policy("Ab1")[0] is False)
run("no upper fails",     passes_policy("nouppercase1")[0] is False)
run("no lower fails",     passes_policy("NOLOWER1")[0] is False)
run("no digit fails",     passes_policy("NoDigitsHere")[0] is False)

# 7. Nigerian Phone Numbers
print("\n7. Nigerian Phone Validation")
run("08012345678 valid",    valid_ng_phone("08012345678"))
run("+2348012345678 valid", valid_ng_phone("+2348012345678"))
run("09012345678 valid",    valid_ng_phone("09012345678"))
run("too short invalid",    not valid_ng_phone("080123456"))
run("UK number invalid",    not valid_ng_phone("+447911123456"))
run("letters invalid",      not valid_ng_phone("080ABCDE123"))
run("starts 05 invalid",    not valid_ng_phone("05012345678"))

# 8. Role Logic
print("\n8. Role Logic")
class M:
    def __init__(self, role): self.role = role
    def is_admin(self): return self.role == "admin"
    def is_student(self): return self.role == "student"

run("admin.is_admin() True",    M("admin").is_admin())
run("admin.is_student() False", not M("admin").is_student())
run("student.is_student() True", M("student").is_student())
run("student.is_admin() False",  not M("student").is_admin())

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*45}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 2 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
