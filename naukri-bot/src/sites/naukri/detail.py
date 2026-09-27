"""Job detail fetch: description + freshness + applicants + has in-site Apply."""
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap


async def fetch_detail(page: Page, url: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await nap(1.5, 2.5)
    desc = ""
    for sel in ("section.job-desc, div.dang-inner-html, div.job-description",
                "div[class*='job-desc']", "main"):
        el = await page.query_selector(sel)
        if el:
            t = (await el.inner_text()).strip()
            if len(t) > 200:
                desc = t
                break
    posted, appli = "", ""
    try:
        body = (await page.content())[:20000]
        import re
        pm = re.search(r"(\d+\s*(?:min|hour|day)s?\s*ago|Just now|Today)", body, re.I)
        if pm:
            posted = pm.group(1)
        am = re.search(r"(\d+\+?\s*applicants?)", body, re.I)
        if am:
            appli = am.group(1)
    except Exception as e:
        logger.debug(f"meta parse: {e}")
    # in-site apply button only (skip external per v1 spec)
    has_apply = False
    for sel in ("button:has-text('Apply')", "a:has-text('Apply on company')"):
        el = await page.query_selector(sel)
        if el:
            txt = (await el.inner_text()).lower()
            if "apply on company" in txt or "external" in txt:
                has_apply = False
                break
            has_apply = True
            break
    return {"description": desc, "posted_ago": posted,
            "applicants": appli, "has_apply": has_apply}
