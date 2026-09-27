"""Safety guards: block/captcha detection. No numeric cap per spec."""
from playwright.async_api import Page


BLOCK_WORDS = ["unusual activity", "captcha", "verify you are human",
               "account blocked", "temporarily blocked", "access denied"]


async def is_blocked(page: Page) -> bool:
    try:
        txt = (await page.content()).lower()
        return any(w in txt for w in BLOCK_WORDS)
    except Exception:
        return False
