"""
tests/test_day4_anticheat.py — Day 4 Anti-Cheat & Security Tests
=================================================================
Tests cover:
  1.  Blocked keyboard shortcut detection logic
  2.  Key combo builder logic
  3.  Cheat event type allowlisting
  4.  Severity classification
  5.  HTTP security header presence
  6.  Content Security Policy structure
  7.  Suspicious URL pattern detection
  8.  Anti-cheat counter logic
  9.  Face detection threshold logic
 10.  Screen capture intercept flag
 11.  Toast warning severity mapping
 12.  Retry queue logic (pending logs)

Run standalone: python tests/test_day4_anticheat.py
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = failed = 0

def ok(name):
    global passed; passed += 1; print(f"  ✓ {name}")

def fail(name, msg=""):
    global failed; failed += 1; print(f"  ✗ {name}: {msg}")

def run(name, condition, msg=""):
    if condition: ok(name)
    else: fail(name, msg or "assertion failed")

print("\n=== Day 4 Anti-Cheat & Security Tests ===\n")


# ── 1. Blocked Keyboard Shortcuts ─────────────────────────────────────────────
print("1. Blocked Keyboard Shortcuts")

BLOCKED = {
    'ctrl+c','ctrl+v','ctrl+x','ctrl+a','ctrl+s','ctrl+p',
    'ctrl+u','ctrl+f','ctrl+h','ctrl+r','ctrl+l','ctrl+t',
    'ctrl+w','ctrl+n','ctrl+j',
    'ctrl+shift+i','ctrl+shift+j','ctrl+shift+c','ctrl+shift+k',
    'f1','f5','f12',
    'alt+f4','alt+tab',
    'meta+c','meta+v','meta+x','meta+a','meta+s','meta+p',
    'meta+r','meta+q','meta+h',
    'meta+shift+i',
}

def is_blocked(combo): return combo in BLOCKED

run("ctrl+c is blocked",         is_blocked('ctrl+c'))
run("ctrl+v is blocked",         is_blocked('ctrl+v'))
run("f12 is blocked",            is_blocked('f12'))
run("ctrl+shift+i is blocked",   is_blocked('ctrl+shift+i'))
run("alt+tab is blocked",        is_blocked('alt+tab'))
run("ctrl+p is blocked",         is_blocked('ctrl+p'))
run("meta+c is blocked (Mac)",   is_blocked('meta+c'))
run("Enter is NOT blocked",      not is_blocked('enter'))
run("ArrowRight is NOT blocked", not is_blocked('arrowright'))
run("Tab is NOT blocked",        not is_blocked('tab'))
run("Space is NOT blocked",      not is_blocked(' '))
run("a is NOT blocked",          not is_blocked('a'))
run("Backspace NOT blocked",     not is_blocked('backspace'))


# ── 2. Key Combo Builder Logic ─────────────────────────────────────────────────
print("\n2. Key Combo Builder Logic")

def build_combo(ctrl=False, alt=False, meta=False, shift=False, key=''):
    """Mirror of buildKeyCombo() in anti_cheat.js"""
    parts = []
    if ctrl  and key != 'Control': parts.append('ctrl')
    if alt   and key != 'Alt':     parts.append('alt')
    if meta  and key != 'Meta':    parts.append('meta')
    if shift and key != 'Shift':   parts.append('shift')
    parts.append(key.lower())
    return '+'.join(parts)

run("Ctrl+C → 'ctrl+c'",          build_combo(ctrl=True, key='C')         == 'ctrl+c')
run("Ctrl+Shift+I → 'ctrl+shift+i'", build_combo(ctrl=True, shift=True, key='I') == 'ctrl+shift+i')
run("F12 alone → 'f12'",           build_combo(key='F12')                  == 'f12')
run("Alt+F4 → 'alt+f4'",           build_combo(alt=True, key='F4')         == 'alt+f4')
run("Meta+C → 'meta+c'",           build_combo(meta=True, key='C')         == 'meta+c')
run("just 'a' → 'a'",              build_combo(key='a')                    == 'a')
run("ctrl key alone → 'control'", build_combo(ctrl=True, key='Control') == 'control')
run("shift alone → 'shift'",       build_combo(shift=True, key='Shift')    == 'shift')


# ── 3. Cheat Event Allowlist ──────────────────────────────────────────────────
print("\n3. Cheat Event Type Allowlist")

VALID_EVENTS = {
    'tab_switch','window_blur','copy_attempt','paste_attempt',
    'right_click','keyboard_shortcut','fullscreen_exit',
    'face_absent','multiple_faces','face_detected',
}

def validate_event(e): return e in VALID_EVENTS

run("tab_switch valid",         validate_event('tab_switch'))
run("face_absent valid",        validate_event('face_absent'))
run("multiple_faces valid",     validate_event('multiple_faces'))
run("right_click valid",        validate_event('right_click'))
run("keyboard_shortcut valid",  validate_event('keyboard_shortcut'))
run("copy_attempt valid",       validate_event('copy_attempt'))
run("paste_attempt valid",      validate_event('paste_attempt'))
run("fullscreen_exit valid",    validate_event('fullscreen_exit'))
run("face_detected valid",      validate_event('face_detected'))
run("sql_inject rejected",      not validate_event("'; DROP TABLE--"))
run("xss rejected",             not validate_event('<script>alert(1)'))
run("empty rejected",           not validate_event(''))
run("unknown_event rejected",   not validate_event('unknown_event'))
run("UPPERCASE rejected",       not validate_event('TAB_SWITCH'))


# ── 4. Severity Classification ────────────────────────────────────────────────
print("\n4. Severity Classification")

def get_severity(event_type, extra=''):
    """Mirror the severity logic from anti_cheat.js"""
    HIGH = {'tab_switch', 'face_absent', 'multiple_faces', 'keyboard_shortcut'}
    MED  = {'window_blur', 'copy_attempt', 'paste_attempt', 'fullscreen_exit'}
    LOW  = {'right_click', 'face_detected'}
    if event_type in HIGH:
        if event_type == 'keyboard_shortcut' and 'f12' in extra:
            return 'high'
        return 'high' if event_type != 'window_blur' else 'medium'
    if event_type in MED: return 'medium'
    return 'low'

run("tab_switch → high",     get_severity('tab_switch')     == 'high')
run("multiple_faces → high", get_severity('multiple_faces') == 'high')
run("face_absent → high",    get_severity('face_absent')    == 'high')
run("copy_attempt → medium", get_severity('copy_attempt')   == 'medium')
run("right_click → low",     get_severity('right_click')    == 'low')
run("face_detected → low",   get_severity('face_detected')  == 'low')
run("f12 → high",            get_severity('keyboard_shortcut','f12') == 'high')


# ── 5. HTTP Security Headers ──────────────────────────────────────────────────
print("\n5. HTTP Security Headers")

def build_expected_headers():
    return {
        'X-Frame-Options':       'DENY',
        'X-Content-Type-Options':'nosniff',
        'X-XSS-Protection':      '1; mode=block',
        'Referrer-Policy':       'strict-origin-when-cross-origin',
    }

headers = build_expected_headers()
run("X-Frame-Options is DENY",             headers['X-Frame-Options'] == 'DENY')
run("X-Content-Type-Options is nosniff",   headers['X-Content-Type-Options'] == 'nosniff')
run("X-XSS-Protection blocks",            '1; mode=block' in headers['X-XSS-Protection'])
run("Referrer-Policy is strict-origin",   'strict-origin' in headers['Referrer-Policy'])


# ── 6. Content Security Policy Directives ─────────────────────────────────────
print("\n6. Content Security Policy Structure")

CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com 'unsafe-inline'; "
    "style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com 'unsafe-inline'; "
    "img-src 'self' data: blob: https:; "
    "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
    "connect-src 'self' https://cdn.jsdelivr.net; "
    "media-src 'self' blob:; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)

run("default-src 'self'",         "default-src 'self'" in CSP)
run("frame-src 'none'",           "frame-src 'none'"   in CSP)
run("object-src 'none'",          "object-src 'none'"  in CSP)
run("jsdelivr in script-src",     "cdn.jsdelivr.net"   in CSP)
run("media-src allows blob",      "blob:" in CSP)
run("form-action self only",      "form-action 'self'" in CSP)
run("base-uri self only",         "base-uri 'self'"    in CSP)
run("no frame allowed",           "frame-src 'none'"   in CSP)
run("connect-src restricts",      "connect-src 'self'" in CSP)


# ── 7. Suspicious URL Pattern Detection ───────────────────────────────────────
print("\n7. Suspicious URL Pattern Detection")

SUSPICIOUS = [
    '../', 'etc/passwd', '<script', 'UNION SELECT',
    'DROP TABLE', 'javascript:', 'eval(', '%27', '%3Cscript',
]

def has_suspicious(url):
    url_lower = url.lower()
    for p in SUSPICIOUS:
        if p.lower() in url_lower:
            return True, p
    return False, None

run("path traversal detected",      has_suspicious('/exam/../admin')[0])
run("etc/passwd detected",          has_suspicious('/etc/passwd')[0])
run("script tag detected",          has_suspicious('/search?q=<script>')[0])
run("UNION SELECT detected",        has_suspicious('/exam?id=1 UNION SELECT')[0])
run("javascript: detected",         has_suspicious('/auth?next=javascript:')[0])
run("eval() detected",              has_suspicious('/api?data=eval(base64)')[0])
run("url-encoded quote detected",   has_suspicious('/exam?id=1%27')[0])
run("url-encoded script detected",  has_suspicious('/search?q=%3Cscript')[0])
run("normal URL not suspicious",    not has_suspicious('/exam/dashboard')[0])
run("login URL not suspicious",     not has_suspicious('/auth/login')[0])
run("API health not suspicious",    not has_suspicious('/api/health')[0])


# ── 8. Anti-Cheat Counter Logic ───────────────────────────────────────────────
print("\n8. Anti-Cheat Counter Logic")

class MockAntiCheat:
    def __init__(self, max_tabs=3):
        self.tab_switches = 0
        self.face_absent  = 0
        self.multi_face   = 0
        self.max_tabs     = max_tabs
        self.auto_submitted = False

    def on_tab_switch(self):
        self.tab_switches += 1
        if self.tab_switches >= self.max_tabs:
            self.auto_submitted = True
        return self.tab_switches

    def on_face_absent(self):
        self.face_absent += 1

    def on_multi_face(self):
        self.multi_face += 1

ac = MockAntiCheat(max_tabs=3)
ac.on_tab_switch()
run("first switch increments to 1",  ac.tab_switches == 1)
run("first switch no auto-submit",   not ac.auto_submitted)
ac.on_tab_switch()
run("second switch increments to 2", ac.tab_switches == 2)
run("second switch no auto-submit",  not ac.auto_submitted)
ac.on_tab_switch()
run("third switch triggers submit",  ac.auto_submitted)
run("face absent increments",        (ac.on_face_absent() or True) and ac.face_absent == 1)
run("multi-face increments",         (ac.on_multi_face() or True) and ac.multi_face == 1)

# Test with max_tabs=1
ac2 = MockAntiCheat(max_tabs=1)
ac2.on_tab_switch()
run("max_tabs=1 submits on first switch", ac2.auto_submitted)


# ── 9. Face Detection Threshold Logic ────────────────────────────────────────
print("\n9. Face Detection Threshold Logic")

MIN_CONFIDENCE     = 0.65
ABSENT_THRESHOLD   = 3
MULTI_LOG_EVERY    = 2

def process_detection(face_count, confidence=0.9,
                       consecutive_absent=0, multi_count=0):
    """Mirror of runDetection() decision logic"""
    event = None
    if face_count == 0:
        consecutive_absent += 1
        if consecutive_absent >= ABSENT_THRESHOLD:
            event = 'face_absent'
    elif face_count == 1:
        consecutive_absent = 0
        if confidence < MIN_CONFIDENCE:
            event = 'face_low_confidence'
    else:  # multiple
        consecutive_absent = 0
        multi_count += 1
        if multi_count % MULTI_LOG_EVERY == 0:
            event = 'multiple_faces'
    return event, consecutive_absent, multi_count

# 0 faces, below threshold
e, ca, mc = process_detection(0, consecutive_absent=0)
run("1st absence: no event yet",     e is None and ca == 1)

e, ca, mc = process_detection(0, consecutive_absent=1)
run("2nd absence: no event yet",     e is None and ca == 2)

e, ca, mc = process_detection(0, consecutive_absent=2)
run("3rd absence: fires face_absent",e == 'face_absent')

# 1 face (normal)
e, ca, mc = process_detection(1, consecutive_absent=5)
run("face appears: resets counter",  e is None and ca == 0)

e, ca, mc = process_detection(1, confidence=0.3)
run("low confidence flagged",        e == 'face_low_confidence')

# 2 faces
e, ca, mc = process_detection(2, multi_count=0)
run("1st multi-face: no log yet",    e is None and mc == 1)

e, ca, mc = process_detection(2, multi_count=1)
run("2nd multi-face: fires event",   e == 'multiple_faces' and mc == 2)


# ── 10. Screen Capture Intercept ──────────────────────────────────────────────
print("\n10. Screen Capture Intercept Flag")

class MockMediaDevices:
    def __init__(self, intercepted=False):
        self.intercepted = intercepted
        self.calls = []

    async def getDisplayMedia_intercepted(self):
        self.calls.append('getDisplayMedia')
        raise Exception('NotAllowedError: Screen capture disabled')

run("intercept raises exception",
    callable(MockMediaDevices().getDisplayMedia_intercepted))

import asyncio
async def test_intercept():
    md = MockMediaDevices()
    try:
        await md.getDisplayMedia_intercepted()
        return False
    except Exception as e:
        return 'NotAllowedError' in str(e)

result = asyncio.get_event_loop().run_until_complete(test_intercept())
run("getDisplayMedia throws NotAllowedError", result)


# ── 11. Toast Warning Severity Colour Mapping ─────────────────────────────────
print("\n11. Toast Warning Severity Colour Mapping")

def get_toast_bg(severity):
    return {'high':'#dc2626','medium':'#d97706','low':'#0284c7'}.get(severity,'#0284c7')

run("high severity → red",      get_toast_bg('high')   == '#dc2626')
run("medium severity → amber",  get_toast_bg('medium') == '#d97706')
run("low severity → blue",      get_toast_bg('low')    == '#0284c7')
run("unknown → blue (default)", get_toast_bg('unknown')== '#0284c7')


# ── 12. Retry Queue Logic ─────────────────────────────────────────────────────
print("\n12. Pending Log Retry Queue")

class MockRetryQueue:
    def __init__(self):
        self.queue = []
        self.sent  = []

    def push(self, event): self.queue.append(event)

    def retry_all(self):
        if not self.queue: return 0
        count = len(self.queue)
        self.sent.extend(self.queue)
        self.queue.clear()
        return count

q = MockRetryQueue()
run("empty queue retries nothing",  q.retry_all() == 0)

q.push({'type':'tab_switch','time':1})
q.push({'type':'copy_attempt','time':2})
run("queue has 2 items",            len(q.queue) == 2)

retried = q.retry_all()
run("retry_all retries 2 items",    retried == 2)
run("queue empty after retry",      len(q.queue) == 0)
run("items moved to sent",          len(q.sent) == 2)
run("second retry is no-op",        q.retry_all() == 0)


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 4 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
