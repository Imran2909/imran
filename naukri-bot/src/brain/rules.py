"""Fallback helpers — NOT decision makers.

The AI decision tool (brain/answer_tool.py) answers every question like a
human reading it: resume + policy prompt, model decides. Nothing in this
module picks answers by keywords. It holds only:

- date helpers and number stripping (formatting, not decisions),
- emergency_fallback(): returns "" (decline) when the model is unreachable,
  which makes the drawer SKIP the job instead of filing anything unconfirmed.
"""
from __future__ import annotations


def today_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%d/%m/%Y")  # Indian format DD/MM/YYYY


def today_iso() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")  # for date-picker fields


def strip_to_number(text: str) -> str:
    """Bare number from text (site-feedback retry only, never a decision)."""
    import re
    m = re.search(r"\d+(\.\d+)?", text or "")
    return m.group() if m else text


def emergency_fallback(question: str, options: list[str] | None = None) -> str:
    """Always decline. An unanswered job skipped is infinitely safer than a
    wrong answer filed. The drawer treats "" as skip."""
    return ""
