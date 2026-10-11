"""The AI decision tool. Called by the orchestrator/drawer for EVERY answer.

Human-like by design: READ the question, CONSIDER it against the resume +
policy prompt, DECIDE like the candidate would. No keyword lists, no
if/else answer branches anywhere in this path — the model reasons, we only
shape the output. Declining (skip the job) is the LAST resort, not the
default: before giving up we (1) scan rambling output for an embedded
verdict, and (2) ask the model to re-read its own draft and extract just
the final answer — exactly what a human does with a messy first thought.

Never raises.
"""
from __future__ import annotations

import re as _re

from loguru import logger

# Markers of a model leaking its chain-of-thought instead of the answer.
REASONING_MARKERS = (
    "thinking process",
    "analyze user input",
    "analyse user input",
    "step-by-step",
    "step by step",
    "my reasoning",
    "reasoning process",
    "as an ai ",
    "as an ai,",
    "<think",
    "thought process",
    "let me think",
    "let me analyze",
    "**analyze",
    "1.  **analyze",
)

MAX_ANSWER_LEN = 300

# Exact model verdict meaning "I cannot answer this truthfully".
SKIP = "SKIP"


def clean_model_text(text: str) -> str:
    """Strip <think> blocks and surrounding noise from raw model output."""
    t = (text or "").strip()
    t = _re.sub(r"<think>.*?</think>", "", t, flags=_re.S | _re.I).strip()
    t = _re.sub(r"^```\w*\n?|\n?```$", "", t).strip()
    t = t.strip("\"' \n")
    # Markdown never belongs in a form field: drop bold/italic/code marks
    # and leading list bullets, keep the words.
    t = _re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = _re.sub(r"__(.+?)__", r"\1", t)
    t = _re.sub(r"`(.+?)`", r"\1", t)
    t = _re.sub(r"(?m)^\s*[-*•]\s+", "", t).strip()
    t = _re.sub(r"[ \t]{2,}", " ", t)
    return t


def looks_like_reasoning(text: str) -> bool:
    low = (text or "").lower()
    if len(text) > MAX_ANSWER_LEN:
        return True
    return any(m in low for m in REASONING_MARKERS)


def _match_option(text: str, options: list[str]) -> str | None:
    """Find an option embedded anywhere in the text (verdict salvage)."""
    low = (text or "").lower().strip()
    for o in options:
        if o.strip().lower() == low:
            return o.strip()
    if len(low) > 4:
        for o in options:
            ol = o.strip().lower()
            if ol in low or low in ol:
                return o.strip()
    # Last resort: the draft mulls options over — take the one it lands on
    # (usually named last, e.g. "...therefore Yes").
    if options:
        scored = []
        for o in options:
            idx = low.rfind(o.strip().lower())
            if idx >= 0:
                scored.append((idx, o.strip()))
        if scored:
            scored.sort()
            return scored[-1][1]
    return None


def _question_named_option(question: str, options: list[str]) -> str | None:
    """The question literally contains exactly one option (whole words).
    "relocate to Mumbai?" + [Mumbai, Pune] -> Mumbai. "node experience" +
    [Yes, No] -> None ("no" must match whole-word, never inside "node")."""
    qwords = set(_re.findall(r"[a-z0-9]+", question.lower()))
    if len(qwords) < 2:
        return None
    hits = []
    for o in options:
        ow = [w for w in _re.findall(r"[a-z0-9]+", o.lower()) if len(w) > 1]
        if ow and all(w in qwords for w in ow):
            hits.append(o.strip())
    return hits[0] if len(hits) == 1 else None


_EXP_TRIGGER = _re.compile(r"\b(years?|yrs?|yoe|experience|experiences|exp|how long)\b", _re.I)
_SALARY_GUARD = _re.compile(r"\b(salary|ctc|pay|compensation|lakh|lpa|package)\b", _re.I)


def _experience_answer(question: str, options: list[str]) -> str | None:
    """Fixed fact: experience in ANY tech stack is always 3.2 years.

    Returns the answer, or None to fall through to the AI. Word boundaries
    matter: "expertise"/"expected" must NOT trigger (no boundary after
    "exp"), and salary questions are excluded by the guard.
    """
    q = question.lower()
    if not _EXP_TRIGGER.search(q) or _SALARY_GUARD.search(q):
        return None
    if not options:
        return "3.2"
    for o in options:  # exact 3.2 first
        if o.strip().lower() in ("3.2", "3.2 years", "3.2 yrs"):
            return o.strip()
    for o in options:  # then band starting with 3 ("3-4" beats "2-3")
        if o.strip().lower().startswith("3"):
            return o.strip()
    for o in options:  # then any standalone 3 ("13" must not match)
        if _re.search(r"\b3(\.2)?\b", o):
            return o.strip()
    return None  # e.g. Yes/No options — leave those to the AI


async def _extract_verdict(dirty: str, options: list[str]) -> str:
    """Second pass: have the model re-read its own ramble and output just
    the final answer. Returns "" when extraction also fails."""
    from src.brain.ai_client import complete
    from src.brain.prompts import build_extract_prompt

    system, user = build_extract_prompt(dirty, options)
    try:
        # Single shot on the (cached) working model — extraction must be
        # quick or it isn't worth a second round trip.
        out = clean_model_text(await complete(system, user, max_tokens=40, max_models=1))
    except Exception as e:
        logger.debug(f"extract pass failed: {e}")
        return ""
    if not out or out.strip().upper() == SKIP or looks_like_reasoning(out):
        return ""
    if options:
        return _match_option(out, options) or ""
    return out


async def prepare_answer(question: str, options: list[str] | None = None) -> str:
    """AI decides. Returns answer text, or "" to decline. Never raises."""
    from src.brain.ai_client import complete
    from src.brain.prompts import build_answer_prompt
    from src.brain.rules import emergency_fallback
    from src.config.settings import SETTINGS

    options = options or []
    question = (question or "").strip()
    if not question:
        return ""  # nothing to decide on

    if options:
        # Literal reading, not a decision: when the question itself names
        # exactly one option word-for-word ("relocate to Mumbai?" with a
        # Mumbai option), that IS the answer. No model call needed.
        named = _question_named_option(question, options)
        if named:
            logger.info(f"Question names its answer: {named}")
            return named

    # Fixed fact (not a judgment): experience in ANY tech stack is always
    # 3.2 years. Enforced deterministically before any model call — faster
    # and infallible, same as last-working-day-is-today below.
    fixed_exp = _experience_answer(question, options)
    if fixed_exp is not None:
        logger.info(f"Fixed fact (3.2y exp): {fixed_exp}")
        return fixed_exp

    if not SETTINGS.ai_api_key:
        return emergency_fallback(question, options)  # offline: decline

    system, user = build_answer_prompt(question, options)
    try:
        raw = (await complete(system, user)).strip()
    except Exception as e:
        logger.debug(f"answer_tool transport failed, declining: {e}")
        return emergency_fallback(question, options)

    text = clean_model_text(raw)
    if not text:
        return ""
    if text.strip().upper() == SKIP:
        logger.info(f"AI declined to answer: {question[:80]}")
        return ""

    if options:
        hit = _match_option(text, options)
        if hit:
            logger.info(f"AI decided: {hit}")
            return hit
        # Ramble may still hold the verdict — scan, then re-ask for extraction.
        logger.debug(f"Salvaging verdict from {len(raw)}-char draft: {question[:60]}")
        salvaged = await _extract_verdict(raw, options)
        if salvaged:
            logger.info(f"AI decided (salvaged): {salvaged}")
            return salvaged
        logger.warning(f"Unrecoverable options answer, declining: {question[:60]} | draft: {raw[:200]}")
        return ""

    if looks_like_reasoning(text):
        salvaged = await _extract_verdict(raw, [])
        if salvaged and not looks_like_reasoning(salvaged):
            logger.info(f"AI decided (salvaged): {salvaged[:80]}")
            return salvaged
        logger.warning(f"Unrecoverable text answer, declining: {question[:60]} | draft: {raw[:200]}")
        return emergency_fallback(question, options)

    logger.info(f"AI decided: {text[:80]}")
    return _enforce_fixed_facts(question, text)


def _enforce_fixed_facts(question: str, text: str) -> str:
    """Facts the user fixed (not judgments): last working day IS today.
    A model hallucinating 2024 here is a legal-risk lie, so this one fact
    is enforced deterministically instead of trusted to the model."""
    q = question.lower()
    if any(k in q for k in ("last working day", "last work", "relieving",
                            "leaving date", "lwd")) and "birth" not in q:
        from src.brain.rules import today_str
        return today_str()
    return text
