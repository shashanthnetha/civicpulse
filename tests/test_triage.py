import pytest
from app.triage import parse_triage_json, analyze_image

VALID = '{"category":"road_damage","severity":"high","confidence":0.87,"rationale":"Large pothole in the carriageway."}'

def test_parse_valid():
    d = parse_triage_json(VALID)
    assert d["category"] == "road_damage" and d["severity"] == "high"
    assert d["confidence"] == pytest.approx(0.87)

def test_parse_strips_markdown_fence():
    d = parse_triage_json("```json\n" + VALID + "\n```")
    assert d["category"] == "road_damage"

def test_parse_with_surrounding_text():
    d = parse_triage_json("Here you go:\n" + VALID + "\nHope that helps")
    assert d["severity"] == "high"

def test_rejects_bad_category():
    with pytest.raises(ValueError):
        parse_triage_json('{"category":"alien_invasion","severity":"low","confidence":0.1,"rationale":"x"}')

def test_rejects_bad_severity():
    with pytest.raises(ValueError):
        parse_triage_json('{"category":"garbage","severity":"catastrophic","confidence":0.1,"rationale":"x"}')

def test_rejects_non_json():
    with pytest.raises(ValueError):
        parse_triage_json("I cannot help with that image.")

def test_confidence_clamped():
    d = parse_triage_json('{"category":"garbage","severity":"low","confidence":7,"rationale":"x"}')
    assert d["confidence"] == 1.0

def test_no_key_returns_pending(monkeypatch):
    monkeypatch.setattr("app.triage.config.GEMINI_API_KEY", "")
    r = analyze_image(b"\x89PNG fake", "image/png", "note")
    assert r.state == "pending" and r.category is None

def test_api_error_returns_failed_not_fabricated(monkeypatch):
    monkeypatch.setattr("app.triage.config.GEMINI_API_KEY", "fake-key")
    import sys, types
    fake = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    def boom(*a, **k): raise RuntimeError("quota exceeded")
    genai.Client = boom
    genai.types = types.ModuleType("google.genai.types")
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai.types)
    r = analyze_image(b"img", "image/jpeg")
    assert r.state == "failed" and "quota" in r.error and r.category is None
