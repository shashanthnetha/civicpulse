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
    from google import genai
    def boom(*a, **k):
        raise RuntimeError("quota exceeded")
    monkeypatch.setattr(genai, "Client", boom)
    r = analyze_image(b"img", "image/jpeg")
    assert r.state == "failed" and "quota" in r.error and r.category is None


def test_sdk_success_formats_prompt_and_parses_response(monkeypatch):
    from types import SimpleNamespace
    from google import genai
    from app import triage
    monkeypatch.setattr(triage.config, "GEMINI_API_KEY", "fake-key")
    calls = []
    client_options = []
    def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=VALID)
    def make_client(**kwargs):
        client_options.append(kwargs)
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(genai, "Client", make_client)
    result = analyze_image(b"image", "image/jpeg", "Test note {literal}")
    assert result.state == "done"
    assert result.category == "road_damage"
    assert len(calls) == 1
    assert client_options[0]["http_options"].timeout == 20000
    assert client_options[0]["http_options"].retry_options.attempts == 1
    assert '"category"' in calls[0]["contents"][1]
    assert "Citizen note: Test note {literal}" in calls[0]["contents"][1]
