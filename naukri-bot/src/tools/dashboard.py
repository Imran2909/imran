"""Dashboard data exporter: history.db -> dashboard/data.json (+ S3 upload).

Called by the orchestrator after every keyword cycle. Works fully offline:
without AWS_DASHBOARD_BUCKET it just writes the local file (used by `nk`
runs and the local preview). With the bucket set (EC2), it also uploads
data.json so the S3-hosted dashboard stays live with zero redeploys.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from loguru import logger

from src.config.settings import SETTINGS
from src.tools.history import now_ist

LIMIT = 500


def _pick(table_cols: list[str], *wants: str) -> str | None:
    low = {c.lower(): c for c in table_cols}
    for w in wants:
        if w in low:
            return low[w]
    return None


def _rows(db_path: Path, table: str, want_cols: list[str], order: str) -> list[dict]:
    """Read rows, adapting to url/job_url and skipped/skipped_jobs variants."""
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in tables:
            return []
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        sel = []
        for w in want_cols:
            if w == "url":
                sel.append((_pick(cols, "url", "job_url", "link") or "url") + " AS url")
            elif w == "at":
                sel.append((_pick(cols, "applied_at", "skipped_at", "created_at") or "applied_at") + " AS at")
            else:
                sel.append(w if w in cols else f"'' AS {w}")
        order_col = _pick(cols, "applied_at", "skipped_at", "created_at", "rowid") or "rowid"
        cur = con.execute(f"SELECT {', '.join(sel)} FROM {table} ORDER BY {order_col} DESC LIMIT {LIMIT}")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.debug(f"dashboard read {table}: {e}")
        return []
    finally:
        con.close()


def _today_count(db_path: Path) -> int:
    # applied_at is an IST string like "2026-09-27 03:29 PM" — match date prefix.
    try:
        today = now_ist()[:10]
        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT COUNT(*) FROM applications WHERE applied_at LIKE ?", (today + "%",)
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()
    except Exception:
        return 0


def build_payload() -> dict:
    db = SETTINGS.data_dir / "history.db"
    applied = _rows(db, "applications",
                    ["title", "company", "url", "at", "applicants", "posted_ago", "reason"],
                    "at")
    for r in applied:
        r["applied_at"] = r.pop("at", "")
        r["date"] = (r["applied_at"] or "")[:10]  # YYYY-MM-DD for filters
    skipped = _rows(db, "skipped", ["title", "company", "url", "at", "reason"], "at")
    if not skipped:
        skipped = _rows(db, "skipped_jobs", ["title", "company", "url", "at", "reason"], "at")
    for r in skipped:
        r["skipped_at"] = r.pop("at", "")
        r["date"] = (r["skipped_at"] or "")[:10]
    # applied_at stored as "YYYY-MM-DD HH:MM AM/PM" IST strings; lexical sort
    # matches chronological order for same-day runs and is good enough here.
    return {
        "generated_at": now_ist() + " IST",
        "stats": {
            "applied": len(applied),
            "skipped": len(skipped),
            "applied_today": _today_count(db),
        },
        "applied": applied,
        "skipped": skipped,
    }


def _upload_s3(local: Path) -> None:
    bucket = os.getenv("AWS_DASHBOARD_BUCKET", "").strip()
    if not bucket:
        return
    try:
        import boto3  # optional; EC2 image includes it

        boto3.client("s3").upload_file(
            str(local), bucket, "data.json",
            ExtraArgs={"ContentType": "application/json", "CacheControl": "max-age=60"},
        )
        logger.info(f"Dashboard data uploaded to s3://{bucket}/data.json")
    except Exception as e:
        logger.warning(f"S3 dashboard upload skipped: {e}")


def export_dashboard() -> Path:
    """Write dashboard/data.json locally; upload to S3 when configured."""
    out = SETTINGS.data_dir.parent / "dashboard" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.debug(f"Dashboard data: {payload['stats']}")
    _upload_s3(out)
    return out
