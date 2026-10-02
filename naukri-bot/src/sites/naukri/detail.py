"""Job detail fetch: description + freshness + applicants + has in-site Apply."""
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap


async def fetch_detail(page: Page, url: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await nap(0.8, 1.4)
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
    # in-site apply button only (skip external per v1 spec).
    # Scan ALL apply elements: if any pure in-site "Apply" exists -> True.
    # If only "Apply on company site" / external exists -> False (skip fast,
    # so orchestrator never calls apply_to_job on external jobs).
    EXTERNAL_HINTS = ("apply on company", "company site", "on company",
                      "external", "visit website", "career site")
    has_apply = False
    try:
        els = await page.query_selector_all(
            "button, a, span[class*='apply' i], div[class*='apply' i]")
        found_external = False
        for el in els:
            try:
                if not await el.is_visible():
                    continue
                txt = ((await el.inner_text()) or "").strip().lower()
                if not txt or "apply" not in txt:
                    continue
                # ignore tiny nav/menu noise, but keep real buttons
                if len(txt) > 60:
                    continue
                if any(h in txt for h in EXTERNAL_HINTS):
                    found_external = True
                    continue
                # pure in-site Apply (e.g. "Apply", "Apply Now", "Apply for this job")
                has_apply = True
                break
            except Exception:
                continue
        if not has_apply and found_external:
            has_apply = False
    except Exception as e:
        logger.debug(f"has_apply scan: {e}")
    return {"description": desc, "posted_ago": posted,
            "applicants": appli, "has_apply": has_apply}
