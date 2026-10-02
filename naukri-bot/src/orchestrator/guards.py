"""Safety guards: block/captcha detection. No numeric cap per spec.

IMPORTANT: detection runs on RENDERED visible text + visible widgets + URL —
never on raw HTML. page.content() includes <script> sources, and Naukri loads
reCAPTCHA/anti-bot scripts on perfectly normal pages, so substring-scanning
raw HTML caused false 5-minute pauses with no captcha in sight.
"""
from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

# Strong phrases = visible text only. Bare "captcha" is deliberately absent:
# help footers and scripts mention it on healthy pages.
BLOCK_PHRASES = (
    "unusual activity",
    "verify you are human",
    "prove you are human",
    "complete the captcha",
    "complete this captcha",
    "account blocked",
    "temporarily blocked",
    "access denied",
    "suspicious activity",
)

# Classic visible challenge widgets (v2 checkbox etc.). reCAPTCHA v3's tiny
# badge alone does NOT count — it sits on healthy pages too.
CHALLENGE_IFRAMES = (
    "recaptcha/api2/anchor",
    "recaptcha/enterprise/anchor",
    "hcaptcha.com/captcha",
    "challenge-platform",
)

BLOCK_URL_HINTS = ("captcha", "challenge", "blocked", "/verify", "robot")


def url_blocked(url: str) -> tuple[bool, str]:
    low = (url or "").lower()
    for hint in BLOCK_URL_HINTS:
        if hint in low and "job-listings" not in low and "jobs" not in low:
            return True, f"url:{hint}"
    return False, ""


async def is_blocked(page: Page) -> tuple[bool, str]:
    """Return (blocked, reason). Never raises; logs the exact trigger."""
    try:
        hit, why = url_blocked(page.url)
        if hit:
            logger.warning(f"Block signal ({why}) on {page.url[:100]}")
            return True, why
    except Exception:
        pass

    # Visible challenge widget with real size?
    try:
        frames = await page.query_selector_all("iframe")
        for f in frames:
            try:
                src = (await f.get_attribute("src")) or ""
                if any(k in src for k in CHALLENGE_IFRAMES) and await f.is_visible():
                    box = await f.bounding_box()
                    if box and box["width"] > 20 and box["height"] > 20:
                        logger.warning(f"Block signal (challenge iframe {src[:60]})")
                        return True, "challenge-iframe"
            except Exception:
                pass
    except Exception:
        pass

    # Rendered text only — scripts/styles excluded by the browser.
    try:
        txt = ((await page.evaluate(
            "document.body ? document.body.innerText : ''")) or "").lower()
        for phrase in BLOCK_PHRASES:
            if phrase in txt:
                logger.warning(f"Block signal (text:{phrase})")
                return True, f"text:{phrase}"
    except Exception:
        pass
    return False, ""
