"""LinkedIn job detail: description + Easy Apply detection.

Easy Apply (in-site) vs external "Apply" is distinguished the same way as
Naukri: only a pure Easy Apply button counts. External jobs return
has_apply=False so the orchestrator skips them instantly.
"""
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap


async def fetch_detail(page: Page, url: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await nap(1.5, 2.5)
    desc = ""
    for sel in ("div.jobs-description__content",
                "div[class*='jobs-description']",
                "div[class*='description__text']",
                "main"):
        try:
            el = await page.query_selector(sel)
            if el:
                t = ((await el.inner_text()) or "").strip()
                if len(t) > 200:
                    desc = t
                    break
        except Exception:
            pass
    company = ""
    for sel in ("div.job-details-jobs-unified-top-card__company-name",
                "div[class*='top-card__company-name']",
                "a[class*='topcard__org-name']",
                "span[class*='company-name']"):
        try:
            el = await page.query_selector(sel)
            if el:
                t = ((await el.inner_text()) or "").strip().split("\n")[0].strip()
                if t and len(t) < 100:
                    company = t
                    break
        except Exception:
            pass
    posted, appli = "", ""
    try:
        body = ((await page.evaluate(
            "document.body ? document.body.innerText.slice(0, 8000) : ''")) or "")
        import re
        pm = re.search(r"(\d+\s*(?:minute|minutes|hour|hours|day|days?)\s*ago|"
                       r"Just now|Today|Yesterday)", body, re.I)
        if pm:
            posted = pm.group(1)
        am = re.search(r"(\d[\d,]*\+?\s*applicants?)", body, re.I)
        if am:
            appli = am.group(1)
    except Exception as e:
        logger.debug(f"meta parse: {e}")
    has_apply = False
    try:
        btns = await page.query_selector_all("button.jobs-apply-button, div.jobs-apply-button button")
        if not btns:
            btns = await page.query_selector_all("button")
        for el in btns:
            try:
                if not await el.is_visible():
                    continue
                txt = ((await el.inner_text()) or "").strip().lower()
                if "easy apply" in txt:
                    has_apply = True
                    break
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"apply scan: {e}")
    return {"description": desc, "posted_ago": posted,
            "applicants": appli, "has_apply": has_apply, "company": company}
