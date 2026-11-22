"""Static category -> suggested-authority mapping.

These are SUGGESTIONS ONLY. The app never submits anything to any authority.
Actual responsible bodies vary by city and state; the dashboard shows this
text alongside an explicit "not submitted" label.
"""

CATEGORIES = [
    "road_damage",
    "garbage",
    "water_leak",
    "streetlight",
    "pollution",
    "flooding",
    "other",
]

ROUTING = {
    "road_damage": "Municipal roads/engineering department",
    "garbage": "Municipal sanitation / solid waste department",
    "water_leak": "City water supply board",
    "streetlight": "Municipal electrical / street lighting wing",
    "pollution": "State pollution control board",
    "flooding": "Municipal disaster management / emergency cell",
    "other": "General municipal grievance cell",
}

DISCLAIMER = (
    "Suggested routing only - this demo does not file anything with any "
    "authority. The responsible body depends on the city."
)

def suggested_authority(category: str) -> str:
    return ROUTING.get(category, ROUTING["other"])
