"""Stealth hardening for Playwright."""
from playwright.async_api import BrowserContext

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    "--lang=en-IN",
]

INIT_SCRIPT = """() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-IN','en'] });
  window.chrome = window.chrome || { runtime: {} };
}"""


async def harden(context: BrowserContext) -> None:
    await context.add_init_script(INIT_SCRIPT)
