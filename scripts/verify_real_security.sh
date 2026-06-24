#!/bin/bash
# scripts/verify_real_security.sh — Real Source Code Security Verification
# ============================================================================
# Unlike tests/test_day8_pentest.py's mirrored logic, this script imports
# the ACTUAL backend/utils/security.py file and fires real attack payloads
# at it. Run this after ANY change to security.py to confirm no regression.
#
# Why this exists as a separate script (not just inline in pytest):
#   - It needs to stub Flask extensions that may not be installed in every
#     environment (CI runners, local dev without full requirements.txt yet)
#   - It's meant to be run manually/in CI specifically when security.py changes,
#     as an extra confidence layer beyond the regular test suite
#
# Usage:
#   bash scripts/verify_real_security.sh
#
# Exit code 0 = all real-source checks passed
# Exit code 1 = a real vulnerability was found in the actual source file

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================================"
echo "EduShield NG — Real Source Code Security Verification"
echo "============================================================"
echo "Project root: $PROJECT_ROOT"
echo ""

python3 << 'PYEOF'
import sys, os, importlib.util

PROJECT_ROOT = os.getcwd()

# Create minimal stub packages for Flask extensions not installed in this env
import tempfile
stub_dir = tempfile.mkdtemp(prefix="edushield_stubs_")
os.makedirs(os.path.join(stub_dir, "flask_wtf"), exist_ok=True)

with open(os.path.join(stub_dir, "flask_login.py"), "w") as f:
    f.write(
        "class LoginManager:\n"
        "    def init_app(self, app): pass\n"
        "    def user_loader(self, f): return f\n"
        "class UserMixin: pass\n"
        "def login_required(f): return f\n"
        "def login_user(*a, **k): pass\n"
        "def logout_user(*a, **k): pass\n"
        "current_user = None\n"
    )
with open(os.path.join(stub_dir, "flask_wtf", "__init__.py"), "w") as f:
    f.write(
        "class FlaskForm:\n"
        "    def __init__(self, *a, **k): pass\n"
        "class CSRFProtect:\n"
        "    def init_app(self, app): pass\n"
    )
with open(os.path.join(stub_dir, "flask_wtf", "csrf.py"), "w") as f:
    f.write(
        "class CSRFProtect:\n"
        "    def init_app(self, app): pass\n"
        "def generate_csrf(): return 'fake-csrf-token'\n"
    )

sys.path.insert(0, stub_dir)

import flask
class FakeRequest:
    host_url = "http://localhost:5000/"
    path = "/test"
    args = {}
    form = {}
flask.request = FakeRequest()

spec_path = os.path.join(PROJECT_ROOT, "backend", "utils", "security.py")
spec = importlib.util.spec_from_file_location("real_security", spec_path)
sec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sec)

print(f"Loaded real module from: {spec_path}\n")

XSS_CASES = [
    ('<script>alert(1)</script>Hello',                          ['<script', '</script', 'alert(1)']),
    ('<img src=x onerror=alert(1)>',                              ['<img', 'onerror']),
    ('javascript:alert(document.cookie)',                         ['javascript:']),
    ('<iframe src=evil.com></iframe>Safe text',                   ['<iframe', '</iframe']),
    ('<style>body{background:url(javascript:evil)}</style>clean', ['<style', '</style', 'javascript:']),
    ('<svg onload=alert(1)>',                                      ['<svg', 'onload', 'alert(1)']),
    ('<svg/onload=alert(1)>',                                      ['<svg', 'onload']),
    ('<video><source onerror=alert(1)></video>',                  ['<video', 'onerror']),
    ('<audio src=x onerror=alert(1)>',                             ['<audio', 'onerror']),
    ('<base href=javascript:alert(1)//>',                          ['<base', 'javascript:']),
    ('<details open ontoggle=alert(1)>',                           ['<details', 'ontoggle']),
    ('<marquee onstart=alert(1)>',                                  ['<marquee', 'onstart']),
    ('<ScRiPt>alert(1)</ScRiPt>',                                   ['<script', '</script']),
    ('<svg><script>alert(1)</script></svg>',                       ['<svg', '<script', 'alert(1)']),
]

failures = 0
for payload, must_not_contain in XSS_CASES:
    result = sec.sanitize_input(payload)
    leftover = [f for f in must_not_contain if f.lower() in result.lower()]
    if leftover:
        print(f"  ✗ VULNERABLE: {payload!r} -> {result!r} (leftover: {leftover})")
        failures += 1
    else:
        print(f"  ✓ {payload!r} -> {result!r}")

SAFE_CASES = [
    "If x > 5 and y < 10, what is x + y?",
    "University of Lagos — Score: 85% (17/20)",
    "Aminu Bello",
]
for safe in SAFE_CASES:
    result = sec.sanitize_input(safe)
    if result != safe:
        print(f"  ✗ FALSE POSITIVE: {safe!r} was mangled to {result!r}")
        failures += 1
    else:
        print(f"  ✓ (safe, unchanged) {safe!r}")

redirect_cases = [
    ("https://evil.com", False),
    ("//evil.com", False),
    ("/exam/dashboard", True),
]
for target, expected_safe in redirect_cases:
    result = sec.is_safe_redirect_url(target)
    if result != expected_safe:
        print(f"  ✗ REDIRECT CHECK FAILED: {target!r} expected safe={expected_safe}, got {result}")
        failures += 1
    else:
        print(f"  ✓ is_safe_redirect_url({target!r}) -> {result}")

tokens = [sec.generate_token() for _ in range(20)]
if len(set(tokens)) != 20:
    print("  ✗ TOKEN COLLISION DETECTED")
    failures += 1
else:
    print(f"  ✓ generate_token() produced 20/20 unique tokens")

print()
if failures == 0:
    print("✅ ALL REAL-SOURCE SECURITY CHECKS PASSED")
    sys.exit(0)
else:
    print(f"🚨 {failures} REAL VULNERABILITY/VULNERABILITIES FOUND IN backend/utils/security.py")
    sys.exit(1)
PYEOF

EXIT_CODE=$?
echo ""
echo "============================================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "RESULT: PASS"
else
    echo "RESULT: FAIL — fix backend/utils/security.py before deploying"
fi
echo "============================================================"
exit $EXIT_CODE
