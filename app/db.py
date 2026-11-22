import os
import sqlite3
import threading
import time

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    description TEXT DEFAULT '',
    lat REAL, lon REAL,
    image_path TEXT,
    analysis_state TEXT NOT NULL,
    category TEXT, severity TEXT, confidence REAL, rationale TEXT,
    suggested_authority TEXT,
    status TEXT NOT NULL DEFAULT 'reported',
    source TEXT NOT NULL DEFAULT 'user',
    model TEXT, error TEXT
);
"""
STATUSES = ["reported", "acknowledged", "resolved"]

USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_usage (
    day TEXT PRIMARY KEY,
    calls INTEGER NOT NULL DEFAULT 0
);
"""


def connect(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executescript(USAGE_SCHEMA)
    return conn


def insert_report(conn, **fields):
    cols = ", ".join(fields)
    vals = ", ".join(f":{k}" for k in fields)
    with _lock:
        cur = conn.execute(f"INSERT INTO reports ({cols}) VALUES ({vals})", fields)
        conn.commit()
        return cur.lastrowid


def get_report(conn, rid):
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
    return dict(row) if row else None


def list_reports(conn, limit=200):
    rows = conn.execute(
        "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def update_status(conn, rid, status):
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}")
    with _lock:
        cur = conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, rid))
        conn.commit()
        return cur.rowcount > 0


def stats(conn):
    out = {"total": 0, "by_category": {}, "by_severity": {}, "by_status": {}}
    for row in conn.execute(
        "SELECT category, severity, status, COUNT(*) c FROM reports GROUP BY category, severity, status"
    ):
        out["total"] += row["c"]
        if row["category"]:
            out["by_category"][row["category"]] = out["by_category"].get(row["category"], 0) + row["c"]
        if row["severity"]:
            out["by_severity"][row["severity"]] = out["by_severity"].get(row["severity"], 0) + row["c"]
        out["by_status"][row["status"]] = out["by_status"].get(row["status"], 0) + row["c"]
    return out


def ai_calls_today(conn, day):
    row = conn.execute("SELECT calls FROM ai_usage WHERE day = ?", (day,)).fetchone()
    return row["calls"] if row else 0


def ai_increment(conn, day):
    with _lock:
        conn.execute(
            "INSERT INTO ai_usage (day, calls) VALUES (?, 1) "
            "ON CONFLICT(day) DO UPDATE SET calls = calls + 1", (day,))
        conn.commit()
