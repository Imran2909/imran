"""Company-name extraction shared by search cards and detail pages.

Works on any Playwright scope (Page or ElementHandle): tries known
selectors first, then falls back to reading text lines. Never raises.
"""
from __future__ import annotations

import re

COMPANY_SELECTORS = (
    "a.subTitle",
    "a.comp-name",
    "span.comp-name",
    "[class*='comp-name']",
    "a[href*='/company-']",
    "[class*='companyName']",
    "[class*='company-name']",
    "[class*='companyInfo']",
    "[data-testid*='company']",
    "[class*='employer']",
)

# Lines that are never a company name (nav junk, meta info).
_SKIP_LINE = re.compile(
    r"^(login|register|jobs?|search|home|notifications?|profile|"
    r"save|apply|share|report|posted|ratings?|reviews?|salaries?|"
    r"\d|₹|\*)",
    re.I,
)

_META_LINE = re.compile(
    r"(\bago\b|applicants?|posted|years?|yrs?|lakh|ratings?|\bstar\b|"
    r"reviews?|^\d[\d\s.,+\-]*$)",
    re.I,
)


async def extract_company(scope, title: str = "") -> str:
    """Best-effort company name from a card element or a whole page."""
    # 1) known selectors
    try:
        for sel in COMPANY_SELECTORS:
            try:
                el = await scope.query_selector(sel)
                if el is None:
                    continue
                try:
                    if not await el.is_visible():
                        continue
                except Exception:
                    pass
                t = ((await el.inner_text()) or "").strip().split("\n")[0].strip()
                if t and len(t) < 100 and "apply" not in t.lower():
                    return t
            except Exception:
                pass
    except Exception:
        pass
    # 2) text-line fallback: first meaningful line that isn't the title/meta
    try:
        try:
            txt = await scope.inner_text()  # ElementHandle (card)
        except Exception:
            txt = await scope.evaluate(  # Page
                "document.body ? document.body.innerText.slice(0, 1500) : ''")
        for line in (txt or "").splitlines():
            t = line.strip()
            if not t or len(t) > 80 or len(t) < 2:
                continue
            if title and t.lower() == title.lower():
                continue
            if _SKIP_LINE.match(t) or _META_LINE.search(t):
                continue
            if not re.search(r"[a-zA-Z]", t):
                continue
            return t
    except Exception:
        pass
    return ""
