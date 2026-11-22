import importlib
import io
import os

import pytest
from PIL import Image
from fastapi.testclient import TestClient

os.environ["DB_PATH"] = "/tmp/test_civicpulse.db"
os.environ["UPLOAD_DIR"] = "/tmp/test_uploads"
os.environ["ADMIN_TOKEN"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["RATE_LIMIT_PER_MINUTE"] = "5"

import app.config as cfg  # noqa: E402
import app.main as m  # noqa: E402


def make_png(w=64, h=64, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def client():
    os.environ["ADMIN_TOKEN"] = ""
    importlib.reload(cfg)
    importlib.reload(m)
    if os.path.exists("/tmp/test_civicpulse.db"):
        os.remove("/tmp/test_civicpulse.db")
    yield TestClient(m.app)
    os.environ["ADMIN_TOKEN"] = ""
    importlib.reload(cfg)
    importlib.reload(m)


def submit(client, desc="test pothole"):
    return client.post(
        "/api/reports",
        files={"image": ("p.png", make_png(), "image/png")},
        data={"description": desc, "lat": "17.4", "lon": "78.5"},
    )


def test_submit_without_key_stores_pending_honestly(client):
    r = submit(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["analysis_state"] == "pending"
    assert body["category"] is None and body["severity"] is None
    assert body["status"] == "reported"


def test_submit_rejects_non_image(client):
    r = client.post("/api/reports", files={"image": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 400


def test_submit_rejects_bad_mime(client):
    r = client.post("/api/reports", files={"image": ("x.gif", make_png(), "image/gif")})
    assert r.status_code == 400


def test_list_and_stats(client):
    submit(client, "one")
    submit(client, "two")
    reports = client.get("/api/reports").json()
    assert len(reports["reports"]) == 2
    assert "does not" in reports["routing_disclaimer"]
    stats = client.get("/api/stats").json()
    assert stats["total"] == 2 and stats["by_status"]["reported"] == 2


def test_status_change_disabled_without_admin_token_configured(client):
    rid = submit(client).json()["id"]
    r = client.patch(f"/api/reports/{rid}/status", json={"status": "acknowledged"},
                     headers={"X-Admin-Token": "anything"})
    assert r.status_code == 503


def test_status_change_requires_token_when_configured(client):
    os.environ["ADMIN_TOKEN"] = "secret-token"
    importlib.reload(cfg)
    importlib.reload(m)
    c = TestClient(m.app)
    r = c.post("/api/reports", files={"image": ("p.png", make_png(), "image/png")}, data={"description": "x"})
    rid = r.json()["id"]
    bad = c.patch(f"/api/reports/{rid}/status", json={"status": "acknowledged"}, headers={"X-Admin-Token": "wrong"})
    assert bad.status_code == 401
    ok = c.patch(f"/api/reports/{rid}/status", json={"status": "acknowledged"}, headers={"X-Admin-Token": "secret-token"})
    assert ok.status_code == 200 and ok.json()["status"] == "acknowledged"
    badstatus = c.patch(f"/api/reports/{rid}/status", json={"status": "bogus"}, headers={"X-Admin-Token": "secret-token"})
    assert badstatus.status_code == 400


def test_rate_limit_trips(client):
    codes = [submit(client, f"n{i}").status_code for i in range(7)]
    assert 429 in codes


def test_upload_served_and_traversal_blocked(client):
    body = submit(client).json()
    img = client.get("/uploads/" + body["image_path"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get("/uploads/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)


def test_exif_stripped_on_upload(client):
    body = submit(client).json()
    path = os.path.join("/tmp/test_uploads", body["image_path"])
    with Image.open(path) as img:
        assert img.format == "JPEG"
        assert not img.getexif()


def test_demo_flag_marks_source(client):
    r = client.post(
        "/api/reports",
        files={"image": ("p.png", make_png(), "image/png")},
        data={"description": "seeded", "demo": "true"},
    )
    assert r.status_code == 200 and r.json()["source"] == "demo"


def test_default_source_is_user(client):
    assert submit(client).json()["source"] == "user"


def test_seed_on_boot_marks_demo_reports():
    os.environ["SEED_DEMO"] = "1"
    importlib.reload(cfg)
    importlib.reload(m)
    if os.path.exists("/tmp/test_civicpulse.db"):
        os.remove("/tmp/test_civicpulse.db")
    with TestClient(m.app) as c:
        reports = c.get("/api/reports").json()["reports"]
    assert len(reports) == 3
    assert all(r["source"] in {"demo", "recorded_demo"} for r in reports)
    os.environ.pop("SEED_DEMO")
    importlib.reload(cfg)
    importlib.reload(m)


def test_ai_daily_cap_blocks_unbounded_calls():
    os.environ["AI_DAILY_CALL_CAP"] = "1"
    os.environ["GEMINI_API_KEY"] = "fake-key"
    importlib.reload(cfg)
    importlib.reload(m)
    calls = []
    def fake_analyze(img, mime, note=""):
        calls.append(1)
        from app.triage import TriageResult
        return TriageResult(state="done", category="garbage", severity="low",
                            confidence=0.5, rationale="x", model="fake")
    m.triage.analyze_image = fake_analyze
    c = TestClient(m.app)
    png = make_png()
    r1 = c.post("/api/reports", files={"image": ("a.png", png, "image/png")}, data={"description": "1"})
    r2 = c.post("/api/reports", files={"image": ("b.png", png, "image/png")}, data={"description": "2"})
    assert r1.json()["analysis_state"] == "done"
    assert r2.json()["analysis_state"] == "limited"
    assert len(calls) == 1
    os.environ["AI_DAILY_CALL_CAP"] = "30"
    os.environ["GEMINI_API_KEY"] = ""
    importlib.reload(cfg)
    importlib.reload(m)


def test_boot_seeding_never_calls_ai():
    os.environ["SEED_DEMO"] = "1"
    os.environ["GEMINI_API_KEY"] = "fake-key"
    importlib.reload(cfg)
    importlib.reload(m)
    def boom(*a, **k):
        raise AssertionError("AI must not be called during boot seeding")
    m.triage.analyze_image = boom
    if os.path.exists("/tmp/test_civicpulse.db"):
        os.remove("/tmp/test_civicpulse.db")
    with TestClient(m.app) as c:
        reports = c.get("/api/reports").json()["reports"]
    assert len(reports) == 3
    recorded = [r for r in reports if r["source"] == "recorded_demo"]
    assert len(recorded) == 1
    r = recorded[0]
    assert r["analysis_state"] == "done" and r["category"] == "road_damage"
    assert r["severity"] == "high" and r["confidence"] == 0.95
    assert r["model"] == "gemini-3.5-flash"
    assert r["created_at"] == 1795367316.9761746
    assert r["lat"] is None and r["lon"] is None
    assert "not re-analyzed" in r["description"]
    assert all(r["analysis_state"] == "pending" for r in reports if r["source"] == "demo")
    os.environ.pop("SEED_DEMO")
    os.environ["GEMINI_API_KEY"] = ""
    importlib.reload(cfg)
    importlib.reload(m)


def test_public_deploy_ai_disabled_by_default():
    os.environ["SEED_DEMO"] = "0"
    os.environ["RENDER"] = "true"
    os.environ["GEMINI_API_KEY"] = "fake-key"
    os.environ.pop("AI_LIVE_ENABLED", None)
    importlib.reload(cfg)
    importlib.reload(m)
    def boom(*a, **k):
        raise AssertionError("AI must not run on public deploy without AI_LIVE_ENABLED")
    m.triage.analyze_image = boom
    c = TestClient(m.app)
    r = c.post("/api/reports", files={"image": ("a.png", make_png(), "image/png")}, data={"description": "x"})
    assert r.json()["analysis_state"] == "disabled"
    os.environ["AI_LIVE_ENABLED"] = "true"
    calls = []
    def fake(img, mime, note=""):
        calls.append(1)
        from app.triage import TriageResult
        return TriageResult(state="done", category="garbage", severity="low", confidence=0.5, rationale="x", model="fake")
    m.triage.analyze_image = fake
    r2 = c.post("/api/reports", files={"image": ("b.png", make_png(), "image/png")}, data={"description": "y"})
    assert r2.json()["analysis_state"] == "done" and len(calls) == 1
    for k in ("RENDER", "AI_LIVE_ENABLED"):
        os.environ.pop(k, None)
    os.environ["GEMINI_API_KEY"] = ""
    importlib.reload(cfg)
    importlib.reload(m)
