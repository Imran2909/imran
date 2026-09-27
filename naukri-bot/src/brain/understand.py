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
    if any(k in q for k in ("experience", "exp", "how many year", "how long")) \
            and not any(k in q for k in ("salary", "ctc", "pay")):
        return "experience"
    if any(k in q for k in ("salary", "ctc", "compensation", "pay")):
        return "salary"
    if any(k in q for k in ("notice", "joining", "join")):
        return "notice"
    if any(k in q for k in ("relocat", "location", "remote", "hybrid", "city", "based")):
        return "location"
    if is_yes_no_question(question):
        return "yes_no"
    return "unknown"


async def understand_and_answer(question: str, options: list[str] | None = None) -> str:
    """Classify first, then answer appropriately. Never raises."""
    from src.brain.rules import rule_answer

    options = options or []
    intent = classify(question)
    logger.debug(f"understand: intent={intent} q={question[:80]}")

    if options:
        return rule_answer(question, options)  # choice lists resolved by rules

    if intent in ("ex_employee", "conditional"):
        # Honest negative branch (e.g. ex-Infosys ID box) — never "3.1".
        neg = rule_answer(question, [])
        return neg if neg in ("No", "Yes") else "No"

    base = rule_answer(question, [])
    if base == "Yes" and intent == "unknown":
        # Rules defaulted; let the free model actually understand it.
        from src.brain.ai_client import ai_answer

        ai = await ai_answer(question, [])
        if ai and ai.strip().lower() not in ("yes",):
            logger.info(f"understand: AI answered '{ai[:60]}' for: {question[:60]}")
            return ai
    return base
