"""One persistent browser for the whole run. Never kill/relaunch in loop.

Uses isolated user-data-dir so user's own Chrome is untouched.
Stays headed + open until user closes / Ctrl+C.
"""
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page

from src.browser.stealth import STEALTH_ARGS, harden
from src.config.settings import SETTINGS


class BrowserManager:
    def __init__(self) -> None:
        self._pw = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        profile: Path = SETTINGS.profile_dir
        profile.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=SETTINGS.headless,
            # Maximized window, viewport follows window, scale 1:1 for full clear view.
            args=[*STEALTH_ARGS, "--start-maximized"],
            viewport=None,
            device_scale_factor=1,
            locale="en-IN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await harden(self.context)
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        return self.page

    async def stop(self) -> None:
        # Close cleanly but never crash on shutdown; profile stays on disk.
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        finally:
            self.context = None
            try:
                if self._pw:
                    await self._pw.stop()
            except Exception:
                pass
            finally:
                self._pw = None
