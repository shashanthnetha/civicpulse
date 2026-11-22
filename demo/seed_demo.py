"""Seed a running CivicPulse server with three attributed demo photos.

These are REAL, openly licensed Wikimedia Commons photos (see ATTRIBUTION.md),
submitted through the public API exactly like a user submission. Synthetic
colored test fixtures are used only in the automated test suite, never here.

Usage: python3 demo/seed_demo.py [base_url]   (default http://localhost:8000)
"""
import sys
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

CASES = [
    ("pothole.jpg", "Deep potholes in the carriageway, bikes swerving around them", 17.4401, 78.4989),
    ("garbage.jpg", "Garbage dump not cleared for days, smell spreading", 17.4439, 78.5012),
    ("water_main.jpg", "Water main burst, road flooded", 17.4372, 78.4945),
]

def post(path, fields, filename):
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    with open(path, "rb") as f:
        data = f.read()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
             f'filename="{filename}"\r\nContent-Type: image/jpeg\r\n\r\n').encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/reports", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return urllib.request.urlopen(req).read().decode()

import os
for fname, desc, lat, lon in CASES:
    resp = post(os.path.join(os.path.dirname(__file__), fname),
                {"description": desc, "lat": lat, "lon": lon, "demo": "true"}, fname)
    print(fname, "->", resp[:120])
