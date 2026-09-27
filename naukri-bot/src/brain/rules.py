"""Deterministic rule engine — answers 95% of Naukri chat precisely.

Core contract:
- Every tech/exp question -> 3.1 (retry number-only on validation error)
- Positive bias: relocate Yes, immediate Yes, remote Yes, auth Yes
- Radio: Yes > Immediate > 15 days > Pune > highest rating > shortest notice
- Checkbox multi: tick all resume skills present
"""
from __future__ import annotations

from src.config.candidate import CANDIDATE, SKILLS

EXP = CANDIDATE["exp"]  # 3.1


def _pick_positive(options: list[str]) -> str | None:
    if not options:
        return None
    for o in options:
        if o.strip().lower() == "yes":
            return o
    for o in options:
        low = o.lower()
        if any(k in low for k in ("yes", "agree", "immediate", "willing", "available")):
            return o
    for o in options:
        if o.strip().lower() != "no":
            return o
    return options[0]


def _pick_exp(options: list[str]) -> str:
    if not options:
        return EXP
    for o in options:  # starts with 3 first: "3-5" beats "2-3"
        if o.strip().lower().startswith("3") or o.strip().lower().startswith("three"):
            return o
    nums = [(o, _num(o)) for o in options]
    nums = [(o, n) for o, n in nums if n is not None]
    if nums:
        nums.sort(key=lambda x: -x[1])
        return nums[0][0]
    return options[-1]


def _num(s: str) -> float | None:
    try:
        import re
        m = re.search(r"\d+(\.\d+)?", s)
        return float(m.group()) if m else None
    except Exception:
        return None


def pick_experience_option(options: list[str]) -> str:
    """Public: pick the experience band/option containing 3.1 yrs.

    Prefers the option starting with 3 ("3-4" beats "2-3"), then any
    option containing 3, else the highest numeric option (never lowball).
    """
    return _pick_exp(options)


def rule_answer(question: str, options: list[str] | None = None) -> str:
    options = options or []
    q = question.lower()

    # Experience — ALWAYS 3.1 for numbers, Yes for choice-only options.
    # (A Yes/No/Skip question mentioning "experience" must NOT fall into
    # numeric picking — that wrongly returned "Skip this question".)
    if any(k in q for k in ("experience", "exp", "how many year", "how long")) \
            and not any(k in q for k in ("salary", "ctc", "pay")):
        if options:
            import re as _re
            if any(_re.search(r"\d", o) for o in options):
                return _pick_exp(options)
            return _pick_positive(options) or EXP
        return EXP

    # Any named resume skill -> 3.1
    for s in SKILLS:
        if len(s) > 2 and s in q and any(k in q for k in ("year", "exp", "long", "many", "rating", "profici")):
            if "rat" in q or "profici" in q:
                if options:
                    vals = [_num(o) for o in options]
                    if all(v is not None for v in vals):
                        best = max(range(len(vals)), key=lambda i: vals[i])
                        return options[best]
                    return options[-1]
                return "8"
            return _pick_exp(options) if options else EXP

    # Salary
    if "current" in q and any(k in q for k in ("salary", "ctc", "compensation", "pay")):
        if "month" in q:
            return CANDIDATE["current_monthly"]
        return CANDIDATE["current_ctc"]
    if any(k in q for k in ("expect", "desir")) and any(k in q for k in ("salary", "ctc", "pay")):
        if "month" in q:
            return CANDIDATE["expected_monthly"]
        return CANDIDATE["expected_ctc"]

    # Notice / joining — always positive
    if any(k in q for k in ("notice", "joining", "join", "available", "when can you", "start")):
        if options:
            for o in options:
                if "immediate" in o.lower():
                    return o
            for o in options:
                if "15" in o or "2 week" in o.lower():
                    return o
            return _pick_positive(options) or options[0]
        return CANDIDATE["notice"]

    # Relocation / location / remote — always Yes
    if any(k in q for k in ("relocat", "willing to work", "open to")):
        return _pick_positive(options) if options else CANDIDATE["relocate"]
    if any(k in q for k in ("remote", "hybrid", "onsite", "on-site", "work mode", "wfh")):
        if options:
            for o in options:
                if any(k in o.lower() for k in ("both", "any", "flexib", "hybrid", "remote", "yes")):
                    return o
            return _pick_positive(options) or options[0]
        return "Yes"
    if "location" in q or "where are you" in q or "current city" in q or "based" in q:
        if options:
            for o in options:
                if "pune" in o.lower():
                    return o
            return _pick_positive(options) or options[0]
        return CANDIDATE["city"]

    if any(k in q for k in ("authoriz", "eligible", "legally")):
        return _pick_positive(options) if options else "Yes"
    if "sponsor" in q or "visa" in q:
        if options:
            for o in options:
                if o.strip().lower() == "no":
                    return o
        return "No"

    # Other offers in hand — always No (never jeopardize negotiating stance,
    # and never invent an offer). Placed after salary/visa branches.
    if "offer" in q and "visa" not in q:
        if options:
            for o in options:
                if o.strip().lower() == "no":
                    return o
            return _pick_positive(options) or options[0]
        return "No"

    if "phone" in q or "mobile" in q:
        return CANDIDATE["phone"]
    if "email" in q:
        return CANDIDATE["email"]
    if "linkedin" in q:
        return CANDIDATE["linkedin"]
    if "github" in q or "portfolio" in q or "website" in q:
        return CANDIDATE["github"]
    if "gender" in q:
        return "Male"

    # Conditional explanation boxes ("If Yes: give ID, If No: ...") and
    # ex-employee questions: take the honest negative branch — NEVER exp.
    # Placed after relocate/notice/salary branches so those stay positive.
    if any(k in q for k in ("ex-employee", "ex employee", "former employee")):
        if options:
            for o in options:
                if o.strip().lower() == "no":
                    return o
        return "No"
    if "if yes" in q or "if no" in q:
        if options:
            for o in options:
                if o.strip().lower() == "no":
                    return o
            return _pick_positive(options) or options[0]
        return "No"

    if options:
        return _pick_positive(options) or options[0]
    return "Yes"


def strip_to_number(text: str) -> str:
    """If site complains expecting number-only, retry with bare number."""
    import re
    m = re.search(r"\d+(\.\d+)?", text)
    return m.group() if m else text
