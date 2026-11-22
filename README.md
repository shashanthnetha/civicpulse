# CivicPulse

AI-assisted civic grievance triage — IDEA//FORGE Online Hackathon, Track 1,
Problem 2 (Transparent Civic Grievance & Infrastructure Triage System).

Citizens report issues (road damage, garbage, water leaks, streetlights,
pollution, flooding) with a photo and optional location. A Gemini vision model
classifies the issue, estimates severity (assistive, not a safety rating) and
suggests the type of authority that usually handles it. A public dashboard
shows all reports, summary counts and a map.

**Honest scope:** "Suggested routing" is only a suggestion. This app does not
file anything with any government authority. If no Gemini key is configured,
reports are stored and marked "AI analysis pending" — the app never invents a
classification.

## Requirements
- Python 3.10+ (macOS: `brew install python` if needed)
- A Gemini API key for live AI analysis (create/view on your own Google
  account at https://aistudio.google.com). The app runs without it, but
  photo analysis stays "pending".

## Setup (macOS)
```bash
cd civicpulse
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: paste your GEMINI_API_KEY, set ADMIN_TOKEN to any long random string
```

## Run
```bash
uvicorn app.main:app --reload
```
Open http://localhost:8000 — submit a report with a real photo, watch it
appear on the dashboard. API docs at http://localhost:8000/docs.

## Test
```bash
python3 -m pytest tests/ -q
```
21 tests: triage JSON parsing/validation, routing map, submission validation,
EXIF stripping, rate limiting, admin-token protection, honest no-key behavior.

## Configuration (.env)
| Key | Purpose |
|---|---|
| GEMINI_API_KEY | Enables live AI photo analysis |
| GEMINI_MODEL | Default `gemini-3.8-flash` (stable model code from the official Gemini API docs). Change if Google retires it. |
| ADMIN_TOKEN | Required to enable status changes (acknowledge/resolve). Unset = status endpoint disabled. |
| DB_PATH / UPLOAD_DIR | Storage locations |
| MAX_UPLOAD_MB / RATE_LIMIT_PER_MINUTE | Abuse limits |
| AI_LIVE_ENABLED | Must be `true` for live AI calls on a public deployment (Render / SEED_DEMO). Default off: deploys run with AI disabled until the key's no-cost status is verified. |
| AI_DAILY_CALL_CAP | Best-effort live-call counter per UTC day (default 30). NOT a spend cap: the count resets when the host's ephemeral filesystem resets, and it authorizes no spend. Over the cap, reports are stored as "AI daily limit reached". |

## Security and limitations (read before deploying)
This is a hackathon MVP, not a hardened public service:
- Submissions are rate-limited per IP and uploads are validated + re-encoded
  (EXIF stripped), but there is no user authentication on reads or reports.
- Status changes need the ADMIN_TOKEN header; keep it secret.
- SQLite is single-instance; use a real database for multi-user deployment.
- The API key lives only in the server-side .env. Never commit .env or photos.
- Photo privacy: inform citizens photos appear on a public dashboard.

## Deploying (recommended route: Render free tier)
The hackathon requires a working MVP link anyone can open. Recommended:
Render's free web service (render.yaml included). Steps once approved:
1. Push this repo to GitHub (public or private - your choice).
2. Create a Render account (GitHub sign-in works) and a new Web Service from
   the repo; Render reads render.yaml automatically.
3. In the Render dashboard set GEMINI_API_KEY and ADMIN_TOKEN as env vars.
4. Live AI on the public deployment stays DISABLED by default. Only after the
   key's no-cost status is verified (free tier / no billing on the project),
   set AI_LIVE_ENABLED=true in the dashboard to turn it on.

Verified free-tier limits (render.com/docs/free, Nov 2026): sleeps after
15 min idle with about a 1-minute cold start (judges may see a loading page);
filesystem is ephemeral, so the SQLite data and uploads reset on every
redeploy/restart/spin-down - SEED_DEMO=1 (set in render.yaml) re-seeds the
three attributed demo reports on boot so the dashboard is never empty;
750 free instance-hours per month. Demo-grade only, not production.
Ruled out: Hugging Face Spaces (Docker/Gradio Spaces now need a paid plan;
only static Spaces are free) and PythonAnywhere free (1-month expiry,
100 CPU-seconds/day, WSGI-first).

## Demo data
`demo/seed_demo.py` seeds three real, openly licensed Wikimedia Commons
photos (credits and license links in `demo/ATTRIBUTION.md`) through the public
API. Automated tests use synthetic generated images only.

## Credits
Built with FastAPI, SQLite, Leaflet + OpenStreetMap, and the Google Gemini API
(google-genai SDK). AI model output is credited to Gemini per the hackathon's
originality rules.
