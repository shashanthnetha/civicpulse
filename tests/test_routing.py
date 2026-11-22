from app.routing import CATEGORIES, ROUTING, DISCLAIMER, suggested_authority

def test_every_category_has_suggestion():
    for c in CATEGORIES:
        assert suggested_authority(c), c

def test_unknown_category_falls_back():
    assert suggested_authority("nonsense") == ROUTING["other"]

def test_disclaimer_says_not_filed():
    assert "not" in DISCLAIMER.lower() and "filed" in DISCLAIMER.lower() or "does not" in DISCLAIMER.lower()
