"""LinkedIn Easy Apply wizard walker: READ -> ANSWER -> NEXT, step by step.

Safety contract (same as the Naukri drawer): advance ONLY on confirmed
answers. Anything unanswerable ends the job as failed (skip), never as a
blind submit. Any unexpected error fails safe. Returns
'applied' | 'already' | 'external' | 'failed'.

Two narrow deterministic rules (documented, not answer decisions):
- phone fields are filled from settings (exact format, no AI call),
- demographic self-ID (veteran/disability/gender/race) may ONLY pick an
  explicit "decline to answer" option, else the field is left untouched.
  The AI must never invent these attributes.
Everything else is decided by the AI tool from resume + policy.
"""
from __future__ import annotations

import asyncio
import random

from loguru import logger
from playwright.async_api import Page

from src.browser.human import act_delay, nap
from src.config.candidate import CANDIDATE, SKILLS
from src.config.settings import SETTINGS

MODAL_SELECTORS = (
    "div.jobs-easy-apply-modal",
    "div[data-test-modal]",
)

SUCCESS_TEXTS = (
    "application sent",
    "application submitted",
    "successfully applied",
    "your application was sent",
)

ERROR_SELECTORS = (
    ".artdeco-inline-feedback--error",
    "span[class*='error']",
    "div[class*='error-message']",
)

NUMBER_HINTS = ("number", "digit", "numeric", "invalid", "enter a valid", "only digits")

_SELFID_TOPICS = ("veteran", "disability", "disabilities", "gender", "race",
                  "ethnicity", "sexual orientation", "lgbt")
_DECLINE_OPTS = ("decline", "don't wish", "do not wish", "prefer not")


async def _modal_scope(page: Page):
    for sel in MODAL_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return el
        except Exception:
            pass
    return await page.query_selector("body")


async def _label_for(el) -> str:
    try:
        aria = await el.get_attribute("aria-label")
        if aria and aria.strip():
            return aria.strip()[:300]
        eid = await el.get_attribute("id") or ""
        if eid:
            try:
                lab = await el.evaluate(
                    """(e, eid) => {
                      const l = document.querySelector(`label[for="${CSS.escape(eid)}"]`);
                      return l ? l.innerText.trim().slice(0, 300) : '';
                    }""", eid)
                if lab:
                    return lab
            except Exception:
                pass
        ph = await el.get_attribute("placeholder")
        if ph and ph.strip():
            return ph.strip()[:300]
        txt = await el.evaluate(
            """e => {
              let n = e.parentElement;
              for (let i = 0; i < 4 && n; i++) {
                const t = (n.innerText || '').trim();
                if (t.length > 4 && t.length < 300) return t.slice(0, 300);
                n = n.parentElement;
              }
              return '';
            }""")
        return (txt or "").strip()[:300]
    except Exception:
        return ""


async def _success(page: Page) -> bool:
    try:
        txt = ((await page.evaluate(
            "document.body ? document.body.innerText.slice(0, 12000) : ''")) or "").lower()
        return any(s in txt for s in SUCCESS_TEXTS)
    except Exception:
        return False


async def _selfid_answer(label: str, options: list[str]) -> str | None:
    """Compliance: decline-to-answer option, else None (leave untouched)."""
    low = label.lower()
    if not any(t in low for t in _SELFID_TOPICS):
        return None
    for o in options:
        if any(d in o.lower() for d in _DECLINE_OPTS):
            return o
    return None  # no decline option -> do not touch this field


async def _fill_text(page: Page, el, label: str) -> bool:
    from src.brain.answer_tool import prepare_answer

    low = label.lower()
    if any(k in low for k in ("phone", "mobile", "telephone")) and "extension" not in low:
        ans = SETTINGS.phone
    elif "email" in low and "confirm" not in low:
        ans = CANDIDATE["email"]
    else:
        ans = (await prepare_answer(label, [])).strip()
        if not ans:
            return False
    try:
        await el.click()
        try:
            await el.fill("")
        except Exception:
            pass
        for ch in ans:
            await page.keyboard.type(ch, delay=random.randint(25, 70))
            if random.random() < 0.02:
                await asyncio.sleep(random.uniform(0.15, 0.35))
        await nap(0.2, 0.5)
        logger.info(f"Q: {label[:90]} -> A(text): {ans}")
        return True
    except Exception as e:
        logger.debug(f"text fill: {e}")
        return False


async def _answer_select(page: Page, el, label: str) -> bool:
    from src.brain.answer_tool import prepare_answer

    del page
    try:
        pairs = await el.evaluate(
            "e => Array.from(e.options).map(o => ({t: o.text.trim(), v: o.value}))")
        labels = [p["t"] for p in pairs if p["t"]]
        if not labels:
            return False
        # skip placeholder-selected dropdowns already answered
        try:
            cur = await el.evaluate("e => e.options[e.selectedIndex] ? e.options[e.selectedIndex].text.trim() : ''")
            if cur and not any(k in cur.lower() for k in ("select", "choose", "please", "--", "decline")):
                return True  # already answered (or intentionally declined)
        except Exception:
            pass
        if _SELFID_TOPICS and any(t in label.lower() for t in _SELFID_TOPICS):
            for p in pairs:
                if p["t"] and any(d in p["t"].lower() for d in _DECLINE_OPTS):
                    await el.evaluate(
                        "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles:true})); }",
                        p["v"])
                    logger.info(f"Q: {label[:90]} -> A(self-id decline)")
                    return True
            return False
        best = (await prepare_answer(label, labels)).strip()
        if not best:
            return False
        val = next((p["v"] for p in pairs if p["t"] == best), None)
        if val is None:
            return False
        await el.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles:true})); }",
            val)
        logger.info(f"Q: {label[:90]} -> A(select): {best}")
        return True
    except Exception as e:
        logger.debug(f"select: {e}")
        return False


async def _answer_radios(page: Page, scope, question: str) -> bool:
    from src.brain.answer_tool import prepare_answer

    del page
    groups: dict[str, list] = {}
    try:
        els = await scope.query_selector_all("input[type='radio']")
        for el in els:
            try:
                if not await el.is_visible():
                    continue
                name = await el.get_attribute("name") or ""
                groups.setdefault(name, []).append(el)
            except Exception:
                pass
    except Exception:
        pass
    if not groups:
        return False
    advanced = False
    for name, els in groups.items():
        try:
            already = False
            for e in els:
                try:
                    if await e.is_checked():
                        already = True
                        break
                except Exception:
                    pass
            if already:
                advanced = True
                continue  # already answered
            opts = []
            for el in els:
                try:
                    lab = await el.evaluate(
                        """e => {
                          const l = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
                          const t = l ? l.innerText : ((e.closest('div') || {}).innerText || '');
                          return (t || '').trim().slice(0, 80);
                        }""")
                    if lab:
                        opts.append((el, lab))
                except Exception:
                    pass
            if not opts:
                continue
            labels = [lab for _, lab in opts]
            # group-level question beats the generic step heading
            gq = ""
            try:
                gq = await els[0].evaluate(
                    """e => {
                      let n = e.parentElement;
                      for (let i = 0; i < 4 && n; i++) {
                        const t = (n.innerText || '').trim();
                        if (t.length > 4 && t.length < 300) return t.slice(0, 300);
                        n = n.parentElement;
                      }
                      return '';
                    }""") or ""
            except Exception:
                pass
            qtext = f"{gq or question} | {' | '.join(labels)}"
            declined = await _selfid_answer(qtext, labels)
            if declined is not None:
                best = declined
            else:
                best = (await prepare_answer(qtext, labels)).strip()
                if not best:
                    return False
            hit = False
            for el, lab in opts:
                if lab.lower().strip() == best.lower().strip():
                    await act_delay()
                    await el.evaluate(
                        """e => {
                          const l = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
                          (l || e).click();
                        }""")
                    await nap(0.4, 0.8)
                    logger.info(f"Q: {question[:90]} -> A(radio): {best}")
                    hit = True
                    break
            if not hit:
                return False
            advanced = True
        except Exception as e:
            logger.debug(f"radio group: {e}")
            return False
    return advanced


async def _answer_checkboxes(scope, question: str) -> bool:
    try:
        els = await scope.query_selector_all("input[type='checkbox']")
        boxes = []
        for el in els:
            try:
                if not await el.is_visible() or await el.is_checked():
                    continue
                lab = await el.evaluate(
                    "e => ((e.closest('label') || e.parentElement || {}).innerText || '').trim()")
                if lab:
                    boxes.append((el, lab))
            except Exception:
                pass
        if not boxes:
            return False
        hit = False
        for el, lab in boxes:
            low = lab.strip().lower()
            if "follow" in low:
                continue  # leave "Follow company" alone
            if any(s in low for s in SKILLS if len(s) > 2):
                try:
                    await el.check()
                    hit = True
                except Exception:
                    pass
        if hit:
            logger.info(f"Q: {question[:90]} -> A(checkbox): resume skills ticked")
        return hit
    except Exception:
        return False


async def _answer_files(scope, question: str) -> bool:
    try:
        els = await scope.query_selector_all("input[type='file']")
        for el in els:
            try:
                if not await el.is_visible():
                    continue
                lab = await _label_for(el)
                low = (lab + " " + question).lower()
                if "cover letter" in low:
                    logger.warning("Cover-letter upload required — skipping job (never substitute resume)")
                    return False
                if any(k in low for k in ("resume", "cv")):
                    await el.set_input_files(SETTINGS.resume_path)
                    logger.info("Resume uploaded (explicitly requested)")
                    return True
            except Exception as e:
                logger.debug(f"file upload: {e}")
        return False
    except Exception:
        return False


async def _visible_errors(scope) -> list[str]:
    out = []
    for sel in ERROR_SELECTORS:
        try:
            for el in await scope.query_selector_all(sel):
                try:
                    if await el.is_visible():
                        t = ((await el.inner_text()) or "").strip()
                        if t:
                            out.append(t[:200])
                except Exception:
                    pass
        except Exception:
            pass
    return out


async def _advance(page: Page, scope) -> bool:
    """Click Submit > Review > Next, in that priority. Returns False if none clickable."""
    cands = []
    for sel in ("button[aria-label='Submit application']",
                "button[aria-label='Review your application']",
                "button[aria-label='Continue to next step']"):
        try:
            el = await scope.query_selector(sel) or await page.query_selector(sel)
            if el and await el.is_visible():
                try:
                    if await el.is_disabled():
                        continue
                except Exception:
                    pass
                cands.append(el)
        except Exception:
            pass
    if not cands:
        for txt in ("Submit application", "Review your application", "Continue to next step", "Next"):
            try:
                el = await scope.query_selector(f"button:has-text('{txt}')")
                if el and await el.is_visible():
                    cands.append(el)
                    break
            except Exception:
                pass
    if not cands:
        return False
    await act_delay()
    try:
        await cands[0].click()
        return True
    except Exception:
        return False


async def _dismiss(page: Page) -> None:
    for _ in range(2):
        try:
            btn = await page.query_selector("button[aria-label='Dismiss']")
            if btn and await btn.is_visible():
                await btn.click()
                await nap(0.8, 1.2)
                try:
                    confirm = await page.query_selector("button[data-test-dialog-primary-btn]")
                    if confirm and await confirm.is_visible():
                        txt = ((await confirm.inner_text()) or "").lower()
                        if "discard" in txt:
                            await confirm.click()
                            await nap(0.5, 1.0)
                except Exception:
                    pass
                return
        except Exception:
            pass


async def _solve_wizard(page: Page, max_steps: int = 15) -> bool:
    scope = await _modal_scope(page)
    for step in range(max_steps):
        if await _success(page):
            return True
        scope = await _modal_scope(page)
        # current step question = modal heading, for logging context
        question = ""
        try:
            h = await scope.query_selector("h2, h3, legend, div[class*='form-title']")
            if h:
                question = ((await h.inner_text()) or "").strip()[:200]
        except Exception:
            pass
        if question:
            logger.info(f"[step {step+1}] {question[:120]}")
        filled_any = False
        try:
            # text inputs (empty only — never overwrite prefilled values)
            for el in await scope.query_selector_all(
                    "input[type='text'], input[type='tel'], input[type='number'], "
                    "input:not([type]), textarea"):
                try:
                    if not await el.is_visible():
                        continue
                    try:
                        if await el.is_disabled() or await el.is_readonly():
                            continue
                    except Exception:
                        pass
                    try:
                        if ((await el.input_value()) or "").strip():
                            continue
                    except Exception:
                        pass
                    if await _fill_text(page, el, await _label_for(el) or question):
                        filled_any = True
                except Exception:
                    pass
            # dropdowns
            for el in await scope.query_selector_all("select"):
                try:
                    if await el.is_visible():
                        if await _answer_select(page, el, await _label_for(el) or question):
                            filled_any = True
                except Exception:
                    pass
            # radios / checkboxes / files
            if await _answer_radios(page, scope, question):
                filled_any = True
            if await _answer_checkboxes(scope, question):
                filled_any = True
            if await _answer_files(scope, question):
                filled_any = True
        except Exception as e:
            logger.warning(f"Wizard step failed safe ({e}) — skipping job")
            await _dismiss(page)
            return False
        await nap(0.5, 1.0)
        if not await _advance(page, scope):
            # No Next/Submit button: success, or dead end.
            await nap(1.0, 1.5)
            if await _success(page):
                return True
            logger.warning("No advance button — skipping job")
            await _dismiss(page)
            return False
        await nap(1.2, 2.0)
        # validation errors after advancing?
        errs = await _visible_errors(scope if scope else page)
        if errs:
            logger.warning(f"Form validation errors: {errs[0][:120]} — skipping job")
            await _dismiss(page)
            return False
        if await _success(page):
            await _dismiss(page)
            return True
    logger.warning("Wizard exceeded max steps — skipping job")
    await _dismiss(page)
    return False


async def apply_to_job(page: Page) -> str:
    """Returns 'applied' | 'already' | 'external' | 'failed'."""
    await nap(0.4, 0.8)
    try:
        body_txt = ((await page.evaluate(
            "document.body ? document.body.innerText.slice(0, 6000) : ''")) or "").lower()
    except Exception:
        body_txt = ""
    if "applied on" in body_txt or "application sent" in body_txt:
        return "already"
    easy_btn = None
    try:
        for el in await page.query_selector_all("button"):
            try:
                if not await el.is_visible():
                    continue
                txt = ((await el.inner_text()) or "").strip()
                low = txt.lower()
                if "easy apply" in low and len(txt) < 40:
                    easy_btn = el
                    break
            except Exception:
                pass
        if easy_btn is None:
            # applied-state button?
            for el in await page.query_selector_all("button"):
                try:
                    if not await el.is_visible():
                        continue
                    txt = ((await el.inner_text()) or "").strip().lower()
                    if txt == "applied" or txt.startswith("applied "):
                        return "already"
                except Exception:
                    pass
    except Exception:
        pass
    if easy_btn is None:
        if "apply" in body_txt and ("company site" in body_txt or "apply on" in body_txt):
            return "external"
        return "failed"
    try:
        await act_delay()
        await easy_btn.click(timeout=5000)
    except Exception:
        return "failed"
    await nap(1.5, 2.5)
    try:
        ok = await asyncio.wait_for(_solve_wizard(page), timeout=180)
        return "applied" if ok else "failed"
    except asyncio.TimeoutError:
        logger.warning("Easy Apply wizard timed out — skipping to next job")
        try:
            await _dismiss(page)
        except Exception:
            pass
        return "failed"
    except Exception as e:
        logger.debug(f"wizard solve: {e}")
        return "failed"
