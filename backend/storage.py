from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("DEBRIEF_DB", Path(__file__).resolve().parent.parent / "data" / "reports.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    filename TEXT,
    racer TEXT,
    track TEXT,
    session_date TEXT,
    headline TEXT,
    report_json TEXT NOT NULL
)"""


def _connect(path: Path = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def save_report(report: dict, path: Path = None) -> str:
    rid = uuid.uuid4().hex
    s = report["stats"]["session"]
    report = {**report, "id": rid, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?)",
            (rid, report["created_at"], s.get("filename"), s.get("racer"), s.get("track"), s.get("date"),
             (report.get("narrative") or {}).get("headline"), json.dumps(report)))
    return rid


def get_report(rid: str, path: Path = None) -> dict | None:
    with _connect(path) as conn:
        row = conn.execute("SELECT report_json FROM reports WHERE id = ?", (rid,)).fetchone()
    return json.loads(row["report_json"]) if row else None


def summaries(ids: list[str], path: Path = None) -> list[dict]:
    ids = [i for i in ids if isinstance(i, str)][:200]
    if not ids:
        return []
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT id, created_at, filename, racer, track, session_date, headline FROM reports "
            f"WHERE id IN ({','.join('?' * len(ids))}) ORDER BY created_at DESC", ids).fetchall()
    return [dict(r) for r in rows]


def delete_report(rid: str, path: Path = None) -> bool:
    with _connect(path) as conn:
        cur = conn.execute("DELETE FROM reports WHERE id = ?", (rid,))
    return cur.rowcount > 0


def update_narrative(rid: str, narrative: dict, path: Path = None) -> None:
    report = get_report(rid, path)
    if not report:
        return
    report["narrative"] = narrative
    with _connect(path) as conn:
        conn.execute("UPDATE reports SET report_json = ?, headline = ? WHERE id = ?",
                     (json.dumps(report), narrative.get("headline"), rid))
