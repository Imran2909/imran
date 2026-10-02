"""Click in-site Apply, then let the drawer tool READ -> ANSWER -> SUBMIT.

No blind resume uploads: the drawer tool uploads the resume only when
the drawer explicitly asks for resume/CV.

External jobs ("Apply on company site") are skipped INSTANTLY — no click,
no drawer wait, no new-tab hang. Returns 'external' so the orchestrator
moves to the next job right away.
"""
import asyncio

from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap
from src.sites.naukri.drawer import solve_drawer

EXTERNAL_HINTS = (
    "apply on company",
    "company site",
    "on company site",
    "apply externally",
    "external",
    "visit website",
    "career site",
    "company website",
)


def _is_external_text(txt: str) -> bool:
    t = (txt or "").lower()
    return "apply" in t and any(h in t for h in EXTERNAL_HINTS)


async def _scan_apply_buttons(page: Page):
    """Returns (insite_btn, found_external).

    insite_btn = element handle for pure in-site Apply, or None.
    found_external = True if any visible 'Apply on company site' found.
    """
    insite_btn = None
    found_external = False
    try:
        els = await page.query_selector_all("button, a")
        for el in els:
            try:
                if not await el.is_visible():
                    continue
                txt = ((await el.inner_text()) or "").strip()
                if not txt or "apply" not in txt.lower():
                    continue
                if len(txt) > 60:
                    continue
                if _is_external_text(txt):
                    found_external = True
                    continue
                # pure in-site Apply — prefer <button> over <a>
                if insite_btn is None:
                    insite_btn = el
                elif el.evaluate is not None:
                    try:
                        tag = await el.evaluate("e => e.tagName.toLowerCase()")
                        cur_tag = await insite_btn.evaluate("e => e.tagName.toLowerCase()")
                        if cur_tag != "button" and tag == "button":
                            insite_btn = el
                    except Exception:
                        pass
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"apply scan: {e}")
    return insite_btn, found_external


async def _close_extra_tabs(page: Page) -> None:
    """Close any popup/new-tab opened by an external apply click."""
    try:
        ctx = page.context
        for p in list(ctx.pages):
            if p is not page:
                try:
                    await p.close()
                except Exception:
                    pass
    except Exception:
        pass


async def apply_to_job(page: Page) -> str:
    """Returns 'applied' | 'already' | 'external' | 'failed'.

    Never hangs on external jobs: pre-scan skips them before any click,
    post-click re-check catches late-revealed external buttons / popups.
    """
    await nap(0.4, 0.8)

    # --- fast path 1: already applied ---
    try:
        body_txt = ((await page.evaluate(
            "document.body ? document.body.innerText : ''")) or "").lower()
    except Exception:
        body_txt = ""
    if "already applied" in body_txt or "applied on" in body_txt:
        return "already"

    # --- fast path 2: pre-click external scan (NO click on external) ---
    insite_btn, found_external = await _scan_apply_buttons(page)
    if insite_btn is None:
        if found_external or "apply on company" in body_txt:
            logger.info("External job ('Apply on company site') — skipping to next job")
            await _close_extra_tabs(page)
            return "external"
        # may already be inside the apply drawer (sidebar open after click)
        try:
            if await page.query_selector(
                    "div[class*='chatbot'], div[class*='drawer'], div[class*='modal']"):
                return "applied" if await solve_drawer(page) else "failed"
        except Exception:
            pass
        return "failed"

    # --- in-site Apply exists: click it, but guard against external redirect ---
    pages_before = set()
    try:
        pages_before = set(page.context.pages)
    except Exception:
        pass
    try:
        await insite_btn.click(timeout=5000)
    except Exception as e:
        logger.debug(f"apply click: {e}")
        # re-scan: click may have failed because button was actually external
        _, found_ext2 = await _scan_apply_buttons(page)
        if found_ext2:
            return "external"
        return "failed"

    await nap(1.5, 2.5)

    # --- fast path 3: post-click checks BEFORE expensive drawer solve ---
    # (a) new tab/popup opened -> it was external. Close it, skip.
    try:
        current_pages = list(page.context.pages)
        if len(current_pages) > len(pages_before):
            logger.info("Apply opened new tab (company site) — closing, skipping to next job")
            await _close_extra_tabs(page)
            return "external"
    except Exception:
        pass
    # (b) page now shows external text / navigated off naukri -> skip
    try:
        url = (page.url or "").lower()
        if "naukri.com" not in url and "apply" in url:
            logger.info(f"Left naukri to {url[:80]} — external, skipping")
            return "external"
    except Exception:
        pass
    try:
        after_txt = ((await page.evaluate(
            "document.body ? document.body.innerText : ''")) or "").lower()
    except Exception:
        after_txt = ""
    if "apply on company" in after_txt:
        _, found_ext3 = await _scan_apply_buttons(page)
        if found_ext3 or insite_btn is None:
            logger.info("External apply revealed after click — skipping to next job")
            await _close_extra_tabs(page)
            return "external"

    # --- in-site flow: solve drawer with a hard timeout so we never stuck ---
    try:
        ok = await asyncio.wait_for(solve_drawer(page), timeout=120)
        if ok:
            return "applied"
    except asyncio.TimeoutError:
        logger.warning("Drawer solve timed out (120s) — skipping to next job")
        return "failed"
    except Exception as e:
        logger.debug(f"drawer solve: {e}")

    try:
        html2 = ((await page.evaluate(
            "document.body ? document.body.innerText : ''")) or "").lower()
    except Exception:
        html2 = ""
    if "applied" in html2 or "submitted" in html2 or "successfully applied" in html2:
        return "applied"
    if "apply on company" in html2:
        await _close_extra_tabs(page)
        return "external"
    return "failed"
