"""Orchestrator: one browser, title loop forever, 30-min profile refresh.

Pan-India, past-24h, in-site Apply only, no cap (max related jobs).
"""
import argparse
import asyncio
import os
import random
import sys
import time
from types import SimpleNamespace
from loguru import logger

from src.brain.ai_client import score_job
from src.browser.human import nap
from src.browser.manager import BrowserManager
from src.config.settings import SETTINGS
from src.config.targets import JOB_TITLES
from src.orchestrator.guards import is_blocked
from src.tools.dashboard import export_dashboard
from src.tools.history import log_applied, log_skipped, seen, stats

LAST_PROFILE = 0.0
PROFILE_EVERY = 30 * 60


def _site_modules(site: str) -> SimpleNamespace:
    """Site adapter set. LinkedIn reuses the loop, guards, brain, history."""
    if site == "linkedin":
        from src.sites.linkedin.apply import apply_to_job
        from src.sites.linkedin.detail import fetch_detail
        from src.sites.linkedin.login import login
        from src.sites.linkedin.search import search_jobs
        return SimpleNamespace(login=login, search_jobs=search_jobs,
                               fetch_detail=fetch_detail,
                               apply_to_job=apply_to_job,
                               refresh_profile=None)  # no profile game on LinkedIn
    from src.sites.naukri.apply import apply_to_job
    from src.sites.naukri.detail import fetch_detail
    from src.sites.naukri.login import login
    from src.sites.naukri.profile import refresh_profile
    from src.sites.naukri.search import search_jobs
    return SimpleNamespace(login=login, search_jobs=search_jobs,
                           fetch_detail=fetch_detail,
                           apply_to_job=apply_to_job,
                           refresh_profile=refresh_profile)


async def maybe_refresh(page, refresh_fn) -> None:
    global LAST_PROFILE
    if refresh_fn is not None and time.time() - LAST_PROFILE >= PROFILE_EVERY:
        await refresh_fn(page)
        LAST_PROFILE = time.time()


async def run_forever(site: str = "naukri") -> None:
    SETTINGS.validate()
    if site == "linkedin" and (not SETTINGS.linkedin_email or not SETTINGS.linkedin_password):
        raise RuntimeError("Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")
    S = _site_modules(site)
    mgr = BrowserManager()
    page = await mgr.start()
    logger.info(f"[{site}] Browser open — keep it open, Ctrl+C to stop. Isolated profile, your Chrome untouched.")
    while True:  # login retry loop: sleep on failure, never crash-loop the container
        try:
            await S.login(page)
            break
        except RuntimeError as e:
            logger.error(f"{e} — sleeping 60 min before retry")
            await asyncio.sleep(3600)
    global LAST_PROFILE
    LAST_PROFILE = time.time()
    applied = skipped = 0
    try:
        while True:  # restart titles from top forever
            for title in JOB_TITLES:
                await maybe_refresh(page, S.refresh_profile)
                blocked, why = await is_blocked(page)
                if blocked:
                    logger.warning(f"Block/captcha detected ({why}) — pausing 5 sec")
                    await asyncio.sleep(5)
                    continue
                logger.info(f"=== {title} (24h, Pan-India) ===")
                try:
                    jobs = await S.search_jobs(page, title)
                except Exception as e:
                    logger.warning(f"search '{title}' failed: {e}")
                    continue
                for j in jobs:
                    await maybe_refresh(page, S.refresh_profile)
                    if seen(j.job_id):
                        continue
                    from src.tools.blocklist import is_company_blocked

                    blocked, entry = is_company_blocked(j.company)
                    if blocked:
                        log_skipped(j.job_id, j.title, j.company, j.url,
                                    f"blocklisted company ({entry})")
                        skipped += 1
                        continue
                    try:
                        d = await S.fetch_detail(page, j.url)
                    except Exception as e:
                        log_skipped(j.job_id, j.title, j.company, j.url, f"detail fail {e}")
                        skipped += 1
                        continue
                    if not d["description"]:
                        log_skipped(j.job_id, j.title, j.company, j.url, "no description")
                        skipped += 1
                        continue
                    if not d["has_apply"]:
                        log_skipped(j.job_id, j.title, j.company, j.url, "external/no in-site apply")
                        skipped += 1
                        continue
                    # Final company name: card first, detail page as backup.
                    # Blocklist is enforced HERE, right before any apply.
                    company = j.company or d.get("company", "")
                    if not company:
                        logger.warning(f"Company unknown for '{j.title}' — blocklist cannot be checked")
                    blocked2, entry2 = is_company_blocked(company)
                    if blocked2:
                        log_skipped(j.job_id, j.title, company, j.url,
                                    f"blocklisted company ({entry2})")
                        logger.info(f"⛔ Blocklisted, skipping: '{j.title}' @ {company} ({entry2})")
                        skipped += 1
                        continue
                    score, reason, ok = await score_job(j.title, d["description"], company)
                    logger.info(f"{j.title} @ {company} | {score}% {reason} | {d['posted_ago']} | {d['applicants']}")
                    if not ok:
                        log_skipped(j.job_id, j.title, company, j.url, reason)
                        skipped += 1
                        continue
                    try:
                        res = await S.apply_to_job(page)
                    except Exception as e:
                        log_skipped(j.job_id, j.title, j.company, j.url, f"apply error {e}")
                        skipped += 1
                        continue
                    posted = d["posted_ago"] or j.posted_ago
                    appli = d["applicants"] or j.applicants
                    if res == "applied":
                        log_applied(j.job_id, j.title, company, j.url, appli, posted, reason)
                        applied += 1
                        logger.info(f"APPLIED #{applied}: {j.title} @ {company}")
                    elif res in ("already", "external"):
                        log_skipped(j.job_id, j.title, j.company, j.url, res)
                        skipped += 1
                        await nap(1, 2)  # external/already: skip fast to next job
                        continue
                    else:
                        log_skipped(j.job_id, j.title, j.company, j.url, "apply failed")
                        skipped += 1
                    await nap(3, 6)  # human gap after real attempts, no cap but safe pacing
                    s = stats()
                    logger.info(f"session applied={applied} skipped={skipped} total_db={s}")
                try:
                    export_dashboard()  # local file always; S3 upload when configured
                except Exception as e:
                    logger.debug(f"dashboard export: {e}")
                await nap(1, 2)
    except KeyboardInterrupt:
        logger.info("Stopping — browser stays on disk profile for resume")
    finally:
        await mgr.stop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=["naukri", "linkedin"],
                    default=os.getenv("SITE", "naukri"),
                    help="which site to auto-apply on (default: naukri)")
    args = ap.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(str(SETTINGS.data_dir / "bot.log"), rotation="5 MB", level="DEBUG")
    asyncio.run(run_forever(args.site))


if __name__ == "__main__":
    main()
