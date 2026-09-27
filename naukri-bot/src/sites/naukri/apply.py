"""Click in-site Apply, then let the drawer tool READ -> ANSWER -> SUBMIT.

No blind resume uploads: the drawer tool uploads the resume only when
the drawer explicitly asks for resume/CV.
"""
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap
from src.sites.naukri.drawer import solve_drawer


async def apply_to_job(page: Page) -> str:
    """Returns 'applied' | 'already' | 'external' | 'failed'."""
    await nap(0.8, 1.5)
    html = (await page.content()).lower()
    if "already applied" in html or "applied on" in html:
        return "already"
    btn = await page.query_selector("button:has-text('Apply'):not(:has-text('company'))")
    if not btn:
        link = await page.query_selector("a:has-text('Apply')")
        if link and "company" in (await link.inner_text()).lower():
            return "external"  # v1 spec: skip external applies
        btn = link
    if not btn:
        # may already be inside the apply drawer (sidebar open after click)
        if await page.query_selector("div[class*='chatbot'], div[class*='drawer'], div[class*='modal']"):
            return "applied" if await solve_drawer(page) else "failed"
        return "failed"
    await btn.click()
    await nap(1.5, 2.5)
    if await solve_drawer(page):
        return "applied"
    html2 = (await page.content()).lower()
    if "applied" in html2 or "submitted" in html2:
        return "applied"
    if "apply on company" in html2:
        return "external"
    return "failed"
