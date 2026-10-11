"""AI transport with live model discovery. Provider-agnostic (AIML API,
OpenRouter, any OpenAI-compatible base): tries models in order, caches the
first working one. Decision-making lives in answer_tool.py (AI-first).
"""
from __future__ import annotations

from loguru import logger
from openai import AsyncOpenAI

from src.config.settings import SETTINGS

# Preferred cheap + obedient chat models when the provider offers them.
# Discovery (live catalogue) always wins; this is only the offline fallback.
_fallback_static = [
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "openrouter/free",
]

_working_model: str | None = None
_discovered: list[str] | None = None

_SKIP_IDS = ("embed", "whisper", "tts", "image", "dall", "moderation",
             "transcri", "realtime", "audio")


async def discover_free_models() -> list[str]:
    """Ask the provider which chat models exist RIGHT NOW.

    Hardcoded slugs rot constantly, so the chain rebuilds itself from the
    live /models catalogue. Prefers small/cheap instruction-followers
    (mini/flash/8b) — the obedient ones for form-filling. Cached per
    process; static fallback offline. Explicit AI_MODEL env wins outright.
    """
    global _discovered
    if _discovered is not None:
        return _discovered
    if SETTINGS.ai_model:
        _discovered = [SETTINGS.ai_model]
        return _discovered
    try:
        import asyncio as _aio
        import json as _json
        import urllib.request as _url

        base = SETTINGS.ai_base_url.rstrip("/")
        key = SETTINGS.ai_api_key

        def _fetch() -> list:
            req = _url.Request(
                base + "/models",
                headers={"User-Agent": "naukri-bot/1.0",
                         "Authorization": "Bearer " + key},
            )
            with _url.urlopen(req, timeout=20) as r:
                return _json.load(r).get("data", [])

        data = await _aio.to_thread(_fetch)
        ids = [m.get("id", "") for m in data if m.get("id")]
        chat = [i for i in ids
                if not any(s in i.lower() for s in _SKIP_IDS)]
        rank = ("mini", "flash", "haiku", "8b", "7b", "instruct", "chat",
                "gpt-4o", "llama")
        chat.sort(key=lambda i: next((n for n, k in enumerate(rank)
                                      if k in i.lower()), 99))
        _discovered = chat[:8] or list(_fallback_static)
        logger.info(f"Discovered {len(_discovered)} models: {_discovered[:3]}...")
    except Exception as e:
        logger.warning(f"Free-model discovery failed, static fallback: {e}")
        _discovered = list(_fallback_static)
    return _discovered


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=SETTINGS.ai_api_key,
        base_url=SETTINGS.ai_base_url,
    )


async def complete(system: str, user: str, max_tokens: int = 60,
                   temperature: float = 0.2, max_models: int = 3) -> str:
    """Raw transport over the free-model chain. Raises on total failure.

    Bounded: max 3 models x 10s each, so one question costs 30s worst-case
    cold and ~5-10s once the working model is cached. Low temperature keeps
    verdicts short and deterministic.
    """
    if not SETTINGS.ai_api_key:
        raise RuntimeError("no AI API key (set AI_API_KEY in .env)")
    global _working_model
    discovered = await discover_free_models()
    chain = [_working_model] if _working_model else []
    for m in discovered:
        if m and m not in chain:
            chain.append(m)
    chain = chain[:max_models]
    client = _client()
    last_err: Exception | None = None
    for model in chain:
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=10,  # fail fast to next free model instead of hanging
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            _working_model = model
            return text
        except Exception as e:
            last_err = e
            logger.debug(f"model {model} failed: {e}")
    raise RuntimeError(f"all free models failed: {last_err}")


async def ai_answer(question: str, options: list[str] | None = None) -> str:
    """Thin wrapper over the decision prompt. "" on any failure (callers
    treat it as decline/skip, never as an answer to file)."""
    from src.brain.answer_tool import SKIP, clean_model_text, looks_like_reasoning
    from src.brain.prompts import build_answer_prompt

    options = options or []
    if not SETTINGS.ai_api_key:
        return ""
    system, user = build_answer_prompt(question, options)
    try:
        text = clean_model_text(await complete(system, user))
    except Exception:
        return ""
    if not text or text.strip().upper() == SKIP or looks_like_reasoning(text):
        return ""
    if options:
        low = text.lower().strip()
        for o in options:
            if o.strip().lower() == low:
                return o.strip()
        return ""
    return text


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
    # experience gate: skip 5+ yr roles for 3.2 profile
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:yr|year)", description.lower())
    if m and float(m.group(1)) >= 5:
        return 0, f"needs {m.group(1)}+ yrs", False
    rel = any(k in tl for k in ("react", "next", "node", "mern", "full stack",
                                "frontend", "backend", "javascript", "express"))
    if rel:
        return 85, "good skill match", True
    # borderline -> ask AI (free) briefly. User policy: apply at 50%+ match,
    # so even a weak verdict still applies — only hard blocks skip.
    try:
        ans = await ai_answer(f"Should a 3.2yr full-stack dev apply for '{title}' at {company}? Reply Yes or No.", ["Yes", "No"])
        if ans.lower() == "yes":
            return 70, "AI: possible match", True
        return 50, "AI: weak match, applying per 50% policy", True
    except Exception:
        return 55, "possible match, applying per 50% policy", True
