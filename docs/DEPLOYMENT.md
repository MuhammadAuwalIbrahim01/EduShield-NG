# EduShield NG — Production Deployment Guide

This document walks through deploying EduShield NG to Render, migrating
from SQLite to PostgreSQL, and the pre-launch checklist to run through
before pointing real students at the platform.

---

## 1. Architecture Recap — What Runs Where

```
┌─────────────────────────────────────────────────────────┐
│  Render (required)                                       │
│  ├── Web Service: Flask + gunicorn (the actual app)      │
│  └── PostgreSQL Database (managed, attached automatically)│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Netlify (optional — NOT a substitute for Render)         │
│  └── Static marketing/landing page that LINKS to the      │
│      real app running on Render. See Section 6.           │
└─────────────────────────────────────────────────────────┘
```

**Why not split the Flask app across both?** Netlify does not run
persistent Python processes or maintain a database connection — it
serves static files and short-lived serverless functions. EduShield
NG's session management, exam timers, and database all require a
long-running server process, which only Render (in this two-service
setup) provides.

---

## 2. Pre-Deployment Checklist

Run these BEFORE pushing to Render:

```bash
# 1. All tests pass locally
pytest tests/ -v
# or, if pytest extensions aren't installed locally:
for f in tests/test_day*.py; do python "$f"; done

# 2. Real-source security verification passes
bash scripts/verify_real_security.sh

# 3. No secrets committed to git
git log --all --full-history -- .env
# Should return NOTHING. If it returns commits, your .env was
# committed at some point — rotate every secret in it immediately,
# even after removing it from git history.

# 4. .gitignore actually excludes .env and *.db
cat .gitignore | grep -E "^\.env$|^\*\.db$"

# 5. requirements.txt has no unused packages (Day 10 audit found
#    and removed Pillow — verify nothing similar has crept back in)
```

---

## 3. Deploying to Render — Step by Step

### Option A: Blueprint Deploy (Recommended — uses render.yaml)

1. Push your code to a GitHub repository (Render deploys from GitHub,
   GitLab, or Bitbucket — not from a local zip upload for Blueprints).
2. In the Render dashboard, click **New +** → **Blueprint**.
3. Connect your GitHub repository and select it.
4. Render reads `render.yaml` automatically and shows you a preview of
   what it will create: one Web Service + one PostgreSQL database.
5. Click **Apply**. Render provisions both resources.
6. Go to the new web service's **Environment** tab and set
   `ADMIN_PASSWORD` manually (we marked it `sync: false` in
   `render.yaml` specifically so it's never committed to git).
7. Wait for the first deploy to finish (check the **Logs** tab).

### Option B: Manual Setup (if you want to understand each piece)

1. **Create the database first:**
   - New + → PostgreSQL
   - Name: `edushield-db`
   - Region: match what you'll choose for the web service
   - Plan: Free (see the 90-day expiry warning in `render.yaml`)
   - Click **Create Database**, wait for it to provision
   - Copy the **Internal Database URL** shown on its dashboard page

2. **Create the web service:**
   - New + → Web Service
   - Connect your repository
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn wsgi:app --workers 4 --bind 0.0.0.0:$PORT --timeout 120`
   - Add environment variables (see Section 4 below)
   - Click **Create Web Service**

---

## 4. Required Environment Variables

Set these in the Render dashboard's **Environment** tab (or they're
auto-set by the Blueprint if you used `render.yaml`):

| Variable | Value | Notes |
|---|---|---|
| `FLASK_ENV` | `production` | Switches to `ProductionConfig` |
| `SECRET_KEY` | (auto-generated) | Never reuse your local dev value |
| `DATABASE_URL` | (auto-linked from the database) | Don't set manually — Render injects this |
| `ALLOWED_ORIGINS` | `https://your-app.onrender.com` | Update after first deploy when you know your real URL |
| `ADMIN_EMAIL` | `admin@edushield.ng` | The seed admin account email |
| `ADMIN_PASSWORD` | (set manually, never committed) | **Change immediately after first login** |

---

## 5. First Deploy Verification

Once Render shows "Live" status:

```bash
# 1. Health check responds
curl https://your-app.onrender.com/api/health
# Expected: {"status": "ok", "service": "EduShield NG", "db": "connected"}

# 2. Login page loads
curl -I https://your-app.onrender.com/auth/login
# Expected: HTTP/2 200

# 3. Log in as the seed admin and IMMEDIATELY change the password
#    via Profile > Change Password — the seed password from
#    ADMIN_PASSWORD should never remain active long-term.

# 4. Create one test exam, add 2-3 questions, publish it, and
#    take it as a test student account to confirm the full flow
#    works end-to-end in the real production environment —
#    not just in local dev.
```

---

## 6. Optional: Netlify Companion Landing Page

If you want a fast-loading marketing page at a custom domain that
then directs visitors to the real application on Render:

1. Create a simple static `index.html` (NOT the Flask app) with your
   institution's branding and a prominent "Launch EduShield NG" button
   linking to `https://your-app.onrender.com`.
2. In Netlify: **New site from Git** → connect the repo (or a
   dedicated landing-page-only repo) → set the publish directory to
   wherever that static `index.html` lives.
3. Netlify deploys it instantly and gives you a free `*.netlify.app`
   subdomain, or attach your own custom domain.

This is genuinely optional — EduShield NG is fully functional accessed
directly via its Render URL with no Netlify component at all.

---

## 7. Database Migration Notes (SQLite → PostgreSQL)

You do NOT need to manually migrate schema — `db.create_all()` in
`app.py`'s `create_app()` function runs automatically on startup and
creates all tables fresh in the new PostgreSQL database. This means:

- **Your local SQLite data does NOT automatically transfer.** If you
  have real student/exam data in local SQLite you need in production,
  you must export and import it manually (out of scope for this guide
  — for a fresh production launch, this typically isn't needed).
- The seed admin account IS automatically created on first startup via
  `_seed_admin()` in `app.py`, using `ADMIN_EMAIL`/`ADMIN_PASSWORD`
  from your environment variables.
- Run `python scripts/seed_db.py` against production ONLY if you want
  the sample exam data for demo purposes — skip it for a real launch.

---

## 8. Known Limitations to Communicate to Stakeholders

Being upfront about these now avoids surprises later:

1. **Free tier sleeps after 15 minutes of inactivity** and takes
   30-50 seconds to wake on the next request. The first student to
   visit after a quiet period will experience this delay.
2. **Free PostgreSQL expires after 90 days.** Set a calendar reminder
   well before this to upgrade the plan or migrate data out.
3. **No native TTS voices for Hausa/Yoruba/Igbo** in most browsers —
   the text is correctly translated, but pronunciation falls back to
   whatever default voice the browser provides (documented in Day 6).
4. **Face calibration requires camera access** — students on shared
   computers or those without a working webcam cannot take
   webcam-required exams; admins should offer non-webcam exam
   variants for these cases.
