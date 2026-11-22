import io
import os
import time
import uuid
from datetime import date
from collections import defaultdict, deque

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import config, db, triage
from .routing import DISCLAIMER, suggested_authority

ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

app = FastAPI(title="CivicPulse", version="0.1.0")
_conn = None
_hits = defaultdict(deque)  # ip -> deque[timestamps] for POST /api/reports


def get_conn():
    global _conn
    if _conn is None:
        _conn = db.connect(config.DB_PATH)
    return _conn


def analyze_with_cap(image_bytes: bytes, note: str) -> triage.TriageResult:
    """Live AI calls are capped per UTC day so public unauthenticated uploads
    cannot create unbounded API usage. Over cap -> honest 'limited' state."""
    if not config.GEMINI_API_KEY:
        return triage.TriageResult(state="pending")
    # On a public deployment, live AI stays off unless explicitly enabled after
    # the key's no-cost status is verified. The daily cap below is a
    # best-effort call counter only: it resets with the ephemeral filesystem
    # and is not spend authorization or a dollar limit.
    public_deploy = bool(os.environ.get("RENDER")) or os.environ.get("SEED_DEMO") == "1"
    if public_deploy and os.environ.get("AI_LIVE_ENABLED") != "true":
        return triage.TriageResult(state="disabled")
    day = date.today().isoformat()
    conn = get_conn()
    if db.ai_calls_today(conn, day) >= config.AI_DAILY_CALL_CAP:
        return triage.TriageResult(state="limited")
    db.ai_increment(conn, day)
    return triage.analyze_image(image_bytes, "image/jpeg", note)


def rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MINUTE:
        return True
    q.append(now)
    return False


def reencode_image(raw: bytes, mime: str) -> bytes:
    """Validate and re-encode (strips EXIF/metadata). Raises ValueError."""
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


@app.post("/api/reports")
async def create_report(
    request: Request,
    image: UploadFile = File(...),
    description: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    demo: bool = Form(False),
):
    ip = request.client.host if request.client else "unknown"
    if rate_limited(ip):
        raise HTTPException(429, "Too many submissions. Try again in a minute.")
    if image.content_type not in ALLOWED_MIME:
        raise HTTPException(400, "Only JPEG, PNG or WebP photos are accepted.")
    raw = await image.read()
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Photo is too large.")
    try:
        clean = reencode_image(raw, image.content_type)
    except Exception:
        raise HTTPException(400, "That file does not look like a valid image.")

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.jpg"
    with open(os.path.join(config.UPLOAD_DIR, fname), "wb") as f:
        f.write(clean)

    result = analyze_with_cap(clean, description)
    authority = suggested_authority(result.category) if result.state == "done" else None
    rid = db.insert_report(
        get_conn(),
        created_at=time.time(),
        description=description[:1000],
        lat=lat, lon=lon,
        image_path=fname,
        analysis_state=result.state,
        category=result.category, severity=result.severity,
        confidence=result.confidence, rationale=result.rationale,
        suggested_authority=authority,
        status="reported", model=result.model, error=result.error,
        source="demo" if demo else "user",
    )
    return db.get_report(get_conn(), rid)


@app.get("/api/reports")
def list_reports():
    return {"reports": db.list_reports(get_conn()), "routing_disclaimer": DISCLAIMER}


@app.get("/api/stats")
def get_stats():
    return db.stats(get_conn())


@app.patch("/api/reports/{rid}/status")
def set_status(rid: int, payload: dict, x_admin_token: str | None = Header(None)):
    if not config.ADMIN_TOKEN:
        raise HTTPException(503, "Status changes are disabled: ADMIN_TOKEN is not set.")
    if x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(401, "Invalid admin token.")
    status = payload.get("status", "")
    try:
        ok = db.update_status(get_conn(), rid, status)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "Report not found.")
    return db.get_report(get_conn(), rid)


@app.get("/uploads/{fname}")
def get_upload(fname: str):
    if "/" in fname or ".." in fname:
        raise HTTPException(400, "bad name")
    path = os.path.join(config.UPLOAD_DIR, fname)
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="image/jpeg")


def seed_demo_if_empty():
    """On hosts with ephemeral disks (e.g. Render free), re-seed the three
    attributed demo reports after every restart when SEED_DEMO=1."""
    if os.environ.get("SEED_DEMO") != "1":
        return
    conn = get_conn()
    if db.stats(conn)["total"] > 0:
        return
    demo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo")
    cases = [
        ("pothole.jpg", "Deep potholes in the carriageway, bikes swerving around them", 17.4401, 78.4989),
        ("garbage.jpg", "Garbage dump not cleared for days, smell spreading", 17.4439, 78.5012),
        ("water_main.jpg", "Water main burst, road flooded", 17.4372, 78.4945),
    ]
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    for fname, desc, lat, lon in cases:
        path = os.path.join(demo_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            clean = reencode_image(f.read(), "image/jpeg")
        out = f"{uuid.uuid4().hex}.jpg"
        with open(os.path.join(config.UPLOAD_DIR, out), "wb") as f:
            f.write(clean)
        # Boot seeding NEVER calls AI. This one result is a historical recording
        # from the deployed public form on 22 Nov 2026 at 22:38:36 IST, not a
        # fresh inference, current local hazard, or report filed with an authority.
        # Input: demo/pothole.jpg, SHA256 aac0b3542eebcc40600d5cf8c55cf01493160fb0c1a18d5560b00ae2f5699b80
        # Original response: https://civicpulse-k0go.onrender.com/api/reports
        # Verified on commit ef665f2; full output preserved with demo evidence.
        result = triage.TriageResult(state="pending")
        authority = None
        source = "demo"
        created_at = {"pothole.jpg": 1795367283.844938, "garbage.jpg": 1795367284.0346038, "water_main.jpg": 1795367284.1331096}[fname]
        if fname == "pothole.jpg":
            result = triage.TriageResult(
                state="done", category="road_damage", severity="high",
                confidence=0.95,
                rationale="Severe pavement deterioration with deep potholes poses a hazard to vehicles.",
                model="gemini-3.5-flash",
            )
            desc = "Recorded AI demo from 22 Nov 2026, 22:38 IST. Sample photo only; not re-analyzed on restart or a current local report."
            lat = lon = None
            source = "recorded_demo"
            created_at = 1795367316.9761746
            authority = "Municipal roads/engineering department"
        db.insert_report(
            conn, created_at=created_at, description=desc, lat=lat, lon=lon,
            image_path=out, analysis_state=result.state, category=result.category,
            severity=result.severity, confidence=result.confidence,
            rationale=result.rationale, suggested_authority=authority,
            status="reported", model=result.model, error=result.error, source=source,
        )


@app.on_event("startup")
def _startup():
    seed_demo_if_empty()


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
