"""History store: sqlite dedupe + applied.csv / skipped.csv tables."""
import csv
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config.settings import SETTINGS

IST = timezone(timedelta(hours=5, minutes=30))

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
  job_id TEXT PRIMARY KEY, title TEXT, company TEXT, url TEXT,
  applied_at TEXT, applicants TEXT, posted_ago TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS skipped (
  job_id TEXT PRIMARY KEY, title TEXT, company TEXT, url TEXT,
  skipped_at TEXT, reason TEXT);
"""


def _db() -> sqlite3.Connection:
    SETTINGS.data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(SETTINGS.data_dir / "history.db")
    con.executescript(SCHEMA)
    return con


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %I:%M %p")


def seen(job_id: str) -> bool:
    con = _db()
    try:
        for tbl in ("applications", "skipped"):
            if con.execute(f"SELECT 1 FROM {tbl} WHERE job_id=?", (job_id,)).fetchone():
                return True
        return False
    finally:
        con.close()


def _append_csv(name: str, row: dict) -> None:
    p = SETTINGS.data_dir / name
    new = not p.exists()
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def log_applied(job_id: str, title: str, company: str, url: str,
                applicants: str, posted_ago: str, reason: str) -> None:
    ts = now_ist()
    con = _db()
    try:
        con.execute("INSERT OR IGNORE INTO applications VALUES (?,?,?,?,?,?,?,?)",
                    (job_id, title, company, url, ts, applicants, posted_ago, reason))
        con.commit()
    finally:
        con.close()
    _append_csv("applied.csv", {"job_title": title, "company": company, "job_url": url,
                                "applied_at": ts, "applicants": applicants,
                                "posted_ago": posted_ago, "reason": reason})


def log_skipped(job_id: str, title: str, company: str, url: str, reason: str) -> None:
    ts = now_ist()
    con = _db()
    try:
        con.execute("INSERT OR IGNORE INTO skipped VALUES (?,?,?,?,?,?)",
                    (job_id, title, company, url, ts, reason))
        con.commit()
    finally:
        con.close()
    _append_csv("skipped.csv", {"job_title": title, "company": company, "job_url": url,
                                "skipped_at": ts, "reason": reason})


def stats() -> dict:
    con = _db()
    try:
        a = con.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        s = con.execute("SELECT COUNT(*) FROM skipped").fetchone()[0]
        return {"applied": a, "skipped": s}
    finally:
        con.close()
