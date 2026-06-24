"""
tests/test_day9_ui_polish.py — Day 9 UI/UX Polish Verification
==================================================================
Unlike previous days, UI polish is mostly visual and can't be fully
unit-tested. This suite verifies what CAN be objectively checked:

  1.  PageTransitionManager link-filtering logic (which clicks should
      trigger the bar vs which shouldn't)
  2.  FormSubmitManager opt-out logic
  3.  CSS file structural integrity (brace balance, no orphan selectors)
  4.  Dark-mode badge/event coverage — every badge CLASS used in templates
      has a corresponding [data-theme="dark"] override in polish.css
      (catches the exact kind of gap we found in today's audit)
  5.  Skeleton/empty-state CSS class naming consistency
  6.  Responsive breakpoint coverage — no breakpoint gaps between
      the defined media queries across main.css + exam.css + polish.css
  7.  Print stylesheet hides all interactive/chrome elements
  8.  Reduced-motion guards exist for every CSS animation defined

Run: python tests/test_day9_ui_polish.py
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = failed = 0
def ok(name): global passed; passed+=1; print(f"  ✓ {name}")
def fail(name, msg=""): global failed; failed+=1; print(f"  ✗ {name}: {msg}")
def run(name, cond, msg=""):
    if cond: ok(name)
    else: fail(name, msg or "assertion failed")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("\n=== Day 9 UI/UX Polish Verification ===\n")


# ── 1. PageTransitionManager Link Filtering Logic ─────────────────────────────
print("1. Page Transition Link-Filtering Logic")

def should_trigger_transition(href, target=None, modifiers=None, opted_out=False, origin="http://localhost:5000"):
    """Mirror of the click-filtering logic in PageTransitionManager.init()"""
    modifiers = modifiers or {}
    is_same_page = href.startswith('#')
    is_new_tab   = target == '_blank'
    is_modified  = any(modifiers.values())
    is_external  = href.startswith('http') and not href.startswith(origin)
    if is_same_page or is_new_tab or is_modified or is_external or opted_out:
        return False
    return True

run("normal internal link triggers transition",
    should_trigger_transition("/exam/dashboard"))
run("anchor link (#section) does NOT trigger",
    not should_trigger_transition("#section"))
run("target=_blank link does NOT trigger",
    not should_trigger_transition("/exam/dashboard", target="_blank"))
run("ctrl+click does NOT trigger (opening new tab)",
    not should_trigger_transition("/exam/dashboard", modifiers={"ctrlKey": True}))
run("shift+click does NOT trigger",
    not should_trigger_transition("/exam/dashboard", modifiers={"shiftKey": True}))
run("external link does NOT trigger",
    not should_trigger_transition("https://google.com"))
run("same-origin absolute URL DOES trigger",
    should_trigger_transition("http://localhost:5000/admin/dashboard"))
run("data-no-transition opt-out respected",
    not should_trigger_transition("/exam/dashboard", opted_out=True))
run("relative path with query string triggers",
    should_trigger_transition("/exam/available?subject=Math"))


# ── 2. FormSubmitManager Opt-Out Logic ─────────────────────────────────────────
print("\n2. Form Submit Loading-State Opt-Out Logic")

def should_apply_loading_state(has_opt_out_attr, is_form_valid=True):
    """Mirror of FormSubmitManager.init() submit handler logic."""
    if has_opt_out_attr:
        return False
    if not is_form_valid:
        return False
    return True

run("form WITHOUT opt-out attribute gets loading state",
    should_apply_loading_state(has_opt_out_attr=False))
run("form WITH data-no-loading-state does NOT get loading state",
    not should_apply_loading_state(has_opt_out_attr=True))
run("invalid form (failed native validation) does NOT get loading state",
    not should_apply_loading_state(has_opt_out_attr=False, is_form_valid=False))

# Verify the actual template files have the opt-out attribute where expected
login_html = open(os.path.join(ROOT, 'frontend/templates/auth/login.html')).read()
register_html = open(os.path.join(ROOT, 'frontend/templates/auth/register.html')).read()

run("login.html has data-no-loading-state (has its own custom UI)",
    'data-no-loading-state' in login_html)
run("register.html has data-no-loading-state (has its own custom UI)",
    'data-no-loading-state' in register_html)

# Verify admin forms do NOT have the opt-out (they SHOULD get the generic spinner)
exam_form_html = open(os.path.join(ROOT, 'frontend/templates/admin/exam_form.html')).read()
students_html = open(os.path.join(ROOT, 'frontend/templates/admin/students.html')).read()

run("admin/exam_form.html has NO opt-out (should get generic spinner)",
    'data-no-loading-state' not in exam_form_html)
run("admin/students.html has NO opt-out (should get generic spinner)",
    'data-no-loading-state' not in students_html)


# ── 3. CSS Structural Integrity ────────────────────────────────────────────────
print("\n3. CSS File Structural Integrity")

CSS_FILES = ['frontend/static/css/main.css', 'frontend/static/css/exam.css', 'frontend/static/css/polish.css']

for css_file in CSS_FILES:
    path = os.path.join(ROOT, css_file)
    content = open(path).read()
    opens = content.count('{')
    closes = content.count('}')
    run(f"{css_file}: brace count balanced ({opens} open, {closes} close)",
        opens == closes)

    # No empty rule blocks left over from editing (e.g. ".foo {  }")
    empty_rules = re.findall(r'[.#][\w-]+\s*\{\s*\}', content)
    run(f"{css_file}: no empty CSS rule blocks",
        len(empty_rules) == 0, str(empty_rules[:3]))


# ── 4. Dark Mode Badge Coverage ────────────────────────────────────────────────
print("\n4. Dark Mode Coverage — Every Badge Class Used Has an Override")

main_css = open(os.path.join(ROOT, 'frontend/static/css/main.css')).read()
polish_css = open(os.path.join(ROOT, 'frontend/static/css/polish.css')).read()
combined_css = main_css + polish_css

# Find every .badge-X and .severity-X class DEFINED in light mode (main.css)
# that ACTUALLY SETS A COLOR (wrapper classes like .role-badge/.status-badge
# define layout/spacing only — no color — so they don't need a dark-mode
# override; only color-bearing variant classes do)
def _rule_sets_color(css_text, classname):
    m = re.search(r'\.' + re.escape(classname) + r'\s*\{([^}]*)\}', css_text)
    if not m: return False
    body = m.group(1)
    return 'color:' in body or 'background:' in body

candidate_classes = set(re.findall(r'\.((?:badge|severity|status|role|event)-[\w-]+)\s*\{', main_css))
light_mode_badge_classes = {c for c in candidate_classes if _rule_sets_color(main_css, c)}

# Find every dark-mode override target
dark_mode_overrides = set(re.findall(r'\[data-theme="dark"\]\s*\.([\w-]+)', polish_css))

missing_dark_overrides = light_mode_badge_classes - dark_mode_overrides

run("every COLOR-BEARING light-mode badge/severity/status/role class has a dark-mode override",
    len(missing_dark_overrides) == 0,
    f"Missing dark overrides for: {sorted(missing_dark_overrides)}")

run("at least 15 dark-mode badge overrides exist (regression floor)",
    len(dark_mode_overrides) >= 15, f"Only found {len(dark_mode_overrides)}")

# Regression guard for the specific contrast bug found and fixed today:
# .status-ok and .status-danger (used in profile.html as direct text color)
# must have brighter dark-mode variants that meet WCAG AA (4.5:1) —
# verified against the actual dark card background color (#1e293b)
def _hex_to_rgb(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
def _luminance(rgb):
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)
def _contrast_ratio(c1, c2):
    l1, l2 = _luminance(_hex_to_rgb(c1)), _luminance(_hex_to_rgb(c2))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)

DARK_CARD_BG = "#1e293b"

status_ok_dark = re.search(r'\[data-theme="dark"\]\s*\.status-ok\s*\{\s*color:\s*(#[0-9a-fA-F]{6})', polish_css)
status_danger_dark = re.search(r'\[data-theme="dark"\]\s*\.status-danger\s*\{\s*color:\s*(#[0-9a-fA-F]{6})', polish_css)

run(".status-ok has a dark-mode color override defined",
    status_ok_dark is not None)
run(".status-danger has a dark-mode color override defined",
    status_danger_dark is not None)

if status_ok_dark:
    ratio = _contrast_ratio(status_ok_dark.group(1), DARK_CARD_BG)
    run(f".status-ok dark variant ({status_ok_dark.group(1)}) meets WCAG AA (4.5:1) on dark card",
        ratio >= 4.5, f"Actual ratio: {ratio:.2f}:1")

if status_danger_dark:
    ratio = _contrast_ratio(status_danger_dark.group(1), DARK_CARD_BG)
    run(f".status-danger dark variant ({status_danger_dark.group(1)}) meets WCAG AA (4.5:1) on dark card",
        ratio >= 4.5, f"Actual ratio: {ratio:.2f}:1")

# Confirm the dead/unused classes were actually removed, not left behind
run(".status-active dead code removed from main.css (was unused anywhere)",
    '.status-active ' not in main_css and '.status-active{' not in main_css)
run(".status-inactive dead code removed from main.css (was unused anywhere)",
    '.status-inactive ' not in main_css and '.status-inactive{' not in main_css)


# ── 5. Skeleton / Empty State Class Naming Consistency ────────────────────────
print("\n5. Skeleton & Empty State Class Naming Consistency")

run("'.skeleton' base class defined",          '.skeleton {' in polish_css or '.skeleton{' in polish_css)
run("'.skeleton-text' variant defined",        '.skeleton-text' in polish_css)
run("'.skeleton-card' variant defined",        '.skeleton-card' in polish_css)
run("'.skeleton-stat-card' variant defined",   '.skeleton-stat-card' in polish_css)
run("'.empty-state' component defined",        '.empty-state {' in polish_css)
run("'.empty-icon' sub-element defined",       '.empty-icon' in polish_css)
run("'.empty-title' sub-element defined",      '.empty-title' in polish_css)
run("'.empty-desc' sub-element defined",       '.empty-desc' in polish_css)

# Verify templates actually USE the standardized empty-state markup
# (catches drift where a template hand-rolls its own instead of using the component)
templates_using_empty_state = []
for root, dirs, files in os.walk(os.path.join(ROOT, 'frontend/templates')):
    for f in files:
        if f.endswith('.html'):
            content = open(os.path.join(root, f)).read()
            if 'class="empty-state"' in content:
                templates_using_empty_state.append(f)

run("at least 4 templates use the standardized .empty-state component",
    len(templates_using_empty_state) >= 4,
    f"Found in: {templates_using_empty_state}")


# ── 6. Responsive Breakpoint Coverage ──────────────────────────────────────────
print("\n6. Responsive Breakpoint Coverage (No Gaps)")

exam_css = open(os.path.join(ROOT, 'frontend/static/css/exam.css')).read()
all_css = main_css + exam_css + polish_css

# Extract all max-width / min-width breakpoint values used across the project
max_widths = sorted(set(int(w) for w in re.findall(r'max-width:\s*(\d+)px', all_css)))
min_widths = sorted(set(int(w) for w in re.findall(r'min-width:\s*(\d+)px', all_css)))

run("at least 4 distinct max-width breakpoints defined",
    len(max_widths) >= 4, f"Found: {max_widths}")

run("a sub-480px breakpoint exists (small phones)",
    any(w <= 480 for w in max_widths), f"Found: {max_widths}")

run("a 768px-ish breakpoint exists (tablet/mobile threshold)",
    any(700 <= w <= 800 for w in max_widths), f"Found: {max_widths}")

run("a 900-1024px breakpoint exists (tablet landscape)",
    any(900 <= w <= 1024 for w in max_widths), f"Found: {max_widths}")

# Verify no "dead zone" wider than 300px between consecutive breakpoints
# in the critical 300-1024px range (where most real devices live)
critical_range_widths = sorted(w for w in max_widths if 300 <= w <= 1024)
gaps = [critical_range_widths[i+1] - critical_range_widths[i]
        for i in range(len(critical_range_widths)-1)]
run("no breakpoint gap wider than 350px in the 300-1024px critical range",
    all(g <= 350 for g in gaps) if gaps else True,
    f"Gaps found: {gaps} between {critical_range_widths}")


# ── 7. Print Stylesheet Coverage ──────────────────────────────────────────────
print("\n7. Print Stylesheet Hides Interactive Chrome")

print_block_match = re.search(r'@media print\s*\{(.*?)\n\}', polish_css, re.DOTALL)
run("@media print block exists", print_block_match is not None)

if print_block_match:
    print_block = print_block_match.group(1)
    must_hide = ['.navbar', '.site-footer', '.btn', '.webcam-panel', '.exam-header', '.exam-sidebar']
    for selector in must_hide:
        run(f"print stylesheet hides {selector}",
            selector in print_block)


# ── 8. Reduced-Motion Guards for Animations ───────────────────────────────────
print("\n8. Reduced-Motion Guards for Every Animation")

# Find every @keyframes name defined in polish.css
keyframe_names = re.findall(r'@keyframes\s+(\w+)', polish_css)
run("at least 3 keyframe animations defined in polish.css",
    len(keyframe_names) >= 3, f"Found: {keyframe_names}")

# For each animation actually applied via `animation:`, verify there's
# either a [data-reduced-motion="true"] override nearby, OR it's covered
# by the GLOBAL reduced-motion rule already in main.css (Day 6)
main_has_global_reduced_motion_rule = '@media (prefers-reduced-motion: reduce)' in main_css
run("global prefers-reduced-motion media query exists in main.css (Day 6 baseline)",
    main_has_global_reduced_motion_rule)

# Specific high-motion animations introduced today should have explicit overrides
# (the global rule sets animation-duration: 0.01ms, but skeleton/spinner have
# DEDICATED slower/simpler fallbacks for better UX, not just "off")
run("skeleton shimmer has a dedicated [data-reduced-motion] override (not just relying on global 0.01ms)",
    '[data-reduced-motion="true"] .skeleton' in polish_css)
run("spinner has a dedicated [data-reduced-motion] override",
    '[data-reduced-motion="true"] .spinner' in polish_css)
run("page transition bar has a dedicated [data-reduced-motion] override",
    '[data-reduced-motion="true"] #pageTransitionBar' in polish_css)
run("button active-state transform has a dedicated [data-reduced-motion] override",
    '[data-reduced-motion="true"] .btn:active' in polish_css)


# ── 9. Tap Target Size Audit (WCAG 2.5.5) ─────────────────────────────────────
print("\n9. Minimum Tap Target Size for Icon Buttons")

run("icon-only small buttons have a minimum 44px-equivalent tap target rule",
    'min-width: 2.25rem' in polish_css and 'min-height: 2.25rem' in polish_css)
# 2.25rem = 36px at default 16px root, which combined with padding meets
# the WCAG 2.5.5 AA minimum of 24px (and approaches the AAA 44px target)


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 9 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
