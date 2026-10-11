"""LinkedIn login with session reuse.

LinkedIn is far more aggressive than Naukri about automation: repeated
logins trigger email/phone verification walls ("checkpoint/challenge").
So this NEVER force-relogs: if a saved session is alive we reuse it, and
if LinkedIn shows any verification wall we stop immediately to protect
the account instead of pushing through it.
"""
from loguru import logger
from playwright.async_api import Page

from src.browser.human import human_type, nap
from src.config.settings import SETTINGS


async def _on_verification_wall(page: Page) -> bool:
    try:
        url = (page.url or "").lower()
        if "checkpoint" in url or "challenge" in url:
            return True
        txt = ((await page.evaluate(
            "document.body ? document.body.innerText.slice(0, 2000) : ''")) or "").lower()
        return any(h in txt for h in (
            "verify your identity", "verify it's you", "unusual activity",
            "confirm it's really you", "security verification",
            "confirm your identity", "enter the code", "we've sent a code",
            "check your email to verify", "suspicious activity"))
    except Exception:
        return False


async def _looks_logged_in(page: Page) -> bool:
    """Avatar in DOM = logged in (checked before URL, so slow post-login
    redirects still count). Footer links are never used as signals."""
    try:
        me = await page.query_selector(
            "a.global-nav__me-photo, div.feed-identity-module, div.scaffold-layout__sidebar")
        if me:
            try:
                if await me.is_visible():
                    return True
            except Exception:
                return True  # present in DOM
        if "login" in page.url or "checkpoint" in page.url:
            return False
        return "/feed" in page.url
    except Exception:
        return False


async def _find_login_fields(page: Page):
    """Username + password fields via known selector variants. (None, None) if absent."""
    user = pwd = None
    for sel in ("#username", "input[name='session_key']",
                "input[type='email']", "input[autocomplete='username']"):
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                user = el
                break
        except Exception:
            pass
    for sel in ("#password", "input[name='session_password']",
                "input[type='password']"):
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                pwd = el
                break
        except Exception:
            pass
    return user, pwd


async def login(page: Page) -> None:
    """Never raises raw Playwright errors: every failure becomes a
    RuntimeError the orchestrator's retry loop handles (no crash)."""
    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000)
    await nap(1, 2)
    if await _on_verification_wall(page):
        raise RuntimeError("LinkedIn verification wall — stopping to protect account")
    if await _looks_logged_in(page):
        logger.info("Already logged in (session reused)")
        return

    if not SETTINGS.linkedin_email or not SETTINGS.linkedin_password:
        raise RuntimeError("Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")

    last_url = ""
    for attempt in (1, 2, 3):
        try:
            await page.goto("https://www.linkedin.com/login",
                            wait_until="domcontentloaded", timeout=45000)
            await nap(2, 3)
            last_url = page.url
            if await _on_verification_wall(page):
                raise RuntimeError("LinkedIn verification wall — stopping to protect account")
            if await _looks_logged_in(page):
                logger.info("Already logged in (session reused)")
                return
            # login form variants first; inspector drives the rest.
            # NOTE: never reload after the inspector acts — reload wipes
            # whatever it just typed (that bug caused the email-only loop).
            user, pwd = await _find_login_fields(page)
            if user is not None and pwd is not None:
                await human_type(user, SETTINGS.linkedin_email)
                await human_type(pwd, SETTINGS.linkedin_password)
                submit = await page.query_selector("button[type='submit']")
                if submit:
                    await submit.click()
                await nap(2, 4)
            else:
                logger.warning(f"Standard login fields not found (attempt {attempt}/3, "
                               f"url={last_url[:100]}) — inspector driving login")
                from src.tools.inspector import resolve_stuck
                progress: list[str] = []
                for _ in range(4):
                    if await _looks_logged_in(page):
                        logger.info("Logged in to LinkedIn (inspector-driven)")
                        return
                    res = await resolve_stuck(
                        page,
                        goal=("Log in to LinkedIn: fill the email/username field, "
                              "fill the password field, then click the sign-in button"),
                        context=(f"Attempt {attempt}/3 on {last_url[:100]}. "
                                 f"Completed so far: {'; '.join(progress) or 'nothing'}. "
                                 f"Do the next single step only."),
                        fill_map={"email": SETTINGS.linkedin_email,
                                  "password": SETTINGS.linkedin_password},
                    )
                    progress.append(str(res.get("detail", ""))[:120])
                    if "click" in str(res.get("detail", "")).lower():
                        # Likely the submit — give the login a chance to land
                        # before spending another model call.
                        for _ in range(8):
                            await nap(1.0, 1.5)
                            if await _looks_logged_in(page):
                                logger.info("Logged in to LinkedIn (inspector-driven)")
                                return
                    else:
                        await nap(1, 2)
                if await _looks_logged_in(page):
                    logger.info("Logged in to LinkedIn (inspector-driven)")
                    return
                try:
                    await page.wait_for_selector(
                        "a.global-nav__me-photo, div.feed-identity-module", timeout=15000)
                    logger.info("Logged in to LinkedIn (inspector-driven)")
                    return
                except Exception:
                    logger.warning(f"Inspector login incomplete (attempt {attempt}/3) — reloading")
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    continue
            if await _on_verification_wall(page):
                raise RuntimeError("LinkedIn verification wall after login — stopping to protect account")
            try:
                await page.wait_for_selector(
                    "a.global-nav__me-photo, div.feed-identity-module", timeout=20000)
                logger.info("Logged in to LinkedIn")
                return
            except Exception:
                err = ""
                try:
                    e = await page.query_selector(".alert-content, div[role='alert'], .form__label--error")
                    if e:
                        err = ((await e.inner_text()) or "").strip()[:150]
                except Exception:
                    pass
                raise RuntimeError(
                    f"LinkedIn login not confirmed (attempt {attempt}/3, "
                    f"url={page.url[:100]}, msg={err or 'no error shown'})")
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning(f"Login attempt {attempt}/3 failed: {type(e).__name__} "
                           f"(url={(last_url or page.url)[:100]})")
            continue
    raise RuntimeError(f"LinkedIn login form never appeared (last url={last_url[:100]}) — stopping")
