"""Search Pan-India, past-24h, exp 2-3. No location filter per spec."""
import re
import urllib.parse
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap
from src.sites.base import Job


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


async def search_jobs(page: Page, keyword: str, max_cards: int = 40) -> list[Job]:
    slug = _slug(keyword)
    q = urllib.parse.quote_plus(keyword)
    # jobAge=1 -> last 24h on Naukri; experience=3 targets 2-3 band
    url = f"https://www.naukri.com/{slug}-jobs?k={q}&experience=3&jobAge=1&sort=r"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await nap(2, 3)
    # scroll to load cards
    for _ in range(3):
        await page.mouse.wheel(0, 900)
        await nap(0.6, 1.0)
    cards = await page.query_selector_all("article.jobTuple, div.jobTuple, a.title")
    jobs: list[Job] = []
    seen: set[str] = set()
    for card in cards:
        try:
            link = await card.query_selector("a.title, a[href*='/job-listings-']")
            if not link:
                link = card if await card.get_attribute("href") else None
            if not link:
                continue
            href = await link.get_attribute("href") or ""
            title = (await link.inner_text()).strip()
            if not href or not title or href in seen:
                continue
            if href.startswith("/"):
                href = "https://www.naukri.com" + href
            job_id_m = re.search(r"(\d{10,})", href)
            job_id = job_id_m.group(1) if job_id_m else href
            # company / meta from card text
            card_text = (await card.inner_text())[:600]
            company = ""
            m = await card.query_selector("a.subTitle, div a.comp-name, span.comp-name")
            if m:
                company = (await m.inner_text()).strip()
            posted, appli = "", ""
            pm = re.search(r"(\d+\s*(?:min|mins|hour|hours|day|days?)\s*ago|Just now|Today|Yesterday)", card_text, re.I)
            if pm:
                posted = pm.group(1)
            am = re.search(r"(\d+\+?\s*applicants?|100\+?\s*applicants?)", card_text, re.I)
            if am:
                appli = am.group(1)
            seen.add(href)
            jobs.append(Job(job_id=job_id, title=title, company=company,
                            location="Pan-India", url=href,
                            posted_ago=posted, applicants=appli))
            if len(jobs) >= max_cards:
                break
        except Exception as e:
            logger.debug(f"card parse skip: {e}")
    logger.info(f"'{keyword}' -> {len(jobs)} cards (24h)")
    return jobs
