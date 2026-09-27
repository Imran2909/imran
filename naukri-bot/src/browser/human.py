"""Human-like interactions: delays, typing, scroll."""
import asyncio
import random


async def nap(a: float = 0.5, b: float = 1.2) -> None:
    await asyncio.sleep(random.uniform(a, b))


async def human_type(target, text: str) -> None:
    """Works with both Locator and ElementHandle targets."""
    await target.click()
    try:
        await target.fill("")
    except Exception:
        pass
    if hasattr(target, "press_sequentially"):
        for ch in text:
            await target.press_sequentially(ch, delay=random.randint(40, 120))
            if random.random() < 0.03:
                await asyncio.sleep(random.uniform(0.2, 0.5))
    else:
        # ElementHandle has no press_sequentially — type() with delay instead.
        await target.type(text, delay=random.randint(40, 120))
    await nap(0.2, 0.5)


async def human_scroll(page) -> None:
    for _ in range(random.randint(2, 4)):
        await page.mouse.wheel(0, random.randint(300, 700))
        await nap(0.3, 0.7)
