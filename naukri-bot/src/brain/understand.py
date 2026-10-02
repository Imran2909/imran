"""Understand-first answering: READ the question, CLASSIFY intent, then answer.

Rule engine is instant but dumb (it once typed "3.1" into
"Are you an ex-Infosys employee?"). This tool classifies FIRST:
  - experience/years questions           -> 3.1
  - ex-employee / If-Yes-If-No conditionals -> No (the honest branch)
  - salary / notice / location / remote  -> profile values (rules)
  - genuine yes/no questions             -> rules (positive bias)
  - anything else free-text              -> free OpenRouter model understands
                                           and answers; rules as fallback.
"""
from __future__ import annotations

from loguru import logger

YES_NO_STARTS = (
    "are you", "do you", "have you", "has ", "is it", "is this",
    "can you", "will you", "would you", "did you", "should ",
)


def is_yes_no_question(q: str) -> bool:
    low = q.strip().lower()
    return low.endswith("?") and low.startswith(YES_NO_STARTS)


def classify(question: str) -> str:
    """Return intent label for logging/debugging."""
    q = question.lower()
    if any(k in q for k in ("ex-employee", "ex employee", "former employee")):
        return "ex_employee"
    if "if yes" in q or "if no" in q:
        return "conditional"
    if any(k in q for k in ("last working day", "last work", "relieving",
                            "lwd", "leaving date", "end date")):
        return "date"
    if any(k in q for k in ("experience", "exp", "how many year", "how long")) \
            and not any(k in q for k in ("salary", "ctc", "pay")):
        return "experience"
    if any(k in q for k in ("salary", "ctc", "compensation", "pay")):
        return "salary"
    if any(k in q for k in ("notice", "joining", "join")):
        return "notice"
    if any(k in q for k in ("relocat", "willing", "open to")):
        return "relocate"
    if any(k in q for k in ("location", "remote", "hybrid", "city", "based")):
        return "location"
    if is_yes_no_question(question):
        return "yes_no"
    return "unknown"


def sanitize(intent: str, answer: str, question: str) -> str:
    """Post-validation: an answer of the wrong TYPE can never go out.

    This is what makes relocate->3.1 and last-day->Yes impossible no matter
    which upstream branch produced the answer.
    """
    import re as _re

    from src.config.candidate import CANDIDATE, EXP

    ans = (answer or "").strip()
    q = question.lower()

    if intent == "relocate":
        # Must be affirmative, never a number.
        if _re.fullmatch(r"[\d.\s]+(?:years?|yrs?)?", ans.lower()) or ans == "":
            return "Yes"
        return ans
    if intent == "location":
        # Current-location Qs need a place; relocate-style need Yes.
        if _re.fullmatch(r"[\d.\s]+(?:years?|yrs?)?", ans.lower()) or ans == "":
            if any(k in q for k in ("current", "where", "live", "based", "city")):
                return CANDIDATE["city"]
            return "Yes"
        return ans
    if intent == "experience":
        # Must carry a number; bare Yes/No means a branch misfired.
        if ans in ("Yes", "No") or not _re.search(r"\d", ans):
            return EXP
        return ans
    if intent == "date":
        # Must look like a date; anything else means a misfire.
        if not _re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", ans):
            from src.brain.rules import today_str
            return today_str()
        return ans
    return ans


async def understand_and_answer(question: str, options: list[str] | None = None) -> str:
    """Classify first, then answer appropriately. Never raises."""
    from src.brain.rules import rule_answer

    options = options or []
    intent = classify(question)
    logger.debug(f"understand: intent={intent} q={question[:80]}")

    if options:
        # Choice lists resolved by rules, then sanitized (a numeric pick must
        # never land on a relocate Q, an exp band must never miss an exp Q).
        return sanitize(intent, rule_answer(question, options), question)

    if intent in ("ex_employee", "conditional"):
        # Honest negative branch (e.g. ex-Infosys ID box) — never "3.1".
        neg = rule_answer(question, [])
        return sanitize(intent, neg if neg in ("No", "Yes") else "No", question)

    base = rule_answer(question, [])
    if base == "Yes" and intent == "unknown":
        # Rules defaulted; let the free model actually understand it.
        from src.brain.ai_client import ai_answer

        ai = await ai_answer(question, [])
        if ai and ai.strip().lower() not in ("yes",):
            logger.info(f"understand: AI answered '{ai[:60]}' for: {question[:60]}")
            return sanitize(intent, ai, question)
    return sanitize(intent, base, question)
