"""Profile touch: open + Save without changes every 30 min (keeps active)."""
from datetime import datetime
from loguru import logger
from playwright.async_api import Page

from src.browser.human import nap
from src.tools.profile_tracker import log_refresh


async def refresh_profile(page: Page) -> bool:
    try:
        await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=30000)
        await nap(2, 3)
        # open edit then save without modifying (headline edit toggle)
        edit = await page.query_selector("em.icon-edit, span:has-text('Edit'), button:has-text('Edit')")
        if edit:
            await edit.click()
            await nap(1, 2)
            save = await page.query_selector("button:has-text('Save'), button:has-text('SAVE')")
            if save:
                await save.click()
                await nap(1, 2)
        ts = datetime.now().strftime("%I:%M %p").lstrip("0")
        log_refresh(f"updated at {ts}")
        logger.info(f"Profile refreshed at {ts}")
        return True
    except Exception as e:
        logger.warning(f"profile refresh failed: {e}")
        return False
