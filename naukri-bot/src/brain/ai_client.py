"""OpenRouter free-model client with fallback chain.

Uses OpenAI-compatible endpoint. Tries free models in order,
caches first working one. Rule engine always runs first —
AI is fallback only, so free quota lasts.
"""
from __future__ import annotations

from loguru import logger
from openai import AsyncOpenAI

from src.brain.prompts import SYSTEM, user_prompt
from src.brain.rules import rule_answer
from src.config.settings import SETTINGS

FREE_CHAIN = [
    "openrouter/free",  # auto router
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemma-2-9b-it:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]

_working_model: str | None = None


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=SETTINGS.openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    )


async def ai_answer(question: str, options: list[str] | None = None) -> str:
    """Rule-first, AI-fallback. Never raises — returns rule answer on failure."""
    options = options or []
    fallback = rule_answer(question, options)
    if not SETTINGS.openrouter_key:
        return fallback
    global _working_model
    chain = [_working_model] if _working_model else []
    chain += [m for m in FREE_CHAIN if m not in chain]
    # honor explicit env model first
    if SETTINGS.openrouter_model and SETTINGS.openrouter_model not in chain:
        chain.insert(0, SETTINGS.openrouter_model)
    client = _client()
    for model in chain:
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=30,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_prompt(question, options)},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            _working_model = model
            if options:
                low = text.lower().strip()
                for o in options:
                    if o.lower().strip() == low or o.lower() in low or low in o.lower():
                        return o
                return fallback  # AI gave non-option -> trust rules
            if fallback != "Yes":
                return text
            return text
        except Exception as e:
            logger.debug(f"model {model} failed: {e}")
            continue
    return fallback


async def score_job(title: str, description: str, company: str) -> tuple[int, str, bool]:
    """Return (score, reason, should_apply). Rules first, AI only if borderline."""
    import re as _re

    from src.config.candidate import BLOCKED_COMPANIES, BLOCKED_TITLES
    from src.tools.blocklist import is_company_blocked

    tl, cl = title.lower(), (company or "").lower()

    def _word_hit(text: str, token: str) -> bool:
        # Word-boundary match so "sap" doesn't hit "sapphire" and
        # short tokens don't misfire; multi-word tokens match as phrase.
        token = token.strip().lower()
        if not token:
            return False
        if " " in token or "/" in token or "-" in token:
            return token in text
        return _re.search(r"\b" + _re.escape(token) + r"\b", text) is not None

    if any(b in cl for b in BLOCKED_COMPANIES):
        return 0, f"blocked company {company}", False
    blocked, entry = is_company_blocked(company or "")
    if blocked:
        return 0, f"blocklisted company ({entry})", False
    hit = next((b for b in BLOCKED_TITLES if _word_hit(tl, b)), None)
    if hit:
        return 0, f"blocked title ({hit})", False
    # experience gate: skip 5+ yr roles for 3.1 profile
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:yr|year)", description.lower())
    if m and float(m.group(1)) >= 5:
        return 0, f"needs {m.group(1)}+ yrs", False
    rel = any(k in tl for k in ("react", "next", "node", "mern", "full stack",
                                "frontend", "backend", "javascript", "express"))
    if rel:
        return 85, "good skill match", True
    # borderline -> ask AI (free) briefly, fallback to 70
    try:
        ans = await ai_answer(f"Should a 3.1yr full-stack dev apply for '{title}' at {company}? Reply Yes or No.", ["Yes", "No"])
        if ans.lower() == "yes":
            return 70, "AI: possible match", True
        return 20, "AI: weak match", False
    except Exception:
        return 70, "possible match", True
