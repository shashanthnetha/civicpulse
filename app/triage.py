"""AI triage of civic-issue photos.

Uses Gemini vision when GEMINI_API_KEY is configured. Without a key, or on
any API/parse failure, reports are stored with an honest "pending"/"failed"
analysis state. No fabricated classifications, ever.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from . import config
from .routing import CATEGORIES

SEVERITIES = ["low", "medium", "high"]

PROMPT = """You are triaging citizen-reported civic infrastructure issues.
Look at the photo and the citizen's note (if any), then respond with ONLY a
JSON object, no markdown, no extra text:
{
  "category": one of ["road_damage","garbage","water_leak","streetlight","pollution","flooding","other"],
  "severity": one of ["low","medium","high"],
  "confidence": a number from 0 to 1 for how sure you are,
  "rationale": one short sentence explaining the assessment
}
Severity is an assistive estimate of urgency for municipal attention, not a
safety certification. If the photo does not show a civic issue, use category
"other", severity "low", low confidence, and say so in the rationale.
Citizen note: {note}"""


@dataclass
class TriageResult:
    state: str  # "done" | "pending" | "failed"
    category: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    error: Optional[str] = None
    model: Optional[str] = None


def parse_triage_json(text: str) -> dict:
    """Extract and validate the model's JSON. Raises ValueError on bad output."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    data = json.loads(cleaned[start : end + 1])
    if data.get("category") not in CATEGORIES:
        raise ValueError(f"invalid category: {data.get('category')!r}")
    if data.get("severity") not in SEVERITIES:
        raise ValueError(f"invalid severity: {data.get('severity')!r}")
    conf = float(data.get("confidence", 0))
    data["confidence"] = max(0.0, min(1.0, conf))
    data["rationale"] = str(data.get("rationale", ""))[:300]
    return data


def analyze_image(image_bytes: bytes, mime_type: str, note: str = "") -> TriageResult:
    """Classify one photo. Honest states only; raises nothing."""
    if not config.GEMINI_API_KEY:
        return TriageResult(state="pending")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=20000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                PROMPT.replace("{note}", note or "(none)"),
            ],
        )
        data = parse_triage_json(response.text)
        return TriageResult(
            state="done",
            category=data["category"],
            severity=data["severity"],
            confidence=data["confidence"],
            rationale=data["rationale"],
            model=config.GEMINI_MODEL,
        )
    except Exception as exc:  # API down, quota, bad output: store honestly
        return TriageResult(state="failed", error=f"{type(exc).__name__}: {exc}"[:300])
