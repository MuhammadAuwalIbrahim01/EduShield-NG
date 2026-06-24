# Security Audit Record — EduShield NG

This document records every **real** vulnerability discovered during
development, how it was found, and how it was fixed. These are not
hypothetical risks — each one was demonstrated against the actual
source code before being patched.

---

## Finding 1: XSS Sanitization Gap — Closing Tags Survived Filtering

**Discovered:** Day 8, while running real attack payloads against the
actual `backend/utils/security.py` source file (not a test mirror).

**The bug:**

```python
sanitize_input('<script>alert(1)</script>Hello')
# Before fix: 'alert(1)</script>Hello'
# The opening <script> tag was removed, but the visible text content
# and the closing </script> tag survived.
```

**Root cause:** The original regex `<(script|...)[^>]*>` only matched
opening tags. It never accounted for paired elements whose *content*
(not just the tag) is the dangerous part.

**Fix:** Added `_DANGEROUS_PAIRED_TAGS`, which matches the entire
element including content, using `DOTALL` so multi-line payloads are
caught:

```python
_DANGEROUS_PAIRED_TAGS = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
```

**Verification:** Re-ran the same payload and 13 variants (including
case-randomization attempts like `<ScRiPt>`) against the real source
file after the fix. All confirmed clean.

---

## Finding 2: `<svg onload=...>` Not Recognized as Dangerous

**Discovered:** Day 8, immediately after fixing Finding 1, while
testing adjacent payload variants to check whether the fix
generalized.

**The bug:**

```python
sanitize_input('<svg onload=alert(1)>')
# Before fix: '<svg alert(1)>'
# The onload= attribute was stripped by an unrelated regex, but the
# <svg> tag itself was never in the dangerous-tags list, so it (and
# the bare alert(1) text) survived intact.
```

**Root cause:** The dangerous-tags list was built around "obviously
script-like" tags (`script`, `iframe`, `object`) without accounting
for the broader set of HTML elements that support executable
event-handler attributes. `<svg>`, `<video>`, `<audio>`, `<base>`,
`<details>`, and `<marquee>` all support `onload`/`onerror`/
`ontoggle`/`onstart` and are documented XSS vectors.

**Fix:** Extended the stray-tag and wrapper-tag patterns to include
all six element types.

**Verification:** Tested 14 real payloads (including a nested
`<svg><script>alert(1)</script></svg>` case) against the real source
file post-fix. All confirmed clean. Also verified the fix introduces
no false positives against legitimate exam content containing bare
`<`/`>` characters (e.g. math comparison expressions like `x > 5`).

---

## Finding 3: Missing `postgres://` → `postgresql://` URL Scheme Handling

**Discovered:** Day 10, during pre-deployment configuration review,
by cross-referencing Render/Heroku deployment documentation against
our actual `ProductionConfig` class.

**The bug:** `ProductionConfig.SQLALCHEMY_DATABASE_URI` was set
directly from `os.environ.get("DATABASE_URL")` with no transformation.
SQLAlchemy 1.4+ (we use 2.0.31) rejects the `postgres://` URL scheme
outright — `create_engine()` raises immediately if handed one. Some
PostgreSQL providers (including older Render connection strings,
historically Heroku) issue URLs with this exact scheme.

**Why this matters more than a typical bug:** this would not surface
in local development (SQLite doesn't have this scheme issue) or even
in most manual testing — it would only appear as a production
crash-loop on first deploy, with a confusing low-level SQLAlchemy
error rather than an obvious message.

**Fix:**

```python
_raw_database_url = os.environ.get("DATABASE_URL", "")
if _raw_database_url.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URI = _raw_database_url.replace(
        "postgres://", "postgresql://", 1
    )
else:
    SQLALCHEMY_DATABASE_URI = _raw_database_url
```

**Verification:** Tested three scenarios directly against the loaded
config module: (1) a `postgres://` URL is correctly rewritten, (2) an
already-correct `postgresql://` URL is left untouched (no
double-rewriting), (3) a missing `DATABASE_URL` environment variable
doesn't crash with an `AttributeError` on `None`.

---

## Finding 4 (Minor): Unused Dependency Increasing Attack Surface

**Discovered:** Day 10, during a requirements.txt audit against
actual imports used across the codebase.

**The issue:** `Pillow==10.4.0` was listed in `requirements.txt` from
Day 1 but never imported anywhere — face snapshot handling ended up
being implemented entirely client-side as base64 data URIs (Day 5),
making server-side image processing unnecessary.

**Why this matters:** every dependency is attack surface — a
supply-chain compromise of an unused package still executes during
`pip install`, and an unused package still needs security patches
tracked even though it provides zero functionality.

**Fix:** Removed from `requirements.txt`.

---

## Methodology Notes

A pattern worth naming explicitly: Findings 1 and 2 were caught
specifically because Day 8's testing imported the **actual production
source file** rather than relying solely on mirrored test logic. The
mirror-based tests (93 of them) all passed cleanly and gave false
confidence — they tested a *re-implementation* of the sanitization
logic, not the real code path a live HTTP request would hit. The
lesson generalizes: a test suite that never imports the real module
under test can pass indefinitely while the real module is broken.

This is why `scripts/verify_real_security.sh` exists as a permanent,
standalone tool — not folded silently into the regular test suite —
so it gets run deliberately whenever `security.py` changes, as an
explicit confidence checkpoint beyond unit tests.
