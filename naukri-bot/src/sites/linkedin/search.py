"""LinkedIn job search: Easy Apply only, past 24h, India.

f_AL=true  -> Easy Apply filter (in-site applies only, per spec)
f_TPR=r86400 -> posted in the past 24 hours
sortBy=DD -> newest first
"""
import re
import urllib.parse
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap
from src.sites.base import Job

CARD_SELECTORS = (
    "div.job-card-container",
    "li.scaffold-layout__list-item",
    "div[data-job-id]",
    "a.job-card-list__title",
)


async def _card_company(card) -> str:
    for sel in ("div.job-card-container__primary-description",
                "div[class*='primary-description']",
                "span.job-card-container__primary-description",
                "a[class*='company']"):
        try:
            el = await card.query_selector(sel)
            if el:
                t = ((await el.inner_text()) or "").strip().split("\n")[0].strip()
                if t and len(t) < 100:
                    return t
        except Exception:
            pass
    return ""


async def search_jobs(page: Page, keyword: str, max_cards: int = 40) -> list[Job]:
    q = urllib.parse.quote_plus(keyword)
    loc = urllib.parse.quote_plus("India")
    url = (f"https://www.linkedin.com/jobs/search/?keywords={q}"
           f"&location={loc}&f_AL=true&f_TPR=r86400&sortBy=DD")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await nap(2, 3)
    # LinkedIn lazy-loads the list on scroll.
    for _ in range(5):
        await page.mouse.wheel(0, 1200)
        await nap(0.6, 1.0)
    jobs: list[Job] = []
    seen: set[str] = set()
    cards = []
    for sel in CARD_SELECTORS:
        try:
            found = await page.query_selector_all(sel)
            if found:
                cards = found
                break
        except Exception:
            pass
    for card in cards:
        try:
            link = await card.query_selector("a[href*='/jobs/view/']")
            if link is None:
                try:
                    href0 = await card.get_attribute("href") or ""
                    if "/jobs/view/" in href0:
                        link = card
                    else:
                        continue
                except Exception:
                    continue
            href = await link.get_attribute("href") or ""
            m = re.search(r"/jobs/view/(\d+)", href)
            if not m:
                continue
            jid = m.group(1)
            if href.startswith("/"):
                href = "https://www.linkedin.com" + href.split("?")[0]
            else:
                href = href.split("?")[0]
            if jid in seen:
                continue
            title = ""
            try:
                t_el = await card.query_selector(
                    "a.job-card-list__title, div[class*='job-title'], strong")
                if t_el:
                    title = ((await t_el.inner_text()) or "").strip()
            except Exception:
                pass
            if not title:
                try:
                    title = ((await link.inner_text()) or "").strip().split("\n")[0]
                except Exception:
                    pass
            if not title:
                continue
            company = await _card_company(card)
            posted = ""
            try:
                txt = ((await card.inner_text()) or "")[:400]
                pm = re.search(r"(\d+\s*(?:minute|minutes|hour|hours|day|days?)\s*ago|"
                              r"Just now|Today|Yesterday)", txt, re.I)
                if pm:
                    posted = pm.group(1)
            except Exception:
                pass
            seen.add(jid)
            jobs.append(Job(job_id=f"li:{jid}", title=title, company=company,
                            location="India", url=href, posted_ago=posted))
            if len(jobs) >= max_cards:
                break
        except Exception as e:
            logger.debug(f"card parse skip: {e}")
    logger.info(f"'{keyword}' -> {len(jobs)} cards (24h, Easy Apply)")
    return jobs
