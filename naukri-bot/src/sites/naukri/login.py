"""Naukri login with session reuse (persistent profile = usually already logged in)."""
from loguru import logger
from playwright.async_api import Page

from src.browser.human import human_type, nap
from src.config.settings import SETTINGS


async def login(page: Page) -> None:
    await page.goto("https://www.naukri.com/", wait_until="domcontentloaded", timeout=30000)
    await nap(1, 2)
    # already logged in?
    try:
        avatar = await page.query_selector("img.nI-gNb-header__avatar, div.view-profile-wrapper, a[href*='/mnjuser/profile']")
        if avatar:
            logger.info("Already logged in (session reused)")
            return
    except Exception:
        pass
    login_btn = await page.query_selector("a:has-text('Login'), button:has-text('Login')")
    if login_btn:
        await login_btn.click()
        await nap(1, 2)
    await page.wait_for_selector("input[placeholder*='Email'], input[type='text']", timeout=15000)
    email = await page.query_selector("input[placeholder*='Email'], input[type='text']")
    pwd = await page.query_selector("input[type='password']")
    await human_type(email, SETTINGS.naukri_email)
    await human_type(pwd, SETTINGS.naukri_password)
    submit = await page.query_selector("button[type='submit']:has-text('Login'), button:has-text('Login')")
    if submit:
        await submit.click()
    await nap(2, 4)
    # fully automatic — no manual step. Verify session, fail fast if blocked.
    try:
        await page.wait_for_selector(
            "img.nI-gNb-header__avatar, div.view-profile-wrapper, a[href*='/mnjuser/profile']",
            timeout=15000,
        )
        logger.info("Logged in to Naukri")
    except Exception:
        raise RuntimeError("Naukri auto-login failed (possible block/captcha) — stopping to protect profile")
