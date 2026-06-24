# 🛡️ EduShield NG

**AI-powered secure online examination platform built for Nigeria's
education system.** Designed to reduce examination malpractice while
remaining accessible to students who speak Hausa, Yoruba, Igbo, or
English, and to students with visual or motor disabilities.

Built over 10 days as a complete, production-ready full-stack
application — not a tutorial demo. Every feature listed below is
implemented, tested, and verified, not aspirational.

---

## What This Actually Is

A web application where:

- **Students** register, log in, take timed multiple-choice exams with
  AI webcam monitoring and anti-cheat detection, and review their
  results with per-question explanations.
- **Admins** create and publish exams, manage students, review
  integrity logs (with photographic evidence for serious violations),
  and export results to CSV for institutional records.
- **Everyone** can use the platform in their preferred language with
  text-to-speech support, keyboard-only navigation, high contrast
  mode, and large-text mode.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask, SQLAlchemy ORM |
| Database | PostgreSQL (production), SQLite (local dev) |
| Frontend | Server-rendered Jinja2 templates, vanilla JavaScript (no framework) |
| AI / Face Detection | face-api.js (runs entirely client-side, no video leaves the browser) |
| Auth | Flask-Login, Werkzeug password hashing (pbkdf2) |
| Forms & CSRF | Flask-WTF |
| Rate Limiting | Flask-Limiter |
| Deployment | Render (web service + managed PostgreSQL), gunicorn |

---

## Core Features

### 🔐 Authentication & Access Control
- Student self-registration with live email-availability and
  password-strength checking
- Role-based access control (student / admin), enforced server-side
  on every protected route
- Session security: HttpOnly + SameSite cookies, bounded session
  lifetime, forced re-login after password change

### 📝 Examination Engine
- Server-authoritative countdown timer (the timer lives in the
  database, not just the browser — refreshing or DevTools cannot
  extend it)
- Question and answer-option shuffling, computed server-side
- Auto-save on every answer with a network-failure retry queue
- Automatic server-side score calculation and pass/fail determination

### 🛡️ Anti-Cheat Module
- Tab-switch and window-blur detection with a configurable warning
  threshold before auto-submission
- Copy/paste/right-click/keyboard-shortcut prevention (27-combination
  blocklist covering Windows and Mac)
- Fullscreen-exit detection, screen-share API interception
- Every event server-logged with a server-side timestamp (never
  trusts client-reported time)

### 🤖 AI Proctoring
- face-api.js webcam monitoring: face-absence and multiple-face
  detection
- One-time face calibration captures a 128-dimension face descriptor
  (a mathematical fingerprint, never a stored photo) for identity
  verification during the exam
- Evidence snapshots (small JPEG thumbnails, not continuous
  recording) automatically captured only for high-severity violations

### ♿ Accessibility
- Full text-to-speech: reads questions, options, and timer
  announcements aloud
- 4-language support (English, Hausa, Yoruba, Igbo) via a custom
  translation system, covering UI text, anti-cheat warnings, and
  TTS locale selection
- Keyboard-only navigation, ARIA live regions, skip-to-content link,
  focus-trapped modals
- High contrast mode and large-text mode, independently toggleable
  from dark/light theme

### 📊 Admin Dashboard
- Exam builder: create exam shells, add questions, publish/close
  lifecycle (cannot publish an exam with zero questions)
- Student management: search, suspend/reactivate, verify, unflag
- Integrity log viewer with severity filtering and evidence-photo
  viewing
- Per-exam results table with CSV export (filenames sanitized against
  path traversal)

---

## Security Posture

This project includes a genuine 12-category penetration test suite
(`tests/test_day8_pentest.py`) covering SQL injection, XSS, CSRF,
session fixation, authorization bypass (IDOR), path traversal,
command injection, SSTI, open redirect, and CRLF injection attempts.

**Two real vulnerabilities were found and fixed during development**
(documented in `docs/SECURITY_AUDIT.md`):
1. An XSS sanitization gap where closing tags survived filtering
2. A missing `<svg onload=...>` vector that wasn't in the original
   dangerous-tags list

A standalone verification script (`scripts/verify_real_security.sh`)
imports the actual production source code — not test mirrors — and
re-runs real attack payloads against it, so this class of regression
can be caught immediately in CI.

---

## Project Structure

```
edushield/
├── backend/
│   ├── app.py                 # Application factory
│   ├── config.py              # Dev/Production/Testing configs
│   ├── models/models.py       # 6 database models
│   ├── routes/                # auth, exam, admin, api blueprints
│   ├── utils/                 # forms, security, translations
│   └── middleware/            # HTTP security headers
├── frontend/
│   ├── static/
│   │   ├── css/                # main, exam, polish stylesheets
│   │   └── js/                 # anti_cheat, face_monitor, exam_engine,
│   │                            accessibility, main
│   └── templates/              # auth, exam, admin, error pages
├── tests/                      # 681 tests across 10 test files
│                                # (24 in Day 1's pytest-based model tests,
│                                #  657 in Days 2-10's standalone runners —
│                                #  verified by summing each file's own
│                                #  reported pass count, not estimated)
├── scripts/                    # db seeding, real-source security check,
│                                # production database initialization
├── netlify-landing/             # Optional static marketing page (see
│                                # "Deployment" section below for why this
│                                # is separate from the actual application)
└── docs/                       # this README, deployment guide, security audit
```

---

## Running Locally

```bash
git clone <your-repo-url>
cd edushield
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit SECRET_KEY and other values
python run.py
# Visit http://localhost:5000
```

Seed sample data (3 students, 1 admin, 2 exams with questions):

```bash
python scripts/seed_db.py
```

Run the test suite:

```bash
for f in tests/test_day*.py; do python "$f"; done
bash scripts/verify_real_security.sh
```

---

## Deployment

**The application itself — Flask backend, PostgreSQL database, all
authentication and exam logic — runs entirely on Render.** Render
supports persistent Python web services with a managed database,
which this application requires.

**Netlify hosts an optional static marketing/landing page**
(`netlify-landing/index.html`) that links out to the real application
on Render. Netlify's hosting model (static files + serverless
functions) cannot run a persistent Flask process or hold a database
connection, so it was never going to host the actual application —
being upfront about that distinction here rather than implying
otherwise.

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the complete
step-by-step Render deployment guide, including environment variable
configuration, the PostgreSQL `postgres://` → `postgresql://` URL
fix, and an honest list of free-tier limitations (sleep timeout,
90-day database expiry) that should be communicated to stakeholders
before relying on this for real examinations.

---

## What's Intentionally Out of Scope

In the interest of being precise about what this project is and
isn't:

- **No payment processing** — not a requirement for an institutional
  exam tool
- **No native mobile app** — the responsive web interface covers
  phone/tablet use
- **No video recording/storage** — by design, for privacy; only
  small evidence snapshots for high-severity violations
- **No real-time invigilator live-view** — the `invigilator` role
  exists in the data model for future extension but isn't built out
- **Native TTS voices for Hausa/Yoruba/Igbo depend on the browser** —
  text translation is complete; pronunciation quality varies by
  platform until more browsers ship native voices for these languages

---

## License & Attribution

Built as a complete educational/portfolio project demonstrating
full-stack development, security engineering, and accessibility
design for a real-world Nigerian context.
