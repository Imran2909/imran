"""Company blocklist: one name per line in data/blocklist.txt.

Matching is typo-tolerant:
  1. normalize (lowercase, strip Pvt/Ltd/Technologies-type suffixes)
  2. substring either direction ("infosys" matches "Infosys Limited")
  3. fuzzy similarity >= 0.85 ("Infosis" still matches "Infosys")
  4. multi-word entries match when all their words appear ("Tata Consultancy"
     matches "Tata Consultancy Services Ltd")

Edit the file any time — it is re-read on every check, no restart needed.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from src.config.settings import SETTINGS

SUFFIXES = {
    "private", "limited", "pvt", "ltd", "inc", "incorporated", "corp",
    "corporation", "technologies", "technology", "tech", "solutions",
    "services", "systems", "system", "infotech", "info", "consulting",
    "consultancy", "india", "group", "labs", "digital",
}

THRESHOLD = 0.85


def blocklist_path() -> Path:
    return SETTINGS.data_dir / "blocklist.txt"


def ensure_file() -> Path:
    p = blocklist_path()
    if not p.exists():
        p.write_text(
            "# Companies to NEVER apply to - one per line. Lines starting with # are ignored.\n"
            "# Matching ignores case, Pvt/Ltd-type suffixes, and small spelling mistakes.\n"
            "# Examples:\n"
            "# Infosys\n"
            "# Tata Consultancy\n",
            encoding="utf-8",
        )
    return p


def load_entries() -> list[str]:
    p = ensure_file()
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def normalize(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def is_company_blocked(company: str, entries: list[str] | None = None) -> tuple[bool, str]:
    """Return (blocked, matched_entry). Typo-tolerant, never raises."""
    try:
        c = normalize(company or "")
        if not c:
            return False, ""
        for entry in entries if entries is not None else load_entries():
            n = normalize(entry)
            if not n or len(n) < 3:
                continue
            if n in c or c in n:
                return True, entry
            if difflib.SequenceMatcher(None, n, c).ratio() >= THRESHOLD:
                return True, entry
            ew, cw = set(n.split()), set(c.split())
            if len(ew) >= 2 and ew <= cw:
                return True, entry
    except Exception:
        pass
    return False, ""
